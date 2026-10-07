"""Pure architect contracts; adoption input must come from a trusted user shell.

Coverage is structural evidence, not proof that an optimized question preserves
meaning. No parser of provider text may manufacture a trusted user action.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .contracts import Contract, DebateSpec, Identifier, Revision, Sha256, Text


def _hash(value: Contract) -> str:
    payload = json.dumps(value.model_dump(mode="json"), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class QuestionSnapshot(Contract):
    debate_id: Identifier
    original_request_exact: Text
    constraints_exact: tuple[Text, ...]
    source_revision: Revision

    @classmethod
    def from_debate(cls, debate: DebateSpec) -> Self:
        validated = DebateSpec.model_validate(debate)
        return cls(debate_id=validated.debate_id, original_request_exact=validated.original_request,
                   constraints_exact=validated.constraints, source_revision=validated.revision)

    @property
    def content_hash(self) -> str:
        return _hash(self)


class ArchitectProposal(Contract):
    snapshot_hash: Sha256
    proposal_version: Annotated[int, Field(ge=1)]
    optimized_request: Text
    constraints_exact: tuple[Text, ...]
    constraint_coverage: tuple[Annotated[int, Field(ge=0)], ...]
    assumptions: tuple[Text, ...]
    visible_changes: tuple[Text, ...]
    origin: Literal["LIVE_GENERATED", "MANUAL", "MOCK"]

    @model_validator(mode="after")
    def full_ordered_coverage(self) -> Self:
        if self.constraint_coverage != tuple(range(len(self.constraints_exact))):
            raise ValueError("Every constraint needs exactly one ordered coverage entry")
        return self

    @property
    def content_hash(self) -> str:
        return _hash(self)


class PromptAdoption(Contract):
    proposal_hash: Sha256
    trusted_user_action_id: Identifier
    adopted_revision: Revision


class AdoptedQuestion(Contract):
    original: QuestionSnapshot
    proposal: ArchitectProposal
    adoption: PromptAdoption

    @model_validator(mode="after")
    def consistent_binding(self) -> Self:
        if self.proposal.snapshot_hash != self.original.content_hash:
            raise ValueError("Proposal belongs to a different question snapshot")
        if self.proposal.constraints_exact != self.original.constraints_exact:
            raise ValueError("Original constraints must be retained exactly")
        if self.adoption.proposal_hash != self.proposal.content_hash:
            raise ValueError("User action does not approve this proposal version")
        if self.adoption.adopted_revision != self.original.source_revision + 1:
            raise ValueError("Adoption must advance the captured revision exactly once")
        return self

    @property
    def effective_request(self) -> str:
        return self.proposal.optimized_request

    @property
    def constraints_exact(self) -> tuple[str, ...]:
        return self.original.constraints_exact


def adopt_proposal(snapshot: QuestionSnapshot, proposal: ArchitectProposal,
                   approval: PromptAdoption, *, expected_revision: int) -> AdoptedQuestion:
    snapshot = QuestionSnapshot.model_validate(snapshot)
    if type(expected_revision) is not int or snapshot.source_revision != expected_revision:
        raise ValueError("Stale question revision")
    return AdoptedQuestion(original=snapshot, proposal=proposal, adoption=approval)
