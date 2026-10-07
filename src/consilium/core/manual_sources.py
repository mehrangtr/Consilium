"""Manual content has local acceptance, never verified external generation provenance."""
from typing import Annotated, Literal, Self
from uuid import uuid5

from pydantic import Field, field_validator, model_validator

from .contracts import Answer, ConnectionSpec, Contract, Identifier, Revision, RoundSpec, Sha256, Text
from .question_contracts import _hash
from .round_context import ContextSource


class ManualAnswerSubmission(Contract):
    """A file supplies content and references, never the expected prompt or approval."""
    schema_version: Literal[1]
    candidate_id: Identifier
    debate_id: Identifier
    round_id: Identifier
    participant_id: Identifier
    actual_prompt: Text
    round_seen: bool
    answer: Annotated[Text, Field(max_length=262144)]
    claimed_origin: Annotated[Text, Field(max_length=1024)] | None = None
    data_class: Literal["PUBLIC", "PRIVATE"] = "PRIVATE"

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("Manual submission version must be an integer")
        return value


class ManualAnswerCandidate(Contract):
    schema_version: Literal[1] = 1
    scope: Literal["LOCAL_MANUAL_CONTENT_EXTERNAL_ORIGIN_UNVERIFIED"] = "LOCAL_MANUAL_CONTENT_EXTERNAL_ORIGIN_UNVERIFIED"
    candidate_id: Identifier
    round_spec: RoundSpec
    participant_id: Identifier
    connection: ConnectionSpec
    connection_revision: Revision
    staged_revision: Revision
    expected_prompt: Text
    actual_prompt: Text
    round_seen: bool
    answer: Annotated[Text, Field(max_length=262144)]
    claimed_origin: Annotated[Text, Field(max_length=1024)] | None = None
    data_class: Literal["PUBLIC", "PRIVATE"] = "PRIVATE"

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("Manual schema version must be an integer")
        return value

    @model_validator(mode="after")
    def local_role(self) -> Self:
        if (self.connection.mode != "MANUAL" or self.round_spec.kind != "INDEPENDENT"
                or self.round_spec.number != 1 or self.participant_id not in self.round_spec.participant_ids
                or len(self.model_dump_json().encode("utf-8")) > 1048576):
            raise ValueError("Manual answer exceeds its initial-round local contract")
        return self

    @property
    def alignment(self) -> str:
        return "ALIGNED" if self.round_seen and self.actual_prompt == self.expected_prompt else "DIVERGED"

    @property
    def content_hash(self) -> str:
        return _hash(self)


class AcceptedManualAnswer(Contract):
    schema_version: Literal[1] = 1
    scope: Literal["USER_ACCEPTED_MANUAL_ANSWER_NOT_LIVE_DELIVERY_PROOF"] = "USER_ACCEPTED_MANUAL_ANSWER_NOT_LIVE_DELIVERY_PROOF"
    candidate: ManualAnswerCandidate
    candidate_hash: Sha256
    trusted_user_action_id: Identifier
    actor: Text
    accepted_revision: Revision
    alignment: Literal["ALIGNED", "DIVERGED"]
    external_origin_verified: Literal[False] = False
    source: ContextSource

    @model_validator(mode="after")
    def exact_accepted_content(self) -> Self:
        c = self.candidate
        answer = Answer(answer_id=uuid5(c.candidate_id, "consilium/manual-answer/v1"),
            debate_id=c.round_spec.debate_id, round_id=c.round_spec.round_id, participant_id=c.participant_id,
            content=c.answer, provenance="MANUAL", used_prompt=c.actual_prompt, round_seen=c.round_seen,
            logical_operation_id=None)
        expected = ContextSource(item=answer, source_round=c.round_spec, source_revision=self.accepted_revision,
                                 provenance="MANUAL", data_class=c.data_class)
        if (self.candidate_hash != c.content_hash or self.alignment != c.alignment or self.source != expected
                or self.accepted_revision != c.staged_revision + 1):
            raise ValueError("Manual acceptance differs from the reviewed content")
        return self

    @property
    def content_hash(self) -> str:
        return _hash(self)


def accept_candidate(candidate: ManualAnswerCandidate, *, user_action_id, actor, accepted_revision):
    candidate = ManualAnswerCandidate.model_validate(candidate)
    answer = Answer(answer_id=uuid5(candidate.candidate_id, "consilium/manual-answer/v1"),
        debate_id=candidate.round_spec.debate_id, round_id=candidate.round_spec.round_id,
        participant_id=candidate.participant_id, content=candidate.answer, provenance="MANUAL",
        used_prompt=candidate.actual_prompt, round_seen=candidate.round_seen, logical_operation_id=None)
    return AcceptedManualAnswer(candidate=candidate, candidate_hash=candidate.content_hash,
        trusted_user_action_id=user_action_id, actor=actor, accepted_revision=accepted_revision,
        alignment=candidate.alignment, source=ContextSource(item=answer, source_round=candidate.round_spec,
            source_revision=accepted_revision, provenance="MANUAL", data_class=candidate.data_class))
