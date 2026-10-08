#!/usr/bin/env python3
"""One portable check; control and application foundation results remain separate."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

import qualityctl as q
from development_progress import atomic_json, milestone, step_id

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
    milestone("state_navigation_python_syntax_finished")
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
    has_probe = (ROOT / "tools/run_browser_probe_tests.py").is_file()
    if has_probe:
        commands.append(("browser_probe_preparation_tests", [sys.executable, "tools/run_browser_probe_tests.py"]))
    if (ROOT / "tools/run_architect_tests.py").is_file():
        commands.append(("architect_contract_tests", [sys.executable, "tools/run_architect_tests.py"]))
    if (ROOT / "tools/run_council_tests.py").is_file():
        commands.append(("council_pipeline_tests", [sys.executable, "tools/run_council_tests.py"]))
    has_architect = (ROOT / "tools/run_architect_tests.py").is_file()
    for name, argv in commands:
        try:
            code = subprocess.run(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                                  timeout=60, shell=False).returncode
            results.append({"id": name, "status": "PASS" if code == 0 else "FAIL", "returncode": code})
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({"id": name, "status": "FAIL", "error": type(exc).__name__})
        milestone(name + "_finished")
    after = q.source_digest(ROOT)
    passed = before == after and all(x["status"] == "PASS" for x in results)
    artifact_names = ["evidence/environment/RUN.json"]
    for folder in ("control-tests", "foundation-tests", "persistence-tests", "browser-probe-tests", "architect-tests", "council-tests"):
        artifact_names += ["evidence/" + folder + "/" + file for file in ("RUN.json", "JUNIT.xml")]
    artifacts = {name: {"path": name, "sha256": q.digest((ROOT / name).read_bytes())}
                 for name in artifact_names if (ROOT / name).is_file()}
    report = {"schema_version": 1, "development_step_id": step_id(), "artifacts": artifacts,
              "scope": "DEVELOPMENT_CHECK_WITH_SEPARATE_FOUNDATION_TESTS" if has_application else "DEVELOPMENT_CONTROL_TOOLING_ONLY",
              "status": "PASS" if passed else "FAIL", "checks": results,
              "source_digest_before": before, "source_digest_after": after,
              "application_runtime_tests": "FOUNDATION_P02_KERNEL_P03_P04_AND_P05_OFFLINE_COUNCIL" if (ROOT / "tools/run_council_tests.py").is_file() else "FOUNDATION_P02_KERNEL_P03_OFFLINE_PROBE_AND_P04_OFFLINE_SLICES" if has_architect else "FOUNDATION_P02_KERNEL_AND_P03_OFFLINE_PROBE" if has_probe else "FOUNDATION_AND_P02_DURABLE_KERNEL" if has_persistence else "FOUNDATION_ONLY" if has_application else "NOT_RUN", "application_phase_accepted": False,
              "static_type_check": "NOT_RUN", "visual_rendering": "NOT_RUN"}
    destination = ROOT / "evidence/maintenance-check/RUN.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(destination, report)
    milestone("development_check_receipt_written", receipt=destination)
    print(q.encoded(report).decode())
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
