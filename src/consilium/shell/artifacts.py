"""Frozen schema and canonical typed mock sources; no external I/O or authority.

This ledger does not accept self-declared LIVE or MANUAL provenance. Those
paths require separate transport/user acceptance evidence in subsequent work.
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid5

from pydantic import ValidationError

from consilium.core.artifact_contracts import ArtifactResponseContract, AnswerOutput, parse_artifact_response
from consilium.core.contracts import Answer, Critique, RoundSpec
from consilium.core.operation_states import AttemptState
from consilium.core.round_context import ContextSource
from consilium.core.source_contracts import CanonicalSourceBatch
from consilium.shell.storage import Conflict, SchemaError, _identifier

if TYPE_CHECKING:
    from consilium.shell.storage import SQLiteStore


class ArtifactLedger:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self._db = store._db

    def validate_preparation(self, contract, intent):
        contract.require_intent(intent)
        row = self._db.execute("SELECT spec_json FROM rounds WHERE round_id=?", (str(intent.round_id),)).fetchone()
        if row is None or RoundSpec.model_validate_json(row[0]) != contract.round_spec:
            raise Conflict("Output contract differs from its registered round")
        self._validate_targets(contract)

    def _validate_targets(self, contract):
        for target in contract.targets:
            # Check graph direction before recursively reading any source batch.
            # A corrupted self/future reference must fail, never recurse forever.
            row = self._db.execute("SELECT r.spec_json FROM operations o JOIN rounds r ON o.round_id=r.round_id "
                "WHERE o.logical_operation_id=?", (str(target.logical_operation_id),)).fetchone()
            parent_round = None if row is None else RoundSpec.model_validate_json(row[0])
            if (parent_round is None or parent_round.debate_id != contract.round_spec.debate_id
                    or parent_round.number >= contract.round_spec.number):
                raise Conflict("Review target must belong to a strictly earlier registered round")
            old = self.store.sources.get(target.logical_operation_id)
            batch = self.get(target.logical_operation_id)
            sources = ((old.source,) if old is not None else ()) + (batch.sources if batch is not None else ())
            matches = [s for s in sources if isinstance(s.item, Answer) and s.item.answer_id == target.answer_id
                       and s.content_hash == target.source_hash]
            if (len(matches) != 1 or matches[0].item.debate_id != contract.round_spec.debate_id
                    or matches[0].source_round.number >= contract.round_spec.number):
                raise Conflict("Review target is not an exact prior canonical answer")

    def get_contract(self, intent) -> ArtifactResponseContract | None:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get_contract(intent)
        operation = _identifier(intent.identity.logical_operation_id)
        row = self._db.execute("SELECT * FROM response_contracts WHERE logical_operation_id=?", (operation,)).fetchone()
        if row is None:
            marker = self._db.execute("SELECT 1 FROM events WHERE kind='OPERATION_PREPARED' "
                "AND json_extract(payload_json,'$.logical_operation_id')=? "
                "AND json_type(payload_json,'$.response_contract_hash') IS NOT NULL", (operation,)).fetchone()
            if marker is not None:
                raise SchemaError("Frozen output contract was removed")
            return None
        try:
            contract = ArtifactResponseContract.model_validate_json(row["contract_json"])
            contract.require_intent(intent)
            prepared = self.store.get_intent(UUID(row["prepared_attempt_id"]))
            contract.require_intent(prepared)
            round_row = self._db.execute("SELECT spec_json FROM rounds WHERE round_id=?", (str(intent.round_id),)).fetchone()
            if round_row is None or RoundSpec.model_validate_json(round_row[0]) != contract.round_spec:
                raise ValueError("Frozen output round differs from registered state")
        except (ValueError, Conflict, ValidationError):
            raise SchemaError("Stored output contract differs from its operation") from None
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
        if (contract.content_hash != row["contract_hash"] or event is None
                or (event["debate_id"], event["kind"], event["revision"]) !=
                (str(intent.debate_id), "OPERATION_PREPARED", prepared.expected_revision + 1)):
            raise SchemaError("Frozen output contract has no matching preparation event")
        payload = json.loads(event["payload_json"])
        if (payload.get("logical_operation_id") != operation
                or payload.get("attempt_id") != row["prepared_attempt_id"]
                or payload.get("response_contract_hash") != contract.content_hash):
            raise SchemaError("Output contract checksum differs from its preparation event")
        return contract

    def _reconstruct(self, operation_id, published_revision, data_class):
        result = self.store.ledger.canonical_result(operation_id)
        if result is None:
            raise Conflict("Typed source publication requires a confirmed result")
        attempt = self.store.ledger.get_attempt(result.identity.attempt_id)
        contract = attempt.response_contract
        if (attempt.state != AttemptState.CONFIRMED or contract is None
                or attempt.validation.schema_id != contract.validation_schema):
            raise Conflict("Typed source publication requires its frozen output contract")
        self.validate_preparation(contract, attempt.intent)
        output = parse_artifact_response(result.content, contract)
        intent = attempt.intent
        if isinstance(output, AnswerOutput):
            items = (Answer(answer_id=uuid5(operation_id, "consilium/typed-answer/v1"),
                debate_id=intent.debate_id, round_id=intent.round_id, participant_id=intent.participant_id,
                content=output.answer, provenance="MOCK", round_seen=True,
                used_prompt=intent.frozen_input.canonical_bytes().decode("utf-8"), logical_operation_id=operation_id),)
        else:
            by_alias = {c.target_alias: c for c in output.critiques}
            items = tuple(Critique(critique_id=uuid5(operation_id, "consilium/typed-critique/v1/" + str(t.answer_id)),
                debate_id=intent.debate_id, round_id=intent.round_id, reviewer_id=intent.participant_id,
                target_answer_id=t.answer_id, rubric_version=contract.rubric_version,
                **by_alias[t.alias].model_dump(mode="python", exclude={"target_alias"})) for t in contract.targets)
        sources = tuple(ContextSource(item=item, source_round=contract.round_spec,
            source_revision=attempt.active_revision, provenance="MOCK", data_class=data_class) for item in items)
        result_hash = hashlib.sha256(self.store._public(result.model_dump(mode="json")).encode("utf-8")).hexdigest()
        return CanonicalSourceBatch(logical_operation_id=operation_id, attempt_id=result.identity.attempt_id,
            request_hash=intent.request_hash, result_hash=result_hash, response_contract_hash=contract.content_hash,
            validation_schema=contract.validation_schema, confirmed_revision=attempt.active_revision,
            published_revision=published_revision, sources=sources)

    def publish(self, operation_id: UUID, *, expected_revision: int,
                data_class: Literal["PUBLIC", "PRIVATE", "SECRET"] = "PRIVATE") -> CanonicalSourceBatch:
        operation = _identifier(operation_id)
        if data_class not in {"PUBLIC", "PRIVATE", "SECRET"}:
            raise ValueError("Source classification must be explicit")
        with self.store._transaction():
            row = self._db.execute("SELECT debate_id FROM operations WHERE logical_operation_id=?", (operation,)).fetchone()
            if row is None:
                raise Conflict("Source operation is not registered")
            debate = UUID(row[0])
            self.store._checked_debate(debate, expected_revision)
            old = self.get(operation_id)
            if old is not None:
                if any(s.data_class != data_class for s in old.sources):
                    raise Conflict("Published sources cannot be reclassified")
                return old
            record = self._reconstruct(operation_id, expected_revision + 1, data_class)
            payload = self._publication_payload(record)
            checkpoint = self.store._advance(debate, expected_revision, "SOURCE_BATCH_PUBLISHED", payload)
            self._db.execute("INSERT INTO canonical_source_batches VALUES(?,?,?,?,?)",
                (operation, str(record.attempt_id), self.store._public(record.model_dump(mode="json")),
                 record.content_hash, checkpoint.event_sequence))
            return record

    @staticmethod
    def _publication_payload(record):
        return {"logical_operation_id": str(record.logical_operation_id), "attempt_id": str(record.attempt_id),
                "response_contract_hash": record.response_contract_hash, "record_hash": record.content_hash,
                "source_hashes": [s.content_hash for s in record.sources]}

    def get(self, operation_id: UUID) -> CanonicalSourceBatch | None:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get(operation_id)
        operation = _identifier(operation_id)
        row = self._db.execute("SELECT * FROM canonical_source_batches WHERE logical_operation_id=?", (operation,)).fetchone()
        if row is None:
            marker = self._db.execute("SELECT 1 FROM events WHERE kind='SOURCE_BATCH_PUBLISHED' "
                "AND json_extract(payload_json,'$.logical_operation_id')=?", (operation,)).fetchone()
            if marker is not None:
                raise SchemaError("Published source batch was removed")
            return None
        try:
            record = CanonicalSourceBatch.model_validate_json(row["record_json"])
            expected = self._reconstruct(operation_id, record.published_revision, record.sources[0].data_class)
        except (ValueError, Conflict, ValidationError, KeyError, TypeError):
            raise SchemaError("Source batch cannot be reconstructed from its confirmed result") from None
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
        debate_id = record.sources[0].item.debate_id
        if (record != expected or record.content_hash != row["record_hash"]
                or str(record.attempt_id) != row["attempt_id"] or event is None
                or (event["debate_id"], event["revision"], event["kind"]) !=
                (str(debate_id), record.published_revision, "SOURCE_BATCH_PUBLISHED")
                or json.loads(event["payload_json"]) != self._publication_payload(record)
                or record.published_revision > self.store.checkpoint(debate_id).revision):
            raise SchemaError("Source batch differs from its canonical result or publication event")
        return record

    def for_debate(self, debate_id: UUID) -> tuple[CanonicalSourceBatch, ...]:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.for_debate(debate_id)
        self.store.get_debate(debate_id)
        self.store.checkpoint(debate_id)
        events = self._db.execute("SELECT payload_json FROM events WHERE debate_id=? "
            "AND kind='SOURCE_BATCH_PUBLISHED' ORDER BY sequence", (_identifier(debate_id),)).fetchall()
        records = tuple(self.get(UUID(json.loads(e[0])["logical_operation_id"])) for e in events)
        if any(r is None or r.sources[0].item.debate_id != debate_id for r in records):
            raise SchemaError("Source batches do not match their debate")
        return records

    def export_fields(self, debate_id):
        return {"typed_mock_source_batches": [r.model_dump(mode="json") for r in self.for_debate(debate_id)]}

    def check_integrity(self):
        contracts = self._db.execute("SELECT * FROM response_contracts").fetchall()
        for row in contracts:
            intent = self.store.get_intent(UUID(row["prepared_attempt_id"]))
            contract = self.get_contract(intent)
            try:
                self.validate_preparation(contract, intent)
            except (ValueError, Conflict):
                raise SchemaError("Stored output contract has invalid canonical targets") from None
        markers = self._db.execute("SELECT sequence,payload_json FROM events WHERE kind='OPERATION_PREPARED' "
            "AND json_type(payload_json,'$.response_contract_hash') IS NOT NULL").fetchall()
        actual = {(r["logical_operation_id"], r["event_sequence"]) for r in contracts}
        marked = {(json.loads(r["payload_json"]).get("logical_operation_id"), r["sequence"]) for r in markers}
        if actual != marked:
            raise SchemaError("Output contracts and preparation events do not match")
        rows = self._db.execute("SELECT logical_operation_id,event_sequence FROM canonical_source_batches").fetchall()
        for row in rows:
            self.get(UUID(row["logical_operation_id"]))
        markers = self._db.execute("SELECT sequence,payload_json FROM events WHERE kind='SOURCE_BATCH_PUBLISHED'").fetchall()
        if {(r["logical_operation_id"], r["event_sequence"]) for r in rows} != {
                (json.loads(r["payload_json"]).get("logical_operation_id"), r["sequence"]) for r in markers}:
            raise SchemaError("Source batches and publication events do not match")
