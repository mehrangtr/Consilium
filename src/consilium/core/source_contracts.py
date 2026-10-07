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


class CanonicalSourceBatch(Contract):
    """One confirmed typed mock response can publish several separate critiques."""
    schema_version: Literal[2] = 2
    scope: Literal["CONFIRMED_TYPED_MOCK_SOURCES_NOT_LIVE_OR_MANUAL"] = "CONFIRMED_TYPED_MOCK_SOURCES_NOT_LIVE_OR_MANUAL"
    logical_operation_id: Identifier
    attempt_id: Identifier
    request_hash: Sha256
    result_hash: Sha256
    response_contract_hash: Sha256
    validation_schema: Literal["P04SourceAnswer.v1", "P04SourceCritiques.v1"]
    confirmed_revision: Revision
    published_revision: Revision
    sources: tuple[ContextSource, ...]

    @model_validator(mode="after")
    def batch_matches(self) -> Self:
        if not self.sources or self.published_revision <= self.confirmed_revision:
            raise ValueError("Source batch requires sources and a committed confirmation")
        first = self.sources[0]
        for source in self.sources:
            if (source.provenance != "MOCK" or source.source_revision != self.confirmed_revision
                    or source.source_round != first.source_round
                    or isinstance(source.item, Answer) != (self.validation_schema == "P04SourceAnswer.v1")
                    or isinstance(source.item, Answer) and source.item.logical_operation_id != self.logical_operation_id):
                raise ValueError("Typed source batch has inconsistent identities or provenance")
        if self.validation_schema == "P04SourceAnswer.v1" and len(self.sources) != 1:
            raise ValueError("Answer schema publishes exactly one answer")
        if len({s.content_hash for s in self.sources}) != len(self.sources):
            raise ValueError("Source batch must not contain repeated sources")
        return self

    @property
    def content_hash(self) -> str:
        return _hash(self)
