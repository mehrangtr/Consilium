#!/usr/bin/env python3
"""Portable offline demos; P02 persists and resumes without a live provider."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from consilium.adapters.mock import MockAdapter, Scenario
from consilium.core.contracts import AdapterRequest, ConnectionSpec, DebateSpec, FrozenInput, Message, OperationIdentity, OperationIntent, ResponseState, RoundSpec
from consilium.core.operation_states import AttemptState
from consilium.shell.private import ensure_public_payload
from consilium.shell.runner import DurableRunner
from consilium.shell.storage import Conflict, SchemaError, SQLiteStore


def durable_demo(args):
    database = Path(args.database).resolve()
    root = Path(__file__).resolve().parents[1]
    if database.is_relative_to(root):
        raise ValueError("Keep local debate data outside the source repository")
    if database.exists():
        raise FileExistsError("Use resume for an existing database; new demos never replace or resend it")
    participant = uuid4()
    debate = DebateSpec(debate_id=uuid4(), original_request=args.question, participant_ids=(participant,))
    round_spec = RoundSpec(round_id=uuid4(), debate_id=debate.debate_id, number=1,
                           kind="INDEPENDENT", participant_ids=(participant,))
    connection = ConnectionSpec(connection_id=uuid4(), provider_id="mock", model_id="mock-v1", mode=args.mode)
    frozen = FrozenInput(messages=(Message(role="USER", content=args.question),))
    with SQLiteStore(database, require_new=True) as store:
        checkpoint = store.create_debate(debate)
        checkpoint = store.register_round(round_spec, expected_revision=checkpoint.revision)
        checkpoint = store.bind_connection(debate.debate_id, participant, connection,
            expected_revision=checkpoint.revision, expected_connection_revision=None)
        intent = OperationIntent(identity=OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
            debate_id=debate.debate_id, round_id=round_spec.round_id, participant_id=participant,
            connection_id=connection.connection_id, expected_revision=checkpoint.revision, connection_revision=0,
            frozen_input=frozen, request_hash=frozen.content_hash)
        checkpoint = store.prepare_intent(intent)
        request = AdapterRequest(intent=intent, connection=connection, timeout_seconds=2.0)
        plan = DurableRunner(store).execute(request, MockAdapter(mode=args.mode, scenario=Scenario(args.scenario)),
                                            expected_revision=checkpoint.revision)
        exported = store.export_debate(debate.debate_id)
    # Reopen before export: this path proves the checkpoint survives a restart.
    with SQLiteStore(database) as restored:
        after_restart = restored.export_debate(debate.debate_id)
        if after_restart != exported:
            raise SchemaError("Restart changed the committed debate")
    output = {"project": "Consilium", "phase": "P02", "scope": "OFFLINE_DURABLE_MOCK_DEMO",
              "live_provider_calls": 0, "debate_completed": False, "restart_verified": True,
              "resume": plan.model_dump(mode="json"), "export": after_restart}
    return output, 0 if plan.attempt.state == AttemptState.CONFIRMED else 2


def resume_demo(args):
    database = Path(args.database).resolve()
    if not database.is_file():
        raise FileNotFoundError("Resume requires an existing local database")
    with SQLiteStore(database) as store:
        exported = store.export_debate(UUID(args.debate_id))
        plans = [store.ledger.resume(UUID(x["intent"]["identity"]["attempt_id"])).model_dump(mode="json")
                 for x in exported["attempts"]]
    return {"project": "Consilium", "phase": "P02", "scope": "OFFLINE_STORED_STATE_RESUME",
            "debate_completed": False, "live_provider_calls": 0, "provider_calls": 0,
            "resume": plans, "export": exported}, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Consilium P01 offline foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    mock = commands.add_parser("mock")
    mock.add_argument("--question", required=True)
    mock.add_argument("--mode", choices=("API", "BROWSER"), default="API")
    mock.add_argument("--scenario", choices=[x.value for x in Scenario], default="success")
    durable = commands.add_parser("durable-mock")
    durable.add_argument("--database", required=True)
    durable.add_argument("--question", required=True)
    durable.add_argument("--mode", choices=("API", "BROWSER"), default="API")
    durable.add_argument("--scenario", choices=[x.value for x in Scenario], default="success")
    resume = commands.add_parser("resume")
    resume.add_argument("--database", required=True)
    resume.add_argument("--debate-id", required=True)
    args = parser.parse_args(argv)
    if args.command != "mock":
        try:
            output, code = durable_demo(args) if args.command == "durable-mock" else resume_demo(args)
            ensure_public_payload(output, ())
        except (ValueError, OSError, Conflict, SchemaError):
            print(json.dumps({"project": "Consilium", "phase": "P02", "status": "ERROR",
                              "error": "LOCAL_STATE_OR_REQUEST_REJECTED", "debate_completed": False}))
            return 1
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return code
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
