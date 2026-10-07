"""Explicit local abandonment preserves prior transport facts; it proves no delivery."""
import hashlib
import json
from typing import Literal, Self

from pydantic import model_validator

from consilium.core.contracts import ConnectionSpec, Contract, Identifier, Revision, RoundSpec, Sha256, Text
from consilium.core.operation_states import AttemptRecord, AttemptState

ABANDONABLE = frozenset({AttemptState.PREPARED, AttemptState.SENT, AttemptState.UNKNOWN,
    AttemptState.RESPONSE_PENDING, AttemptState.PARTIAL_RESPONSE, AttemptState.INVALID_RESPONSE,
    AttemptState.NOT_SENT, AttemptState.WAITING_LOGIN})


class ManualReconciliationReview(Contract):
    round_spec: RoundSpec
    participant_id: Identifier
    expected_revision: Revision
    prior_connection: ConnectionSpec
    prior_connection_revision: Revision
    manual_connection: ConnectionSpec
    attempts: tuple[AttemptRecord, ...]

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (self.participant_id not in self.round_spec.participant_ids or not self.attempts
                or self.manual_connection.mode != "MANUAL"
                or self.manual_connection.connection_id == self.prior_connection.connection_id):
            raise ValueError("Manual continuation requires a new manual binding and existing attempts")
        identities = tuple(a.intent.identity.attempt_id for a in self.attempts)
        if len(identities) != len(set(identities)):
            raise ValueError("Every prior attempt must occur once")
        for attempt in self.attempts:
            intent = attempt.intent
            if (intent.debate_id != self.round_spec.debate_id or intent.round_id != self.round_spec.round_id
                    or intent.participant_id != self.participant_id or attempt.state not in ABANDONABLE):
                raise ValueError("Received, validated or confirmed responses must be handled before manual continuation")
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class ManualReconciliationRecord(Contract):
    review: ManualReconciliationReview
    review_hash: Sha256
    trusted_user_action_id: Identifier
    actor: Text
    reason: Text
    accepted_revision: Revision
    action: Literal["CONTINUE_MANUALLY_KEEP_PRIOR_DELIVERY"] = "CONTINUE_MANUALLY_KEEP_PRIOR_DELIVERY"
    prior_delivery_reverified: Literal[False] = False
    automatic_send: Literal[False] = False

    @model_validator(mode="after")
    def exact_acceptance(self) -> Self:
        if self.review_hash != self.review.content_hash or self.accepted_revision != self.review.expected_revision + 1:
            raise ValueError("Acceptance must bind the exact reviewed content and revision")
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
