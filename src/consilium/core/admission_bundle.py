"""Immutable local policy facts, not a live transport authorization."""
from typing import Self
from pydantic import model_validator

from .contracts import ConnectionSpec, Contract, OperationIntent, Revision
from .dispatch_policy import ContextAdmission, HistoryEvidence, PrivacyDecision, TokenBudget, evaluate_dispatch_policy
from .independent_context import IndependentContext
from .question_contracts import _hash


class AdmissionBundle(Contract):
    context: IndependentContext
    connection: ConnectionSpec
    connection_revision: Revision
    privacy: PrivacyDecision
    budget: TokenBudget
    history: HistoryEvidence
    admission: ContextAdmission

    @model_validator(mode="after")
    def checked_facts(self) -> Self:
        checked = evaluate_dispatch_policy(context=self.context, connection=self.connection,
            privacy=self.privacy, budget=self.budget, history=self.history,
            expected_revision=self.admission.ledger_revision)
        if self.admission != checked:
            raise ValueError("Admission differs from its policy facts")
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
                self.connection_revision, self.admission.ledger_revision):
            raise ValueError("Admission bundle does not belong to the prepared intent")
