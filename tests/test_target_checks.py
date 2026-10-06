"""Synthetic checks of the evidence validator; not native Windows execution."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import qualityctl as q
from check_target_matrix import inspect_matrix


def synthetic_smoke_rows():
    """Complete validator fixtures; these are never host execution evidence."""
    rows = []
    for mode, scenario, code, delivery, response, failure in (
        ("API", "success", 0, "CONFIRMED_DELIVERY", "COMPLETE", "NONE"),
        ("BROWSER", "success", 0, "CONFIRMED_DELIVERY", "COMPLETE", "NONE"),
        ("BROWSER", "timeout_after_send", 2, "UNKNOWN_DELIVERY", "NONE", "TIMEOUT"),
        ("API", "partial", 2, "CONFIRMED_DELIVERY", "PARTIAL", "TIMEOUT"),
    ):
        rows.append({"mode": mode, "scenario": scenario, "returncode": code, "expected": code,
                     "status": "PASS", "output": {"project": "Consilium", "phase": "P01",
                     "scope": "OFFLINE_FOUNDATION_DEMO", "live_provider_calls": 0,
                     "debate_completed": False, "result": {"delivery": delivery,
                     "response_state": response, "failure": failure,
                     "content": None if response == "NONE" else "synthetic fixture content"}}})
    return rows


class TargetEvidenceControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "SCOPE.json").write_bytes(q.encoded({"target_platforms": ["Windows", "Linux"]}))
        (self.root / "requirements.lock").write_text("synthetic-package==1.0\n", encoding="utf-8")
        self.source = q.source_digest(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else q.encoded(value))
        return {"path": name, "sha256": q.digest(path.read_bytes())}

    def target(self, name, *, source=None, skipped=False, host=None, persistence=False):
        prefix = "evidence/targets/" + name + "/synthetic"
        artifacts = {}
        reports = ["maintenance_report", "environment_report", "control_report", "foundation_report"]
        if persistence:
            reports.append("persistence_report")
        for role in reports:
            value = {"status": "PASS", "host": {"system": host or name, "python": "3.12.14"},
                     "counts": {"tests": 1, "failures": 0, "errors": 0, "skipped": int(skipped)},
                     "source_digest_before": source or self.source, "source_digest_after": source or self.source}
            value["scope"] = {"maintenance_report": "DEVELOPMENT_CHECK_WITH_SEPARATE_FOUNDATION_TESTS",
                              "environment_report": "CURRENT_HOST_DEPENDENCY_LOCK_NOT_OTHER_OS_PROOF",
                              "control_report": "DEVELOPMENT_CONTROL_TOOLING_ONLY",
                              "foundation_report": "APPLICATION_FOUNDATION_OFFLINE_NOT_FULL_V1_CONFORMANCE",
                              "persistence_report": "P02_STORAGE_AND_PREPARED_INTENT_SLICE_NOT_PHASE_ACCEPTANCE"}[role]
            if role == "environment_report":
                value["dependencies"] = [{"package": "synthetic-package", "required": "1.0",
                                          "installed": "1.0", "status": "PASS"}]
            artifacts[role] = self.write(prefix + "/" + role + ".json", value)
        artifacts["check_log"] = self.write(prefix + "/CHECK.log", b"Synthetic validator fixture; not an OS run\n")
        xml = b'<testsuite tests="1"><testcase name="synthetic-validator-case">' + \
              (b'<skipped/>' if skipped else b'') + b'</testcase></testsuite>'
        for role in ["control_junit", "foundation_junit"] + (["persistence_junit"] if persistence else []):
            artifacts[role] = self.write(prefix + "/" + role + ".xml", xml)
        report = {"phase": "P01", "scope": "NATIVE_TARGET_OFFLINE_EXECUTION", "host": {"system": host or name, "python": "3.12.14"},
                  "status": "PASS", "source_digest_before": source or self.source,
                  "source_digest_after": source or self.source, "artifacts": artifacts,
                  "live_provider_calls": 0, "smoke": synthetic_smoke_rows()}
        ref = self.write(prefix + "/RUN.json", report)
        self.write("evidence/targets/" + name + "/LATEST.json", ref)
        return ref

    def test_missing_native_runs_do_not_pass(self):
        report = inspect_matrix(self.root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual([x["status"] for x in report["targets"]], ["NOT_RUN", "NOT_RUN"])

    def test_linux_success_does_not_count_as_windows(self):
        self.target("Linux")
        report = inspect_matrix(self.root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual([x["status"] for x in report["targets"]], ["NOT_RUN", "PASS"])

    def test_stale_source_is_rejected(self):
        self.target("Linux", source="0" * 64)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_another_host_cannot_be_renamed_windows(self):
        self.target("Windows", host="Linux")
        self.assertEqual(inspect_matrix(self.root)["targets"][0]["status"], "FAIL")

    def test_skipped_native_test_is_rejected(self):
        self.target("Linux", skipped=True)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_tampered_target_bytes_are_rejected(self):
        ref = self.target("Linux")
        (self.root / ref["path"]).write_bytes(b'{}')
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_complete_current_synthetic_graph_exercises_success_path(self):
        self.target("Windows")
        self.target("Linux")
        self.assertEqual(inspect_matrix(self.root)["status"], "PASS")

    def change_report(self, reference, edit):
        report = q.load(self.root / reference["path"])
        edit(report)
        refreshed = self.write(reference["path"], report)
        self.write("evidence/targets/Linux/LATEST.json", refreshed)

    def test_duplicate_smoke_scenarios_are_not_complete_evidence(self):
        reference = self.target("Linux")
        self.change_report(reference, lambda r: r.update(smoke=[r["smoke"][0]] * 4))
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_smoke_label_cannot_hide_a_wrong_delivery_outcome(self):
        reference = self.target("Linux")
        def edit(report):
            report["smoke"][2]["output"]["result"]["delivery"] = "CONFIRMED_DELIVERY"
        self.change_report(reference, edit)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_status_only_smoke_rows_are_rejected(self):
        reference = self.target("Linux")
        self.change_report(reference, lambda r: r.update(smoke=[{"status": "PASS"}] * 4))
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_missing_check_log_is_rejected(self):
        reference = self.target("Linux")
        self.change_report(reference, lambda r: r["artifacts"].pop("check_log"))
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_native_report_test_counts_must_match_junit(self):
        reference = self.target("Linux")
        def edit(report):
            item = report["artifacts"]["foundation_report"]
            child = q.load(self.root / item["path"])
            child["counts"]["tests"] = 200
            report["artifacts"]["foundation_report"] = self.write(item["path"], child)
        self.change_report(reference, edit)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_false_subcheck_status_cannot_hide_recorded_failures(self):
        reference = self.target("Linux")
        def edit(report):
            item = report["artifacts"]["control_report"]
            child = q.load(self.root / item["path"])
            child["counts"]["failures"] = 1
            report["artifacts"]["control_report"] = self.write(item["path"], child)
        self.change_report(reference, edit)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_environment_pass_label_cannot_hide_a_wrong_locked_dependency(self):
        reference = self.target("Linux")
        def edit(report):
            item = report["artifacts"]["environment_report"]
            child = q.load(self.root / item["path"])
            child["dependencies"][0]["installed"] = "0.9"
            report["artifacts"]["environment_report"] = self.write(item["path"], child)
        self.change_report(reference, edit)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def test_wrong_python_version_is_rejected_even_if_every_label_says_pass(self):
        reference = self.target("Linux")
        def edit(report):
            report["host"]["python"] = "3.11.9"
            for role in ("environment_report", "foundation_report", "control_report"):
                item = report["artifacts"][role]
                child = q.load(self.root / item["path"])
                child["host"]["python"] = "3.11.9"
                report["artifacts"][role] = self.write(item["path"], child)
        self.change_report(reference, edit)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")

    def require_persistence(self):
        path = self.root / "tools/run_persistence_tests.py"
        path.parent.mkdir()
        path.write_text("# Synthetic validator fixture only\n", encoding="utf-8")
        self.source = q.source_digest(self.root)

    def test_persistence_source_requires_native_persistence_artifacts(self):
        self.require_persistence()
        self.target("Windows"); self.target("Linux")
        self.assertEqual([r["status"] for r in inspect_matrix(self.root)["targets"]], ["FAIL", "FAIL"])

    def test_complete_persistence_fixture_exercises_both_hosts_without_claiming_execution(self):
        self.require_persistence()
        self.target("Windows", persistence=True); self.target("Linux", persistence=True)
        report = inspect_matrix(self.root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual([r["persistence_tests"] for r in report["targets"]], [1, 1])

    def test_persistence_report_from_another_host_is_refused(self):
        self.require_persistence()
        reference = self.target("Linux", persistence=True)
        def edit(report):
            item = report["artifacts"]["persistence_report"]
            child = q.load(self.root / item["path"])
            child["host"]["system"] = "Windows"
            report["artifacts"]["persistence_report"] = self.write(item["path"], child)
        self.change_report(reference, edit)
        self.assertEqual(inspect_matrix(self.root)["targets"][1]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
