#!/usr/bin/env python3
"""Stage and explicitly review local manual answers; no provider I/O."""
import argparse
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from consilium.core.contracts import RoundSpec
from consilium.core.manual_sources import ManualAnswerSubmission
from consilium.shell.manual_review import review_manual_answer
from consilium.shell.storage import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--revision", required=True, type=int)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--submission", required=True)
    review = commands.add_parser("review")
    review.add_argument("--candidate-id", required=True, type=UUID)
    args = parser.parse_args()
    database = Path(args.database).resolve()
    if not database.is_file() or database.is_relative_to(ROOT):
        raise ValueError("Use an existing local debate database outside the source repository")
    with SQLiteStore(database) as store:
        if args.command == "stage":
            path = Path(args.submission)
            if path.stat().st_size > 1048576:
                raise ValueError("Manual submission exceeds byte limit")
            submission = ManualAnswerSubmission.model_validate_json(path.read_bytes())
            row = store._db.execute("SELECT spec_json FROM rounds WHERE debate_id=? AND round_id=?",
                (str(submission.debate_id), str(submission.round_id))).fetchone()
            if row is None:
                raise ValueError("Manual submission round is not registered")
            data = submission.model_dump(mode="python", exclude={"schema_version", "debate_id", "round_id"})
            candidate = store.manual_sources.stage_answer(round_spec=RoundSpec.model_validate_json(row[0]),
                **data, expected_revision=args.revision)
            output = {"status": "STAGED_NOT_ACCEPTED", "candidate_id": str(candidate.candidate_id),
                      "candidate_hash": candidate.content_hash, "alignment": candidate.alignment,
                      "provider_calls": 0, "phase_accepted": False}
        else:
            output = review_manual_answer(store, args.candidate_id, expected_revision=args.revision,
                                          read_line=input, write=print)
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        print(json.dumps({"status": "REJECTED", "error": "LOCAL_MANUAL_STATE_OR_INPUT_REJECTED",
                          "provider_calls": 0, "phase_accepted": False}))
        raise SystemExit(1)
