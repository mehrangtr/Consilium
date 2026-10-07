"""Pure validation of trusted-shell attestations; no live measurement or send.

Schemas cannot establish that external attestations are true. Real transport
must obtain them from trusted observers/tokenizers/user actions, never from
provider text. Synthetic positive tests prove local rules, not live capability.
"""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field

from .contracts import ConnectionSpec, Contract, Identifier, Revision, Sha256
from .independent_context import IndependentContext
from .question_contracts import _hash


class PolicyBlocked(ValueError):
    """A fixed reason code; never contains private input content."""


def destination_hash(connection: ConnectionSpec) -> str:
    return _hash(ConnectionSpec.model_validate(connection))


class PolicyBinding(Contract):
    view_hash: Sha256
    request_hash: Sha256
    destination_hash: Sha256
    ledger_revision: Revision


class PrivacyDecision(PolicyBinding):
    decision: Literal["ALLOW", "BLOCK", "UNKNOWN"]
    contains_secret: bool | None
    trusted_user_action_id: Identifier


class TokenBudget(PolicyBinding):
    measurement: Literal["EXACT", "ESTIMATE", "UNKNOWN"]
    input_tokens: Annotated[int, Field(ge=1)] | None
    transport_overhead_tokens: Annotated[int, Field(ge=0)] | None
    reserved_output_tokens: Annotated[int, Field(ge=1)]
    context_capacity: Annotated[int, Field(ge=1)]


class HistoryEvidence(PolicyBinding):
    debate_id: Identifier
    state: Literal["FRESH_EMPTY", "VERIFIED_AUTHORIZED", "NO_REMOTE_HISTORY", "UNVERIFIED", "CONTAINS_PEERS"]
    conversation_id: Identifier | None
    new_topic: bool


class ContextAdmission(PolicyBinding):
    scope: Literal["LOCAL_ATTESTATION_VALIDATION_NOT_LIVE_VERIFICATION"] = "LOCAL_ATTESTATION_VALIDATION_NOT_LIVE_VERIFICATION"
    privacy_decision_hash: Sha256
    budget_hash: Sha256
    history_hash: Sha256


def evaluate_dispatch_policy(*, context: IndependentContext, connection: ConnectionSpec,
                             privacy: PrivacyDecision, budget: TokenBudget, history: HistoryEvidence,
                             expected_revision: int) -> ContextAdmission:
    context = IndependentContext.model_validate(context)
    connection = ConnectionSpec.model_validate(connection)
    privacy = PrivacyDecision.model_validate(privacy)
    budget = TokenBudget.model_validate(budget)
    history = HistoryEvidence.model_validate(history)
    if type(expected_revision) is not int or expected_revision < context.revision:
        raise PolicyBlocked("INVALID_LEDGER_REVISION")
    binding = dict(view_hash=context.content_hash, request_hash=context.frozen_input.content_hash,
                   destination_hash=destination_hash(connection), ledger_revision=expected_revision)
    for evidence in (privacy, budget, history):
        if any(getattr(evidence, key) != value for key, value in binding.items()):
            raise PolicyBlocked("STALE_OR_UNRELATED_POLICY_EVIDENCE")
    if privacy.decision != "ALLOW" or privacy.contains_secret is not False:
        raise PolicyBlocked("PRIVACY_NOT_CLEARED")
    if (budget.measurement != "EXACT" or budget.input_tokens is None
            or budget.transport_overhead_tokens is None):
        raise PolicyBlocked("BUDGET_NOT_MEASURED")
    if context.frozen_input.parameters.max_output_tokens != budget.reserved_output_tokens:
        raise PolicyBlocked("OUTPUT_RESERVE_NOT_FROZEN")
    if budget.input_tokens + budget.transport_overhead_tokens + budget.reserved_output_tokens > budget.context_capacity:
        raise PolicyBlocked("CONTEXT_BUDGET_EXCEEDED")
    if history.debate_id != context.debate_id or history.state in {"UNVERIFIED", "CONTAINS_PEERS"}:
        raise PolicyBlocked("REMOTE_HISTORY_NOT_AUTHORIZED")
    if connection.mode == "BROWSER" and connection.account_binding_id is None:
        raise PolicyBlocked("BROWSER_ACCOUNT_IDENTITY_MISSING")
    if connection.mode == "API" and history.state == "NO_REMOTE_HISTORY":
        if history.conversation_id is not None:
            raise PolicyBlocked("STATELESS_HISTORY_HAS_CONVERSATION")
    else:
        if history.conversation_id is None or history.state == "NO_REMOTE_HISTORY":
            raise PolicyBlocked("CONVERSATION_IDENTITY_MISSING")
        if history.new_topic and history.state != "FRESH_EMPTY":
            raise PolicyBlocked("NEW_TOPIC_REQUIRES_FRESH_CONVERSATION")
    return ContextAdmission(**binding, privacy_decision_hash=_hash(privacy),
                            budget_hash=_hash(budget), history_hash=_hash(history))
