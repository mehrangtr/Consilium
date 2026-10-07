"""Immutable local publication of the existing, confirmed P02 mock answer."""
from typing import Literal, Self
from pydantic import model_validator

from .contracts import Answer, Contract, Identifier, Revision, Sha256
from .question_contracts import _hash
from .round_context import ContextSource


class CanonicalAnswerSource(Contract):
    schema_version: Literal[1] = 1
    scope: Literal["P02_CONFIRMED_MOCK_ANSWER_NOT_LIVE_COUNCIL"] = "P02_CONFIRMED_MOCK_ANSWER_NOT_LIVE_COUNCIL"
    logical_operation_id: Identifier
    attempt_id: Identifier
    request_hash: Sha256
    result_hash: Sha256
    validation_schema: Literal["P02MockAnswer.v1"] = "P02MockAnswer.v1"
    confirmed_revision: Revision
    published_revision: Revision
    source: ContextSource

    @model_validator(mode="after")
    def confirmed_answer_matches(self) -> Self:
        if (not isinstance(self.source.item, Answer) or self.source.provenance != "MOCK"
                or self.source.item.logical_operation_id != self.logical_operation_id
                or self.source.source_revision != self.confirmed_revision
                or self.published_revision <= self.confirmed_revision):
            raise ValueError("Canonical answer source has inconsistent identity, revision or scope")
        return self

    @property
    def content_hash(self) -> str:
        return _hash(self)
