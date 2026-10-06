#!/usr/bin/env python3
"""One portable check; control and application foundation results remain separate."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


def main():
    before = q.source_digest(ROOT)
    rows = q.source_rows(ROOT)
    results = []
    try:
        q.state(ROOT)
        q.navigation(ROOT, check=True)
        for name, _ in rows:
            if name.endswith(".py"):
                ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
        results.append({"id": "state_navigation_python_syntax", "status": "PASS"})
    except (q.Blocked, SyntaxError, OSError, KeyError, ValueError) as exc:
        results.append({"id": "state_navigation_python_syntax", "status": "FAIL", "error": str(exc)})
    markdown = [name for name, _ in rows if name.endswith(".md")]
    markdown += list(q.NAVIGATION_FILES)
    commands = [
        ("control_tests", [sys.executable, "tools/run_control_tests.py"]),
        ("markdown_lexical", [sys.executable, "tools/check_markdown_bidi.py", *markdown]),
    ]
    has_application = (ROOT / "src/consilium/core/contracts.py").is_file()
    if has_application:
        commands += [
            ("environment_lock", [sys.executable, "tools/check_environment.py"]),
            ("foundation_tests", [sys.executable, "tools/run_foundation_tests.py"]),
        ]
    has_persistence = (ROOT / "tools/run_persistence_tests.py").is_file()
    if has_persistence:
        commands.append(("persistence_tests", [sys.executable, "tools/run_persistence_tests.py"]))
    for name, argv in commands:
        try:
            code = subprocess.run(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                                  timeout=60, shell=False).returncode
            results.append({"id": name, "status": "PASS" if code == 0 else "FAIL", "returncode": code})
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({"id": name, "status": "FAIL", "error": type(exc).__name__})
    after = q.source_digest(ROOT)
    passed = before == after and all(x["status"] == "PASS" for x in results)
    report = {"schema_version": 1, "scope": "DEVELOPMENT_CHECK_WITH_SEPARATE_FOUNDATION_TESTS" if has_application else "DEVELOPMENT_CONTROL_TOOLING_ONLY",
              "status": "PASS" if passed else "FAIL", "checks": results,
              "source_digest_before": before, "source_digest_after": after,
              "application_runtime_tests": "FOUNDATION_AND_P02_STORAGE_SLICE" if has_persistence else "FOUNDATION_ONLY" if has_application else "NOT_RUN", "application_phase_accepted": False,
              "static_type_check": "NOT_RUN", "visual_rendering": "NOT_RUN"}
    destination = ROOT / "evidence/maintenance-check/RUN.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(q.encoded(report))
    print(q.encoded(report).decode())
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
