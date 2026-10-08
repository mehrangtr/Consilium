"""Explicit private bindings; public schemas never hold credential material."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Mapping
from uuid import UUID


class PublicBoundaryError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class TransportSecret:
    _value: str = field(repr=False)

    def __repr__(self) -> str:
        return "TransportSecret([PRIVATE])"

    def reveal_for_transport(self) -> str:
        return self._value


class PrivateBindings:
    def __init__(self, *, environment: Mapping[str, str]):
        self._environment = environment

    def read_environment_secret(self, variable: str) -> TransportSecret:
        if not re.fullmatch(r"CONSILIUM_[A-Z0-9_]+", variable):
            raise ValueError("Credential must use a Consilium-specific environment reference")
        value = self._environment.get(variable)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Credential is missing")
        return TransportSecret(value)

    def profile_path(self, source_root: Path, private_root: Path, profile_id: UUID) -> Path:
        source, private = source_root.resolve(), private_root.resolve()
        if private.is_relative_to(source) or not isinstance(profile_id, UUID) or profile_id.int == 0:
            raise ValueError("Private browser profiles must be outside the source tree")
        path = (private / ("profile-" + str(profile_id))).resolve()
        if path.is_relative_to(source):
            raise ValueError("Resolved private profile must remain outside the source tree")
        return path  # No directory or password is created here.


_PRIVATE_FIELDS = {"api_key", "apikey", "access_token", "accesstoken", "refresh_token", "refreshtoken",
                   "password", "cookies", "cookie", "authorization", "credential", "credentials",
                   "profile_path", "session_token", "private_key"}
_PRIVATE_FIELD_TOKENS = {re.sub(r"[\s_-]+", "", name).casefold() for name in _PRIVATE_FIELDS}


def ensure_public_payload(payload: object, forbidden_values: tuple[str, ...]) -> None:
    """Reject private fields/known material. Not a detector of every unknown secret."""
    protected = tuple(x for x in forbidden_values if isinstance(x, str) and x)

    def walk(value: object) -> None:
        if isinstance(value, str):
            if any(secret in value for secret in protected):
                raise PublicBoundaryError("Private material cannot enter a public payload")
        elif isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or re.sub(r"[\s_-]+", "", key).casefold() in _PRIVATE_FIELD_TOKENS:
                    raise PublicBoundaryError("Private field cannot enter a public payload")
                walk(key)
                walk(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                walk(child)
        elif value is not None and type(value) not in (bool, int, float):
            raise PublicBoundaryError("Payload must contain public JSON data only")

    walk(payload)
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PublicBoundaryError("Payload must contain finite JSON data") from None


def redact_diagnostic(payload: object, forbidden_values: tuple[str, ...] = ()) -> object:
    """Copy diagnostics, redact known secrets and credential fields; never rewrite sources."""
    def clean(value):
        if isinstance(value, str):
            for secret in forbidden_values:
                if secret:
                    value = value.replace(secret, '[REDACTED]')
            return re.sub(r'(?i)\bBearer\s+[^\s,;]+', 'Bearer [REDACTED]', value)
        if isinstance(value, dict):
            return {str(k): '[REDACTED]' if re.sub(r'[\s_-]+', '', str(k)).casefold()
                    in _PRIVATE_FIELD_TOKENS else clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if value is None or type(value) in (bool, int, float):
            return value
        return '[UNSUPPORTED_DIAGNOSTIC]'
    return clean(payload)
