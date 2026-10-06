#!/usr/bin/env python3
"""Record the actual first unfinished phase; never accept it automatically."""
from pathlib import Path
import argparse
import json

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


def main(*, report_blocked=False):
    _, progress, phase = q.state(ROOT)
    q.navigation(ROOT)
    current = next(row for row in progress["phases"] if row["id"] == phase)
    if report_blocked and current["status"] == "BLOCKED":
        print(json.dumps({"phase": phase, "status": "BLOCKED", "execution": "NOT_RUN",
                          "phase_advanced": False, "phase_accepted": False,
                          "scope": "DEVELOPMENT_CI_REPORTS_BLOCKER_WITHOUT_ACCEPTANCE"}))
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
