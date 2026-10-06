#!/usr/bin/env python3
"""Record the actual first unfinished phase; never accept it automatically."""
from pathlib import Path
import json

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


def main():
    _, _, phase = q.state(ROOT)
    q.navigation(ROOT)
    path, receipt = q.run(ROOT, phase)
    print(json.dumps({"phase": phase, "status": receipt["status"], "receipt": path.relative_to(ROOT).as_posix(),
                      "phase_advanced": False}))
    return int(receipt["status"] != "PASS")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (q.Blocked, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc), "phase_advanced": False}))
        raise SystemExit(2)
