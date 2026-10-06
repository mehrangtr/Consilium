#!/usr/bin/env python3
"""Portable offline foundation demo; not yet a Council or durable runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from consilium.adapters.mock import MockAdapter, Scenario
from consilium.core.contracts import AdapterRequest, ConnectionSpec, FrozenInput, Message, OperationIdentity, OperationIntent, ResponseState
from consilium.shell.private import ensure_public_payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="Consilium P01 offline foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    mock = commands.add_parser("mock")
    mock.add_argument("--question", required=True)
    mock.add_argument("--mode", choices=("API", "BROWSER"), default="API")
    mock.add_argument("--scenario", choices=[x.value for x in Scenario], default="success")
    args = parser.parse_args(argv)
    connection = ConnectionSpec(connection_id=uuid4(), provider_id="mock", model_id="mock-v1", mode=args.mode)
    frozen = FrozenInput(messages=(Message(role="USER", content=args.question),))
    intent = OperationIntent(identity=OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
                             debate_id=uuid4(), round_id=uuid4(), participant_id=uuid4(),
                             connection_id=connection.connection_id, expected_revision=0, connection_revision=0,
                             frozen_input=frozen, request_hash=frozen.content_hash)
    request = AdapterRequest(intent=intent, connection=connection, timeout_seconds=2.0)
    result = MockAdapter(mode=args.mode, scenario=Scenario(args.scenario)).send(request)
    output = {"project": "Consilium", "phase": "P01", "scope": "OFFLINE_FOUNDATION_DEMO",
              "debate_completed": False, "live_provider_calls": 0,
              "result": result.model_dump(mode="json")}
    ensure_public_payload(output, ())
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result.response_state == ResponseState.COMPLETE else 2


if __name__ == "__main__":
    raise SystemExit(main())
