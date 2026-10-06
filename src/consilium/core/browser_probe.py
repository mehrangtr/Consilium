"""P03 probe observations, not a production browser driver or live certification."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from consilium.core.contracts import (
    AdapterRequest, Contract, Delivery, Failure, Identifier, OperationIdentity,
    ResponseState, Revision, Sha256, Text, TransportResult,
)


Evidence = Annotated[tuple[Sha256, ...], Field(min_length=1)]


class BrowserBinding(Contract):
    """Local opaque references mapped to observed identities outside public data."""
    connection_id: Identifier
    connection_revision: Revision
    account_binding_id: Identifier
    conversation_binding_id: Identifier
    model_id: Text

    @property
    def content_hash(self) -> str:
        data = json.dumps(self.model_dump(mode="json"), ensure_ascii=False,
                          sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(data).hexdigest()


class BrowserContext(Contract):
    authentication: Literal["SIGNED_OUT", "AUTHENTICATED", "EXPIRED", "UNKNOWN"]
    account_binding_id: Identifier | None = None
    conversation_binding_id: Identifier | None = None
    model_id: Text | None = None
    evidence: Evidence
    prior_authenticated_evidence: tuple[Sha256, ...] = ()

    @model_validator(mode="after")
    def positive_identity_and_expiration(self) -> Self:
        if self.authentication == "AUTHENTICATED" and any(value is None for value in (
                self.account_binding_id, self.conversation_binding_id, self.model_id)):
            raise ValueError("Authentication requires observed account, conversation and model")
        if self.authentication == "EXPIRED" and not self.prior_authenticated_evidence:
            raise ValueError("A sign-in page alone cannot prove session expiration")
        return self


class BrowserObservation(Contract):
    identity: OperationIdentity
    request_hash: Sha256
    context: BrowserContext
    send_action_attempted: bool
    user_message_ref: Identifier | None = None
    observed_prompt_hash: Sha256 | None = None
    assistant_message_ref: Identifier | None = None
    response_to_user_message_ref: Identifier | None = None
    response_state: Literal["NONE", "PARTIAL", "COMPLETE"] = "NONE"
    content: Text | None = None
    completion_evidence: tuple[Sha256, ...] = ()
    evidence: Evidence
    elapsed_seconds: Annotated[float, Field(ge=0.0, le=60.0)]

    @model_validator(mode="after")
    def correlated_messages(self) -> Self:
        if (self.user_message_ref is None) != (self.observed_prompt_hash is None):
            raise ValueError("Observed user message needs its exact prompt hash")
        response_fields = (self.assistant_message_ref, self.response_to_user_message_ref, self.content)
        if self.response_state == "NONE":
            if any(value is not None for value in response_fields) or self.completion_evidence:
                raise ValueError("No response cannot carry response data")
        elif (self.user_message_ref is None or any(value is None for value in response_fields)
              or self.response_to_user_message_ref != self.user_message_ref
              or self.assistant_message_ref == self.user_message_ref):
            raise ValueError("Response must refer to the observed user message")
        if (self.response_state == "COMPLETE") != bool(self.completion_evidence):
            raise ValueError("Only a complete response needs positive completion evidence")
        return self


class ProbeTicket(Contract):
    schema_version: Literal[1] = 1
    request: AdapterRequest
    binding: BrowserBinding
    initial_context: BrowserContext

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version_type(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Probe schema version must be an integer")
        return value

    @model_validator(mode="after")
    def exact_probe_scope(self) -> Self:
        request, binding = self.request, self.binding
        if (request.connection.mode != "BROWSER" or request.timeout_seconds > 60.0
                or len(request.intent.frozen_input.messages) != 1
                or request.intent.frozen_input.messages[0].role != "USER"):
            raise ValueError("P03 probe needs one user prompt and a browser budget at most 60 seconds")
        marker = "[consilium-probe:" + str(request.intent.identity.attempt_id) + "]"
        if marker not in request.intent.frozen_input.messages[0].content:
            raise ValueError("Probe prompt needs its unique attempt marker; old matching prompts are insufficient")
        if (request.connection.connection_id != binding.connection_id
                or request.intent.connection_revision != binding.connection_revision
                or request.connection.account_binding_id != binding.account_binding_id
                or request.connection.model_id != binding.model_id
                or request.transport_binding_hash != binding.content_hash):
            raise ValueError("Probe binding differs from the frozen request")
        if not context_matches(binding, self.initial_context):
            raise ValueError("Probe cannot start without an authenticated exact binding")
        return self


def context_matches(binding: BrowserBinding, context: BrowserContext) -> bool:
    return (context.authentication == "AUTHENTICATED"
            and context.account_binding_id == binding.account_binding_id
            and context.conversation_binding_id == binding.conversation_binding_id
            and context.model_id == binding.model_id)


def classify_observation(ticket: ProbeTicket, observation: BrowserObservation) -> TransportResult:
    """Dispatch has already begun; an absent action/DOM element never proves non-delivery."""
    ticket = ProbeTicket.model_validate(ticket.model_dump(mode="python"))
    observation = BrowserObservation.model_validate(observation.model_dump(mode="python"))
    request, binding = ticket.request, ticket.binding
    if (observation.identity != request.intent.identity
            or observation.request_hash != request.intent.request_hash):
        raise ValueError("Observation belongs to another frozen operation")
    if observation.elapsed_seconds > request.timeout_seconds:
        raise ValueError("Observation exceeds the frozen probe budget")
    prompt = request.intent.frozen_input.messages[0].content
    correlated = (context_matches(binding, observation.context)
                  and observation.user_message_ref is not None
                  and observation.observed_prompt_hash == hashlib.sha256(prompt.encode("utf-8")).hexdigest())
    evidence = tuple("p03-evidence-sha256:" + item for item in dict.fromkeys(
        observation.context.evidence + observation.context.prior_authenticated_evidence
        + observation.evidence + observation.completion_evidence))
    complete = correlated and observation.response_state == "COMPLETE"
    return TransportResult(
        identity=request.intent.identity, request_hash=request.intent.request_hash,
        connection_id=binding.connection_id, connection_revision=binding.connection_revision,
        delivery=Delivery.CONFIRMED if correlated else Delivery.UNKNOWN,
        response_state=ResponseState(observation.response_state) if correlated else ResponseState.NONE,
        content=observation.content if correlated else None,
        response_id=str(observation.assistant_message_ref) if correlated and observation.assistant_message_ref else None,
        failure=Failure.NONE if complete else Failure.SESSION_EXPIRED
            if observation.context.authentication == "EXPIRED" else Failure.TIMEOUT,
        evidence=evidence, elapsed_seconds=observation.elapsed_seconds,
    )
