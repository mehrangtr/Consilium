#!/usr/bin/env python3
"""Check recorded P03 evidence consistency; does not authenticate a live service."""
from pathlib import Path
import json

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]


def validate(root):
    record = q.load(root / "evidence/browser-probe/P03_FEASIBILITY_CHECKPOINT.json")
    q.require(type(record["schema_version"]) is int and record["schema_version"] == 1
              and record["phase"] == "P03", "Wrong feasibility checkpoint")
    q.require(record["source_digest"] == q.source_digest(root), "Feasibility source differs")
    positive = q.load(q.artifact(root, record["positive_live_report"]))
    q.require(type(positive["confirmed_operations"]) is int
              and type(positive["unknown_delivery_operations"]) is int, "Invalid operation counts")
    q.require(positive["authentication"] == "MANUAL_USER_LOGIN_VERIFIED_BY_POSITIVE_UI_STATE"
              and positive["same_conversation_continuation_verified"] is True
              and positive["confirmed_operations"] == 2
              and positive["unknown_delivery_operations"] == 1,
              "Missing actual positive or observer-loss report")
    negative = q.load(q.artifact(root, record["controlled_authloss_report"]))
    for key in ("database_revision_before", "database_revision_after", "ticket_files_created", "external_send_actions"):
        q.require(type(negative[key]) is int, "Invalid authentication-loss counters")
    for key in ("positive_authentication_before", "signed_out_after_controlled_action",
                "prepared_intent_before_sign_out", "programmatic_start_rejected",
                "cli_start_rejected", "fresh_context_required"):
        q.require(negative[key] is True, "Missing controlled authentication-loss proof")
    q.require(negative["status"] == "PASS_CONTROLLED_AUTHENTICATION_LOSS"
              and negative["observation_kind"] == "ACTUAL_CLAUDE_UI_SIGN_OUT; NOT_NATURAL_EXPIRATION"
              and negative["server_natural_expiration_observed"] is False
              and negative["attempt_state"] == "PREPARED"
              and negative["database_revision_before"] == negative["database_revision_after"] == 3
              and negative["ticket_files_created"] == negative["external_send_actions"] == 0,
              "Authentication loss was not blocked without dispatch")
    q.require(negative["source_digest"] == record["source_digest"], "Negative proof source differs")
    before = q.load(q.artifact(root, negative["before_context"]))
    after = q.load(q.artifact(root, negative["after_context"]))
    q.require(before["authentication"] == "AUTHENTICATED" and before["model_visible"] is True
              and before["account_profile_matches_prior"] is True
              and before["same_test_conversation"] is True
              and after["authentication"] == "SIGNED_OUT"
              and after["known_cause"] == "CONTROLLED_SIGN_OUT"
              and after["login_controls_visible"] is True
              and after["server_natural_expiration_observed"] is False,
              "Before and after observations do not support controlled sign-out")
    q.require(negative["before_evidence_sha256"] == negative["before_context"]["sha256"]
              and negative["after_evidence_sha256"] == negative["after_context"]["sha256"], "Context hashes differ")
    for row in negative["guard_source_files"]:
        q.artifact(root, row)
    q.require({r["path"] for r in negative["guard_source_files"]} == {
        "src/consilium/shell/browser_probe.py", "tools/run_browser_probe.py"}, "Guard source proof missing")
    q.require(record["natural_expiration_verification"] == "UNKNOWN_NOT_CERTIFIED"
              and record["expired_state_test_scope"] == "SYNTHETIC_CONTRACT_TEST_NOT_PROVIDER_EXPIRATION"
              and record["unknown_operation_policy"] == "PRESERVE_UNKNOWN_NO_AUTOMATIC_RESEND",
              "Evidence must not overstate expiration or recovery")
    q.artifact(root, record["capability_and_estimate_report"])
    package = record["private_evidence_package"]
    q.require(isinstance(package["filename"], str) and package["filename"].endswith(".zip")
              and isinstance(package["sha256"], str) and len(package["sha256"]) == 64
              and all(c in "0123456789abcdef" for c in package["sha256"])
              and package["status"] == "SAVED_PRIVATELY_FOR_USER",
              "Private evidence preservation not recorded")
    return {"status": "PASS", "phase": "P03",
            "scope": "RECORDED_EVIDENCE_CONSISTENCY_NOT_INDEPENDENT_AUTHENTICITY",
            "natural_expiration_verified": False, "phase_accepted": False}


def main():
    try:
        report = validate(ROOT)
    except (q.Blocked, OSError, KeyError, ValueError, TypeError):
        report = {"status": "BLOCKED", "phase": "P03", "reason": "MISSING_OR_INCONSISTENT_P03_EVIDENCE",
                  "phase_accepted": False}
    print(json.dumps(report))
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
