"""Failure preservation tests with synthetic subprocesses, never native OS proof."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import qualityctl as q
import record_target_checks as recorder
from test_target_checks import synthetic_smoke_rows


class NativeRecordingControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "SCOPE.json").write_bytes(q.encoded({"target_platforms": ["Linux"]}))

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, execution):
        with patch.object(recorder, "ROOT", self.root), patch.object(q, "navigation"), \
             patch.object(recorder.platform, "system", return_value="Linux"), \
             patch.object(recorder.subprocess, "run", side_effect=execution), \
             contextlib.redirect_stdout(io.StringIO()):
            return recorder.main()

    def latest(self):
        return q.load(q.artifact(self.root, q.load(self.root / "evidence/targets/Linux/LATEST.json")))

    def smoke(self, argv):
        rows = synthetic_smoke_rows()
        mode, scenario = argv[argv.index("--mode") + 1], argv[argv.index("--scenario") + 1]
        row = next(r for r in rows if (r["mode"], r["scenario"]) == (mode, scenario))
        return subprocess.CompletedProcess(argv, row["returncode"], json.dumps(row["output"]).encode(), b"")

    def test_old_mutable_reports_cannot_be_reused_as_a_fresh_native_run(self):
        for role, name in (
            ("maintenance", "RUN.json"), ("environment", "RUN.json"),
            ("control-tests", "RUN.json"), ("control-tests", "JUNIT.xml"),
            ("foundation-tests", "RUN.json"), ("foundation-tests", "JUNIT.xml"),
        ):
            folder = self.root / "evidence" / ("maintenance-check" if role == "maintenance" else role)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(b"stale synthetic report")
        def execution(argv, **kwargs):
            if argv[1] == "tools/check.py":
                return subprocess.CompletedProcess(argv, 0, b"did not produce new reports")
            return self.smoke(argv)
        self.assertEqual(self.invoke(execution), 1)
        report = self.latest()
        self.assertEqual(report["status"], "FAIL")
        self.assertNotIn("foundation_report", report["artifacts"])

    def test_failure_before_reports_exist_still_publishes_a_failed_checkpoint(self):
        def execution(argv, **kwargs):
            if argv[1] == "tools/check.py":
                return subprocess.CompletedProcess(argv, 1, b"synthetic import failure")
            return self.smoke(argv)
        self.assertEqual(self.invoke(execution), 1)
        self.assertEqual(self.latest()["status"], "FAIL")

    def test_timed_out_check_preserves_partial_log_and_failed_checkpoint(self):
        def execution(argv, **kwargs):
            if argv[1] == "tools/check.py":
                raise subprocess.TimeoutExpired(argv, 60, output=b"synthetic partial check log")
            return self.smoke(argv)
        self.assertEqual(self.invoke(execution), 1)
        report = self.latest()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(b"synthetic partial check log", q.artifact(self.root, report["artifacts"]["check_log"]).read_bytes())
