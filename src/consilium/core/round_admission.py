"""Immutable later-round source/grant/policy receipt; no live send authority."""
from typing import Self
from pydantic import TypeAdapter, model_validator

from .admission_bundle import AdmissionBundle
from .contracts import ConnectionSpec, Contract, OperationIntent, Revision, Sha256, UserDecision
from .dispatch_policy import ContextAdmission, HistoryEvidence, PrivacyDecision, TokenBudget, evaluate_round_dispatch_policy
from .question_contracts import _hash
from .round_context import ContextSource, JudgeSelection, NamedReviewAuthorization, RoundContext, TransferGrant


class RoundAdmissionBundle(Contract):
    context: RoundContext
    connection: ConnectionSpec
    connection_revision: Revision
    sources: tuple[ContextSource, ...]
    required_source_hashes: tuple[Sha256, ...]
    grants: tuple[TransferGrant, ...]
    continuation_decision: UserDecision
    judge_selection: JudgeSelection | None = None
    named_authorization: NamedReviewAuthorization | None = None
    privacy: PrivacyDecision
    budget: TokenBudget
    history: HistoryEvidence
    admission: ContextAdmission

    @model_validator(mode="after")
    def checked_facts(self) -> Self:
        checked = evaluate_round_dispatch_policy(context=self.context, connection=self.connection,
            privacy=self.privacy, budget=self.budget, history=self.history,
            expected_revision=self.admission.ledger_revision)
        if self.admission != checked:
            raise ValueError("Round admission differs from policy facts")
        return self

    @property
    def content_hash(self) -> str:
        return _hash(self)

    def require_intent(self, intent: OperationIntent) -> None:
        intent = OperationIntent.model_validate(intent)
        if (intent.debate_id, intent.round_id, intent.participant_id, intent.frozen_input,
                intent.request_hash, intent.connection_id, intent.connection_revision, intent.expected_revision) != (
                self.context.debate_id, self.context.round_id, self.context.participant_id,
                self.context.frozen_input, self.admission.request_hash, self.connection.connection_id,
                self.connection_revision, self.context.ledger_revision):
            raise ValueError("Round admission does not belong to the prepared intent")


ADMISSION_ADAPTER = TypeAdapter(AdmissionBundle | RoundAdmissionBundle)
