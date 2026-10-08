#!/usr/bin/env python3
"""P01 cannot close with a missing, stale or unsuccessful selected-OS report."""
from __future__ import annotations

import json
from pathlib import Path

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


SMOKE_EXPECTATIONS = {
    ("API", "success"): (0, "CONFIRMED_DELIVERY", "COMPLETE", "NONE"),
    ("BROWSER", "success"): (0, "CONFIRMED_DELIVERY", "COMPLETE", "NONE"),
    ("BROWSER", "timeout_after_send"): (2, "UNKNOWN_DELIVERY", "NONE", "TIMEOUT"),
    ("API", "partial"): (2, "CONFIRMED_DELIVERY", "PARTIAL", "TIMEOUT"),
}


def validate_smoke_row(row):
    key = (row["mode"], row["scenario"])
    q.require(key in SMOKE_EXPECTATIONS and row["status"] == "PASS", "Invalid smoke scenario or result")
    code, delivery, response, failure = SMOKE_EXPECTATIONS[key]
    q.require(type(row["returncode"]) is int and type(row["expected"]) is int
              and row["returncode"] == row["expected"] == code, "Incorrect smoke exit code")
    output = row["output"]
    q.require(output["project"] == "Consilium" and output["phase"] == "P01"
              and output["scope"] == "OFFLINE_FOUNDATION_DEMO", "Wrong smoke output scope")
    q.require(type(output["live_provider_calls"]) is int and output["live_provider_calls"] == 0
              and output["debate_completed"] is False, "Smoke run is not an incomplete offline demo")
    result = output["result"]
    q.require((result["delivery"], result["response_state"], result["failure"]) == (delivery, response, failure),
              "Smoke output contradicts the expected delivery/response result")
    content = result["content"]
    q.require(content is None if response == "NONE" else isinstance(content, str) and bool(content.strip()),
              "Smoke response content contradicts its state")


def validate_smoke(rows):
    q.require(isinstance(rows, list) and len(rows) == len(SMOKE_EXPECTATIONS), "Incomplete smoke evidence")
    q.require({(r["mode"], r["scenario"]) for r in rows} == set(SMOKE_EXPECTATIONS),
              "Missing or duplicate smoke scenarios")
    for row in rows:
        validate_smoke_row(row)


def inspect_matrix(root):
    source = q.source_digest(root)
    targets = q.load(root / "SCOPE.json")["target_platforms"]
    persistence_required = (root / "tools/run_persistence_tests.py").is_file()
    probe_required = (root / "tools/run_browser_probe_tests.py").is_file()
    architect_required = (root / "tools/run_architect_tests.py").is_file()
    council_required = (root / "tools/run_council_tests.py").is_file()
    rows = []
    for target in targets:
        row = {"target": target, "status": "NOT_RUN"}
        try:
            pointer = root / "evidence/targets" / target / "LATEST.json"
            if not pointer.is_file():
                row["reason"] = "Native target execution has not been supplied"
                rows.append(row)
                continue
            reference = q.load(pointer)
            run = q.load(q.artifact(root, reference))
            q.require(run["phase"] == "P01" and run["scope"] == "NATIVE_TARGET_OFFLINE_EXECUTION"
                      and run["host"]["system"] == target, "Report is for another target or scope")
            q.require(run["status"] == "PASS" and run["source_digest_before"] == run["source_digest_after"] == source,
                      "Target checks failed or were run on different source")
            q.require(type(run["live_provider_calls"]) is int and run["live_provider_calls"] == 0,
                      "Offline report cannot contain live calls")
            validate_smoke(run["smoke"])
            artifacts = run["artifacts"]
            required_roles = {"check_log", "maintenance_report", "environment_report", "control_report",
                              "control_junit", "foundation_report", "foundation_junit"}
            if persistence_required:
                required_roles.update({"persistence_report", "persistence_junit"})
            if probe_required:
                required_roles.update({"browser_probe_report", "browser_probe_junit"})
            if architect_required:
                required_roles.update({"architect_report", "architect_junit"})
            if council_required:
                required_roles.update({"council_report", "council_junit"})
            quality_required = (root / 'tools/run_quality_tests.py').is_file()
            if quality_required:
                required_roles.update({'quality_report', 'quality_junit'})
            pilot_required = (root / 'tools/run_pilot_tests.py').is_file()
            if pilot_required:
                required_roles.update({'pilot_report', 'pilot_junit'})
            q.require(required_roles.issubset(artifacts),
                      "Missing native artifacts")
            for reference_item in artifacts.values():
                q.artifact(root, reference_item)
            report_roles = ["maintenance_report", "environment_report", "control_report", "foundation_report"]
            junit_roles = ["control_junit", "foundation_junit"]
            if persistence_required:
                report_roles.append("persistence_report")
                junit_roles.append("persistence_junit")
            if probe_required:
                report_roles.append("browser_probe_report")
                junit_roles.append("browser_probe_junit")
            if architect_required:
                report_roles.append("architect_report")
                junit_roles.append("architect_junit")
            if council_required:
                report_roles.append("council_report")
                junit_roles.append("council_junit")
            if quality_required:
                report_roles.append('quality_report')
                junit_roles.append('quality_junit')
            if pilot_required:
                report_roles.append('pilot_report')
                junit_roles.append('pilot_junit')
            for role in report_roles:
                q.require(q.load(q.artifact(root, artifacts[role]))["status"] == "PASS", "Failed target subcheck")
            scopes = {"maintenance_report": "DEVELOPMENT_CHECK_WITH_SEPARATE_FOUNDATION_TESTS",
                      "environment_report": "CURRENT_HOST_DEPENDENCY_LOCK_NOT_OTHER_OS_PROOF",
                      "control_report": "DEVELOPMENT_CONTROL_TOOLING_ONLY",
                      "foundation_report": "APPLICATION_FOUNDATION_OFFLINE_NOT_FULL_V1_CONFORMANCE"}
            if persistence_required:
                scopes["persistence_report"] = "P02_DURABILITY_OFFLINE_NOT_FULL_V1_ACCEPTANCE"
            if probe_required:
                scopes["browser_probe_report"] = "P03_PROBE_RECORDER_OFFLINE_NOT_LIVE_BROWSER_ACCEPTANCE"
            if architect_required:
                scopes["architect_report"] = "P04_QUESTION_CONTEXT_AND_POLICY_OFFLINE_NOT_FULL_PHASE_ACCEPTANCE"
            if council_required:
                scopes["council_report"] = "P05_FULL_OFFLINE_COUNCIL_NOT_LIVE_PROVIDER_CERTIFICATION"
            if quality_required:
                scopes['quality_report'] = 'APPROVED_QUALITY_IMPROVEMENTS_OFFLINE_NOT_MODEL_QUALITY'
            if pilot_required:
                scopes['pilot_report'] = 'OFFLINE_PILOT_ACCOUNTING_NOT_MODEL_QUALITY'
            for role, expected_scope in scopes.items():
                q.require(q.load(q.artifact(root, artifacts[role]))["scope"] == expected_scope,
                          "Incorrect target subcheck scope")
            if probe_required:
                probe = q.load(q.artifact(root, artifacts["browser_probe_report"]))
                q.require(probe["phase"] == "P03" and probe["phase_accepted"] is False
                          and type(probe["live_provider_calls"]) is int and probe["live_provider_calls"] == 0
                          and probe["external_transport"] == "SYNTHETIC_OBSERVATIONS_NO_BROWSER_DRIVER",
                          "Offline preparation cannot certify live browser acceptance")
            foundation = q.load(q.artifact(root, artifacts["foundation_report"]))
            q.require(foundation["host"]["system"] == target, "Foundation tests ran on another OS")
            environment = q.load(q.artifact(root, artifacts["environment_report"]))
            q.require(environment["host"]["system"] == target, "Dependency check ran on another OS")
            python_version = run["host"]["python"]
            q.require(isinstance(python_version, str) and python_version.startswith("3.12."),
                      "Target execution used another Python version")
            for role in [r for r in report_roles if r != "maintenance_report"]:
                host = q.load(q.artifact(root, artifacts[role]))["host"]
                q.require(host["system"] == target and host["python"] == python_version,
                          "Target subchecks used different environments")
            locked = dict(line.strip().split("==") for line in (root / "requirements.lock").read_text(encoding="utf-8").splitlines()
                          if line.strip() and not line.lstrip().startswith("#"))
            dependencies = environment["dependencies"]
            q.require(locked and len(dependencies) == len(locked)
                      and {x["package"] for x in dependencies} == set(locked), "Target dependency inventory differs from lock")
            q.require(all(x["status"] == "PASS" and x["required"] == x["installed"] == locked[x["package"]]
                          for x in dependencies), "Target dependencies do not match the lock")
            for role in [r for r in report_roles if r != "environment_report"]:
                subcheck = q.load(q.artifact(root, artifacts[role]))
                q.require(subcheck["source_digest_before"] == subcheck["source_digest_after"] == source,
                          "Target subcheck is stale")
            for role in junit_roles:
                counts = q.junit_counts(q.artifact(root, artifacts[role]))
                q.require(not any(counts[x] for x in ("failures", "errors", "skipped")), "Unsuccessful target JUnit")
                recorded = q.load(q.artifact(root, artifacts[role.replace("_junit", "_report")]))["counts"]
                q.require(all(type(recorded[x]) is int and recorded[x] == counts[x]
                              for x in ("tests", "failures", "errors", "skipped")),
                          "Target report counts contradict its JUnit")
                q.require(not recorded.get("expected_failures", 0) and not recorded.get("unexpected_successes", 0),
                          "Unaccepted control test outcomes")
                row[role.removesuffix("_junit") + "_tests"] = counts["tests"]
            row.update(status="PASS", evidence=reference)
        except (q.Blocked, OSError, KeyError, TypeError, ValueError) as exc:
            row.update(status="FAIL", reason=str(exc))
        rows.append(row)
    return {"phase": "P01", "scope": "SELECTED_OS_FOUNDATION_GATE_NOT_FULL_V1_ACCEPTANCE",
            "source_digest": source, "targets": rows,
            "status": "PASS" if rows and all(x["status"] == "PASS" for x in rows) else "BLOCKED"}


def main():
    report = inspect_matrix(ROOT)
    destination = ROOT / "evidence/target-matrix/RUN.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(q.encoded(report))
    print(json.dumps(report))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
