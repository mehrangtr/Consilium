#!/usr/bin/env python3
"""Record one observation against an existing prepared operation. No UI calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from consilium.core.browser_probe import BrowserObservation, ProbeTicket
from consilium.shell.browser_probe import BrowserProbeRecorder
from consilium.shell.storage import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "record", "inspect"])
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--ticket", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--expected-revision", type=int)
    args = parser.parse_args()
    if (not args.database.is_file() or args.database.is_symlink()
            or args.action != "inspect" and (args.input is None or args.expected_revision is None)):
        parser.error("Use an existing database; mutations need input and expected revision")
    try:
        with SQLiteStore(args.database) as store:
            probe = BrowserProbeRecorder(store)
            if args.action == "start":
                checkpoint = probe.start(ProbeTicket.model_validate_json(args.input.read_bytes()),
                                         args.ticket, expected_revision=args.expected_revision)
                data = {"state": "SENT", "revision": checkpoint.revision, "provider_prompt_sent": "NOT_OBSERVED"}
            else:
                plan = probe.record(args.ticket, BrowserObservation.model_validate_json(args.input.read_bytes()),
                                    expected_revision=args.expected_revision) if args.action == "record" else probe.inspect(args.ticket)
                data = {"state": plan.attempt.state.value, "resume_action": plan.action.value}
            print(json.dumps({"phase": "P03", "scope": "OBSERVATION_RECORDER_NOT_BROWSER_DRIVER",
                              "automatic_send": False, "phase_accepted": False, **data}))
            return 0
    except (ValueError, OSError):
        # Exceptions may involve prompts or private input. Never dump them to logs.
        print(json.dumps({"status": "BLOCKED", "reason": "INVALID_OR_CONFLICTING_PROBE_INPUT", "phase_accepted": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
