"""Text-only provider wire contracts. Pure codecs: no credentials or network I/O."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal

from consilium.core.contracts import FrozenInput

Provider = Literal["google", "qwen"]
MAX_BYTES = 1048576


class CodecError(ValueError):
    """Public errors contain fixed codes, never provider bodies or credentials."""


@dataclass(frozen=True)
class WireRequest:
    provider: Provider
    model: str
    body: bytes
    streaming: bool

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class ApiObservation:
    content: str | None
    state: Literal["COMPLETE", "PARTIAL", "NONE", "INVALID"]
    finish_reason: str | None
    response_id: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


def _json(raw: bytes):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise CodecError("BODY_SIZE_OR_TYPE")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CodecError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                CodecError("NONFINITE_JSON")
            ),
        )
    except (UnicodeError, ValueError, RecursionError):
        raise CodecError("INVALID_JSON") from None
    if type(value) is not dict:
        raise CodecError("OBJECT_REQUIRED")
    return value


def _count(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise CodecError("INVALID_USAGE")
    return value


def _identifier(value):
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", value):
        raise CodecError("INVALID_RESPONSE_ID")
    return value


def _reason(value):
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", value):
        raise CodecError("INVALID_FINISH_REASON")
    return value


def encode(
    provider: Provider, model: str, frozen: FrozenInput, *, streaming: bool = False
) -> WireRequest:
    if provider not in ("google", "qwen") or type(streaming) is not bool:
        raise CodecError("UNSUPPORTED_PROVIDER_OR_MODE")
    if type(model) is not str or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", model
    ):
        raise CodecError("MODEL_ID_REQUIRED")
    frozen = FrozenInput.model_validate(frozen)
    if provider == "qwen":
        body = {
            "model": model,
            "messages": [
                {"role": m.role.lower(), "content": m.content} for m in frozen.messages
            ],
            "stream": streaming,
            "n": 1,
        }
        params = frozen.parameters.model_dump(exclude_none=True)
        if "max_output_tokens" in params:
            params["max_tokens"] = params.pop("max_output_tokens")
        body.update(params)
        if streaming:
            body["stream_options"] = {"include_usage": True}
    else:
        if frozen.parameters.seed is not None:
            raise CodecError("GOOGLE_SEED_UNSUPPORTED")
        systems = [m.content for m in frozen.messages if m.role == "SYSTEM"]
        # Disallow interleaved system messages rather than silently reordering them.
        seen_non_system = False
        for message in frozen.messages:
            if message.role == "SYSTEM" and seen_non_system:
                raise CodecError("INTERLEAVED_SYSTEM_MESSAGE")
            seen_non_system |= message.role != "SYSTEM"
        contents = [
            {
                "role": "model" if m.role == "ASSISTANT" else "user",
                "parts": [{"text": m.content}],
            }
            for m in frozen.messages
            if m.role != "SYSTEM"
        ]
        if not contents:
            raise CodecError("USER_CONTENT_REQUIRED")
        body = {"contents": contents, "generationConfig": {}}
        if systems:
            body["systemInstruction"] = {"parts": [{"text": text} for text in systems]}
        if frozen.parameters.temperature is not None:
            body["generationConfig"]["temperature"] = frozen.parameters.temperature
        if frozen.parameters.max_output_tokens is not None:
            body["generationConfig"]["maxOutputTokens"] = (
                frozen.parameters.max_output_tokens
            )
    raw = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise CodecError("INPUT_TOO_LARGE")
    return WireRequest(provider, model, raw, streaming)


def _extract(provider, obj, *, stream=False):
    if "error" in obj:
        raise CodecError("ERROR_ENVELOPE")
    usage = obj.get("usageMetadata" if provider == "google" else "usage")
    if usage is None:
        usage = {}
    if type(usage) is not dict:
        raise CodecError("INVALID_USAGE")
    names = (
        ("promptTokenCount", "candidatesTokenCount", "totalTokenCount")
        if provider == "google"
        else ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    counts = tuple(_count(usage.get(n)) for n in names)
    remote = _identifier(obj.get("responseId" if provider == "google" else "id"))
    candidates = obj.get("candidates" if provider == "google" else "choices", [])
    if type(candidates) is not list or len(candidates) > 1:
        raise CodecError("ONE_CANDIDATE_REQUIRED")
    if not candidates:
        return "", None, remote, counts, False
    candidate = candidates[0]
    if (
        type(candidate) is not dict
        or type(candidate.get("index", 0)) is not int
        or candidate.get("index", 0) != 0
    ):
        raise CodecError("INVALID_CANDIDATE")
    finish = _reason(
        candidate.get("finishReason" if provider == "google" else "finish_reason")
    )
    if provider == "google":
        content = candidate.get("content", {})
        if type(content) is not dict or content.get("role", "model") != "model":
            raise CodecError("INVALID_CONTENT")
        parts = content.get("parts", [])
        if type(parts) is not list:
            raise CodecError("INVALID_PARTS")
        texts = []
        unsupported = False
        for part in parts:
            if type(part) is not dict:
                raise CodecError("INVALID_PART")
            if "thought" in part and type(part["thought"]) is not bool:
                raise CodecError("INVALID_THOUGHT_FLAG")
            if part.get("thought") is True:
                continue  # Thought text is never presented as the answer.
            if set(part) - {"text", "thought", "thoughtSignature"}:
                unsupported = True
            if "text" in part:
                if type(part["text"]) is not str:
                    raise CodecError("INVALID_TEXT")
                texts.append(part["text"])
        text = "".join(texts)
    else:
        content = candidate.get("delta" if stream else "message", {})
        if type(content) is not dict or content.get("role", "assistant") not in (
            (None, "assistant") if stream else ("assistant",)
        ):
            raise CodecError("INVALID_MESSAGE")
        text = content.get("content")
        if text is None:
            text = ""
        if type(text) is not str:
            raise CodecError("INVALID_TEXT")
        unsupported = bool(content.get("tool_calls") or content.get("function_call"))
    return text, finish, remote, counts, unsupported


def decode(provider: Provider, raw: bytes) -> ApiObservation:
    if provider not in ("google", "qwen"):
        raise CodecError("UNSUPPORTED_PROVIDER")
    text, finish, remote, usage, unsupported = _extract(provider, _json(raw))
    state = (
        "COMPLETE"
        if finish == ("STOP" if provider == "google" else "stop")
        and text.strip()
        and not unsupported
        else "PARTIAL"
        if text.strip() and not unsupported
        else "INVALID"
        if text.strip()
        else "NONE"
    )
    return ApiObservation(text if text.strip() else None, state, finish, remote, *usage)


class StreamDecoder:
    """Incremental bounded SSE; EOF is never a substitute for a finish marker."""

    def __init__(self, provider: Provider):
        if provider not in ("google", "qwen"):
            raise CodecError("UNSUPPORTED_PROVIDER")
        self.provider = provider
        self.buffer = b""
        self.size = 0
        self.text = ""
        self.remote = None
        self.finish = None
        self.usage = (None, None, None)
        self.unsupported = False
        self.broken = False
        self.done = False
        self.closed = False

    def feed(self, chunk: bytes) -> None:
        if self.closed or type(chunk) is not bytes:
            raise CodecError("STREAM_CLOSED_OR_TYPE")
        self.size += len(chunk)
        if self.size > MAX_BYTES:
            self.broken = True
            raise CodecError("STREAM_TOO_LARGE")
        self.buffer += chunk
        # Normalise only full CRLF pairs; a split CRLF remains buffered.
        self.buffer = self.buffer.replace(b"\r\n", b"\n")
        while b"\n\n" in self.buffer:
            event, self.buffer = self.buffer.split(b"\n\n", 1)
            data = b"\n".join(
                line[5:].lstrip(b" ")
                for line in event.split(b"\n")
                if line.startswith(b"data:")
            )
            if not data:
                continue
            if self.done:
                self.broken = True
                raise CodecError("EVENT_AFTER_DONE")
            if data == b"[DONE]":
                if self.provider != "qwen":
                    self.broken = True
                    raise CodecError("UNEXPECTED_DONE")
                self.done = True
                continue
            try:
                text, finish, remote, usage, unsupported = _extract(
                    self.provider, _json(data), stream=True
                )
                if (
                    remote is not None
                    and self.remote is not None
                    and remote != self.remote
                ):
                    raise CodecError("RESPONSE_ID_CHANGED")
                if self.finish is not None and (text or finish is not None):
                    raise CodecError("CONTENT_AFTER_FINISH")
                self.text += text
                self.remote = remote or self.remote
                self.finish = finish or self.finish
                self.usage = tuple(
                    new if new is not None else old
                    for old, new in zip(self.usage, usage)
                )
                self.unsupported |= unsupported
            except CodecError:
                self.broken = True
                raise

    def close(self, *, interrupted: bool = False) -> ApiObservation:
        if self.closed:
            raise CodecError("STREAM_ALREADY_CLOSED")
        self.closed = True
        valid_end = self.finish == ("STOP" if self.provider == "google" else "stop")
        if self.provider == "qwen":
            valid_end &= self.done
        complete = valid_end and not (
            interrupted or self.broken or self.buffer.strip() or self.unsupported
        )
        state = (
            "COMPLETE"
            if complete and self.text.strip()
            else "PARTIAL"
            if self.text.strip() and not self.unsupported
            else "INVALID"
            if self.text.strip()
            else "NONE"
        )
        return ApiObservation(
            self.text if self.text.strip() else None,
            state,
            self.finish,
            self.remote,
            *self.usage,
        )
