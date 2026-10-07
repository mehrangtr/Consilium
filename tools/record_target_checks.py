#!/usr/bin/env python3
"""Run checks on this native host and keep an immutable, source-bound report."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid

import qualityctl as q
from check_target_matrix import validate_smoke_row
from development_progress import milestone, step_id

ROOT = Path(__file__).resolve().parents[1]
# check.py runs several suites, each bounded to 60 seconds. The aggregate
# recorder needs room for those suites and its final source-bound report.
NATIVE_CHECK_BUDGET_SECONDS = 120


def main():
    target = platform.system()
    q.require(target in q.load(ROOT / "SCOPE.json")["target_platforms"], "This is not a selected target OS")
    q.navigation(ROOT)
    before = q.source_digest(ROOT)
    name = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
    folder = ROOT / "evidence/targets" / target / name
    folder.mkdir(parents=True)
    inputs = {
        "maintenance_report": "evidence/maintenance-check/RUN.json",
        "environment_report": "evidence/environment/RUN.json",
        "control_report": "evidence/control-tests/RUN.json",
        "control_junit": "evidence/control-tests/JUNIT.xml",
        "foundation_report": "evidence/foundation-tests/RUN.json",
        "foundation_junit": "evidence/foundation-tests/JUNIT.xml",
    }
    if (ROOT / "tools/run_persistence_tests.py").is_file():
        inputs.update(persistence_report="evidence/persistence-tests/RUN.json",
                      persistence_junit="evidence/persistence-tests/JUNIT.xml")
    if (ROOT / "tools/run_browser_probe_tests.py").is_file():
        inputs.update(browser_probe_report="evidence/browser-probe-tests/RUN.json",
                      browser_probe_junit="evidence/browser-probe-tests/JUNIT.xml")
    if (ROOT / "tools/run_architect_tests.py").is_file():
        inputs.update(architect_report="evidence/architect-tests/RUN.json",
                      architect_junit="evidence/architect-tests/JUNIT.xml")
    # Historical immutable reports remain intact; mutable outputs must be fresh.
    for original in inputs.values():
        (ROOT / original).unlink(missing_ok=True)
    errors = []
    code = None
    try:
        execution = subprocess.run([sys.executable, "tools/check.py"], cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=NATIVE_CHECK_BUDGET_SECONDS, shell=False)
        code, check_output = execution.returncode, execution.stdout
    except subprocess.TimeoutExpired as exc:
        check_output = exc.output or b""
        errors.append({"kind": "CHECK_TIMEOUT", "timeout_seconds": exc.timeout})
    except OSError as exc:
        check_output = b""
        errors.append({"kind": "CHECK_START_FAILED", "error": type(exc).__name__})
    if isinstance(check_output, str):
        check_output = check_output.encode("utf-8")
    (folder / "CHECK.log").write_bytes(check_output)
    milestone("native_development_check_finished")
    artifacts = {}
    artifacts["check_log"] = {"path": (folder / "CHECK.log").relative_to(ROOT).as_posix(),
                              "sha256": q.digest((folder / "CHECK.log").read_bytes())}
    for role, original in inputs.items():
        source = ROOT / original
        if not source.is_file():
            errors.append({"kind": "MISSING_CURRENT_REPORT", "role": role})
            continue
        data = source.read_bytes()
        destination = folder / (role + source.suffix)
        destination.write_bytes(data)
        artifacts[role] = {"path": destination.relative_to(ROOT).as_posix(), "sha256": q.digest(data)}
    smoke = []
    for mode, scenario, expected in [("API", "success", 0), ("BROWSER", "success", 0),
                                     ("BROWSER", "timeout_after_send", 2), ("API", "partial", 2)]:
        argv = [sys.executable, "tools/run_consilium.py", "mock", "--question", "offline smoke question",
                "--mode", mode, "--scenario", scenario]
        row = {"mode": mode, "scenario": scenario, "returncode": None, "expected": expected, "status": "FAIL"}
        raw_output = b""
        try:
            proc = subprocess.run(argv, cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, timeout=10, shell=False)
            row["returncode"] = proc.returncode
            raw_output = proc.stdout + (proc.stderr or b"")
            output = json.loads(proc.stdout)
            row["output"] = output
            row["status"] = "PASS"
            validate_smoke_row(row)
        except subprocess.TimeoutExpired as exc:
            raw_output = exc.output or b""
            row["error"] = "SMOKE_TIMEOUT"
            row["status"] = "FAIL"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row["error"] = type(exc).__name__
            row["status"] = "FAIL"
        if isinstance(raw_output, str):
            raw_output = raw_output.encode("utf-8")
        log = folder / ("smoke_" + str(len(smoke) + 1) + ".log")
        log.write_bytes(raw_output)
        artifacts["smoke_" + str(len(smoke) + 1) + "_log"] = {
            "path": log.relative_to(ROOT).as_posix(), "sha256": q.digest(raw_output)}
        smoke.append(row)
        milestone("native_smoke_" + str(len(smoke)) + "_finished")
    after = q.source_digest(ROOT)
    for entry in artifacts.values():
        q.artifact(ROOT, entry)
    report = {"phase": "P01", "development_step_id": step_id(), "scope": "NATIVE_TARGET_OFFLINE_EXECUTION",
              "status": "PASS" if code == 0 and not errors and before == after and all(x["status"] == "PASS" for x in smoke) else "FAIL",
              "check_returncode": code, "errors": errors,
              "source_digest_before": before, "source_digest_after": after,
              "host": {"system": target, "python": platform.python_version()},
              "date_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "artifacts": artifacts,
              "smoke": smoke, "live_provider_calls": 0, "full_v1_conformance": "NOT_RUN"}
    run_path = folder / "RUN.json"
    run_path.write_bytes(q.encoded(report))
    pointer = folder.parent / "LATEST.json"
    temp = pointer.with_name(pointer.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_bytes(q.encoded({"path": run_path.relative_to(ROOT).as_posix(), "sha256": q.digest(run_path.read_bytes())}))
    os.replace(temp, pointer)
    milestone("native_receipt_and_pointer_written", receipt=run_path)
    print(json.dumps({"status": report["status"], "target": target, "report": run_path.relative_to(ROOT).as_posix()}))
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (q.Blocked, OSError, subprocess.TimeoutExpired, KeyError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        raise SystemExit(1)
