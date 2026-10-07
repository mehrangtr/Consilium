#!/usr/bin/env python3
"""Review and explicitly retire prior operations before separately entering manual content."""
import argparse
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from consilium.core.contracts import ConnectionSpec
from consilium.shell.manual_reconciliation_review import review_manual_reconciliation
from consilium.shell.storage import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--revision", type=int, required=True)
    for name in ("debate-id", "round-id", "participant-id"):
        parser.add_argument("--"+name, type=UUID, required=True)
    parser.add_argument("--manual-connection-file", type=Path, required=True)
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file() or database.is_relative_to(ROOT):
        raise ValueError("Use an existing local database outside source")
    if args.manual_connection_file.stat().st_size > 65536:
        raise ValueError("Manual connection file exceeds the local size limit")
    connection = ConnectionSpec.model_validate_json(args.manual_connection_file.read_bytes())
    with SQLiteStore(database) as store:
        result = review_manual_reconciliation(store, debate_id=args.debate_id, round_id=args.round_id,
            participant_id=args.participant_id, expected_revision=args.revision,
            manual_connection=connection, read_line=input, write=print)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RecursionError):
        print(json.dumps({"status":"REJECTED", "error":"LOCAL_MANUAL_RECONCILIATION_STATE_OR_INPUT_REJECTED",
            "provider_calls":0, "phase_accepted":False}))
        raise SystemExit(1)
