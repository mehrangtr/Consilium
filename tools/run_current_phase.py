#!/usr/bin/env python3
"""Record the actual first unfinished phase; never accept it automatically."""
from pathlib import Path
import argparse
import json
from uuid import uuid4

import qualityctl as q
from development_progress import atomic_json, milestone, step_id

ROOT = Path(__file__).resolve().parents[1]


def main(*, report_blocked=False):
    _, progress, phase = q.state(ROOT)
    q.navigation(ROOT)
    current = next(row for row in progress["phases"] if row["id"] == phase)
    if report_blocked and current["status"] == "BLOCKED":
        source = q.source_digest(ROOT)
        folder = ROOT / 'evidence' / 'phase-blockers' / uuid4().hex
        blocker = folder / 'BLOCKER.json'
        atomic_json(blocker, {"phase": phase, "phase_status": "BLOCKED",
                             "blockers": current['blockers'], "phase_accepted": False,
                             "progress_sha256": q.digest((ROOT / 'PROGRESS.json').read_bytes()),
                             "checks_sha256": q.digest((ROOT / 'CHECKS.json').read_bytes())})
        receipt = folder / 'RUN.json'
        # PASS certifies only recording the blocker. It never certifies a
        # phase test or acceptance. The supervisor still verifies the nonce,
        # unchanged source and declared artifact before completing this task.
        atomic_json(receipt, {"status": "PASS", "phase": phase,
            "scope": "DEVELOPMENT_BLOCKER_RECORDING_ONLY",
            "phase_status": "BLOCKED", "execution": "NOT_RUN", "phase_accepted": False,
            "development_step_id": step_id(), "source_digest_before": source,
            "source_digest_after": q.source_digest(ROOT),
            "artifacts": {"blocker": {"path": blocker.relative_to(ROOT).as_posix(),
                                      "sha256": q.digest(blocker.read_bytes())}}})
        milestone('blocked_phase_recorded', receipt=receipt)
        print(json.dumps({"phase": phase, "status": "BLOCKED", "execution": "NOT_RUN",
                          "phase_advanced": False, "phase_accepted": False,
                          "scope": "DEVELOPMENT_CI_REPORTS_BLOCKER_WITHOUT_ACCEPTANCE",
                          "receipt": receipt.relative_to(ROOT).as_posix()}))
        return 0
    path, receipt = q.run(ROOT, phase)
    print(json.dumps({"phase": phase, "status": receipt["status"], "receipt": path.relative_to(ROOT).as_posix(),
                      "phase_advanced": False}))
    return int(receipt["status"] != "PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-blocked", action="store_true",
                        help="Report a valid blocked phase in development CI without attempting acceptance")
    args = parser.parse_args()
    try:
        raise SystemExit(main(report_blocked=args.report_blocked))
    except (q.Blocked, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc), "phase_advanced": False}))
        raise SystemExit(2)
