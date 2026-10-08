"""Deterministic offline transport scenarios using virtual elapsed time."""
from __future__ import annotations

from enum import StrEnum
import math
from uuid import UUID

from consilium.core.contracts import (
    AdapterCapabilities, AdapterRequest, Delivery, DeliveryObservation, Failure,
    Mode, ResponseState, TransportResult,
)


class Scenario(StrEnum):
    SUCCESS = "success"
    DELAYED = "delayed"
    PARTIAL = "partial"
    TIMEOUT_BEFORE_SEND = "timeout_before_send"
    TIMEOUT_AFTER_SEND = "timeout_after_send"
    TIMEOUT_AFTER_DELIVERY = "timeout_after_delivery"
    INVALID_JSON = "invalid_json"
    SESSION_EXPIRED = "session_expired"
    QUOTA = "quota"
    SEND_REJECTED = "send_rejected"


class MockAdapter:
    def __init__(self, *, mode: Mode = "API", scenario: Scenario = Scenario.SUCCESS,
                 latency_seconds: float = 1.0, response_content: str | None = None):
        if mode not in {"API", "BROWSER"} or not isinstance(scenario, Scenario):
            raise ValueError("Mock mode or scenario is invalid")
        if isinstance(latency_seconds, bool) or not isinstance(latency_seconds, (int, float)) \
                or not math.isfinite(latency_seconds) or latency_seconds < 0:
            raise ValueError("Virtual latency must be finite and nonnegative")
        self._scenario = scenario
        if response_content is not None and (type(response_content) is not str or not response_content.strip()
                                            or len(response_content.encode('utf-8')) > 1048576):
            raise ValueError('Mock fixture output must be bounded nonblank text')
        self._response_content = response_content
        self._latency = float(latency_seconds)
        self._capabilities = AdapterCapabilities(mode=mode, verification="DECLARED_MOCK",
                                                delivery_probe=True, idempotency=False,
                                                continuation=False, streaming=False, structured_output=True)
        self._calls: list[AdapterRequest] = []
        self._results: dict[UUID, TransportResult] = {}
        self._requests: dict[UUID, AdapterRequest] = {}

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    @property
    def calls(self) -> tuple[AdapterRequest, ...]:
        return tuple(self._calls)

    def send(self, request: AdapterRequest) -> TransportResult:
        # In-memory duplicate protection tests the contract; durability starts at P02.
        if request.connection.mode != self.capabilities.mode:
            raise ValueError("Transport mode mismatch")
        attempt = request.intent.identity.attempt_id
        if attempt in self._results:
            raise ValueError("This attempt has already been invoked; do not silently resend")
        self._calls.append(request)
        delivery, state, failure = Delivery.CONFIRMED, ResponseState.COMPLETE, Failure.NONE
        content, elapsed = self._response_content or '{"answer":"offline mock response"}', 0.0
        remote_id = "mock-" + str(attempt)
        if self._scenario == Scenario.DELAYED:
            elapsed = min(self._latency, request.timeout_seconds)
            if self._latency > request.timeout_seconds:
                state, content, failure = ResponseState.NONE, None, Failure.TIMEOUT
        elif self._scenario == Scenario.PARTIAL:
            state, content, failure = ResponseState.PARTIAL, '{"answer":"unfinished', Failure.TIMEOUT
            elapsed = request.timeout_seconds
        elif self._scenario == Scenario.TIMEOUT_AFTER_SEND:
            delivery, state, content, failure = Delivery.UNKNOWN, ResponseState.NONE, None, Failure.TIMEOUT
            elapsed, remote_id = request.timeout_seconds, None
        elif self._scenario == Scenario.TIMEOUT_AFTER_DELIVERY:
            state, content, failure, elapsed = ResponseState.NONE, None, Failure.TIMEOUT, request.timeout_seconds
        elif self._scenario == Scenario.INVALID_JSON:
            state, content, failure = ResponseState.INVALID, '{"answer":broken', Failure.INVALID_RESPONSE
        elif self._scenario in {Scenario.TIMEOUT_BEFORE_SEND, Scenario.SESSION_EXPIRED, Scenario.QUOTA,
                                Scenario.SEND_REJECTED}:
            delivery, state, content, remote_id = Delivery.NOT_SENT, ResponseState.NONE, None, None
            failure = {Scenario.TIMEOUT_BEFORE_SEND: Failure.TIMEOUT,
                       Scenario.SESSION_EXPIRED: Failure.SESSION_EXPIRED,
                       Scenario.QUOTA: Failure.QUOTA,
                       Scenario.SEND_REJECTED: Failure.SEND_REJECTED}[self._scenario]
        result = TransportResult(identity=request.intent.identity, request_hash=request.intent.request_hash,
                                 connection_id=request.connection.connection_id,
                                 connection_revision=request.intent.connection_revision,
                                 delivery=delivery, response_state=state, content=content, failure=failure,
                                 response_id=remote_id, elapsed_seconds=elapsed,
                                 evidence=("MOCK_ONLY:" + self._scenario.value,))
        self._results[attempt] = result
        self._requests[attempt] = request
        return result

    def probe(self, request: AdapterRequest) -> DeliveryObservation:
        if request.connection.mode != self.capabilities.mode:
            raise ValueError("Transport mode mismatch")
        attempt = request.intent.identity.attempt_id
        recorded = self._requests.get(attempt)
        if recorded is not None and (recorded.intent != request.intent or recorded.connection != request.connection):
            raise ValueError("Recorded attempt does not belong to this frozen request and connection")
        result = self._results.get(attempt)
        delivery = result.delivery if result is not None else Delivery.UNKNOWN
        return DeliveryObservation(identity=request.intent.identity, request_hash=request.intent.request_hash,
                                   connection_id=request.connection.connection_id,
                                   connection_revision=request.intent.connection_revision, delivery=delivery,
                                   evidence=("MOCK_ONLY:recorded_attempt" if result else "MOCK_ONLY:no_observation",))
