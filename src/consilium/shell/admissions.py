"""Validate durable local facts; never infer remote truth or authorize a resend."""
import json
from uuid import UUID

from consilium.core.admission_bundle import AdmissionBundle
from consilium.core.contracts import ConnectionSpec, RoundSpec, UserDecision
from consilium.core.independent_context import recover_independent_context
from consilium.core.round_admission import ADMISSION_ADAPTER, RoundAdmissionBundle
from consilium.core.round_context import recover_round_context
from consilium.shell.private import ensure_public_payload
from consilium.shell.storage import Conflict, SchemaError, _identifier


class AdmissionLedger:
    def __init__(self, store):
        self.store = store
        self._db = store._db

    def continuation_for(self, round_spec):
        row = self._db.execute("SELECT d.decision_json FROM user_decisions d JOIN rounds r ON r.round_id=d.round_id "
            "WHERE d.debate_id=? AND r.number=? ORDER BY d.event_sequence DESC LIMIT 1",
            (str(round_spec.debate_id), round_spec.number-1)).fetchone()
        if row is None:
            raise Conflict("Later-round context requires its stored continuation decision")
        decision = UserDecision.model_validate_json(row[0])
        if decision.kind not in {"CONTINUE", "CUSTOM"}:
            raise Conflict("Stored decision does not permit continuation")
        return decision

    def validate_preparation(self, bundle: AdmissionBundle | RoundAdmissionBundle, intent) -> None:
        bundle.require_intent(intent)
        question = self.store.questions.get_adopted(intent.debate_id)
        if question is None:
            raise Conflict("Context admission requires the adopted question")
        ensure_public_payload(question.model_dump(mode="json"), self.store._forbidden_values)
        row = self._db.execute("SELECT spec_json FROM rounds WHERE round_id=? AND debate_id=?",
            (str(intent.round_id), str(intent.debate_id))).fetchone()
        if row is None:
            raise Conflict("Context admission requires its registered round")
        round_spec = RoundSpec.model_validate_json(row[0])
        if isinstance(bundle, RoundAdmissionBundle):
            sources = tuple(s for s in self.store.sources.context_sources(intent.debate_id,
                through_revision=intent.expected_revision) if s.source_round.number < round_spec.number)
            if bundle.sources != sources or bundle.required_source_hashes != tuple(s.content_hash for s in sources):
                raise Conflict("Round admission sources differ from the canonical historical snapshot")
            decision = self.continuation_for(round_spec)
            ensure_public_payload(decision.model_dump(mode="json"), self.store._forbidden_values)
            if bundle.continuation_decision != decision:
                raise Conflict("Round admission differs from the stored continuation decision")
            # Semantic checks precede JSON serialization; escaping is no secret filter.
            for source in sources:
                ensure_public_payload(source.model_dump(mode="json"), self.store._forbidden_values)
            recover_round_context(bundle.context, question=question, debate=self.store.get_debate(intent.debate_id),
                round_spec=round_spec, participant_id=intent.participant_id, expected_revision=intent.expected_revision,
                sources=sources, required_source_hashes=bundle.required_source_hashes, grants=bundle.grants,
                connection=bundle.connection, parameters=intent.frozen_input.parameters,
                judge_selection=bundle.judge_selection, named_authorization=bundle.named_authorization,
                continuation_decision=decision)
        else:
            recover_independent_context(bundle.context, question, round_spec,
                participant_id=intent.participant_id, expected_revision=question.adoption.adopted_revision,
                parameters=intent.frozen_input.parameters)
        from consilium.shell.context_observers import validate_stored_observation
        validate_stored_observation(self.store, bundle, intent)

    def get(self, logical_operation_id: UUID) -> AdmissionBundle | RoundAdmissionBundle | None:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get(logical_operation_id)
        logical = _identifier(logical_operation_id)
        row = self._db.execute("SELECT * FROM context_admissions WHERE logical_operation_id=?", (logical,)).fetchone()
        marked = self._db.execute("SELECT * FROM events WHERE kind='OPERATION_PREPARED' "
            "AND json_extract(payload_json,'$.logical_operation_id')=?", (logical,)).fetchall()
        if row is None:
            if any("admission_bundle_hash" in json.loads(e["payload_json"]) for e in marked):
                raise SchemaError("Prepared admission evidence is missing")
            return None  # Historical foundation operations have no policy bundle.
        try:
            bundle = ADMISSION_ADAPTER.validate_json(row["bundle_json"])
            if bundle.content_hash != row["bundle_hash"]:
                raise ValueError("Bundle checksum mismatch")
            intent = self.store.get_intent(UUID(row["prepared_attempt_id"]))
            if str(intent.identity.logical_operation_id) != logical:
                raise ValueError("Bundle belongs to another logical operation")
            self.validate_preparation(bundle, intent)
            event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
            expected = {"logical_operation_id": logical, "attempt_id": row["prepared_attempt_id"],
                        "admission_bundle_hash": bundle.content_hash}
            if (len(marked) != 1 or event is None or event["kind"] != "OPERATION_PREPARED"
                    or event["debate_id"] != str(intent.debate_id)
                    or event["revision"] != intent.expected_revision + 1
                    or json.loads(event["payload_json"]) != expected):
                raise ValueError("Bundle has no matching preparation event")
            return bundle
        except ValueError:
            raise SchemaError("Stored context admission is inconsistent") from None

    def require_current(self, attempt_id: UUID, *, expected_revision: int) -> AdmissionBundle:
        """A current local checkpoint check, not permission to call a provider."""
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.require_current(attempt_id, expected_revision=expected_revision)
        intent = self.store.get_intent(attempt_id)
        self.store._checked_debate(intent.debate_id, expected_revision)
        bundle = self.get(intent.identity.logical_operation_id)
        if bundle is None:
            raise Conflict("Operation has no durable context admission")
        row = self._db.execute("SELECT prepared_attempt_id FROM context_admissions WHERE logical_operation_id=?",
            (str(intent.identity.logical_operation_id),)).fetchone()
        if row[0] != str(attempt_id):
            raise Conflict("A retry requires fresh policy evidence")
        binding = self._db.execute("SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?",
            (str(intent.debate_id), str(intent.participant_id))).fetchone()
        current_round = self._db.execute("SELECT round_id FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1",
            (str(intent.debate_id),)).fetchone()
        state = self._db.execute("SELECT state FROM attempts WHERE attempt_id=?", (str(attempt_id),)).fetchone()[0]
        if (binding is None or binding["revision"] != bundle.connection_revision
                or ConnectionSpec.model_validate_json(binding["spec_json"]) != bundle.connection
                or current_round is None or current_round[0] != str(intent.round_id)
                or state != "PREPARED" or expected_revision != intent.expected_revision + 1):
            raise Conflict("Saved local admission is stale for continuation")
        return bundle

    def check_integrity(self) -> None:
        logical_ids = {r[0] for r in self._db.execute("SELECT logical_operation_id FROM context_admissions")}
        for event in self._db.execute("SELECT payload_json FROM events WHERE kind='OPERATION_PREPARED'"):
            payload = json.loads(event[0])
            if "admission_bundle_hash" in payload:
                logical_ids.add(payload.get("logical_operation_id"))
        for logical in logical_ids:
            try:
                self.get(UUID(logical))
            except (ValueError, TypeError, AttributeError):
                raise SchemaError("Stored admission graph is inconsistent") from None

    def export_fields(self, debate_id: UUID) -> dict:
        rows = self._db.execute("SELECT ca.logical_operation_id FROM context_admissions ca "
            "JOIN operations o USING(logical_operation_id) WHERE o.debate_id=? ORDER BY ca.event_sequence",
            (str(debate_id),)).fetchall()
        return {"context_admissions": [{"logical_operation_id": row[0],
            "bundle": self.get(UUID(row[0])).model_dump(mode="json")} for row in rows]}
