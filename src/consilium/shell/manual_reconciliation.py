"""Atomic user-selected manual continuation, without dispatch or delivery inference."""
import json
from uuid import UUID

from consilium.core.contracts import ConnectionSpec, RoundSpec
from consilium.core.manual_reconciliation import ManualReconciliationRecord, ManualReconciliationReview
from consilium.shell.storage import Conflict, SchemaError, _identifier


class ManualReconciliationLedger:
    def __init__(self, store):
        self.store, self._db = store, store._db

    def _attempts(self, round_id, participant_id):
        rows = self._db.execute("SELECT a.attempt_id FROM attempts a JOIN operations o USING(logical_operation_id) "
            "WHERE o.round_id=? AND o.participant_id=? ORDER BY a.rowid", (str(round_id), str(participant_id))).fetchall()
        return tuple(self.store.ledger.get_attempt(UUID(row[0])) for row in rows)

    def _snapshot(self, *, debate_id, round_id, participant_id, expected_revision, manual_connection):
        self.store._checked_debate(debate_id, expected_revision)
        row = self._db.execute("SELECT spec_json FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1",
            (_identifier(debate_id),)).fetchone()
        binding = self._db.execute("SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?",
            (str(debate_id), _identifier(participant_id))).fetchone()
        wait = self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(debate_id),)).fetchone()[0]
        if row is None or binding is None or wait not in {"ACTIVE", "WAITING_LOGIN", "WAITING_DECISION"}:
            raise Conflict("Manual continuation requires a current participant and an unresolved work gate")
        spec = RoundSpec.model_validate_json(row[0])
        if spec.round_id != round_id or self.get(round_id, participant_id) is not None:
            raise Conflict("Only a current, unreconciled round slot can continue manually")
        review = ManualReconciliationReview(round_spec=spec, participant_id=participant_id,
            expected_revision=expected_revision, prior_connection=ConnectionSpec.model_validate_json(binding[0]),
            prior_connection_revision=binding[1], manual_connection=manual_connection,
            attempts=self._attempts(round_id, participant_id))
        if wait != "ACTIVE":
            checkpoint = self.store.checkpoint(debate_id)
            event = self._db.execute("SELECT kind,payload_json FROM events WHERE sequence=?", (checkpoint.event_sequence,)).fetchone()
            pending = json.loads(event["payload_json"]).get("attempt_id")
            if event["kind"] not in {"RESULT_RECORDED", "RESPONSE_VALIDATED"} or pending not in {
                    str(a.intent.identity.attempt_id) for a in review.attempts}:
                raise Conflict("Another participant or an explicit user gate cannot be cleared by manual continuation")
        self.store._public(review.model_dump(mode="json"))
        return review

    def review(self, **args):
        with self.store._transaction(write=False):
            return self._snapshot(**args)

    @staticmethod
    def _payload(record):
        review = record.review
        return {"user_action_id":str(record.trusted_user_action_id), "round_id":str(review.round_spec.round_id),
            "participant_id":str(review.participant_id), "review_hash":record.review_hash,
            "record_hash":record.content_hash, "actor":record.actor, "reason":record.reason,
            "action":record.action, "connection_id":str(review.manual_connection.connection_id),
            "connection_revision":review.prior_connection_revision+1, "prior_delivery_reverified":False,
            "automatic_send":False}

    def accept(self, *, review, review_hash, user_action_id, actor, reason, confirmed, expected_revision):
        if (confirmed is not True or type(actor) is not str or not actor.strip()
                or type(reason) is not str or not reason.strip()):
            raise ValueError("Explicit local confirmation, actor and reason are required")
        _identifier(user_action_id)
        review = ManualReconciliationReview.model_validate(review)
        with self.store._transaction():
            current = self._snapshot(debate_id=review.round_spec.debate_id, round_id=review.round_spec.round_id,
                participant_id=review.participant_id, expected_revision=expected_revision,
                manual_connection=review.manual_connection)
            if current != review or review_hash != review.content_hash:
                raise Conflict("Manual continuation review, attempts or revision changed")
            record = ManualReconciliationRecord(review=review, review_hash=review_hash,
                trusted_user_action_id=user_action_id, actor=actor, reason=reason, accepted_revision=expected_revision+1)
            public = self.store._public(record.model_dump(mode="json"))
            self._db.execute("UPDATE bindings SET connection_id=?,revision=?,spec_json=? WHERE debate_id=? AND participant_id=?",
                (str(review.manual_connection.connection_id), review.prior_connection_revision+1,
                 self.store._public(review.manual_connection.model_dump(mode="json")),
                 str(review.round_spec.debate_id), str(review.participant_id)))
            self._db.execute("UPDATE debates SET wait_state='ACTIVE' WHERE debate_id=?", (str(review.round_spec.debate_id),))
            checkpoint = self.store._advance(review.round_spec.debate_id, expected_revision,
                "MANUAL_OPERATIONS_RECONCILED", self._payload(record))
            self._db.execute("INSERT INTO manual_operation_reconciliations VALUES(?,?,?,?,?,?)",
                (str(user_action_id), str(review.round_spec.round_id), str(review.participant_id),
                 public, record.content_hash, checkpoint.event_sequence))
            return record

    def get(self, round_id, participant_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get(round_id, participant_id)
        pair = (_identifier(round_id), _identifier(participant_id))
        row = self._db.execute("SELECT * FROM manual_operation_reconciliations WHERE round_id=? AND participant_id=?", pair).fetchone()
        marked = self._db.execute("SELECT * FROM events WHERE kind='MANUAL_OPERATIONS_RECONCILED' "
            "AND json_extract(payload_json,'$.round_id')=? AND json_extract(payload_json,'$.participant_id')=?", pair).fetchall()
        if row is None:
            if marked:
                raise SchemaError("Manual reconciliation record was removed")
            return None
        try:
            record = ManualReconciliationRecord.model_validate_json(row["record_json"])
            review = record.review
            event = marked[0] if len(marked) == 1 else None
            round_row = self._db.execute("SELECT spec_json FROM rounds WHERE round_id=?", (pair[0],)).fetchone()
            if ((str(review.round_spec.round_id), str(review.participant_id)) != pair
                    or str(record.trusted_user_action_id) != row["user_action_id"] or record.content_hash != row["record_hash"]
                    or event is None or event["sequence"] != row["event_sequence"]
                    or (event["debate_id"], event["revision"]) != (str(review.round_spec.debate_id), record.accepted_revision)
                    or json.loads(event["payload_json"]) != self._payload(record)
                    or round_row is None or RoundSpec.model_validate_json(round_row[0]) != review.round_spec
                    or self._attempts(round_id, participant_id) != review.attempts
                    or any(a.active_revision > review.expected_revision for a in review.attempts)):
                raise ValueError("Manual reconciliation graph mismatch")
            return record
        except (ValueError, TypeError, KeyError, RecursionError):
            raise SchemaError("Stored manual reconciliation is inconsistent") from None

    def for_operation(self, logical_operation_id):
        row = self._db.execute("SELECT round_id,participant_id FROM operations WHERE logical_operation_id=?",
            (_identifier(logical_operation_id),)).fetchone()
        if row is None:
            raise Conflict("Operation is not registered")
        record = self.get(UUID(row[0]), UUID(row[1]))
        if record is not None and logical_operation_id not in {a.intent.identity.logical_operation_id for a in record.review.attempts}:
            raise SchemaError("Operation is outside the explicitly reconciled snapshot")
        return record

    def for_debate(self, debate_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.for_debate(debate_id)
        rows = self._db.execute("SELECT payload_json FROM events WHERE debate_id=? AND kind='MANUAL_OPERATIONS_RECONCILED' ORDER BY sequence",
            (_identifier(debate_id),)).fetchall()
        return tuple(self.get(UUID(p["round_id"]), UUID(p["participant_id"])) for p in (json.loads(r[0]) for r in rows))

    def check_integrity(self):
        actual = set()
        for row in self._db.execute("SELECT round_id,participant_id,event_sequence FROM manual_operation_reconciliations").fetchall():
            self.get(UUID(row[0]), UUID(row[1])); actual.add(tuple(row))
        marked = {(json.loads(r[1])["round_id"], json.loads(r[1])["participant_id"], r[0])
            for r in self._db.execute("SELECT sequence,payload_json FROM events WHERE kind='MANUAL_OPERATIONS_RECONCILED'")}
        if actual != marked:
            raise SchemaError("Manual reconciliation records and events differ")
