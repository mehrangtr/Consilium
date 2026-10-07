"""Validate durable local facts; never infer remote truth or authorize a resend."""
import json
from uuid import UUID

from consilium.core.admission_bundle import AdmissionBundle
from consilium.core.contracts import ConnectionSpec, RoundSpec
from consilium.core.independent_context import recover_independent_context
from consilium.shell.private import ensure_public_payload
from consilium.shell.storage import Conflict, SchemaError, _identifier


class AdmissionLedger:
    def __init__(self, store):
        self.store = store
        self._db = store._db

    def validate_preparation(self, bundle: AdmissionBundle, intent) -> None:
        bundle.require_intent(intent)
        question = self.store.questions.get_adopted(intent.debate_id)
        if question is None:
            raise Conflict("Context admission requires the adopted question")
        ensure_public_payload(question.model_dump(mode="json"), self.store._forbidden_values)
        row = self._db.execute("SELECT spec_json FROM rounds WHERE round_id=? AND debate_id=?",
            (str(intent.round_id), str(intent.debate_id))).fetchone()
        if row is None:
            raise Conflict("Context admission requires its registered round")
        recover_independent_context(bundle.context, question, RoundSpec.model_validate_json(row[0]),
            participant_id=intent.participant_id, expected_revision=question.adoption.adopted_revision,
            parameters=intent.frozen_input.parameters)

    def get(self, logical_operation_id: UUID) -> AdmissionBundle | None:
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
            bundle = AdmissionBundle.model_validate_json(row["bundle_json"])
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
