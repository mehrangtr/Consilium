#!/usr/bin/env python3
"""Verify the declared P00 scope and the untouched protected baseline, offline."""
from __future__ import annotations

import json
from pathlib import Path
import platform
import re
import sys
import zipfile

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


def main():
    plan, progress, _ = q.state(ROOT)
    scope = q.load(ROOT / "SCOPE.json")
    inventory = q.load(ROOT / "INVENTORY.json")
    q.require(scope["target_platforms"] == ["Windows", "Linux"], "Target platforms changed")
    q.require(scope["evaluation_budget"]["paid_calls_authorized"] is False
              and scope["evaluation_budget"]["current_amount"] == 0, "Budget changed")
    q.require(scope["required_connection_modes"] == ["API", "BROWSER", "MANUAL"],
              "A protected connection mode was removed")
    q.require(scope["manual_replaces_browser"] is False, "Manual cannot replace Browser")
    providers = scope["providers"]
    expected = ["openai", "anthropic", "google", "deepseek", "qwen"]
    q.require([p["id"] for p in providers] == expected, "Provider scope differs from user selection")
    for provider in providers:
        q.require(provider["release_target"] == "V1" and provider["model_id"] is None,
                  "Unselected live model must remain explicit")
        q.require(provider["account_access"] == "UNKNOWN", "Live access has not been verified")
        q.require([c["mode"] for c in provider["connections"]] == ["API", "BROWSER"],
                  "Provider connection plan is incomplete")
        for connection in provider["connections"]:
            q.require(connection["implementation_status"] == "PLANNED"
                      and connection["live_verification"] == "NOT_RUN"
                      and connection["capabilities"] == "UNKNOWN",
                      "A plan is not evidence of a live adapter")
    q.require(scope["planned_connection_counts"] == {"API": 5, "BROWSER": 5, "MANUAL": 1},
              "Connection count is inconsistent")
    baseline = ROOT / "baseline" / plan["baseline"]["package_name"]
    canonical = "consilium-governance/requirements/USER_CONSTRAINTS.yaml"
    with zipfile.ZipFile(baseline) as archive:
        data = archive.read(canonical)
    ids = re.findall(r"(?m)^- id: (UR-\d{3})$", data.decode("utf-8"))
    q.require(ids == ["UR-%03d" % i for i in range(1, 31)], "Canonical protected IDs differ")
    q.require(q.digest(data) == scope["protected_baseline"]["requirements_sha256"],
              "Protected requirement bytes changed")
    q.require(inventory["starting_application_source"]["status"] == "NOT_FOUND_IN_REVIEWED_INPUTS"
              and inventory["unresolved_for_p00"] == [], "P00 inventory remains incomplete")
    q.require(scope["unknowns"] and scope["user_decision_evidence"], "Missing uncertainty or provenance")
    output = {
        "schema_version": 1, "phase": "P00", "status": "PASS",
        "scope": "DECLARED_SCOPE_AND_INPUT_INVENTORY_NOT_RUNTIME_ACCEPTANCE",
        "source_digest": q.source_digest(ROOT), "protected_requirements": len(ids),
        "protected_baseline_sha256": q.digest(baseline.read_bytes()),
        "canonical_requirements_sha256": q.digest(data),
        "planned_connection_counts": scope["planned_connection_counts"],
        "host": {"system": platform.system(), "python": platform.python_version()},
        "windows_execution": "NOT_RUN", "live_provider_calls": 0,
        "verified_application_requirements": progress["verified_application_requirements"],
    }
    destination = ROOT / "evidence" / "scope" / "RUN.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(q.encoded(output))
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (q.Blocked, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        raise SystemExit(1)
