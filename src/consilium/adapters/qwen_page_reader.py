"""Strict reader for Qwen rendered captures; no browser actions or live authority.

The format is a local acquisition contract based on historical rendered captures.
A current site driver must separately establish that it produces this contract.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from consilium.core.browser_probe import BrowserContext
from consilium.core.browser_watch import PageMessage, PageSnapshot
from consilium.core.contracts import Contract, Identifier, Text

MAX_CAPTURE_BYTES = 2 * 1048576
PREFIX = "Thinking completed\n"


class QwenRenderedResponse(Contract):
    message_id: Identifier
    reply_to: Identifier
    raw_rendered_text: Text
    thinking_completed: bool
    stop_visible: bool
    response_actions: tuple[Literal["GOOD_RESPONSE", "BAD_RESPONSE", "REGENERATE"], ...]

    @model_validator(mode="after")
    def scoped_response(self):
        if self.message_id == self.reply_to or len(set(self.response_actions)) != len(
            self.response_actions
        ):
            raise ValueError("QWEN_RESPONSE_SCOPE_INVALID")
        if self.thinking_completed and not self.raw_rendered_text.startswith(PREFIX):
            raise ValueError("QWEN_COMPLETION_PREFIX_MISSING")
        return self


class QwenRenderedCapture(Contract):
    schema_version: Literal[1] = 1
    capture_kind: Literal["QWEN_RENDERED_TEXT_V1"]
    sequence: Annotated[int, Field(ge=0)]
    context: BrowserContext
    full_history: bool
    prior_messages: tuple[PageMessage, ...]
    submitted_user: PageMessage | None = None
    response: QwenRenderedResponse | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("QWEN_SCHEMA_VERSION_MUST_BE_INTEGER")
        return value

    @model_validator(mode="after")
    def correlated_response(self):
        if self.submitted_user is not None and self.submitted_user.role != "USER":
            raise ValueError("QWEN_SUBMITTED_MESSAGE_MUST_BE_USER")
        if self.response is not None and (
            self.submitted_user is None
            or self.response.reply_to != self.submitted_user.message_id
        ):
            raise ValueError("QWEN_RESPONSE_REPLY_MISMATCH")
        return self


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("QWEN_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read_qwen_capture(raw: bytes) -> PageSnapshot:
    """Hash the exact input bytes; derive only the documented UI prefix.

    Page text, copied action names and absence of Stop alone cannot complete a
    response. Explicit response-scoped controls are required, but remain local
    declarations until current acquisition provenance is verified separately.
    """
    if type(raw) is not bytes or not raw or len(raw) > MAX_CAPTURE_BYTES:
        raise ValueError("QWEN_CAPTURE_BYTES_INVALID_OR_OVERSIZED")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    capture = QwenRenderedCapture.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )
    evidence = hashlib.sha256(raw).hexdigest()
    messages = list(capture.prior_messages)
    if capture.submitted_user is not None:
        messages.append(capture.submitted_user)
    if capture.response is not None:
        response = capture.response
        text = response.raw_rendered_text
        if response.thinking_completed:
            text = text[len(PREFIX) :]
        complete = (
            response.thinking_completed
            and not response.stop_visible
            and set(response.response_actions)
            == {"GOOD_RESPONSE", "BAD_RESPONSE", "REGENERATE"}
        )
        messages.append(
            PageMessage(
                message_id=response.message_id,
                role="ASSISTANT",
                reply_to=response.reply_to,
                text=text,
                complete=complete,
                completion_evidence=(evidence,) if complete else (),
            )
        )
    return PageSnapshot(
        sequence=capture.sequence,
        context=capture.context,
        messages=tuple(messages),
        full_history=capture.full_history,
        evidence_hash=evidence,
    )
