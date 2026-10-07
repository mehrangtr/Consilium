#!/usr/bin/env python3
"""Review a stored architect candidate locally; never sends a provider request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from consilium.shell.architect_review import review_candidate
from consilium.shell.storage import SQLiteStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--debate-id", required=True)
    parser.add_argument("--proposal-hash", required=True)
    parser.add_argument("--expected-revision", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if (args.database.is_symlink() or not args.database.is_file()
                or args.database.resolve().is_relative_to(ROOT)):
            raise ValueError("Use an existing private database outside the source tree")
        debate_id = UUID(args.debate_id)
        with SQLiteStore(args.database) as store:
            result = review_candidate(store, debate_id, args.proposal_hash,
                expected_revision=args.expected_revision,
                read_line=lambda: sys.stdin.readline(256).rstrip("\r\n"),
                write=lambda text: print(text, flush=True))
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result["status"] == "ADOPTED" else 2
    except (ValueError, OSError, KeyboardInterrupt):
        # Do not print errors containing private paths, prompt fields or identities.
        print(json.dumps({"status": "BLOCKED", "reason": "INVALID_STALE_OR_CANCELLED_REVIEW",
                          "live_provider_calls": 0, "phase_accepted": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
