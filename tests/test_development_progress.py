"""Ownership startup races must not lose a fast task's completion receipt."""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from development_progress import atomic_json, milestone


class DevelopmentProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.progress = self.root / "PROGRESS.json"
        self.environment = {
            "CONSILIUM_DEV_STEP_ID": "fixture-nonce",
            "CONSILIUM_DEV_PROGRESS": str(self.progress),
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_first_milestone_waits_for_owner_record_and_preserves_receipt(self):
        receipt = self.root / "receipt.json"
        atomic_json(receipt, {"status": "PASS"})

        def ready():
            time.sleep(0.03)
            atomic_json(
                self.root / "READY.json",
                {"nonce": "fixture-nonce", "task_pid": os.getpid()},
            )

        thread = threading.Thread(target=ready)
        thread.start()
        try:
            with patch.dict(os.environ, self.environment):
                milestone("receipt_committed", receipt=receipt)
        finally:
            thread.join(timeout=2)
        value = json.loads(self.progress.read_text(encoding="utf-8"))
        self.assertEqual(value["task_pid"], os.getpid())
        self.assertEqual(value["milestone"], "receipt_committed")
        self.assertIsNotNone(value["receipt"])

    def test_missing_ownership_remains_bounded_and_does_not_create_progress(self):
        with (
            patch.dict(os.environ, self.environment),
            patch("development_progress.time.monotonic", side_effect=[0.0, 3.0]),
        ):
            milestone("cannot_claim_owner")
        self.assertFalse(self.progress.exists())

    def test_wrong_owner_record_cannot_authorize_child_milestone(self):
        atomic_json(
            self.root / "READY.json",
            {"nonce": "fixture-nonce", "task_pid": os.getpid() + 1},
        )
        with patch.dict(os.environ, self.environment):
            milestone("child_claim")
        self.assertFalse(self.progress.exists())
