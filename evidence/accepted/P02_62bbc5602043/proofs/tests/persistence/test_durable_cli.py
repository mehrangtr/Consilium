"""Fresh-process CLI path, with real SQLite but zero live model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DurableCliTests(unittest.TestCase):
    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, str(ROOT / "tools/run_consilium.py"), *args], cwd=ROOT,
            capture_output=True, stdin=subprocess.DEVNULL, shell=False, timeout=15,
            env=os.environ | {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        return proc.returncode, json.loads(proc.stdout.decode("utf-8"))

    def test_persist_restart_and_resume_keep_original_question_and_one_canonical_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.sqlite3")
            question = "  اصل سؤال؛ original\n"
            code, output = self.run_cli("durable-mock", "--database", path, "--question", question)
            self.assertEqual(code, 0); self.assertTrue(output["restart_verified"])
            self.assertEqual(output["export"]["debate"]["original_request"], question)
            self.assertEqual(output["resume"]["attempt"]["state"], "CONFIRMED")
            code, resumed = self.run_cli("resume", "--database", path, "--debate-id", output["export"]["debate"]["debate_id"])
            self.assertEqual(code, 0); self.assertEqual(resumed["provider_calls"], 0)
            self.assertEqual(resumed["export"], output["export"])
            self.assertEqual(len(resumed["export"]["canonical_results"]), 1)
            self.assertFalse(resumed["debate_completed"])

    def test_browser_mock_ambiguous_resume_keeps_the_same_attempt_and_never_resends(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.sqlite3")
            code, output = self.run_cli("durable-mock", "--database", path, "--question", "offline",
                                       "--mode", "BROWSER", "--scenario", "timeout_after_send")
            self.assertEqual(code, 2)
            self.assertEqual(output["resume"]["attempt"]["state"], "UNKNOWN_DELIVERY")
            code, resumed = self.run_cli("resume", "--database", path, "--debate-id", output["export"]["debate"]["debate_id"])
            self.assertEqual(code, 0); self.assertEqual(resumed["provider_calls"], 0)
            self.assertEqual(resumed["export"], output["export"])
            self.assertEqual(resumed["resume"][0]["action"], "VERIFY_DELIVERY")
            self.assertFalse(resumed["resume"][0]["automatic_send"])

    def test_new_demo_cannot_overwrite_or_send_again_to_an_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.sqlite3")
            _, output = self.run_cli("durable-mock", "--database", path, "--question", "first")
            code, error = self.run_cli("durable-mock", "--database", path, "--question", "replacement")
            self.assertEqual(code, 1); self.assertEqual(error["status"], "ERROR")
            _, resumed = self.run_cli("resume", "--database", path, "--debate-id", output["export"]["debate"]["debate_id"])
            self.assertEqual(resumed["export"], output["export"])

    def test_resume_missing_database_does_not_create_a_blank_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite3"
            code, output = self.run_cli("resume", "--database", str(path), "--debate-id", "bad-id")
            self.assertEqual(code, 1); self.assertFalse(path.exists())
