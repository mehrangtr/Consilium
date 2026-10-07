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
from consilium.shell.manual_entry import collect_manual_text
from consilium.shell.storage import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--revision", required=True, type=int)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--submission", required=True)
    enter = commands.add_parser("enter")
    for name in ("candidate-id", "debate-id", "round-id", "participant-id"):
        enter.add_argument("--"+name, required=True, type=UUID)
    enter.add_argument("--actual-prompt-file", required=True)
    enter.add_argument("--round-seen", action="store_true")
    enter.add_argument("--claimed-origin")
    review = commands.add_parser("review")
    review.add_argument("--candidate-id", required=True, type=UUID)
    args = parser.parse_args()
    database = Path(args.database).resolve()
    if not database.is_file() or database.is_relative_to(ROOT):
        raise ValueError("Use an existing local debate database outside the source repository")
    with SQLiteStore(database) as store:
        if args.command in {"stage", "enter"}:
            path = Path(args.submission if args.command == "stage" else args.actual_prompt_file)
            if path.stat().st_size > 1048576:
                raise ValueError("Manual submission exceeds byte limit")
            if args.command == "stage":
                submission = ManualAnswerSubmission.model_validate_json(path.read_bytes())
            else:
                answer = collect_manual_text(args.candidate_id, read_line=input, write=print)
                if answer is None:
                    print(json.dumps({"status":"CANCELLED_NOT_STAGED","provider_calls":0,"phase_accepted":False}));return 0
                submission = ManualAnswerSubmission(schema_version=1,candidate_id=args.candidate_id,
                    debate_id=args.debate_id,round_id=args.round_id,participant_id=args.participant_id,
                    actual_prompt=path.read_text(encoding="utf-8"),round_seen=args.round_seen,answer=answer,
                    claimed_origin=args.claimed_origin)
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
