"""Versioned output contracts fixed locally before an offline mock operation.

Schema validity is not live provenance, delivery proof or send authorization.
The provider supplies text and scores, never local identities or authority.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from .contracts import Contract, Identifier, OperationIntent, PeerPoint, RoundSpec, Sha256, Text
from .question_contracts import _hash


class ReviewTarget(Contract):
    alias: Annotated[str, Field(pattern=r"^[A-Z]{1,12}$")]
    logical_operation_id: Identifier
    answer_id: Identifier
    source_hash: Sha256


class ArtifactResponseContract(Contract):
    schema_version: Literal[1] = 1
    scope: Literal["OFFLINE_MOCK_SOURCE_VALIDATION_NOT_LIVE_AUTHORITY"] = "OFFLINE_MOCK_SOURCE_VALIDATION_NOT_LIVE_AUTHORITY"
    logical_operation_id: Identifier
    round_spec: RoundSpec
    participant_id: Identifier
    request_hash: Sha256
    kind: Literal["ANSWER", "CRITIQUES"]
    targets: tuple[ReviewTarget, ...] = ()
    rubric_version: Text | None = None
    max_response_bytes: Annotated[int, Field(ge=1, le=1048576)] = 262144

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("Output contract version must be an integer")
        return value

    @model_validator(mode="after")
    def role_matches_schema(self) -> Self:
        if self.participant_id not in self.round_spec.participant_ids:
            raise ValueError("Output contract participant is outside its round")
        if (self.kind == "CRITIQUES") != (self.round_spec.kind == "REVIEW"):
            raise ValueError("Output kind must match the registered round role")
        if self.kind == "CRITIQUES":
            if not self.targets or self.rubric_version is None:
                raise ValueError("Review requires explicit targets and a local rubric")
            for field in ("alias", "answer_id", "source_hash", "logical_operation_id"):
                values = [getattr(t, field) for t in self.targets]
                if len(values) != len(set(values)):
                    raise ValueError("Review targets must be unambiguous and unique")
        elif self.targets or self.rubric_version is not None:
            raise ValueError("Answer output cannot carry review targets or a rubric")
        return self

    def require_intent(self, intent: OperationIntent) -> None:
        if (intent.identity.logical_operation_id != self.logical_operation_id
                or intent.debate_id != self.round_spec.debate_id or intent.round_id != self.round_spec.round_id
                or intent.participant_id != self.participant_id or intent.request_hash != self.request_hash):
            raise ValueError("Output contract does not belong to this frozen operation")

    @property
    def content_hash(self) -> str:
        return _hash(self)

    @property
    def validation_schema(self) -> str:
        return "P04SourceAnswer.v1" if self.kind == "ANSWER" else "P04SourceCritiques.v1"


class VersionedOutput(Contract):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("Response version must be an integer")
        return value


class AnswerOutput(VersionedOutput):
    answer: Text


class CritiqueOutput(Contract):
    target_alias: Annotated[str, Field(pattern=r"^[A-Z]{1,12}$")]
    points: Annotated[tuple[PeerPoint, ...], Field(min_length=1)]
    score: Annotated[int, Field(ge=1, le=10)]
    scoring_reason: Text
    strengths: tuple[Text, ...] = ()
    weaknesses: tuple[Text, ...] = ()


class CritiquesOutput(VersionedOutput):
    critiques: Annotated[tuple[CritiqueOutput, ...], Field(min_length=1)]


def parse_artifact_response(content: str, contract: ArtifactResponseContract) -> AnswerOutput | CritiquesOutput:
    """Strict wire JSON; exact target coverage, without leaking rejected text."""
    contract = ArtifactResponseContract.model_validate(contract)
    try:
        if type(content) is not str or len(content.encode("utf-8")) > contract.max_response_bytes:
            raise ValueError("Response exceeds its frozen byte budget")

        def unique_keys(pairs):
            data = {}
            for key, value in pairs:
                if key in data:
                    raise ValueError("Duplicate response key")
                data[key] = value
            return data

        def reject_constant(value):
            raise ValueError("Non-finite JSON constant")

        data = json.loads(content, object_pairs_hook=unique_keys, parse_constant=reject_constant)
        # Validate in JSON mode so JSON arrays become immutable tuples, while
        # scalar coercions (string scores, boolean versions) remain forbidden.
        clean = json.dumps(data, ensure_ascii=False, allow_nan=False)
        if contract.kind == "ANSWER":
            return AnswerOutput.model_validate_json(clean)
        output = CritiquesOutput.model_validate_json(clean)
        actual = [x.target_alias for x in output.critiques]
        if len(actual) != len(set(actual)) or set(actual) != {x.alias for x in contract.targets}:
            raise ValueError("Critiques must cover each frozen target exactly once")
        return output
    except (ValueError, TypeError, RecursionError, UnicodeError, ValidationError):
        raise ValueError("INVALID_P04_SOURCE_OUTPUT") from None
