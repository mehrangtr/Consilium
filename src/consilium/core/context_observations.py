"""Versioned observation contracts. Offline facts never certify a live service."""
import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field

from .contracts import ConnectionSpec, Contract, Identifier, Message, Revision, Sha256, Text
from .dispatch_policy import PolicyBinding, PolicyBlocked, destination_hash
from .question_contracts import _hash

OBSERVER_ID = "consilium.offline-context.v1"
TOKENIZER_ID = "mock:utf8-byte-v1"
# A versioned algorithm fingerprint, not a signature or a live certification.
OBSERVER_IMPLEMENTATION_HASH = hashlib.sha256(
    b"Consilium.OfflineContextObserver.v1:canonical-source-reconstruction;"
    b"full-history-exact-match;json-sort-compact-unicode-utf8-byte-codec"
).hexdigest()
MOCK_CONTEXT_CAPACITY = 1_000_000


class HistorySnapshot(Contract):
    scope: Literal["OFFLINE_OBSERVER_NOT_LIVE_CERTIFICATION"] = "OFFLINE_OBSERVER_NOT_LIVE_CERTIFICATION"
    debate_id: Identifier
    destination_hash: Sha256
    conversation_id: Identifier | None
    complete: bool
    entries: tuple[Message, ...]

    @property
    def content_hash(self) -> str:
        return _hash(self)


class SourceObservation(Contract):
    source_hash: Sha256
    source_revision: Revision
    provenance: Literal["MOCK", "MANUAL"]
    external_origin_verified: Literal[False] = False


class ObservationReceipt(PolicyBinding):
    schema_version: Literal[1] = 1
    scope: Literal["OFFLINE_OBSERVER_NOT_LIVE_CERTIFICATION"] = "OFFLINE_OBSERVER_NOT_LIVE_CERTIFICATION"
    observer_id: Text
    observer_implementation_hash: Sha256
    tokenizer_id: Text
    wire_hash: Sha256
    token_count: Annotated[int, Field(ge=1)]
    history_snapshot: HistorySnapshot
    new_topic: bool
    preference: Literal["PREFER_CURRENT", "NEW_CONVERSATION"]
    user_action_id: Identifier | None
    sources: tuple[SourceObservation, ...]


def check_history(*, snapshot, connection, debate_id, authorized_entries,
                  new_topic, preference, user_action_id):
    snapshot = HistorySnapshot.model_validate(snapshot)
    connection = ConnectionSpec.model_validate(connection)
    if (type(new_topic) is not bool or preference not in {"PREFER_CURRENT", "NEW_CONVERSATION"}
            or user_action_id is not None and (not isinstance(user_action_id, UUID) or user_action_id.int == 0)):
        raise PolicyBlocked("INVALID_CONVERSATION_CHOICE")
    if preference == "NEW_CONVERSATION" and user_action_id is None:
        raise PolicyBlocked("NEW_CONVERSATION_REQUIRES_LOCAL_USER_ACTION")
    if (snapshot.debate_id != debate_id or snapshot.destination_hash != destination_hash(connection)
            or not snapshot.complete):
        raise PolicyBlocked("HISTORY_IDENTITY_OR_COMPLETENESS_UNVERIFIED")
    if connection.mode == "API":
        if snapshot.conversation_id is not None or snapshot.entries:
            raise PolicyBlocked("STATELESS_TRANSPORT_HAS_REMOTE_HISTORY")
        return "NO_REMOTE_HISTORY"
    if connection.mode != "BROWSER" or connection.account_binding_id is None or snapshot.conversation_id is None:
        raise PolicyBlocked("REMOTE_CONVERSATION_IDENTITY_MISSING")
    if new_topic or preference == "NEW_CONVERSATION":
        if snapshot.entries:
            raise PolicyBlocked("FRESH_CONVERSATION_REQUIRED")
        return "FRESH_EMPTY"
    if not snapshot.entries:
        return "FRESH_EMPTY"
    if snapshot.entries != authorized_entries:
        raise PolicyBlocked("REMOTE_HISTORY_DIFFERS_FROM_AUTHORIZED_TRANSCRIPT")
    return "VERIFIED_AUTHORIZED"


def mock_wire(frozen_input, history_snapshot) -> bytes:
    """Exact serialization for our local byte-token fixture, never a provider."""
    return json.dumps({"history": [m.model_dump(mode="json") for m in history_snapshot.entries],
                       "input": frozen_input.model_dump(mode="json")},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def observe_sources(sources):
    return tuple(SourceObservation(source_hash=s.content_hash, source_revision=s.source_revision,
                                   provenance=s.provenance) for s in sources)


def validate_observation(receipt, *, context, connection, privacy, budget, history,
                         expected_revision, sources):
    receipt = ObservationReceipt.model_validate(receipt)
    expected = dict(view_hash=context.content_hash, request_hash=context.frozen_input.content_hash,
                    destination_hash=destination_hash(connection), ledger_revision=expected_revision)
    if any(getattr(receipt, k) != v for k, v in expected.items()):
        raise PolicyBlocked("OBSERVATION_BINDING_MISMATCH")
    if (connection.provider_id != "mock" or connection.model_id != "mock-v1"
            or receipt.observer_id != OBSERVER_ID or receipt.tokenizer_id != TOKENIZER_ID
            or receipt.observer_implementation_hash != OBSERVER_IMPLEMENTATION_HASH):
        raise PolicyBlocked("OBSERVER_NOT_REGISTERED")
    wire = mock_wire(context.frozen_input, receipt.history_snapshot)
    if (receipt.wire_hash != hashlib.sha256(wire).hexdigest() or receipt.token_count != len(wire)
            or receipt.sources != observe_sources(sources)
            or budget.input_tokens != receipt.token_count or budget.transport_overhead_tokens != 0
            or budget.measurement != "EXACT" or budget.context_capacity != MOCK_CONTEXT_CAPACITY):
        raise PolicyBlocked("OBSERVATION_CONTENT_OR_MEASUREMENT_MISMATCH")
    # Historical remote truth cannot be refreshed during reconstruction. Verify
    # recorded identity/choice here; the shell separately checks canonical history.
    snap = receipt.history_snapshot
    if (not snap.complete or snap.debate_id != context.debate_id or snap.destination_hash != expected["destination_hash"]
            or snap.conversation_id != history.conversation_id or receipt.new_topic != history.new_topic):
        raise PolicyBlocked("OBSERVED_HISTORY_FACT_MISMATCH")
    observed_state = check_history(snapshot=snap, connection=connection, debate_id=context.debate_id,
        authorized_entries=snap.entries, new_topic=receipt.new_topic, preference=receipt.preference,
        user_action_id=receipt.user_action_id)
    if observed_state != history.state:
        raise PolicyBlocked("OBSERVED_HISTORY_STATE_MISMATCH")
    return receipt
