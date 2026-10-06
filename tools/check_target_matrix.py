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
            q.require({"check_log", "maintenance_report", "environment_report", "control_report",
                       "control_junit", "foundation_report", "foundation_junit"}.issubset(artifacts),
                      "Missing native artifacts")
            for reference_item in artifacts.values():
                q.artifact(root, reference_item)
            for role in ("maintenance_report", "environment_report", "control_report", "foundation_report"):
                q.require(q.load(q.artifact(root, artifacts[role]))["status"] == "PASS", "Failed target subcheck")
            scopes = {"maintenance_report": "DEVELOPMENT_CHECK_WITH_SEPARATE_FOUNDATION_TESTS",
                      "environment_report": "CURRENT_HOST_DEPENDENCY_LOCK_NOT_OTHER_OS_PROOF",
                      "control_report": "DEVELOPMENT_CONTROL_TOOLING_ONLY",
                      "foundation_report": "APPLICATION_FOUNDATION_OFFLINE_NOT_FULL_V1_CONFORMANCE"}
            for role, expected_scope in scopes.items():
                q.require(q.load(q.artifact(root, artifacts[role]))["scope"] == expected_scope,
                          "Incorrect target subcheck scope")
            foundation = q.load(q.artifact(root, artifacts["foundation_report"]))
            q.require(foundation["host"]["system"] == target, "Foundation tests ran on another OS")
            environment = q.load(q.artifact(root, artifacts["environment_report"]))
            q.require(environment["host"]["system"] == target, "Dependency check ran on another OS")
            python_version = run["host"]["python"]
            q.require(isinstance(python_version, str) and python_version.startswith("3.12."),
                      "Target execution used another Python version")
            for role in ("environment_report", "foundation_report", "control_report"):
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
            for role in ("maintenance_report", "foundation_report", "control_report"):
                subcheck = q.load(q.artifact(root, artifacts[role]))
                q.require(subcheck["source_digest_before"] == subcheck["source_digest_after"] == source,
                          "Target subcheck is stale")
            for role in ("control_junit", "foundation_junit"):
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
