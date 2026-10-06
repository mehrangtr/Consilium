"""Development CI can report a blocker; the actual phase gate stays strict."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import qualityctl as q
import run_current_phase as phase_runner


class PhaseReportingControls(unittest.TestCase):
    def test_reporting_blocked_phase_never_runs_or_accepts_it(self):
        progress = {"phases": [{"id": "P03", "status": "BLOCKED"}]}
        output = io.StringIO()
        with patch.object(q, "state", return_value=({}, progress, "P03")), patch.object(q, "navigation"), \
             patch.object(q, "run") as run, contextlib.redirect_stdout(output):
            self.assertEqual(phase_runner.main(report_blocked=True), 0)
        run.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual((report["status"], report["execution"]), ("BLOCKED", "NOT_RUN"))
        self.assertFalse(report["phase_accepted"])

    def test_default_command_still_blocks_on_phase_gate(self):
        progress = {"phases": [{"id": "P03", "status": "BLOCKED"}]}
        with patch.object(q, "state", return_value=({}, progress, "P03")), patch.object(q, "navigation"), \
             patch.object(q, "run", side_effect=q.Blocked("Current phase blocked")):
            with self.assertRaises(q.Blocked):
                phase_runner.main()

    def test_reporting_option_never_hides_invalid_governance(self):
        with patch.object(q, "state", side_effect=q.Blocked("Invalid phase order")):
            with self.assertRaises(q.Blocked):
                phase_runner.main(report_blocked=True)
