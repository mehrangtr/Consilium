"""Verified source snapshots from canonical results; no provider calls or claims.

Only the existing P02 answer schema is supported here. Its provenance stays MOCK.
Council answer/critique validation and durable later-round admission remain open.
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid5

from pydantic import ValidationError
from consilium.core.contracts import Answer, RoundSpec
from consilium.core.operation_states import AttemptState
from consilium.core.round_context import ContextSource
from consilium.core.source_contracts import CanonicalAnswerSource
from consilium.shell.storage import Conflict, SchemaError, _identifier

if TYPE_CHECKING:
    from consilium.shell.storage import SQLiteStore


class SourceLedger:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self._db = store._db

    def _reconstruct(self, operation_id, published_revision, data_class):
        result = self.store.ledger.canonical_result(operation_id)
        if result is None:
            raise Conflict("Source publication requires a confirmed canonical result")
        record = self.store.ledger.get_attempt(result.identity.attempt_id)
        if record.state != AttemptState.CONFIRMED or record.validation.schema_id != "P02MockAnswer.v1":
            raise Conflict("This source path only supports confirmed P02 mock answers")
        intent = record.intent
        round_row = self._db.execute("SELECT spec_json FROM rounds WHERE round_id=?", (str(intent.round_id),)).fetchone()
        if round_row is None:
            raise SchemaError("Canonical source round is missing")
        round_spec = RoundSpec.model_validate_json(round_row[0])
        if (round_spec.round_id != intent.round_id or round_spec.debate_id != intent.debate_id
                or intent.participant_id not in round_spec.participant_ids):
            raise SchemaError("Canonical source does not match its registered round")
        # The ledger revalidates the stored JSON and refuses duplicate keys.
        # Identities, provenance and used prompt come from local state, not text.
        answer = Answer(answer_id=uuid5(operation_id, "consilium/canonical-answer/v1"),
            debate_id=intent.debate_id, round_id=intent.round_id, participant_id=intent.participant_id,
            content=json.loads(result.content)["answer"], provenance="MOCK",
            used_prompt=intent.frozen_input.canonical_bytes().decode("utf-8"), round_seen=True,
            logical_operation_id=operation_id)
        source = ContextSource(item=answer, source_round=round_spec, source_revision=record.active_revision,
            provenance="MOCK", data_class=data_class)
        result_hash = hashlib.sha256(self.store._public(result.model_dump(mode="json")).encode("utf-8")).hexdigest()
        return CanonicalAnswerSource(logical_operation_id=operation_id, attempt_id=result.identity.attempt_id,
            request_hash=intent.request_hash, result_hash=result_hash, confirmed_revision=record.active_revision,
            published_revision=published_revision, source=source)

    def publish_mock_answer(self, logical_operation_id: UUID, *, expected_revision: int,
                            data_class: Literal["PUBLIC", "PRIVATE", "SECRET"] = "PRIVATE") -> CanonicalAnswerSource:
        operation_id = _identifier(logical_operation_id)
        if data_class not in {"PUBLIC", "PRIVATE", "SECRET"}:
            raise ValueError("Source classification must be explicit")
        with self.store._transaction():
            row = self._db.execute("SELECT debate_id FROM operations WHERE logical_operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise Conflict("Source operation is not registered")
            debate_id = UUID(row[0])
            self.store._checked_debate(debate_id, expected_revision)
            existing = self.get(logical_operation_id)
            if existing is not None:
                if existing.source.data_class != data_class:
                    raise Conflict("An immutable published source cannot be reclassified")
                return existing
            record = self._reconstruct(logical_operation_id, expected_revision+1, data_class)
            public = self.store._public(record.model_dump(mode="json"))
            checkpoint = self.store._advance(debate_id, expected_revision, "CONTEXT_SOURCE_PUBLISHED",
                {"logical_operation_id": operation_id, "attempt_id": str(record.attempt_id),
                 "source_hash": record.source.content_hash, "record_hash": record.content_hash})
            self._db.execute("INSERT INTO canonical_context_sources VALUES(?,?,?,?,?,?)",
                (operation_id, str(record.attempt_id), record.source.content_hash, public,
                 record.content_hash, checkpoint.event_sequence))
            return record

    def get(self, logical_operation_id: UUID) -> CanonicalAnswerSource | None:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get(logical_operation_id)
        operation_id = _identifier(logical_operation_id)
        row = self._db.execute("SELECT * FROM canonical_context_sources WHERE logical_operation_id=?", (operation_id,)).fetchone()
        if row is None:
            marker = self._db.execute("SELECT 1 FROM events WHERE kind='CONTEXT_SOURCE_PUBLISHED' "
                "AND json_extract(payload_json,'$.logical_operation_id')=?", (operation_id,)).fetchone()
            if marker is not None:
                raise SchemaError("Published source was removed while its event remains")
            return None
        try:
            record = CanonicalAnswerSource.model_validate_json(row["record_json"])
            expected = self._reconstruct(logical_operation_id, record.published_revision, record.source.data_class)
        except (Conflict, ValueError, ValidationError, KeyError, TypeError):
            raise SchemaError("Stored source cannot be reconstructed from its canonical result") from None
        if (record != expected or record.logical_operation_id != logical_operation_id
                or str(record.attempt_id) != row["attempt_id"] or record.content_hash != row["record_hash"]
                or record.source.content_hash != row["source_hash"]):
            raise SchemaError("Stored source differs from its canonical result or checksum")
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
        payload = {"logical_operation_id": operation_id, "attempt_id": str(record.attempt_id),
                   "source_hash": record.source.content_hash, "record_hash": record.content_hash}
        if (event is None or (event["debate_id"], event["revision"], event["kind"]) !=
                (str(record.source.item.debate_id), record.published_revision, "CONTEXT_SOURCE_PUBLISHED")
                or json.loads(event["payload_json"]) != payload
                or record.published_revision > self.store.checkpoint(record.source.item.debate_id).revision):
            raise SchemaError("Source publication does not match its committed event")
        return record

    def for_debate(self, debate_id: UUID) -> tuple[CanonicalAnswerSource, ...]:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.for_debate(debate_id)
        self.store.get_debate(debate_id)
        self.store.checkpoint(debate_id)
        rows = self._db.execute("SELECT payload_json FROM events WHERE debate_id=? "
            "AND kind='CONTEXT_SOURCE_PUBLISHED' ORDER BY sequence", (_identifier(debate_id),)).fetchall()
        records = tuple(self.get(UUID(json.loads(row[0])["logical_operation_id"])) for row in rows)
        if any(record is None or record.source.item.debate_id != debate_id for record in records):
            raise SchemaError("Source collection does not match its debate's publication events")
        return records

    def export_fields(self, debate_id: UUID) -> dict:
        return {"canonical_context_sources": [x.model_dump(mode="json") for x in self.for_debate(debate_id)]}

    def context_sources(self, debate_id: UUID) -> tuple[ContextSource, ...]:
        """All verified legacy/typed sources, in publication order; no grants."""
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.context_sources(debate_id)
        groups = [(r.published_revision, (r.source,)) for r in self.for_debate(debate_id)]
        groups += [(r.published_revision, r.sources) for r in self.store.artifacts.for_debate(debate_id)]
        groups += [(r.accepted_revision, (r.source,)) for r in self.store.manual_sources.for_debate(debate_id)
                   if r.alignment == "ALIGNED"]
        return tuple(source for _, sources in sorted(groups, key=lambda x: x[0]) for source in sources)

    def check_integrity(self) -> None:
        rows = self._db.execute("SELECT logical_operation_id,event_sequence FROM canonical_context_sources").fetchall()
        for row in rows:
            self.get(UUID(row["logical_operation_id"]))
        events = self._db.execute("SELECT sequence,payload_json FROM events WHERE kind='CONTEXT_SOURCE_PUBLISHED'").fetchall()
        actual = {(row["logical_operation_id"], row["event_sequence"]) for row in rows}
        marked = {(json.loads(row["payload_json"]).get("logical_operation_id"), row["sequence"]) for row in events}
        if actual != marked:
            raise SchemaError("Source publication events and records do not match")
