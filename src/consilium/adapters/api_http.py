"""Single-attempt HTTPS transport with explicit runtime grants; no automatic retries.

This transport is not registered in the live council observation/provenance gate.
Tests inject HTTP frames; a runtime grant alone does not certify free access.
"""

from __future__ import annotations

import http.client
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

from consilium.adapters.api_codec import (
    MAX_BYTES,
    ApiObservation,
    CodecError,
    Provider,
    StreamDecoder,
    WireRequest,
    decode,
)


class AccessBlocked(ValueError):
    pass


@dataclass(frozen=True)
class HttpGrant:
    provider: Provider
    model: str
    account_binding_id: UUID
    user_action_id: UUID
    endpoint: str
    credential_env: str
    free_only_confirmed: bool = False
    enabled: bool = False

    def validate(self, wire: WireRequest) -> None:
        if (
            type(wire) is not WireRequest
            or type(wire.body) is not bytes
            or len(wire.body) > MAX_BYTES
            or type(wire.streaming) is not bool
            or type(wire.model) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", wire.model)
        ):
            raise AccessBlocked("INVALID_WIRE_REQUEST")
        if (
            type(self.enabled) is not bool
            or self.enabled is not True
            or type(self.free_only_confirmed) is not bool
            or self.free_only_confirmed is not True
            or type(self.account_binding_id) is not UUID
            or not self.account_binding_id.int
            or type(self.user_action_id) is not UUID
            or not self.user_action_id.int
            or (self.provider, self.model) != (wire.provider, wire.model)
        ):
            raise AccessBlocked("EXPLICIT_BOUND_FREE_ACCESS_REQUIRED")
        if self.credential_env != (
            "GEMINI_API_KEY" if self.provider == "google" else "DASHSCOPE_API_KEY"
        ):
            raise AccessBlocked("CREDENTIAL_SOURCE_MISMATCH")
        try:
            parts = urlsplit(self.endpoint)
            port = parts.port
        except (ValueError, TypeError):
            raise AccessBlocked("ENDPOINT_NOT_ALLOWED") from None
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.fragment
            or port not in (None, 443)
        ):
            raise AccessBlocked("ENDPOINT_NOT_ALLOWED")
        if self.provider == "google":
            method = "streamGenerateContent" if wire.streaming else "generateContent"
            if (
                parts.hostname != "generativelanguage.googleapis.com"
                or parts.path != f"/v1beta/models/{wire.model}:{method}"
                or parts.query != ("alt=sse" if wire.streaming else "")
            ):
                raise AccessBlocked("GOOGLE_ENDPOINT_MISMATCH")
        elif self.provider == "qwen":
            if (
                not parts.hostname
                or not re.fullmatch(
                    r"[a-z0-9-]+\.ap-southeast-1\.maas\.aliyuncs\.com", parts.hostname
                )
                or parts.path != "/compatible-mode/v1/chat/completions"
                or parts.query
            ):
                raise AccessBlocked("QWEN_SINGAPORE_ENDPOINT_REQUIRED")
        else:
            raise AccessBlocked("PROVIDER_NOT_ALLOWED")


@dataclass(frozen=True)
class HttpFrames:
    status: int
    chunks: tuple[bytes, ...]
    interrupted: bool = False


@dataclass(frozen=True)
class HttpOutcome:
    delivery: str
    code: str
    observation: ApiObservation | None = None
    # Auth is never stored; keep this result safe to log.


class Secret:
    def __init__(self, value: str):
        self._value = value

    def __repr__(self):
        return "<Secret REDACTED>"

    def reveal(self):
        return self._value


def https_once(
    endpoint: str, headers: dict[str, Secret | str], body: bytes, timeout: float
) -> HttpFrames:
    """No redirects, no retry, bounded response and per-socket remaining deadline.

    OS DNS resolution can exceed the socket timeout; caller must additionally
    run live dispatch under the owned-process supervisor for a hard deadline.
    """
    parts = urlsplit(endpoint)
    deadline = time.monotonic() + timeout
    connection = http.client.HTTPSConnection(parts.hostname, timeout=timeout)
    chunks = []
    status = 0
    interrupted = False

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError
        if connection.sock is not None:
            connection.sock.settimeout(value)

    try:
        connection.connect()
        remaining()
        actual = {
            k: v.reveal() if isinstance(v, Secret) else v for k, v in headers.items()
        }
        path = parts.path + ("?" + parts.query if parts.query else "")
        connection.request("POST", path, body=body, headers=actual)
        remaining()
        response = connection.getresponse()
        status = response.status
        size = 0
        while True:
            remaining()
            chunk = response.read1(min(65536, MAX_BYTES - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                interrupted = True
                break
            chunks.append(chunk)
    except (OSError, http.client.HTTPException):
        interrupted = True
    finally:
        connection.close()
    return HttpFrames(status, tuple(chunks), interrupted)


@dataclass
class ApiHttpTransport:
    grant: HttpGrant
    _http: Callable = field(default=https_once, repr=False)
    _attempts: set[UUID] = field(default_factory=set, init=False, repr=False)

    def send(
        self, wire: WireRequest, *, attempt_id: UUID, timeout_seconds: float
    ) -> HttpOutcome:
        import math

        self.grant.validate(wire)
        if (
            type(attempt_id) is not UUID
            or not attempt_id.int
            or attempt_id in self._attempts
            or type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 900
        ):
            raise AccessBlocked("INVALID_OR_REPEATED_ATTEMPT")
        value = os.environ.get(self.grant.credential_env)
        if not value or len(value) > 4096 or any(c.isspace() for c in value):
            raise AccessBlocked("CREDENTIAL_UNAVAILABLE")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if wire.streaming else "application/json",
        }
        auth = Secret(value if wire.provider == "google" else "Bearer " + value)
        headers["x-goog-api-key" if wire.provider == "google" else "Authorization"] = (
            auth
        )
        self._attempts.add(
            attempt_id
        )  # A thrown/ambiguous send is never retried by this transport.
        try:
            frames = self._http(
                self.grant.endpoint, headers, wire.body, float(timeout_seconds)
            )
        except Exception:  # noqa: BLE001 - do not expose a client exception containing auth headers.
            return HttpOutcome("UNKNOWN_DELIVERY", "TRANSPORT_INTERRUPTED")
        if (
            type(frames) is not HttpFrames
            or type(frames.status) is not int
            or type(frames.interrupted) is not bool
            or type(frames.chunks) is not tuple
            or any(type(c) is not bytes for c in frames.chunks)
            or sum(len(c) for c in frames.chunks) > MAX_BYTES
        ):
            return HttpOutcome("UNKNOWN_DELIVERY", "INVALID_HTTP_FRAMES")
        if frames.status != 200:
            code = (
                "AUTH_REQUIRED"
                if frames.status in (401, 403)
                else "QUOTA"
                if frames.status == 429
                else "HTTP_ERROR"
            )
            return HttpOutcome("UNKNOWN_DELIVERY", code)
        try:
            if wire.streaming:
                parser = StreamDecoder(wire.provider)
                try:
                    for chunk in frames.chunks:
                        parser.feed(chunk)
                except CodecError:
                    pass
                observation = parser.close(interrupted=frames.interrupted)
            elif frames.interrupted:
                observation = ApiObservation(None, "NONE", None, None)
            else:
                observation = decode(wire.provider, b"".join(frames.chunks))
            return HttpOutcome(
                "CONFIRMED_DELIVERY" if observation.content else "UNKNOWN_DELIVERY",
                "RESPONSE_" + observation.state,
                observation,
            )
        except CodecError:
            return HttpOutcome("UNKNOWN_DELIVERY", "MALFORMED_RESPONSE")
