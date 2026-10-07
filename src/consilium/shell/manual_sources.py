"""Trusted local manual review boundary; no provider calls or operation confirmation."""
import json
from uuid import UUID

from consilium.core.contracts import ConnectionSpec, RoundSpec
from consilium.core.independent_context import build_independent_context
from consilium.core.manual_sources import ManualAnswerCandidate, AcceptedManualAnswer, accept_candidate
from consilium.shell.storage import Conflict, SchemaError, _identifier


class ManualSourceLedger:
    def __init__(self, store):
        self.store, self._db = store, store._db

    def _expected_prompt(self, round_spec, participant_id):
        question = self.store.questions.get_adopted(round_spec.debate_id)
        if question is None:
            raise Conflict("Manual initial answer requires an explicitly adopted question")
        return build_independent_context(question=question, round_spec=round_spec, participant_id=participant_id,
            revision=question.adoption.adopted_revision).frozen_input.canonical_bytes().decode("utf-8")

    def _current(self, candidate, revision):
        self.store._checked_debate(candidate.round_spec.debate_id, revision)
        latest = self._db.execute("SELECT spec_json FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1",
                                  (str(candidate.round_spec.debate_id),)).fetchone()
        binding = self._db.execute("SELECT * FROM bindings WHERE debate_id=? AND participant_id=?",
                                  (str(candidate.round_spec.debate_id), str(candidate.participant_id))).fetchone()
        wait = self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?",
                               (str(candidate.round_spec.debate_id),)).fetchone()[0]
        if (latest is None or RoundSpec.model_validate_json(latest[0]) != candidate.round_spec or wait != "ACTIVE"
                or binding is None or binding["revision"] != candidate.connection_revision
                or ConnectionSpec.model_validate_json(binding["spec_json"]) != candidate.connection):
            raise Conflict("Manual candidate does not match the current round and binding")
        # A pending/sent operation cannot silently be replaced by manual content.
        operations = self._db.execute("SELECT logical_operation_id FROM operations WHERE round_id=? AND participant_id=?",
                            (str(candidate.round_spec.round_id), str(candidate.participant_id))).fetchall()
        if any(self.store.manual_reconciliation.for_operation(UUID(row[0])) is None for row in operations):
            raise Conflict("An existing operation requires explicit reconciliation before manual replacement")

    def stage_answer(self, *, candidate_id, round_spec, participant_id, actual_prompt, round_seen, answer,
                     claimed_origin=None, data_class="PRIVATE", expected_revision):
        round_spec = RoundSpec.model_validate(round_spec)
        _identifier(candidate_id)
        _identifier(participant_id)
        with self.store._transaction():
            self.store._checked_debate(round_spec.debate_id, expected_revision)
            binding = self._db.execute("SELECT * FROM bindings WHERE debate_id=? AND participant_id=?",
                (str(round_spec.debate_id), str(participant_id))).fetchone()
            if binding is None:
                raise Conflict("Manual participant has no registered connection")
            candidate = ManualAnswerCandidate(candidate_id=candidate_id, round_spec=round_spec,
                participant_id=participant_id, connection=ConnectionSpec.model_validate_json(binding["spec_json"]),
                connection_revision=binding["revision"], staged_revision=expected_revision,
                expected_prompt=self._expected_prompt(round_spec, participant_id), actual_prompt=actual_prompt,
                round_seen=round_seen, answer=answer, claimed_origin=claimed_origin, data_class=data_class)
            self._current(candidate, expected_revision)
            payload = self.store._public(candidate.model_dump(mode="json"))
            checkpoint = self.store.checkpoint(round_spec.debate_id)
            self._db.execute("INSERT INTO manual_answer_candidates VALUES(?,?,?,?,?,?,?,?)", (
                str(candidate_id), candidate.content_hash, str(round_spec.debate_id), str(round_spec.round_id),
                str(participant_id), payload, expected_revision, checkpoint.event_sequence))
            return candidate

    def get_candidate(self, candidate_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get_candidate(candidate_id)
        row = self._db.execute("SELECT * FROM manual_answer_candidates WHERE candidate_id=?",
                               (_identifier(candidate_id),)).fetchone()
        if row is None:
            raise Conflict("Manual candidate is not registered")
        candidate = ManualAnswerCandidate.model_validate_json(row["candidate_json"])
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["checkpoint_sequence"],)).fetchone()
        actual_round = self._db.execute("SELECT spec_json FROM rounds WHERE round_id=?", (row["round_id"],)).fetchone()
        if (str(candidate.candidate_id) != row["candidate_id"] or candidate.content_hash != row["candidate_hash"]
                or (str(candidate.round_spec.debate_id), str(candidate.round_spec.round_id), str(candidate.participant_id)) !=
                    (row["debate_id"], row["round_id"], row["participant_id"])
                or candidate.staged_revision != row["staged_revision"] or event is None
                or (event["debate_id"], event["revision"]) != (row["debate_id"], row["staged_revision"])
                or actual_round is None or RoundSpec.model_validate_json(actual_round[0]) != candidate.round_spec
                or candidate.expected_prompt != self._expected_prompt(candidate.round_spec, candidate.participant_id)):
            raise SchemaError("Stored manual candidate is inconsistent")
        return candidate

    def review_snapshot(self, candidate_id, *, expected_revision):
        with self.store._transaction(write=False):
            candidate = self.get_candidate(candidate_id)
            self._current(candidate, expected_revision)
            if candidate.staged_revision != expected_revision or self.get(candidate_id) is not None:
                raise Conflict("Manual candidate is stale or already accepted")
            return candidate

    @staticmethod
    def _event_payload(record):
        return {"candidate_id": str(record.candidate.candidate_id), "candidate_hash": record.candidate_hash,
                "record_hash": record.content_hash, "user_action_id": str(record.trusted_user_action_id),
                "actor": record.actor, "alignment": record.alignment, "external_origin_verified": False}

    def accept_answer(self, candidate_id, *, candidate_hash, user_action_id, actor, confirmed, expected_revision):
        if confirmed is not True or type(actor) is not str or not actor.strip():
            raise ValueError("Explicit trusted local manual acceptance is required")
        _identifier(user_action_id)
        with self.store._transaction():
            candidate = self.get_candidate(candidate_id)
            self._current(candidate, expected_revision)
            if candidate.staged_revision != expected_revision or candidate.content_hash != candidate_hash:
                raise Conflict("Manual review content or revision changed")
            if self.get(candidate_id) is not None:
                raise Conflict("Manual answer is already accepted")
            record = accept_candidate(candidate, user_action_id=user_action_id, actor=actor,
                                      accepted_revision=expected_revision+1)
            public = self.store._public(record.model_dump(mode="json"))
            checkpoint = self.store._advance(candidate.round_spec.debate_id, expected_revision,
                "MANUAL_ANSWER_ACCEPTED", self._event_payload(record))
            self._db.execute("INSERT INTO manual_answer_acceptances VALUES(?,?,?,?,?,?,?)", (
                str(candidate_id), str(candidate.round_spec.round_id), str(candidate.participant_id),
                str(user_action_id), public, record.content_hash, checkpoint.event_sequence))
            return record

    def get(self, candidate_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get(candidate_id)
        row = self._db.execute("SELECT * FROM manual_answer_acceptances WHERE candidate_id=?",
                               (_identifier(candidate_id),)).fetchone()
        if row is None:
            if self._db.execute("SELECT 1 FROM events WHERE kind='MANUAL_ANSWER_ACCEPTED' "
                "AND json_extract(payload_json,'$.candidate_id')=?", (str(candidate_id),)).fetchone():
                raise SchemaError("Manual acceptance record was removed")
            return None
        record = AcceptedManualAnswer.model_validate_json(row["record_json"])
        candidate = self.get_candidate(candidate_id)
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
        if (record.candidate != candidate or record.content_hash != row["record_hash"]
                or (str(record.candidate.round_spec.round_id), str(record.candidate.participant_id)) !=
                   (row["round_id"], row["participant_id"])
                or str(record.trusted_user_action_id) != row["user_action_id"] or event is None
                or (event["debate_id"], event["revision"], event["kind"]) !=
                   (str(candidate.round_spec.debate_id), record.accepted_revision, "MANUAL_ANSWER_ACCEPTED")
                or json.loads(event["payload_json"]) != self._event_payload(record)):
            raise SchemaError("Manual acceptance differs from its committed review event")
        return record

    def for_debate(self, debate_id):
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.for_debate(debate_id)
        self.store.checkpoint(debate_id)
        rows = self._db.execute("SELECT payload_json FROM events WHERE debate_id=? "
            "AND kind='MANUAL_ANSWER_ACCEPTED' ORDER BY sequence", (_identifier(debate_id),)).fetchall()
        return tuple(self.get(UUID(json.loads(r[0])["candidate_id"])) for r in rows)

    def export_fields(self, debate_id):
        candidates = self._db.execute("SELECT candidate_id FROM manual_answer_candidates WHERE debate_id=? "
                                     "ORDER BY rowid", (_identifier(debate_id),)).fetchall()
        return {"manual_answer_candidates": [self.get_candidate(UUID(r[0])).model_dump(mode="json") for r in candidates],
                "accepted_manual_answers": [r.model_dump(mode="json") for r in self.for_debate(debate_id)]}

    def check_integrity(self):
        try:
            for row in self._db.execute("SELECT candidate_id FROM manual_answer_candidates").fetchall():
                self.get_candidate(UUID(row[0]))
            for row in self._db.execute("SELECT candidate_id FROM manual_answer_acceptances").fetchall():
                self.get(UUID(row[0]))
            records = {(r[0], r[1]) for r in self._db.execute("SELECT candidate_id,event_sequence FROM manual_answer_acceptances")}
            events = {(json.loads(r[1])["candidate_id"], r[0]) for r in self._db.execute(
                "SELECT sequence,payload_json FROM events WHERE kind='MANUAL_ANSWER_ACCEPTED'")}
            if records != events:
                raise SchemaError("Manual acceptance records and events differ")
        except (ValueError, TypeError, KeyError) as exc:
            raise SchemaError("Manual source storage integrity check failed") from None
