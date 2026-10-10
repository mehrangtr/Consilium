"""Pure bound API preparation. Declared profiles never grant live admission."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from pydantic import Field

from consilium.adapters.api_codec import WireRequest, encode
from consilium.adapters.api_http import AccessBlocked, HttpGrant
from consilium.core.contracts import AdapterRequest, Contract, Sha256, Text


class ApiProfile(Contract):
    provider: Text
    model: Text
    endpoint: Text
    revision: int = Field(ge=0)
    context_capacity: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    streaming: bool
    tokenizer_id: Text
    implementation_hash: Sha256

    @property
    def content_hash(self):
        raw = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ApiPlan:
    request_hash: str
    destination_hash: str
    profile_hash: str
    wire: WireRequest
    input_tokens: int
    reserved_output_tokens: int
    live_admitted: bool = False
    scope: str = "DECLARED_OFFLINE_PLAN_NOT_LIVE_ADMISSION"


def prepare_api(
    request: AdapterRequest,
    grant: HttpGrant,
    profile: ApiProfile,
    *,
    input_tokens: int,
    streaming: bool = False,
) -> ApiPlan:
    """Validate all local bindings without inspecting credentials or dispatching.

    input_tokens and profile are declarations. The registered live observer
    must independently measure/certify them before any product send is enabled.
    """
    from consilium.core.dispatch_policy import destination_hash

    request = AdapterRequest.model_validate(request)
    profile = ApiProfile.model_validate(profile)
    connection = request.connection
    if (
        type(grant) is not HttpGrant
        or connection.mode != "API"
        or connection.account_binding_id != grant.account_binding_id
        or (connection.provider_id, connection.model_id)
        != (grant.provider, grant.model)
        or (profile.provider, profile.model, profile.endpoint)
        != (grant.provider, grant.model, grant.endpoint)
        or request.transport_binding_hash != profile.content_hash
    ):
        raise AccessBlocked("API_PLAN_BINDING_MISMATCH")
    if type(streaming) is not bool or streaming and not profile.streaming:
        raise AccessBlocked("STREAMING_NOT_DECLARED")
    output = request.intent.frozen_input.parameters.max_output_tokens
    if (
        type(input_tokens) is not int
        or input_tokens < 1
        or output is None
        or output > profile.max_output_tokens
        or input_tokens + output > profile.context_capacity
    ):
        raise AccessBlocked("API_PLAN_CAPACITY_EXCEEDED_OR_UNKNOWN")
    wire = encode(
        grant.provider, grant.model, request.intent.frozen_input, streaming=streaming
    )
    # Endpoint validation only; replacement must never become an executable grant.
    replace(grant, enabled=True, free_only_confirmed=True).validate(wire)
    return ApiPlan(
        request.intent.request_hash,
        destination_hash(connection),
        profile.content_hash,
        wire,
        input_tokens,
        output,
    )


def verify_plan(
    plan: ApiPlan, request: AdapterRequest, grant: HttpGrant, profile: ApiProfile
) -> None:
    """Reconstruct exact bytes; copied/mutated plans cannot change the input."""
    if type(plan) is not ApiPlan:
        raise AccessBlocked("EXACT_API_PLAN_REQUIRED")
    expected = prepare_api(
        request,
        grant,
        profile,
        input_tokens=plan.input_tokens,
        streaming=plan.wire.streaming,
    )
    if plan != expected:
        raise AccessBlocked("API_PLAN_CHANGED")
