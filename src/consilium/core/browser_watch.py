"""P09 offline browser observation reducer; no browser driver or live authority."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import Field, model_validator

from consilium.core.browser_probe import BrowserBinding, BrowserContext, context_matches
from consilium.core.contracts import Contract, Identifier, Sha256, Text


class PageMessage(Contract):
    message_id: Identifier
    role: Literal["USER", "ASSISTANT"]
    text: Text
    reply_to: Identifier | None = None
    complete: bool = False
    completion_evidence: tuple[Sha256, ...] = ()

    @model_validator(mode="after")
    def response_evidence(self):
        if self.role == "USER":
            if self.reply_to is not None or self.complete or self.completion_evidence:
                raise ValueError("USER_MESSAGE_HAS_RESPONSE_FIELDS")
        elif self.reply_to is None or self.reply_to == self.message_id:
            raise ValueError("ASSISTANT_REPLY_ID_REQUIRED")
        elif self.complete != bool(self.completion_evidence):
            raise ValueError("POSITIVE_COMPLETION_EVIDENCE_REQUIRED")
        return self


class PageSnapshot(Contract):
    sequence: Annotated[int, Field(ge=0)]
    context: BrowserContext
    messages: tuple[PageMessage, ...]
    full_history: bool
    evidence_hash: Sha256

    @model_validator(mode="after")
    def bounded_unique(self):
        if (
            len(self.messages) > 10000
            or len({m.message_id for m in self.messages}) != len(self.messages)
            or sum(len(m.text.encode()) for m in self.messages) > 1048576
        ):
            raise ValueError("PAGE_HISTORY_INVALID_OR_OVERSIZED")
        return self


class BrowserWatch:
    """Require an unchanged prior transcript and a newly correlated response.

    DOM/page text cannot enable dispatch. Snapshot producers are unregistered;
    evidence hashes here are synthetic declarations until a live driver exists.
    """

    def __init__(
        self, binding: BrowserBinding, baseline: PageSnapshot, prompt_hash: str
    ):
        self.binding = BrowserBinding.model_validate(binding)
        self.baseline = PageSnapshot.model_validate(baseline)
        if (
            not baseline.full_history
            or not context_matches(self.binding, baseline.context)
            or not isinstance(prompt_hash, str)
            or len(prompt_hash) != 64
            or any(c not in "0123456789abcdef" for c in prompt_hash)
        ):
            raise ValueError("BROWSER_BASELINE_NOT_VERIFIED")
        self.prompt_hash = prompt_hash
        self.sequence = baseline.sequence
        self.user_id = None
        self.assistant_id = None
        self.content = None
        self.state = "NONE"
        self.stopped = False
        self.failure = None

    def _stop(self, reason):
        self.stopped = True
        self.failure = reason
        # Keep already observed partial bytes; corruption cannot complete them.
        if self.content is not None:
            self.state = "PARTIAL"
        return self.state

    def observe(self, snapshot: PageSnapshot):
        if self.stopped:
            raise ValueError("BROWSER_WATCH_CLOSED_NO_RESEND")
        snapshot = PageSnapshot.model_validate(snapshot)
        if snapshot.sequence <= self.sequence:
            return self._stop("STALE_PAGE_OBSERVATION")
        self.sequence = snapshot.sequence
        if not snapshot.full_history or not context_matches(
            self.binding, snapshot.context
        ):
            return self._stop("BROWSER_BINDING_OR_HISTORY_LOST")
        old = self.baseline.messages
        if snapshot.messages[: len(old)] != old:
            return self._stop("PRIOR_TRANSCRIPT_CHANGED")
        fresh = snapshot.messages[len(old) :]
        if not fresh:
            if self.user_id is not None:
                return self._stop("CORRELATED_MESSAGE_DISAPPEARED")
            return self.state
        if len(fresh) > 2 or fresh[0].role != "USER":
            return self._stop("UNRELATED_OR_AMBIGUOUS_MESSAGES")
        user = fresh[0]
        if (
            hashlib.sha256(user.text.encode()).hexdigest() != self.prompt_hash
            or self.user_id is not None
            and self.user_id != user.message_id
        ):
            return self._stop("USER_MESSAGE_CORRELATION_CHANGED")
        self.user_id = user.message_id
        if len(fresh) == 1:
            if self.assistant_id is not None:
                return self._stop("CORRELATED_MESSAGE_DISAPPEARED")
            return self.state
        answer = fresh[1]
        if (
            answer.role != "ASSISTANT"
            or answer.reply_to != user.message_id
            or self.assistant_id is not None
            and self.assistant_id != answer.message_id
            or self.content is not None
            and not answer.text.startswith(self.content)
        ):
            return self._stop("ASSISTANT_MESSAGE_CORRELATION_CHANGED")
        self.assistant_id, self.content = answer.message_id, answer.text
        self.state = "COMPLETE" if answer.complete else "PARTIAL"
        self.stopped = answer.complete
        return self.state

    def interrupt(self):
        if self.stopped:
            return self.state
        return self._stop("OBSERVATION_INTERRUPTED_UNKNOWN_DELIVERY")
