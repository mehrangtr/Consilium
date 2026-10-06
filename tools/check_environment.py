#!/usr/bin/env python3
"""Validate the exact P01 dependency lock without installing or using a key."""
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import sys

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, required = line.split("==")
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = None
        rows.append({"package": name, "required": required, "installed": installed,
                     "status": "PASS" if required == installed else "FAIL"})
    passed = sys.version_info[:2] == (3, 12) and all(x["status"] == "PASS" for x in rows)
    report = {"status": "PASS" if passed else "FAIL", "phase": "P01",
              "scope": "CURRENT_HOST_DEPENDENCY_LOCK_NOT_OTHER_OS_PROOF",
              "host": {"system": platform.system(), "python": platform.python_version()},
              "dependencies": rows, "windows_execution": "NOT_RUN" if platform.system() != "Windows" else "THIS_RUN",
              "network_calls": 0}
    destination = ROOT / "evidence/environment/RUN.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(q.encoded(report))
    print(json.dumps(report))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
