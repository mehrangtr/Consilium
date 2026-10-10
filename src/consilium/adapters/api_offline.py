"""P08 synthetic HTTP-envelope driver. It cannot open sockets or accept API keys."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from consilium.adapters.api_codec import (
    MAX_BYTES,
    ApiObservation,
    CodecError,
    Provider,
    StreamDecoder,
    decode,
    encode,
)
from consilium.core.contracts import (
    AdapterCapabilities,
    AdapterRequest,
    Delivery,
    DeliveryObservation,
    Failure,
    ResponseState,
    TransportResult,
)


@dataclass(frozen=True)
class ApiFixture:
    status: int = 200
    chunks: tuple[bytes, ...] = ()
    streaming: bool = False
    interrupted: bool = False
    elapsed_seconds: float = 0.0

    def __post_init__(self):
        import math

        if (
            type(self.status) is not int
            or not 100 <= self.status <= 599
            or type(self.chunks) is not tuple
            or any(type(c) is not bytes for c in self.chunks)
            or sum(len(c) for c in self.chunks) > MAX_BYTES
            or type(self.streaming) is not bool
            or type(self.interrupted) is not bool
            or type(self.elapsed_seconds) not in (int, float)
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError("INVALID_OFFLINE_FIXTURE")


class OfflineApiAdapter:
    """Codec integration test driver, bound exclusively to the existing mock gate.

    The provider chooses a wire codec, NOT a destination or live account.
    A fresh instance cannot bypass the durable ledger's duplicate-send check.
    """

    def __init__(self, provider: Provider, model: str, fixture: ApiFixture):
        if type(fixture) is not ApiFixture:
            raise ValueError("EXACT_FIXTURE_REQUIRED")
        if provider not in ("google", "qwen"):
            raise ValueError("UNSUPPORTED_PROVIDER")
        self.provider, self.model, self.fixture = provider, model, fixture
        self._calls: list[UUID] = []
        self._results: dict[UUID, TransportResult] = {}
        self._requests: dict[UUID, AdapterRequest] = {}
        self.observations: dict[UUID, ApiObservation] = {}
        self.wire_hashes: dict[UUID, str] = {}

    @property
    def capabilities(self):
        return AdapterCapabilities(
            mode="API",
            verification="DECLARED_MOCK",
            streaming=True,
            verification_evidence=("P08_SYNTHETIC_CODEC_NOT_LIVE",),
        )

    @property
    def calls(self):
        return tuple(self._calls)

    def _bound(self, request):
        if (
            request.connection.mode != "API"
            or request.connection.provider_id != "mock"
            or request.connection.model_id != "mock-v1"
        ):
            raise ValueError("OFFLINE_MOCK_BINDING_REQUIRED")
        recorded = self._requests.get(request.intent.identity.attempt_id)
        if recorded is not None and recorded != request:
            raise ValueError("ATTEMPT_BINDING_CHANGED")

    def send(self, request: AdapterRequest) -> TransportResult:
        wire = self.preflight(request)
        attempt = request.intent.identity.attempt_id
        self.wire_hashes[attempt] = wire.sha256
        self._requests[attempt] = request
        self._calls.append(attempt)
        delivery, state, content, failure, remote = (
            Delivery.UNKNOWN,
            ResponseState.NONE,
            None,
            Failure.TIMEOUT,
            None,
        )
        code = "INTERRUPTED_AFTER_SEND"
        elapsed = min(float(self.fixture.elapsed_seconds), request.timeout_seconds)
        observation = None
        if self.fixture.status != 200:
            # An error response is NOT evidence that the inference was never run.
            code = "HTTP_" + str(self.fixture.status)
            failure = (
                Failure.SESSION_EXPIRED
                if self.fixture.status in (401, 403)
                else Failure.QUOTA
                if self.fixture.status == 429
                else Failure.SEND_REJECTED
            )
        else:
            try:
                if self.fixture.streaming:
                    parser = StreamDecoder(self.provider)
                    try:
                        for chunk in self.fixture.chunks:
                            parser.feed(chunk)
                    except CodecError:
                        pass  # Keep any safely accumulated text, but never mark complete.
                    observation = parser.close(
                        interrupted=self.fixture.interrupted
                        or self.fixture.elapsed_seconds > request.timeout_seconds
                    )
                elif (
                    self.fixture.interrupted
                    or self.fixture.elapsed_seconds > request.timeout_seconds
                ):
                    observation = ApiObservation(None, "NONE", None, None)
                else:
                    observation = decode(self.provider, b"".join(self.fixture.chunks))
                self.observations[attempt] = observation
                content, remote = observation.content, observation.response_id
                state = ResponseState(observation.state)
                if content is not None:
                    delivery = Delivery.CONFIRMED
                failure = (
                    Failure.INVALID_RESPONSE
                    if state == ResponseState.INVALID
                    else Failure.TIMEOUT
                    if state == ResponseState.NONE
                    or self.fixture.interrupted
                    or self.fixture.elapsed_seconds > request.timeout_seconds
                    else Failure.NONE
                )
                code = "DECODED_" + observation.state
            except CodecError:
                code, failure = "MALFORMED_ENVELOPE", Failure.SEND_REJECTED
        metadata = (
            ()
            if observation is None
            else (
                "API_METADATA:"
                + json.dumps(
                    {
                        "finish_reason": observation.finish_reason,
                        "input_tokens": observation.input_tokens,
                        "output_tokens": observation.output_tokens,
                        "total_tokens": observation.total_tokens,
                    },
                    sort_keys=True,
                ),
            )
        )
        result = TransportResult(
            identity=request.intent.identity,
            request_hash=request.intent.request_hash,
            connection_id=request.connection.connection_id,
            connection_revision=request.intent.connection_revision,
            delivery=delivery,
            response_state=state,
            content=content,
            failure=failure,
            response_id=remote,
            elapsed_seconds=elapsed,
            evidence=(
                "P08_OFFLINE_ONLY:" + self.provider,
                code,
                "WIRE_SHA256:" + wire.sha256,
            )
            + metadata,
        )
        self._results[attempt] = result
        return result

    def preflight(self, request: AdapterRequest):
        """Pure validation must precede a durable SEND_STARTED boundary."""
        self._bound(request)
        attempt = request.intent.identity.attempt_id
        if attempt in self._requests:
            raise ValueError("DUPLICATE_ATTEMPT_NO_RESEND")
        return encode(
            self.provider,
            self.model,
            request.intent.frozen_input,
            streaming=self.fixture.streaming,
        )

    def probe(self, request: AdapterRequest) -> DeliveryObservation:
        self._bound(request)
        result = self._results.get(request.intent.identity.attempt_id)
        return DeliveryObservation(
            identity=request.intent.identity,
            request_hash=request.intent.request_hash,
            connection_id=request.connection.connection_id,
            connection_revision=request.intent.connection_revision,
            delivery=result.delivery if result else Delivery.UNKNOWN,
            evidence=("P08_OFFLINE_ONLY:NO_LIVE_PROBE",),
        )
