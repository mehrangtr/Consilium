"""Short atomic ledger mutations. This module never calls a provider."""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError

from consilium.core.contracts import (
    AdapterRequest, ConnectionSpec, Delivery, DeliveryObservation,
    OperationIdentity, RoundSpec, TransportResult, UserDecision,
)
from consilium.core.operation_states import (
    AttemptRecord, AttemptState, CapabilityBinding, ResponseValidation, ResumeAction, ResumePlan,
    result_state, resume_action, transition, validate_operation_response,
)
from consilium.shell.storage import Conflict, SchemaError, _identifier, _revision

if TYPE_CHECKING:
    from consilium.shell.storage import SQLiteStore


class OperationLedger:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self._db = store._db

    def _event_matches(self, sequence, record, revision, kind):
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (sequence,)).fetchone()
        if event is None or (event["debate_id"], event["revision"], event["kind"]) != (
                str(record.intent.debate_id), revision, kind):
            raise SchemaError("Ledger record does not match its committed event")
        if json.loads(event["payload_json"]).get("attempt_id") != str(record.intent.identity.attempt_id):
            raise SchemaError("Ledger event belongs to another attempt")

    def get_attempt(self, attempt_id: UUID) -> AttemptRecord:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get_attempt(attempt_id)
        intent = self.store.get_intent(attempt_id)
        row = self._db.execute("SELECT * FROM attempts WHERE attempt_id=?", (_identifier(attempt_id),)).fetchone()
        result_row = self._db.execute("SELECT * FROM transport_results WHERE attempt_id=?", (str(attempt_id),)).fetchone()
        try:
            result = None if result_row is None else TransportResult.model_validate_json(result_row["result_json"])
            if result_row is not None and hashlib.sha256(result_row["result_json"].encode("utf-8")).hexdigest() != result_row["result_hash"]:
                raise SchemaError("Stored transport result checksum differs")
            record = AttemptRecord(intent=intent, state=AttemptState(row["state"]), active_revision=row["active_revision"],
                request=None if row["request_json"] is None else AdapterRequest.model_validate_json(row["request_json"]),
                result=result, validation=None if row["validation_json"] is None else ResponseValidation.model_validate_json(row["validation_json"]),
                response_contract=self.store.artifacts.get_contract(intent))
        except (ValueError, ValidationError):
            raise SchemaError("Stored attempt or response is inconsistent") from None
        checkpoint = self.store.checkpoint(intent.debate_id)
        if record.active_revision > checkpoint.revision:
            raise SchemaError("Attempt is newer than the committed checkpoint")
        kind = {AttemptState.PREPARED: {"OPERATION_PREPARED", "RETRY_PREPARED"},
                AttemptState.SENT: {"SEND_STARTED"}, AttemptState.VALIDATED: {"RESPONSE_VALIDATED"},
                AttemptState.CONFIRMED: {"RESULT_CONFIRMED"}}.get(record.state, {"RESULT_RECORDED", "RESPONSE_VALIDATED", "SEND_INTERRUPTED"})
        event = self._db.execute("SELECT sequence,kind FROM events WHERE debate_id=? AND revision=?",
                                 (str(intent.debate_id), record.active_revision)).fetchone()
        if event is None or event["kind"] not in kind:
            raise SchemaError("Attempt state has no matching checkpoint event")
        self._event_matches(event["sequence"], record, record.active_revision, event["kind"])
        if result_row is not None:
            self._event_matches(result_row["event_sequence"], record, result_row["recorded_revision"], "RESULT_RECORDED")
        return record

    def _current_binding_and_round(self, record: AttemptRecord) -> bool:
        intent = record.intent
        row = self._db.execute("SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?",
                               (str(intent.debate_id), str(intent.participant_id))).fetchone()
        if row is None or row["revision"] != intent.connection_revision:
            return False
        connection = ConnectionSpec.model_validate_json(row["spec_json"])
        if connection.connection_id != intent.connection_id or (record.request is not None and connection != record.request.connection):
            return False
        current = self._db.execute("SELECT spec_json FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1",
                                   (str(intent.debate_id),)).fetchone()
        if current is None:
            return False
        spec = RoundSpec.model_validate_json(current["spec_json"])
        return spec.round_id == intent.round_id and intent.participant_id in spec.participant_ids

    def _current(self, record, expected_revision, *, active=True):
        self.store._checked_debate(record.intent.debate_id, expected_revision)
        if (active and record.active_revision != expected_revision) or not self._current_binding_and_round(record):
            raise Conflict("Attempt revision, round or connection is stale")

    def _change(self, record, expected_revision, state, kind, *, request=None, validation=None):
        self._db.execute("UPDATE attempts SET state=?,active_revision=?,request_json=COALESCE(?,request_json),"
            "validation_json=COALESCE(?,validation_json) WHERE attempt_id=?", (state.value, expected_revision+1,
            None if request is None else self.store._public(request.model_dump(mode="json")),
            None if validation is None else self.store._public(validation.model_dump(mode="json")),
            str(record.intent.identity.attempt_id)))
        return self.store._advance(record.intent.debate_id, expected_revision, kind,
            {"attempt_id": str(record.intent.identity.attempt_id), "logical_operation_id": str(record.intent.identity.logical_operation_id),
             "state": state.value})

    def begin_send(self, request: AdapterRequest, *, expected_revision: int):
        request = AdapterRequest.model_validate(request.model_dump(mode="python"))
        with self.store._transaction():
            record = self.get_attempt(request.intent.identity.attempt_id)
            self._current(record, expected_revision, active=False)
            binding = self._db.execute("SELECT spec_json FROM bindings WHERE debate_id=? AND participant_id=?",
                (str(record.intent.debate_id), str(record.intent.participant_id))).fetchone()
            if request.intent != record.intent or request.connection != ConnectionSpec.model_validate_json(binding[0]):
                raise Conflict("Dispatch must use the exact prepared input and bound connection")
            if self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(record.intent.debate_id),)).fetchone()[0] != "ACTIVE":
                raise Conflict("Dispatch is blocked by an explicit wait gate")
            if record.state != AttemptState.PREPARED:
                raise Conflict("An invoked attempt cannot be invoked again")
            bundle = self.store.admissions.get(record.intent.identity.logical_operation_id)
            if bundle is not None or self.store.questions.get_adopted(record.intent.debate_id) is not None:
                self.store.admissions.require_current(request.intent.identity.attempt_id,
                    expected_revision=expected_revision)
                # Persisted synthetic/local facts do not establish token counts
                # or the live conversation's history. P04 prepares, never sends.
                raise Conflict("Policy-managed transport awaits trusted live observers")
            outstanding = self._db.execute("""SELECT a.attempt_id FROM attempts a JOIN operations o USING(logical_operation_id)
                WHERE o.debate_id=? AND a.state IN ('SENT','UNKNOWN_DELIVERY','RESPONSE_PENDING','RESPONSE_RECEIVED','VALIDATED') LIMIT 1""",
                (str(record.intent.debate_id),)).fetchone()
            if outstanding is not None:
                raise Conflict("The serial P02 runner must resolve its outstanding operation first")
            return self._change(record, expected_revision, transition(record.state, "SEND"), "SEND_STARTED", request=request)

    def mark_interrupted(self, attempt_id, *, expected_revision):
        with self.store._transaction():
            record = self.get_attempt(attempt_id)
            self._current(record, expected_revision)
            if record.state != AttemptState.SENT:
                raise Conflict("Only a started dispatch can become interrupted")
            return self._change(record, expected_revision, transition(record.state, "INTERRUPTED"), "SEND_INTERRUPTED")

    def _quarantine(self, record, result_json, result_hash, reason):
        old = self._db.execute("SELECT rejection_id FROM rejected_results WHERE attempt_id=? AND result_hash=? AND reason=?",
            (str(record.intent.identity.attempt_id), result_hash, reason)).fetchone()
        if old is not None:
            return
        revision = self.store.checkpoint(record.intent.debate_id).revision
        checkpoint = self.store._advance(record.intent.debate_id, revision, "RESULT_REJECTED",
            {"attempt_id": str(record.intent.identity.attempt_id), "reason": reason, "result_hash": result_hash})
        self._db.execute("INSERT INTO rejected_results(attempt_id,result_json,result_hash,reason,event_sequence) VALUES(?,?,?,?,?)",
            (str(record.intent.identity.attempt_id), result_json, result_hash, reason, checkpoint.event_sequence))

    def record_result(self, result: TransportResult, *, expected_revision: int):
        result = TransportResult.model_validate(result.model_dump(mode="python"))
        result_json = self.store._public(result.model_dump(mode="json"))
        result_hash = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        _revision(expected_revision)
        rejected = False
        with self.store._transaction():
            record = self.get_attempt(result.identity.attempt_id)
            if (result.identity != record.intent.identity or result.request_hash != record.intent.request_hash
                    or result.connection_id != record.intent.connection_id or result.connection_revision != record.intent.connection_revision):
                raise Conflict("Result belongs to a different frozen operation or connection")
            if record.result == result:
                return self.store.checkpoint(record.intent.debate_id)
            if record.request is None:
                raise Conflict("A result cannot precede a dispatch")
            if record.result is not None:
                self._quarantine(record, result_json, result_hash, "RESULT_CONFLICT")
                rejected = True
            elif (self.store.checkpoint(record.intent.debate_id).revision != expected_revision
                  or record.active_revision != expected_revision or not self._current_binding_and_round(record)
                  or record.state != AttemptState.SENT):
                self._quarantine(record, result_json, result_hash, "STALE_RESULT")
                rejected = True
            else:
                state = transition(record.state, "RESULT_" + result_state(result).value)
                checkpoint = self._change(record, expected_revision, state, "RESULT_RECORDED")
                self._db.execute("INSERT INTO transport_results VALUES(?,?,?,?,?)", (str(result.identity.attempt_id),
                    result_json, result_hash, checkpoint.revision, checkpoint.event_sequence))
                wait = "WAITING_LOGIN" if state == AttemptState.WAITING_LOGIN else "WAITING_DECISION" if state in {
                    AttemptState.PARTIAL_RESPONSE, AttemptState.INVALID_RESPONSE, AttemptState.NOT_SENT} else "ACTIVE"
                self._db.execute("UPDATE debates SET wait_state=? WHERE debate_id=?", (wait, str(record.intent.debate_id)))
                return checkpoint
        # The quarantine and its audit event commit before the caller sees rejection.
        if rejected:
            raise Conflict("Result was quarantined; current state and canonical response were preserved")

    def validate_response(self, attempt_id: UUID, *, expected_revision: int):
        with self.store._transaction():
            record = self.get_attempt(attempt_id)
            self._current(record, expected_revision)
            if record.state != AttemptState.RESPONSE_RECEIVED:
                raise Conflict("Only a complete stored response can be validated")
            if record.response_contract is not None:
                self.store.artifacts.validate_preparation(record.response_contract, record.intent)
            validation = validate_operation_response(record.result.content, record.response_contract)
            state = transition(record.state, "VALIDATE_OK" if validation.valid else "VALIDATE_INVALID")
            checkpoint = self._change(record, expected_revision, state, "RESPONSE_VALIDATED", validation=validation)
            if not validation.valid:
                self._db.execute("UPDATE debates SET wait_state='WAITING_DECISION' WHERE debate_id=?", (str(record.intent.debate_id),))
            return checkpoint

    def confirm_result(self, attempt_id: UUID, *, expected_revision: int):
        with self.store._transaction():
            record = self.get_attempt(attempt_id)
            self._current(record, expected_revision)
            if record.state != AttemptState.VALIDATED:
                raise Conflict("Canonical confirmation needs positive stored validation")
            if record.response_contract is not None:
                self.store.artifacts.validate_preparation(record.response_contract, record.intent)
            checkpoint = self._change(record, expected_revision, transition(record.state, "CONFIRM"), "RESULT_CONFIRMED")
            self._db.execute("INSERT INTO canonical_results VALUES(?,?,?,?)", (str(record.intent.identity.logical_operation_id),
                str(attempt_id), checkpoint.revision, checkpoint.event_sequence))
            return checkpoint

    def canonical_result(self, logical_operation_id: UUID) -> TransportResult | None:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.canonical_result(logical_operation_id)
        row = self._db.execute("SELECT * FROM canonical_results WHERE logical_operation_id=?", (_identifier(logical_operation_id),)).fetchone()
        if row is None:
            return None
        record = self.get_attempt(UUID(row["attempt_id"]))
        if record.state != AttemptState.CONFIRMED or record.intent.identity.logical_operation_id != logical_operation_id:
            raise SchemaError("Canonical result does not match its confirmed operation")
        self._event_matches(row["event_sequence"], record, row["confirmed_revision"], "RESULT_CONFIRMED")
        if row["confirmed_revision"] != record.active_revision:
            raise SchemaError("Canonical result revision differs from its attempt")
        return record.result

    def resume(self, attempt_id: UUID) -> ResumePlan:
        with self.store._transaction(write=False):
            record = self.get_attempt(attempt_id)
            action = resume_action(record.state)
            current = self._current_binding_and_round(record)
            wait = self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(record.intent.debate_id),)).fetchone()[0]
            reason = "STORED_STATE_NO_AUTOMATIC_SEND"
            if record.state != AttemptState.CONFIRMED and (wait not in {"ACTIVE", "WAITING_LOGIN"}
                    or record.state != AttemptState.PREPARED and record.active_revision != self.store.checkpoint(record.intent.debate_id).revision):
                action = ResumeAction.WAIT_FOR_DECISION
                reason = "REVISION_OR_WAIT_GATE_CHANGED_NO_AUTOMATIC_SEND"
            outstanding = self._db.execute("""SELECT a.attempt_id FROM attempts a JOIN operations o USING(logical_operation_id)
                WHERE o.debate_id=? AND a.attempt_id<>? AND a.state IN
                ('SENT','UNKNOWN_DELIVERY','RESPONSE_PENDING','RESPONSE_RECEIVED','VALIDATED') LIMIT 1""",
                (str(record.intent.debate_id), str(attempt_id))).fetchone()
            if record.state == AttemptState.PREPARED and outstanding is not None:
                action, reason = ResumeAction.WAIT_FOR_DECISION, "OUTSTANDING_OPERATION_NO_AUTOMATIC_SEND"
            if record.state != AttemptState.CONFIRMED and not current:
                action = ResumeAction.WAIT_FOR_DECISION
                reason = "BINDING_OR_ROUND_CHANGED_NO_AUTOMATIC_SEND"
            if record.state == AttemptState.CONFIRMED and self.canonical_result(record.intent.identity.logical_operation_id) != record.result:
                raise SchemaError("Resume cannot claim confirmation without a canonical result")
            return ResumePlan(attempt=record, action=action, reason=reason)

    def _round_confirmed(self, debate_id, round_id):
        row = self._db.execute("SELECT spec_json FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1", (str(debate_id),)).fetchone()
        if row is None:
            raise Conflict("No registered round")
        spec = RoundSpec.model_validate_json(row["spec_json"])
        if spec.round_id != round_id:
            raise Conflict("Decision must refer to the current round")
        rows = self._db.execute("""SELECT o.participant_id,c.attempt_id FROM operations o LEFT JOIN canonical_results c
            USING(logical_operation_id) WHERE o.round_id=?""", (str(round_id),)).fetchall()
        manual = {str(r.candidate.participant_id) for r in self.store.manual_sources.for_debate(debate_id)
                  if r.candidate.round_spec.round_id == round_id and r.alignment == "ALIGNED"}
        manual |= {str(r.candidate.participant_id) for r in self.store.manual_rounds.for_debate(debate_id)
                   if r.candidate.round_spec.round_id == round_id and r.alignment == "ALIGNED"}
        generated = {r["participant_id"] for r in rows}
        if (generated | manual != {str(x) for x in spec.participant_ids}
                or generated & manual or any(r["attempt_id"] is None for r in rows)):
            raise Conflict("A decision gate requires confirmed results for every round participant")

    def wait_for_decision(self, debate_id, round_id, *, expected_revision):
        with self.store._transaction():
            self.store._checked_debate(debate_id, expected_revision)
            self._round_confirmed(debate_id, round_id)
            if self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(debate_id),)).fetchone()[0] != "ACTIVE":
                raise Conflict("Debate already has a wait gate")
            self._db.execute("UPDATE debates SET wait_state='WAITING_DECISION' WHERE debate_id=?", (str(debate_id),))
            return self.store._advance(debate_id, expected_revision, "WAITING_DECISION", {"round_id": str(round_id)})

    def record_decision(self, decision: UserDecision, *, actor: str):
        decision = UserDecision.model_validate(decision.model_dump(mode="python"))
        if type(actor) is not str or not actor.strip():
            raise ValueError("An explicit user actor is required")
        with self.store._transaction():
            self.store._checked_debate(decision.debate_id, decision.expected_revision)
            self._round_confirmed(decision.debate_id, decision.round_id)
            if self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(decision.debate_id),)).fetchone()[0] != "WAITING_DECISION":
                raise Conflict("No current user decision gate")
            wait = {"FINISH": "WAITING_JUDGE_SELECTION", "PAUSE": "PAUSED",
                    "CONTINUE": "READY_NEXT_ROUND", "CUSTOM": "READY_NEXT_ROUND"}[decision.kind]
            self._db.execute("UPDATE debates SET wait_state=? WHERE debate_id=?", (wait, str(decision.debate_id)))
            checkpoint = self.store._advance(decision.debate_id, decision.expected_revision, "USER_DECISION",
                {"decision_id": str(decision.decision_id), "round_id": str(decision.round_id), "kind": decision.kind, "actor": actor})
            self._db.execute("INSERT INTO user_decisions VALUES(?,?,?,?,?,?)", (str(decision.decision_id), str(decision.debate_id),
                str(decision.round_id), self.store._public(decision.model_dump(mode="json")), actor, checkpoint.event_sequence))
            return checkpoint

    def prepare_retry(self, previous_attempt_id, next_attempt_id, *, expected_revision, actor, reason,
                      capabilities: CapabilityBinding, observation: DeliveryObservation):
        _identifier(next_attempt_id)
        capabilities = CapabilityBinding.model_validate(capabilities.model_dump(mode="python"))
        observation = DeliveryObservation.model_validate(observation.model_dump(mode="python"))
        if type(actor) is not str or not actor.strip() or type(reason) is not str or not reason.strip():
            raise ValueError("Retry requires an explicit actor and reason")
        if capabilities.capabilities.verification != "LIVE_VERIFIED" or not capabilities.capabilities.delivery_probe:
            raise Conflict("Retry requires a verified authoritative delivery probe")
        with self.store._transaction():
            record = self.get_attempt(previous_attempt_id)
            self._current(record, expected_revision)
            if record.state not in {AttemptState.NOT_SENT, AttemptState.WAITING_LOGIN}:
                raise Conflict("Ambiguous, received or confirmed operations cannot be retried here")
            if (observation.identity != record.intent.identity or observation.request_hash != record.intent.request_hash
                    or observation.connection_id != record.intent.connection_id or observation.connection_revision != record.intent.connection_revision
                    or observation.delivery != Delivery.NOT_SENT or not observation.evidence
                    or capabilities.connection != record.request.connection or capabilities.connection_revision != record.intent.connection_revision):
                raise Conflict("Retry proof does not match this unsent attempt and connection")
            identity = OperationIdentity(logical_operation_id=record.intent.identity.logical_operation_id,
                                         attempt_id=next_attempt_id, generation_id=record.intent.identity.generation_id)
            intent = record.intent.model_copy(update={"identity": identity, "expected_revision": expected_revision})
            self._db.execute("""INSERT INTO attempts(attempt_id,logical_operation_id,state,intent_json,active_revision)
                VALUES(?,?,'PREPARED',?,?)""", (str(next_attempt_id), str(identity.logical_operation_id),
                self.store._public(intent.model_dump(mode="json")), expected_revision+1))
            authorization = {"actor": actor, "reason": reason, "capabilities": capabilities.model_dump(mode="json"),
                             "observation": observation.model_dump(mode="json")}
            self._db.execute("UPDATE debates SET wait_state='ACTIVE' WHERE debate_id=?", (str(intent.debate_id),))
            checkpoint = self.store._advance(intent.debate_id, expected_revision, "RETRY_PREPARED",
                {"attempt_id": str(next_attempt_id), "previous_attempt_id": str(previous_attempt_id), "actor": actor, "reason": reason})
            self._db.execute("INSERT INTO retry_authorizations VALUES(?,?,?,?)", (str(previous_attempt_id), str(next_attempt_id),
                self.store._public(authorization), checkpoint.event_sequence))
            return checkpoint

    def export_fields(self, debate_id):
        records = [self.get_attempt(UUID(row[0])) for row in self._db.execute("""SELECT a.attempt_id FROM attempts a
            JOIN operations o USING(logical_operation_id) WHERE o.debate_id=? ORDER BY a.rowid""", (str(debate_id),)).fetchall()]
        return {"wait_state": self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(debate_id),)).fetchone()[0],
            "attempts": [r.model_dump(mode="json") for r in records],
            "canonical_results": [{"logical_operation_id": str(r.intent.identity.logical_operation_id),
                                   "result": self.canonical_result(r.intent.identity.logical_operation_id).model_dump(mode="json")}
                                  for r in records if r.state == AttemptState.CONFIRMED],
            "rejected_results": [{"reason": row["reason"], "result": json.loads(row["result_json"]), "event_sequence": row["event_sequence"]}
                for row in self._db.execute("SELECT r.* FROM rejected_results r JOIN operations o ON o.logical_operation_id="
                    "(SELECT logical_operation_id FROM attempts WHERE attempt_id=r.attempt_id) WHERE o.debate_id=? ORDER BY rejection_id", (str(debate_id),))],
            "user_decisions": [{"decision": json.loads(row["decision_json"]), "actor": row["actor"]}
                               for row in self._db.execute("SELECT * FROM user_decisions WHERE debate_id=? ORDER BY event_sequence", (str(debate_id),))],
            "retry_authorizations": [json.loads(row[0]) for row in self._db.execute("SELECT r.authorization_json FROM retry_authorizations r "
                "JOIN attempts a ON a.attempt_id=r.next_attempt_id JOIN operations o USING(logical_operation_id) WHERE o.debate_id=? ORDER BY r.event_sequence", (str(debate_id),))]}

    def check_integrity(self):
        for row in self._db.execute("SELECT attempt_id FROM attempts").fetchall():
            record = self.get_attempt(UUID(row[0]))
            canonical = self.canonical_result(record.intent.identity.logical_operation_id)
            if record.state == AttemptState.CONFIRMED and canonical != record.result:
                raise SchemaError("Confirmed response is missing its canonical entry")
        for row in self._db.execute("SELECT * FROM rejected_results").fetchall():
            record = self.get_attempt(UUID(row["attempt_id"]))
            event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
            payload = json.loads(event["payload_json"])
            if hashlib.sha256(row["result_json"].encode()).hexdigest() != row["result_hash"] or event["kind"] != "RESULT_REJECTED" or payload != {
                    "attempt_id": str(record.intent.identity.attempt_id), "reason": row["reason"], "result_hash": row["result_hash"]}:
                raise SchemaError("Rejected result is inconsistent with its audit event")
            result = TransportResult.model_validate_json(row["result_json"])
            if (event["debate_id"] != str(record.intent.debate_id) or result.identity != record.intent.identity
                    or result.request_hash != record.intent.request_hash or result.connection_id != record.intent.connection_id
                    or result.connection_revision != record.intent.connection_revision):
                raise SchemaError("Quarantined result belongs to another operation")
        for row in self._db.execute("SELECT * FROM user_decisions").fetchall():
            decision = UserDecision.model_validate_json(row["decision_json"])
            event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
            if (str(decision.decision_id), str(decision.debate_id), str(decision.round_id)) != (
                    row["decision_id"], row["debate_id"], row["round_id"]) or not row["actor"].strip():
                raise SchemaError("Stored decision identity differs")
            if event["debate_id"] != row["debate_id"] or event["revision"] != decision.expected_revision+1 or event["kind"] != "USER_DECISION" or json.loads(event["payload_json"]) != {
                    "decision_id": row["decision_id"], "round_id": row["round_id"], "kind": decision.kind, "actor": row["actor"]}:
                raise SchemaError("Stored decision differs from its audit event")
        for row in self._db.execute("SELECT * FROM retry_authorizations").fetchall():
            previous = self.get_attempt(UUID(row["previous_attempt_id"]))
            following = self.get_attempt(UUID(row["next_attempt_id"]))
            auth = json.loads(row["authorization_json"])
            binding = CapabilityBinding.model_validate_json(json.dumps(auth["capabilities"]))
            observation = DeliveryObservation.model_validate_json(json.dumps(auth["observation"]))
            if (previous.state not in {AttemptState.NOT_SENT, AttemptState.WAITING_LOGIN}
                    or following.intent.identity.logical_operation_id != previous.intent.identity.logical_operation_id
                    or following.intent.identity.generation_id != previous.intent.identity.generation_id
                    or following.intent.frozen_input != previous.intent.frozen_input
                    or binding.connection != previous.request.connection or binding.connection_revision != previous.intent.connection_revision
                    or binding.capabilities.verification != "LIVE_VERIFIED" or not binding.capabilities.delivery_probe
                    or observation.identity != previous.intent.identity or observation.delivery != Delivery.NOT_SENT
                    or observation.request_hash != previous.intent.request_hash or not observation.evidence
                    or observation.connection_id != previous.intent.connection_id or observation.connection_revision != previous.intent.connection_revision
                    or not isinstance(auth.get("actor"), str) or not auth["actor"].strip()
                    or not isinstance(auth.get("reason"), str) or not auth["reason"].strip()):
                raise SchemaError("Retry does not preserve a verified unsent logical operation")
            self._event_matches(row["event_sequence"], following, following.intent.expected_revision+1, "RETRY_PREPARED")
