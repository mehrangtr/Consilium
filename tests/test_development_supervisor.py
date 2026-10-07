"""Real tree termination and reconciliation; no five-minute waits in the suite."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

import qualityctl as q
from development_progress import atomic_json
from development_supervisor import IDLE_SECONDS, Step, read_progress, reconcile, supervise, timeout_reason

FIXTURE = Path(__file__).with_name("development") / "worker_fixture.py"


class DevelopmentSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "evidence").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def step(self, mode, replay_safe=True):
        return Step(mode, (sys.executable, str(FIXTURE), str(self.root), mode), replay_safe)

    def run_steps(self, *modes, retry_limit=0):
        path = supervise(self.root, tuple(self.step(m) for m in modes), idle_seconds=0.8,
                         hard_seconds=3, retry_limit=retry_limit)
        return json.loads(path.read_text(encoding="utf-8"))

    def assert_child_stopped(self):
        marker = self.root / "evidence/CHILD_ALIVE"
        self.assertTrue(marker.exists(), "Fixture child must really have started")
        before = marker.read_bytes()
        time.sleep(0.15)
        self.assertEqual(before, marker.read_bytes(), "Owned descendant still running")

    def test_default_is_five_minutes_since_progress_not_start(self):
        self.assertEqual(IDLE_SECONDS, 300)
        self.assertIsNone(timeout_reason(0, 10, 309.99))
        self.assertEqual(timeout_reason(0, 10, 310), "IDLE_TIMEOUT")
        self.assertEqual(timeout_reason(0, 899, 900), "HARD_TIMEOUT")

    def test_output_noise_cannot_prevent_killing_parent_and_child(self):
        result = self.run_steps("hang", "complete")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["steps"][0]["stop_reason"], "IDLE_TIMEOUT")
        self.assertFalse((self.root / "evidence/NEXT_RAN").exists())
        self.assert_child_stopped()

    def test_nested_child_cannot_reset_owners_progress(self):
        result = self.run_steps("child_progress")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertNotIn("last_completed_milestone", result["steps"][0])
        self.assert_child_stopped()

    def test_completed_receipt_before_hang_is_reverified_and_queue_continues(self):
        result = self.run_steps("complete_hang", "complete")
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual([r["status"] for r in result["steps"]], ["RECOVERED_COMPLETE", "COMPLETE"])
        self.assertEqual(result["remaining_steps"], [])
        self.assertFalse(result["phase_advanced"])
        self.assert_child_stopped()

    def test_successful_parent_does_not_leave_unfinished_child(self):
        result = self.run_steps("complete_with_child")
        self.assertEqual(result["status"], "PASS", result)
        # The child may be killed before its first write; if it ran, it must stop.
        if (self.root / "evidence/CHILD_ALIVE").exists():
            self.assert_child_stopped()

    def test_old_pass_never_advances_to_next_command(self):
        result = self.run_steps("stale", "complete")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("another execution", result["steps"][0]["reconciliation"]["reason"])
        self.assertEqual(len(result["steps"]), 1)

    def test_incomplete_safe_check_retries_once_and_preserves_both_attempts(self):
        result = self.run_steps("hang", retry_limit=1)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(len(result["steps"]), 2)
        self.assertNotEqual(result["steps"][0]["nonce"], result["steps"][1]["nonce"])
        self.assert_child_stopped()

    def test_nonreplayable_step_is_not_resent_after_timeout(self):
        path = supervise(self.root, (self.step("hang", False),), idle_seconds=0.8,
                         hard_seconds=3, retry_limit=1)
        result = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["status"], "BLOCKED")
        self.assert_child_stopped()

    def test_wrong_nonce_pid_duplicate_milestone_and_sequence_are_not_progress(self):
        path = self.root / "evidence/PROGRESS.json"
        valid = {"nonce": "new", "task_pid": 12, "sequence": 3, "milestone": "done"}
        atomic_json(path, valid)
        self.assertIsNotNone(read_progress(path, "new", 12, 2, set()))
        self.assertIsNone(read_progress(path, "old", 12, 2, set()))
        self.assertIsNone(read_progress(path, "new", 13, 2, set()))
        self.assertIsNone(read_progress(path, "new", 12, 3, set()))
        self.assertIsNone(read_progress(path, "new", 12, 2, {"done"}))

    def test_changed_source_or_modified_receipt_blocks_reconciliation(self):
        source = q.source_digest(self.root)
        path = self.root / "evidence/receipt.json"
        receipt = {"development_step_id": "new", "status": "PASS",
                   "source_digest_before": source, "source_digest_after": source}
        atomic_json(path, receipt)
        progress = {"receipt": {"path": str(path), "sha256": q.digest(path.read_bytes())}}
        self.assertEqual(reconcile(self.root, progress, "new", source)["status"], "VERIFIED_COMPLETE")
        (self.root / "source.py").write_text("changed = True", encoding="utf-8")
        self.assertEqual(reconcile(self.root, progress, "new", source)["status"], "INCOMPLETE")
        (self.root / "source.py").unlink()
        path.write_text("{}", encoding="utf-8")
        self.assertEqual(reconcile(self.root, progress, "new", source)["status"], "INCOMPLETE")

    def test_missing_declared_artifact_cannot_be_reconciled_as_complete(self):
        source = q.source_digest(self.root)
        path = self.root / "evidence/receipt.json"
        atomic_json(path, {"development_step_id": "new", "status": "PASS",
                          "source_digest_before": source, "source_digest_after": source,
                          "artifacts": {"missing": {"path": "evidence/missing.log", "sha256": "0"*64}}})
        progress = {"receipt": {"path": str(path), "sha256": q.digest(path.read_bytes())}}
        self.assertEqual(reconcile(self.root, progress, "new", source)["status"], "INCOMPLETE")
