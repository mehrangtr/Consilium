"""Immutable P01 contracts. Schemas do not replace state/transaction invariants."""
from __future__ import annotations

from enum import StrEnum
import hashlib
import json
from typing import Annotated, Any, Literal, Mapping, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must not be blank")
    return value  # Preserve the exact user's text; validation must not trim it.


def _non_nil(value: UUID) -> UUID:
    if value.int == 0:
        raise ValueError("Identity must not be nil")
    return value


Text = Annotated[str, AfterValidator(_nonblank)]
Identifier = Annotated[UUID, AfterValidator(_non_nil)]
Revision = Annotated[int, Field(ge=0)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Mode = Literal["API", "BROWSER", "MANUAL"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True,
                              hide_input_in_errors=True, revalidate_instances="always",
                              allow_inf_nan=False)

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """Unlike the library's default copy, updates cross the validation boundary."""
        # Every field is immutable; rebuilding validates nested models as well.
        return type(self).model_validate({**self.model_dump(mode="python"), **(update or {})})


class Participant(Contract):
    participant_id: Identifier
    alias: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9]{0,11}$")]


class ConnectionSpec(Contract):
    connection_id: Identifier
    provider_id: Text
    model_id: Text
    mode: Mode
    account_binding_id: Identifier | None = None  # Opaque reference, never a credential.


def _unique_participants(value: tuple[UUID, ...]) -> tuple[UUID, ...]:
    if not value or len(value) != len(set(value)):
        raise ValueError("Participants must be nonempty and unique")
    return value


Participants = Annotated[tuple[Identifier, ...], AfterValidator(_unique_participants)]


class DebateSpec(Contract):
    debate_id: Identifier
    original_request: Text
    participant_ids: Participants
    constraints: tuple[Text, ...] = ()
    revision: Revision = 0
    review_visibility: Literal["BLIND", "NAMED"] = "BLIND"


class RoundSpec(Contract):
    round_id: Identifier
    debate_id: Identifier
    number: Annotated[int, Field(ge=1)]
    kind: Literal["INDEPENDENT", "REVIEW", "TARGETED", "SYNTHESIS"]
    participant_ids: Participants
    targets: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def targeted_scope(self) -> Self:
        if self.kind == "TARGETED" and not self.targets:
            raise ValueError("A targeted round requires explicit unresolved targets")
        return self


class Answer(Contract):
    answer_id: Identifier
    debate_id: Identifier
    round_id: Identifier
    participant_id: Identifier
    content: Text
    provenance: Literal["LIVE_GENERATED", "MANUAL", "MOCK"]
    used_prompt: Text
    round_seen: bool
    logical_operation_id: Identifier | None = None


class PeerPoint(Contract):
    verdict: Literal["ACCEPT", "PARTIALLY_ACCEPT", "REJECT"]
    reference: Text
    reason: Text


class Critique(Contract):
    critique_id: Identifier
    debate_id: Identifier
    round_id: Identifier
    reviewer_id: Identifier
    target_answer_id: Identifier
    points: Annotated[tuple[PeerPoint, ...], Field(min_length=1)]
    score: Annotated[int, Field(ge=1, le=10)] | Literal['NOT_SCORED']
    scoring_reason: Text
    rubric_version: Text
    strengths: tuple[Text, ...] = ()
    weaknesses: tuple[Text, ...] = ()


class UserDecision(Contract):
    decision_id: Identifier
    debate_id: Identifier
    round_id: Identifier
    expected_revision: Revision
    kind: Literal["FINISH", "CONTINUE", "CUSTOM", "PAUSE"]
    instruction: Text | None = None

    @model_validator(mode="after")
    def instruction_matches_choice(self) -> Self:
        if (self.kind == "CUSTOM") != (self.instruction is not None):
            raise ValueError("Only a custom decision carries a required instruction")
        return self


class OperationIdentity(Contract):
    logical_operation_id: Identifier
    attempt_id: Identifier
    generation_id: Identifier | None = None

    @model_validator(mode="after")
    def distinct_identities(self) -> Self:
        values = [self.logical_operation_id, self.attempt_id]
        if self.generation_id is not None:
            values.append(self.generation_id)
        if len(set(values)) != len(values):
            raise ValueError("Logical operation, attempt and generation are separate identities")
        return self


class Message(Contract):
    role: Literal["SYSTEM", "USER", "ASSISTANT"]
    content: Text


class GenerationParameters(Contract):
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] | None = None
    max_output_tokens: Annotated[int, Field(ge=1)] | None = None
    seed: int | None = None


class FrozenInput(Contract):
    schema_version: Literal[1] = 1
    messages: Annotated[tuple[Message, ...], Field(min_length=1)]
    parameters: GenerationParameters = Field(default_factory=GenerationParameters)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version_type(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class OperationIntent(Contract):
    identity: OperationIdentity
    debate_id: Identifier
    round_id: Identifier
    participant_id: Identifier
    connection_id: Identifier
    expected_revision: Revision
    connection_revision: Revision
    frozen_input: FrozenInput
    request_hash: Sha256
    state: Literal["PREPARED"] = "PREPARED"

    @model_validator(mode="after")
    def hash_matches_input(self) -> Self:
        if self.request_hash != self.frozen_input.content_hash:
            raise ValueError("Request hash does not match frozen input")
        return self


class AdapterCapabilities(Contract):
    mode: Mode
    verification: Literal["UNVERIFIED", "DECLARED_MOCK", "LIVE_VERIFIED"] = "UNVERIFIED"
    delivery_probe: bool = False
    idempotency: bool = False
    continuation: bool = False
    streaming: bool = False
    structured_output: bool = False
    verification_evidence: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def live_claim_needs_evidence(self) -> Self:
        if self.verification == "LIVE_VERIFIED" and not self.verification_evidence:
            raise ValueError("Live verification requires evidence references")
        return self


class AdapterRequest(Contract):
    intent: OperationIntent
    connection: ConnectionSpec
    timeout_seconds: Annotated[float, Field(gt=0.0)]
    # Optional opaque transport context, frozen durably with the dispatch request.
    # It is separate from the prompt hash and never contains credentials.
    transport_binding_hash: Sha256 | None = None

    @model_validator(mode="after")
    def intent_matches_connection(self) -> Self:
        if self.intent.connection_id != self.connection.connection_id:
            raise ValueError("Intent and connection identity differ")
        return self


class Delivery(StrEnum):
    NOT_SENT = "NOT_SENT"
    UNKNOWN = "UNKNOWN_DELIVERY"
    CONFIRMED = "CONFIRMED_DELIVERY"


class ResponseState(StrEnum):
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    INVALID = "INVALID"


class Failure(StrEnum):
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    QUOTA = "QUOTA"
    SEND_REJECTED = "SEND_REJECTED"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class TransportResult(Contract):
    identity: OperationIdentity
    request_hash: Sha256
    connection_id: Identifier
    connection_revision: Revision
    delivery: Delivery
    response_state: ResponseState
    content: str | None = None
    failure: Failure = Failure.NONE
    response_id: Text | None = None
    evidence: tuple[Text, ...] = ()
    elapsed_seconds: Annotated[float, Field(ge=0.0)] = 0.0

    @model_validator(mode="after")
    def consistent_observation(self) -> Self:
        if self.response_state != ResponseState.NONE:
            if self.delivery != Delivery.CONFIRMED or self.content is None or not self.content.strip():
                raise ValueError("Received content needs confirmed delivery and nonblank content")
        elif self.content is not None:
            raise ValueError("A missing response cannot carry content")
        if self.response_state == ResponseState.COMPLETE and self.failure != Failure.NONE:
            raise ValueError("A complete successful response cannot carry a failure")
        if self.response_state == ResponseState.INVALID and self.failure != Failure.INVALID_RESPONSE:
            raise ValueError("Invalid response needs an explicit validation failure")
        if self.failure == Failure.INVALID_RESPONSE and self.response_state != ResponseState.INVALID:
            raise ValueError("A response validation failure requires a received invalid response")
        if self.delivery == Delivery.NOT_SENT and self.response_id is not None:
            raise ValueError("An unsent attempt cannot have a remote response identity")
        return self


class DeliveryObservation(Contract):
    identity: OperationIdentity
    request_hash: Sha256
    connection_id: Identifier
    connection_revision: Revision
    delivery: Delivery
    evidence: tuple[Text, ...]
