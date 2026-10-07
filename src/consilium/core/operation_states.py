"""Pure P02 operation decisions; neither transport calls nor database access."""
from __future__ import annotations

from enum import StrEnum
import hashlib
import json
from types import MappingProxyType
from typing import Self

from pydantic import ValidationError, model_validator

from consilium.core.artifact_contracts import ArtifactResponseContract, parse_artifact_response

from consilium.core.contracts import (
    AdapterCapabilities, AdapterRequest, ConnectionSpec, Contract, Failure, OperationIntent, ResponseState, Delivery,
    Revision, Sha256, Text, TransportResult,
)


class AttemptState(StrEnum):
    PREPARED = "PREPARED"
    SENT = "SENT"  # Dispatch started durably; does not prove delivery.
    UNKNOWN = "UNKNOWN_DELIVERY"
    RESPONSE_PENDING = "RESPONSE_PENDING"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    PARTIAL_RESPONSE = "PARTIAL_RESPONSE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NOT_SENT = "NOT_SENT"
    WAITING_LOGIN = "WAITING_LOGIN"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"


class ResumeAction(StrEnum):
    READY_TO_SEND = "READY_TO_SEND"
    VERIFY_DELIVERY = "VERIFY_DELIVERY"
    WAIT_FOR_RESPONSE = "WAIT_FOR_RESPONSE"
    WAIT_FOR_LOGIN = "WAIT_FOR_LOGIN"
    WAIT_FOR_DECISION = "WAIT_FOR_DECISION"
    VALIDATE_STORED_RESPONSE = "VALIDATE_STORED_RESPONSE"
    CONFIRM_STORED_RESPONSE = "CONFIRM_STORED_RESPONSE"
    USE_CONFIRMED_RESULT = "USE_CONFIRMED_RESULT"


_OUTCOMES = {"RESULT_" + state.value: state for state in (
    AttemptState.UNKNOWN, AttemptState.RESPONSE_PENDING, AttemptState.RESPONSE_RECEIVED,
    AttemptState.PARTIAL_RESPONSE, AttemptState.INVALID_RESPONSE, AttemptState.NOT_SENT, AttemptState.WAITING_LOGIN)}
# An explicit immutable transition table; protected runtime code, not model output.
TRANSITIONS = MappingProxyType({
    AttemptState.PREPARED: MappingProxyType({"SEND": AttemptState.SENT}),
    AttemptState.SENT: MappingProxyType(_OUTCOMES | {"INTERRUPTED": AttemptState.UNKNOWN}),
    AttemptState.RESPONSE_RECEIVED: MappingProxyType({"VALIDATE_OK": AttemptState.VALIDATED,
                                                     "VALIDATE_INVALID": AttemptState.INVALID_RESPONSE}),
    AttemptState.VALIDATED: MappingProxyType({"CONFIRM": AttemptState.CONFIRMED}),
})


def transition(state: AttemptState, event: str) -> AttemptState:
    if not isinstance(state, AttemptState) or type(event) is not str:
        raise ValueError("A typed state and explicit event are required")
    try:
        return TRANSITIONS[state][event]
    except KeyError:
        raise ValueError("Illegal operation transition") from None


def result_state(result: TransportResult) -> AttemptState:
    if result.delivery == Delivery.UNKNOWN:
        return AttemptState.UNKNOWN
    if result.delivery == Delivery.NOT_SENT:
        return AttemptState.WAITING_LOGIN if result.failure == Failure.SESSION_EXPIRED else AttemptState.NOT_SENT
    return {ResponseState.NONE: AttemptState.RESPONSE_PENDING,
            ResponseState.COMPLETE: AttemptState.RESPONSE_RECEIVED,
            ResponseState.PARTIAL: AttemptState.PARTIAL_RESPONSE,
            ResponseState.INVALID: AttemptState.INVALID_RESPONSE}[result.response_state]


class ResponseValidation(Contract):
    schema_id: Text
    content_hash: Sha256
    valid: bool
    issues: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def issues_match_validity(self) -> Self:
        if self.valid == bool(self.issues):
            raise ValueError("Invalid output needs issues; valid output cannot carry issues")
        return self


class CapabilityBinding(Contract):
    """Trusted capability verification is scoped to the exact local binding."""
    connection: ConnectionSpec
    connection_revision: Revision
    capabilities: AdapterCapabilities

    @model_validator(mode="after")
    def mode_matches_binding(self) -> Self:
        if self.connection.mode != self.capabilities.mode:
            raise ValueError("Capabilities belong to another transport mode")
        return self


class MockAnswer(Contract):
    answer: Text


def validate_p02_response(content: str) -> ResponseValidation:
    """This small schema proves the P02 path; Council schemas belong to P05."""
    def unique_keys(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError("Duplicate JSON key")
            data[key] = value
        return data
    try:
        data = json.loads(content, object_pairs_hook=unique_keys)
        MockAnswer.model_validate(data)
        issues = ()
    except (ValueError, TypeError, RecursionError, ValidationError):
        # Do not copy untrusted/private input into diagnostic messages.
        issues = ("INVALID_P02_ANSWER_SCHEMA",)
    return ResponseValidation(schema_id="P02MockAnswer.v1", content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                              valid=not issues, issues=issues)


def validate_operation_response(content: str, contract: ArtifactResponseContract | None) -> ResponseValidation:
    if contract is None:
        return validate_p02_response(content)
    try:
        parse_artifact_response(content, contract)
        issues = ()
    except ValueError:
        issues = ("INVALID_P04_SOURCE_OUTPUT",)
    return ResponseValidation(schema_id=contract.validation_schema,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(), valid=not issues, issues=issues)


class AttemptRecord(Contract):
    intent: OperationIntent
    state: AttemptState
    active_revision: Revision
    request: AdapterRequest | None = None
    result: TransportResult | None = None
    validation: ResponseValidation | None = None
    response_contract: ArtifactResponseContract | None = None

    @model_validator(mode="after")
    def consistent_record(self) -> Self:
        if self.response_contract is not None:
            self.response_contract.require_intent(self.intent)
        if self.active_revision <= self.intent.expected_revision:
            raise ValueError("Attempt must refer to its committed revision")
        if self.state == AttemptState.PREPARED:
            if self.request is not None or self.result is not None or self.validation is not None:
                raise ValueError("Prepared attempt cannot contain a dispatch or result")
        elif self.request is None or self.request.intent != self.intent:
            raise ValueError("Dispatched attempt needs its exact frozen request")
        if self.result is not None:
            if (self.result.identity != self.intent.identity or self.result.request_hash != self.intent.request_hash
                    or self.result.connection_id != self.intent.connection_id
                    or self.result.connection_revision != self.intent.connection_revision):
                raise ValueError("Result belongs to a different attempt")
        if self.state in {AttemptState.SENT, AttemptState.PREPARED} and self.result is not None:
            raise ValueError("Result must have its classified state")
        if self.state not in {AttemptState.PREPARED, AttemptState.SENT, AttemptState.UNKNOWN} and self.result is None:
            raise ValueError("This state requires a durable transport result")
        if self.validation is not None:
            if self.result is None or self.result.response_state != ResponseState.COMPLETE or self.result.content is None:
                raise ValueError("Validation requires a complete stored response")
            if self.validation != validate_operation_response(self.result.content, self.response_contract):
                raise ValueError("Validation does not match the stored response")
        if self.state in {AttemptState.VALIDATED, AttemptState.CONFIRMED}:
            if self.validation is None or not self.validation.valid:
                raise ValueError("Confirmation requires valid stored validation")
        elif self.validation is not None and (self.state != AttemptState.INVALID_RESPONSE or self.validation.valid):
            raise ValueError("Invalid validation cannot appear as success")
        if self.result is not None and self.validation is None and self.state != result_state(self.result):
            raise ValueError("State contradicts the transport result")
        return self


class ResumePlan(Contract):
    attempt: AttemptRecord
    action: ResumeAction
    reason: Text
    automatic_send: bool = False

    @model_validator(mode="after")
    def no_implicit_send(self) -> Self:
        if self.automatic_send:
            raise ValueError("Resume classification cannot authorize an external call")
        return self


def resume_action(state: AttemptState) -> ResumeAction:
    return {AttemptState.PREPARED: ResumeAction.READY_TO_SEND,
            AttemptState.SENT: ResumeAction.VERIFY_DELIVERY,
            AttemptState.UNKNOWN: ResumeAction.VERIFY_DELIVERY,
            AttemptState.RESPONSE_PENDING: ResumeAction.WAIT_FOR_RESPONSE,
            AttemptState.WAITING_LOGIN: ResumeAction.WAIT_FOR_LOGIN,
            AttemptState.RESPONSE_RECEIVED: ResumeAction.VALIDATE_STORED_RESPONSE,
            AttemptState.VALIDATED: ResumeAction.CONFIRM_STORED_RESPONSE,
            AttemptState.CONFIRMED: ResumeAction.USE_CONFIRMED_RESULT,
            AttemptState.NOT_SENT: ResumeAction.WAIT_FOR_DECISION,
            AttemptState.PARTIAL_RESPONSE: ResumeAction.WAIT_FOR_DECISION,
            AttemptState.INVALID_RESPONSE: ResumeAction.WAIT_FOR_DECISION}[state]
