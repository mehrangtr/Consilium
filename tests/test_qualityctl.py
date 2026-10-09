"""Synthetic fixtures test the guard itself; they are not Consilium acceptance evidence."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qualityctl", ROOT / "tools" / "qualityctl.py")
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


class QualityControls(unittest.TestCase):
    def test_ignored_evidence_is_not_enumerated_for_source_identity(self):
        before = q.source_rows(self.root)
        ignored = self.root / "evidence"
        nested = ignored / "historical" / "nested"
        nested.mkdir(parents=True)
        (nested / "not_source.py").write_text("historical = True\n")
        entered = []
        real_scandir, real_listdir = q.os.scandir, q.os.listdir

        def scandir(path):
            entered.append(Path(path))
            return real_scandir(path)

        def listdir(path):
            entered.append(Path(path))
            return real_listdir(path)

        with mock.patch.object(q.os, "scandir", side_effect=scandir), mock.patch.object(
                q.os, "listdir", side_effect=listdir):
            self.assertEqual(q.source_rows(self.root), before)
        self.assertFalse(any(path == ignored or ignored in path.parents for path in entered),
                         "Ignored historical evidence must be pruned before enumeration")

    def test_build_products_do_not_change_source_but_real_code_does(self):
        before = q.source_digest(self.root)
        for name in ("build/lib/generated.py", "dist/generated.whl", "src/example.egg-info/PKG-INFO"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"Synthetic packaging output")
        self.assertEqual(q.source_digest(self.root), before)
        path = self.root / "src/example.py"
        path.write_bytes(b"# Actual source must remain in the fingerprint\n")
        self.assertNotEqual(q.source_digest(self.root), before)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        for name in ("ROADMAP.json", "PROGRESS.json"):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "baseline", self.root / "baseline")
        (self.root / "tools").mkdir()
        shutil.copy2(ROOT / "tools" / "qualityctl.py", self.root / "tools" / "qualityctl.py")
        (self.root / "START_HERE_FA.md").write_text("Synthetic fixture only\n")
        self.config = {"schema_version": 1, "phases": {"P%02d" % i: [] for i in range(17)}}
        self.write("CHECKS.json", self.config)
        # Fixtures must start at their own P00, even when the real project advances.
        # Never copy real acceptance claims without their evidence into a synthetic root.
        plan = q.load(self.root / "ROADMAP.json")
        plan["transfer_policy"]["application_source_supplied"] = False
        self.write("ROADMAP.json", plan)
        progress = q.load(self.root / "PROGRESS.json")
        progress["current_phase"] = "P00"
        progress["application_source_commit"] = None
        progress["verified_application_requirements"] = 0
        for index, phase in enumerate(progress["phases"]):
            phase.update(status="READY" if index == 0 else "BLOCKED", tests=[], exit_evidence=[],
                         blockers=[] if index == 0 else ["پیش‌نیاز P%02d کامل نشده است." % (index - 1)])
            for key in ("accepted_source_digest", "accepted_receipt_sha256", "accepted_review_sha256",
                        "evidence_preservation_record"):
                phase.pop(key, None)
        progress["resume"] = {"phase": "P00", "last_verified_checkpoint": None,
                              "next_action": "Synthetic guard fixture only"}
        for row in progress["runtime_conformance"]:
            row.update(implementation_status="UNVERIFIED", verification_status="NOT_RUN", evidence=[])
        self.write("PROGRESS.json", progress)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(q.encoded(data))

    def check(self, phase="P00", xml=None, code=0, writes=True):
        if xml is None:
            xml = '<testsuite tests="1"><testcase name="synthetic"/></testsuite>'
        junit = "evidence/generated/" + phase + ".xml"
        program = ("from pathlib import Path; p=Path(" + repr(junit) + "); "
                   "p.parent.mkdir(parents=True,exist_ok=True); ")
        if writes:
            program += "p.write_text(" + repr(xml) + "); "
        program += "print('synthetic runner'); raise SystemExit(" + str(code) + ")"
        entry = {"id": phase + "_test", "kind": "test",
                 "argv": ["{python}", "-c", program], "junit": junit}
        self.config["phases"][phase] = [entry]
        self.write("CHECKS.json", self.config)
        return entry

    def ready(self):
        self.check()
        path, receipt = q.run(self.root, "P00")
        draft = q.template(self.root, "P00", "evidence/reviews/P00.json")
        review = q.load(draft)
        review.update(status="PASS", reviewer="synthetic reviewer", method="synthetic gate fixture",
                      impact_assessment="Synthetic fixture has no application behavior")
        evidence_path = self.root / "evidence" / "criterion.txt"
        evidence_path.write_text("Synthetic criterion witness; not an application result")
        entry = {"path": "evidence/criterion.txt", "sha256": q.digest(evidence_path.read_bytes())}
        for criterion in review["criteria"]:
            criterion.update(status="PASS", notes="Synthetic test fixture", evidence=[entry])
        draft.write_bytes(q.encoded(review))
        return path.relative_to(self.root).as_posix(), "evidence/reviews/P00.json"

    def transfer(self):
        names = [p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                 if p.is_file() and p.relative_to(self.root).parts[0] != "evidence"]
        names.append("TRANSFER_FILES.json")
        self.write("TRANSFER_FILES.json", {"files": sorted(set(names))})
        out = Path(self.tmp.name) / "handoff.zip"
        return out

    def test_initial_status_retains_unverified_application(self):
        _, progress, phase = q.state(self.root)
        self.assertEqual(phase, "P00")
        self.assertEqual(progress["verified_application_requirements"], 0)

    def test_source_fingerprint_order_is_portable_across_native_path_ordering(self):
        (self.root / "Z-UPPER.md").write_text("upper")
        (self.root / "a-lower.py").write_text("lower")
        class WindowsOrderedPath:
            def __init__(self, real):
                self.real = real
            def __lt__(self, other):
                return str(self.real).casefold() < str(other.real).casefold()
            def relative_to(self, root):
                return self.real.relative_to(root.real)
            def iterdir(self):
                return (WindowsOrderedPath(p) for p in self.real.iterdir())
            def __getattr__(self, name):
                return getattr(self.real, name)
        class WindowsOrderedRoot:
            real = self.root
            def iterdir(self):
                return (WindowsOrderedPath(p) for p in self.real.iterdir())
        self.assertEqual(q.source_rows(self.root), q.source_rows(WindowsOrderedRoot()))

    def test_no_registered_checks_blocks_phase(self):
        with self.assertRaises(q.Blocked):
            q.run(self.root, "P00")

    def test_out_of_order_phase_is_blocked(self):
        self.check("P01")
        with self.assertRaises(q.Blocked):
            q.run(self.root, "P01")

    def test_successful_command_without_junit_fails(self):
        self.check(writes=False)
        self.assertEqual(q.run(self.root, "P00")[1]["status"], "FAIL")

    def test_old_junit_is_not_reused(self):
        self.check(writes=False)
        path = self.root / "evidence/generated/P00.xml"
        path.parent.mkdir(parents=True)
        path.write_text('<testsuite tests="1"><testcase/></testsuite>')
        self.assertEqual(q.run(self.root, "P00")[1]["status"], "FAIL")

    def test_zero_tests_fails(self):
        self.check(xml='<testsuite tests="0"/>')
        self.assertEqual(q.run(self.root, "P00")[1]["status"], "FAIL")

    def test_skipped_test_fails(self):
        self.check(xml='<testsuite tests="1"><testcase><skipped/></testcase></testsuite>')
        self.assertEqual(q.run(self.root, "P00")[1]["status"], "FAIL")

    def test_failing_junit_overrides_zero_exit(self):
        self.check(xml='<testsuite tests="1"><testcase><failure/></testcase></testsuite>')
        self.assertEqual(q.run(self.root, "P00")[1]["status"], "FAIL")

    def test_nonzero_exit_overrides_passing_junit(self):
        self.check(code=5)
        self.assertEqual(q.run(self.root, "P00")[1]["status"], "FAIL")

    def test_inconsistent_junit_totals_fail(self):
        self.check(xml='<testsuite tests="99"><testcase/></testsuite>')
        self.assertEqual(q.run(self.root, "P00")[1]["status"], "FAIL")

    def test_source_change_invalidates_receipt(self):
        receipt, review = self.ready()
        (self.root / "new_source.py").write_text("changed = True\n")
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review)

    def test_progress_change_invalidates_receipt(self):
        receipt, review = self.ready()
        data = q.load(self.root / "PROGRESS.json")
        data["phases"][0]["actual_engineering_hours"] = 1
        self.write("PROGRESS.json", data)
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review)

    def test_missing_exit_criterion_blocks(self):
        receipt, review = self.ready()
        data = q.load(self.root / review)
        data["criteria"].pop()
        self.write(review, data)
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review)

    def test_changed_criterion_text_blocks(self):
        receipt, review = self.ready()
        data = q.load(self.root / review)
        data["criteria"][0]["criterion"] = "Unrelated criterion"
        self.write(review, data)
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review)

    def test_unknown_finding_type_cannot_hide_a_defect(self):
        receipt, review = self.ready()
        data = q.load(self.root / review)
        data["findings"] = [{"kind": "defect", "state": "OPEN"}]
        self.write(review, data)
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review)

    def test_known_low_severity_defect_blocks(self):
        receipt, review = self.ready()
        data = q.load(self.root / review)
        data["findings"] = [{"kind": "DEFECT", "state": "OPEN", "severity": "LOW"}]
        self.write(review, data)
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review)

    def test_tampered_log_blocks(self):
        receipt, review = self.ready()
        data = q.load(self.root / receipt)
        (self.root / data["checks"][0]["log"]).write_text("replacement")
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review)

    def test_accepted_phase_advances_only_one_step(self):
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        _, progress, current = q.state(self.root)
        self.assertEqual(current, "P01")
        self.assertEqual(progress["phases"][1]["status"], "READY")
        self.assertTrue(all(p["status"] == "BLOCKED" for p in progress["phases"][2:]))
        self.assertEqual(progress["verified_application_requirements"], 0)

    def test_accepted_criterion_bytes_survive_later_changes(self):
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        (self.root / "evidence/criterion.txt").write_text("Later phase changed the original artifact")
        out = self.transfer()
        q.handoff(self.root, out)
        self.assertEqual(q.verify(out)["status"], "PASS")
        progress = q.load(self.root / "PROGRESS.json")
        frozen = q.load(self.root / progress["phases"][0]["exit_evidence"][0])
        witness = frozen["criteria"][0]["evidence"][0]
        self.assertIn("Synthetic criterion witness", q.artifact(self.root, witness).read_text())

    def test_handoff_keeps_native_report_graph_without_editing_source_allowlist(self):
        self.write("SCOPE.json", {"target_platforms": ["Linux", "Windows"]})
        out = self.transfer()
        original_allowlist = (self.root / "TRANSFER_FILES.json").read_bytes()
        evidence = self.root / "evidence/targets/Linux/synthetic/TEST.xml"
        evidence.parent.mkdir(parents=True)
        evidence.write_text('<testsuite tests="1"><testcase name="synthetic"/></testsuite>')
        report_name = "evidence/targets/Linux/synthetic/RUN.json"
        self.write(report_name, {"status": "PASS", "source_digest_before": q.source_digest(self.root),
                                "artifacts": {"junit": {"path": evidence.relative_to(self.root).as_posix(),
                                                        "sha256": q.digest(evidence.read_bytes())}}})
        self.write("evidence/targets/Linux/LATEST.json", {"path": report_name,
                                                         "sha256": q.digest((self.root / report_name).read_bytes())})
        q.handoff(self.root, out)
        with zipfile.ZipFile(out) as archive:
            self.assertIn(report_name, archive.namelist())
            self.assertIn(evidence.relative_to(self.root).as_posix(), archive.namelist())
        self.assertEqual((self.root / "TRANSFER_FILES.json").read_bytes(), original_allowlist)

    def test_existing_acceptance_evidence_can_be_preserved_without_advancing(self):
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        # Model an older accepted record created before automatic snapshots.
        data = q.load(self.root / "PROGRESS.json")
        data["phases"][0]["exit_evidence"] = [review]
        data["phases"][0]["accepted_review_sha256"] = q.digest((self.root / review).read_bytes())
        self.write("PROGRESS.json", data)
        old_review_bytes = (self.root / review).read_bytes()
        result = q.preserve_accepted_evidence(self.root, "P00")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(q.state(self.root)[2], "P01")
        self.assertEqual((self.root / review).read_bytes(), old_review_bytes)
        self.assertNotEqual(q.load(self.root / "PROGRESS.json")["phases"][0]["exit_evidence"][0], review)

    def test_preservation_refuses_already_changed_original_proof(self):
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        data = q.load(self.root / "PROGRESS.json")
        data["phases"][0]["exit_evidence"] = [review]
        data["phases"][0]["accepted_review_sha256"] = q.digest((self.root / review).read_bytes())
        self.write("PROGRESS.json", data)
        (self.root / "evidence/criterion.txt").write_text("tampered")
        before = (self.root / "PROGRESS.json").read_bytes()
        with self.assertRaises(q.Blocked):
            q.preserve_accepted_evidence(self.root, "P00")
        self.assertEqual((self.root / "PROGRESS.json").read_bytes(), before)

    def test_independent_next_phase_blocker_is_preserved(self):
        data = q.load(self.root / "PROGRESS.json")
        data["phases"][1]["blockers"].append("Independent unresolved prerequisite")
        self.write("PROGRESS.json", data)
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        _, progress, current = q.state(self.root)
        self.assertEqual(current, "P01")
        self.assertEqual(progress["phases"][1]["status"], "BLOCKED")
        self.assertEqual(progress["phases"][1]["blockers"], ["Independent unresolved prerequisite"])
        with self.assertRaises(q.Blocked):
            q.run(self.root, "P01")

    def test_gate_lock_blocks_parallel_update(self):
        receipt, review = self.ready()
        (self.root / "evidence/gate.lock").write_text("other owner")
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", receipt, review, True)
        self.assertEqual(q.state(self.root)[2], "P00")

    def test_fabricated_completed_status_is_rejected(self):
        data = q.load(self.root / "PROGRESS.json")
        data["phases"][0]["status"] = "COMPLETED"
        self.write("PROGRESS.json", data)
        with self.assertRaises(q.Blocked):
            q.state(self.root)

    def test_changed_baseline_is_rejected(self):
        p = next((self.root / "baseline").iterdir())
        p.write_bytes(p.read_bytes() + b"changed")
        with self.assertRaises(q.Blocked):
            q.state(self.root)

    def test_duplicate_check_ids_are_rejected(self):
        entry = self.check()
        self.config["phases"]["P00"].append(entry)
        self.write("CHECKS.json", self.config)
        with self.assertRaises(q.Blocked):
            q.run(self.root, "P00")

    def test_shared_junit_output_is_rejected(self):
        entry = self.check()
        self.config["phases"]["P00"].append({**entry, "id": "another_test"})
        self.write("CHECKS.json", self.config)
        with self.assertRaises(q.Blocked):
            q.run(self.root, "P00")

    def test_invalid_timeout_is_rejected(self):
        self.check()
        self.config["phases"]["P00"][0]["timeout_seconds"] = -1
        self.write("CHECKS.json", self.config)
        with self.assertRaises(q.Blocked):
            q.run(self.root, "P00")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(q.Blocked):
            q.safe_path(self.root, "../outside")

    def test_symlink_is_rejected(self):
        (self.root / "link").symlink_to(self.root / "ROADMAP.json")
        with self.assertRaises(q.Blocked):
            q.safe_path(self.root, "link")

    def test_regression_checks_are_included(self):
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        self.check("P01")
        _, record = q.run(self.root, "P01")
        self.assertEqual(record["status"], "PASS")
        self.assertEqual([x["id"] for x in record["checks"]], ["P00_test", "P01_test"])
        old = q.load(self.root / receipt)
        archived = self.root / old["checks"][0]["junit"]
        self.assertEqual(q.digest(archived.read_bytes()), old["checks"][0]["junit_sha256"])

    def test_expensive_acceptance_check_is_not_silently_repeated(self):
        base = self.check()
        expensive = {**base, "id": "expensive_evaluation",
                     "junit": "evidence/generated/evaluation.xml",
                     "execution_mode": "REAL_EVALUATION",
                     "acceptance_only": True, "reason": "Full real evaluation has a separate budget"}
        program = base["argv"][-1].replace("evidence/generated/P00.xml",
                                         "evidence/generated/evaluation.xml")
        expensive["argv"] = ["{python}", "-c", program]
        self.config["phases"]["P00"].append(expensive)
        self.write("CHECKS.json", self.config)
        _, _, checks = q.selected(self.root, "P00")
        self.assertEqual(len(checks), 2)
        receipt, review = self.ready()
        # ready() registers the ordinary fixture; append the expensive fixture again.
        self.config["phases"]["P00"].append(expensive)
        self.write("CHECKS.json", self.config)
        path, record = q.run(self.root, "P00")
        data = q.load(self.root / review)
        data["source_digest"] = q.source_digest(self.root)
        self.write(review, data)
        q.gate(self.root, "P00", path.relative_to(self.root).as_posix(), review, True)
        self.check("P01")
        _, _, checks = q.selected(self.root, "P01")
        self.assertEqual([x["id"] for x in checks], ["P00_test", "P01_test"])

    def test_incomplete_handoff_is_explicit(self):
        out = self.transfer()
        info = q.handoff(self.root, out)
        self.assertEqual(info["state_label"], "INCOMPLETE")
        self.assertFalse(info["application_source_supplied"])
        self.assertIsNone(info["last_accepted_phase"])
        self.assertEqual(q.verify(out)["status"], "PASS")

    def test_handoff_keeps_precise_in_phase_resume_point(self):
        data = q.load(self.root / "PROGRESS.json")
        data["resume"].update(next_action="Continue an explicitly recorded unfinished subtask",
                              working_changes=["partial_module.py"], next_command=["python", "--version"])
        self.write("PROGRESS.json", data)
        out = self.transfer()
        info = q.handoff(self.root, out)
        self.assertEqual(info["next_action"], data["resume"]["next_action"])
        self.assertEqual(info["resume"]["working_changes"], ["partial_module.py"])

    def test_handoff_roundtrip_preserves_source_fingerprint(self):
        out = self.transfer()
        info = q.handoff(self.root, out)
        restored = Path(self.tmp.name) / "restored"
        with zipfile.ZipFile(out) as archive:
            archive.extractall(restored)
        self.assertEqual(q.source_digest(restored), info["source_snapshot_digest"])
        self.assertEqual(q.state(restored)[2], "P00")

    def test_handoff_includes_accepted_evidence(self):
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        out = self.transfer()
        q.handoff(self.root, out)
        with zipfile.ZipFile(out) as archive:
            self.assertIn(receipt, archive.namelist())
            self.assertIn(review, archive.namelist())

    def test_omitted_source_is_rejected(self):
        out = self.transfer()
        (self.root / "forgotten.py").write_text("value = 1")
        with self.assertRaises(q.Blocked):
            q.handoff(self.root, out)

    def test_sensitive_file_is_rejected(self):
        (self.root / ".env").write_text("fixture only")
        out = self.transfer()
        with self.assertRaises(q.Blocked):
            q.handoff(self.root, out)

    def test_empty_multiline_environment_example_is_safe(self):
        q.secret_check(".env.example", b"CONSILIUM_OPENAI_API_KEY=\nCONSILIUM_ANTHROPIC_API_KEY=\n")

    def test_nonempty_recognizable_environment_credential_is_rejected(self):
        payload = b"CONSILIUM_TEST_API_KEY=" + b"f" * 32
        with self.assertRaises(q.Blocked):
            q.secret_check(".env.example", payload)

    def test_archive_byte_tampering_is_rejected(self):
        out = self.transfer()
        q.handoff(self.root, out)
        with zipfile.ZipFile(out) as archive:
            data = {n: archive.read(n) for n in archive.namelist()}
        data["START_HERE_FA.md"] += b"changed"
        with zipfile.ZipFile(out, "w") as archive:
            for n, content in data.items():
                archive.writestr(n, content)
        with self.assertRaises(q.Blocked):
            q.verify(out)

    def test_archive_unsafe_member_is_rejected(self):
        out = Path(self.tmp.name) / "unsafe.zip"
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("../escape", "bad")
        with self.assertRaises(q.Blocked):
            q.verify(out)

    def test_archive_case_collisions_are_rejected(self):
        out = Path(self.tmp.name) / "collision.zip"
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("A.txt", "one")
            archive.writestr("a.txt", "two")
        with self.assertRaises(q.Blocked):
            q.verify(out)

    def test_missing_review_does_not_advance_progress(self):
        self.check()
        path, _ = q.run(self.root, "P00")
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P00", path.relative_to(self.root).as_posix(), "evidence/missing.json", True)
        self.assertEqual(q.state(self.root)[2], "P00")

    def test_failed_work_in_progress_preserves_checkpoint_and_run(self):
        receipt, review = self.ready()
        q.gate(self.root, "P00", receipt, review, True)
        self.check("P01", xml='<testsuite tests="1"><testcase><failure>unfinished</failure></testcase></testsuite>', code=1)
        progress = q.load(self.root / "PROGRESS.json")
        progress["phases"][1]["status"] = "IN_PROGRESS"
        progress["resume"].update(next_action="Repair the failing current subtask", working_changes=["partial.py"])
        self.write("PROGRESS.json", progress)
        path, record = q.run(self.root, "P01")
        self.assertEqual(record["status"], "FAIL")
        with self.assertRaises(q.Blocked):
            q.gate(self.root, "P01", path.relative_to(self.root).as_posix(), review, True)
        out = self.transfer()
        info = q.handoff(self.root, out)
        self.assertEqual(info["last_accepted_phase"], "P00")
        self.assertEqual(info["latest_current_phase_run"]["status"], "FAIL")
        self.assertEqual(info["current_phase"], "P01")
        with zipfile.ZipFile(out) as archive:
            self.assertIn(receipt, archive.namelist())
            self.assertIn(path.relative_to(self.root).as_posix(), archive.namelist())
            for check in record["checks"]:
                self.assertIn(check["log"], archive.namelist())
                self.assertIn(check["junit"], archive.namelist())

    def test_current_failed_run_without_junit_keeps_error_and_log(self):
        self.check(writes=False)
        path, record = q.run(self.root, "P00")
        out = self.transfer()
        info = q.handoff(self.root, out)
        self.assertEqual(info["latest_current_phase_run"]["status"], "FAIL")
        with zipfile.ZipFile(out) as archive:
            kept = json.loads(archive.read(path.relative_to(self.root).as_posix()))
            self.assertIn("Missing/oversized JUnit", kept["checks"][0]["error"])
            self.assertIn(record["checks"][0]["log"], archive.namelist())

    def test_current_run_from_older_source_is_explicit(self):
        self.check()
        q.run(self.root, "P00")
        (self.root / "new_source.py").write_text("unfinished = True\n")
        out = self.transfer()
        info = q.handoff(self.root, out)
        self.assertFalse(info["latest_current_phase_run"]["source_matches_current"])
        self.assertEqual(q.state(self.root)[2], "P00")

    def test_current_run_receipt_tampering_blocks_handoff(self):
        self.check()
        path, _ = q.run(self.root, "P00")
        path.write_bytes(path.read_bytes() + b"\n")
        out = self.transfer()
        with self.assertRaises(q.Blocked):
            q.handoff(self.root, out)

    def test_current_run_log_tampering_blocks_handoff(self):
        self.check()
        _, record = q.run(self.root, "P00")
        (self.root / record["checks"][0]["log"]).write_text("changed")
        out = self.transfer()
        with self.assertRaises(q.Blocked):
            q.handoff(self.root, out)

    def test_current_run_junit_tampering_blocks_handoff(self):
        self.check()
        _, record = q.run(self.root, "P00")
        (self.root / record["checks"][0]["junit"]).write_text('<testsuite tests="0"/>')
        out = self.transfer()
        with self.assertRaises(q.Blocked):
            q.handoff(self.root, out)

    def test_latest_pointer_cannot_reference_another_phase(self):
        self.check()
        q.run(self.root, "P00")
        name = "evidence/latest/P00.json"
        pointer = q.load(self.root / name)
        pointer["phase"] = "P01"
        self.write(name, pointer)
        out = self.transfer()
        with self.assertRaises(q.Blocked):
            q.handoff(self.root, out)

    def test_navigation_does_not_advance_or_change_canonical_data(self):
        before = (self.root / "PROGRESS.json").read_bytes()
        q.navigation(self.root)
        self.assertEqual((self.root / "PROGRESS.json").read_bytes(), before)
        self.assertEqual(q.state(self.root)[2], "P00")
        self.assertEqual(q.navigation(self.root, check=True)["status"], "PASS")
        text = (self.root / "evidence/navigation/BACKLOG_FA.md").read_text(encoding="utf-8")
        self.assertIn("`P00`", text)
        self.assertIn("`BLOCKED`", text)
        self.assertIn(q.load(self.root / "ROADMAP.json")["phases"][0]["exit"][0], text)

    def test_navigation_detects_changed_progress_and_refreshes(self):
        q.navigation(self.root)
        progress = q.load(self.root / "PROGRESS.json")
        progress["resume"]["next_action"] = "A newly recorded subtask"
        self.write("PROGRESS.json", progress)
        with self.assertRaises(q.Blocked):
            q.navigation(self.root, check=True)
        q.navigation(self.root)
        self.assertEqual(q.navigation(self.root, check=True)["status"], "PASS")

    def test_handoff_includes_generated_navigation(self):
        q.navigation(self.root)
        out = self.transfer()
        q.handoff(self.root, out)
        with zipfile.ZipFile(out) as archive:
            self.assertIn("evidence/navigation/STATUS_FA.md", archive.namelist())
            self.assertIn("evidence/navigation/BACKLOG_FA.md", archive.namelist())

    def test_stale_navigation_blocks_handoff(self):
        q.navigation(self.root)
        progress = q.load(self.root / "PROGRESS.json")
        progress["resume"]["next_action"] = "Changed after navigation was generated"
        self.write("PROGRESS.json", progress)
        out = self.transfer()
        with self.assertRaises(q.Blocked):
            q.handoff(self.root, out)

    def test_manually_changed_navigation_is_not_a_second_truth(self):
        q.navigation(self.root)
        path = self.root / "evidence/navigation/STATUS_FA.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nInvented success\n", encoding="utf-8")
        with self.assertRaises(q.Blocked):
            q.navigation(self.root, check=True)

    def test_navigation_detects_changes_to_acceptance_checks(self):
        q.navigation(self.root)
        self.check()
        with self.assertRaises(q.Blocked):
            q.navigation(self.root, check=True)


if __name__ == "__main__":
    unittest.main()
