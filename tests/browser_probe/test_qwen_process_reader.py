"""Real process budgets and fixture-only capture ingestion, on both native OSes."""

import base64
import json
import sys
import time
import unittest
from pathlib import Path
from uuid import uuid4

import test_qwen_capture_journal

from consilium.adapters.qwen_process_reader import (
    QwenProcessReader,
    decode_reader_output,
)
from consilium.shell.qwen_capture_ingest import record_qwen_read

FIXTURE = Path(__file__).with_name("qwen_reader_fixture.py")


class QwenProcessReaderTests(unittest.TestCase):
    def setUp(self):
        self.f = test_qwen_capture_journal.QwenCaptureJournalTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        context = self.f.f.f.context.model_dump(mode="json")
        self.value = {
            "schema_version": 1, "before": context, "after": context,
            "raw_capture_base64": base64.b64encode(self.f.raw).decode("ascii"),
        }
        self.packet = self.f.root / "packet.json"
        self.packet.write_bytes(json.dumps(self.value).encode())

    def reader(self, mode, path=None, timeout=10):
        return QwenProcessReader(
            (sys.executable, str(FIXTURE), mode, str(path or self.packet)),
            timeout_seconds=timeout,
        )

    def test_actual_process_exact_capture_ingest_and_reuse_without_process(self):
        reader = self.reader("success")
        result = record_qwen_read(self.f.journal, reader, event_id=self.f.event, expected_revision=0)
        self.assertEqual(result["raw"], self.f.raw)
        self.assertFalse(result["live_origin_verified"])
        self.packet.unlink()
        replay = record_qwen_read(self.f.open(), reader, event_id=self.f.event, expected_revision=0)
        self.assertTrue(replay["reused"])
        self.assertFalse(replay["reader_invoked"])

    def test_actual_process_timeout_stops_descendant_and_preserves_partial(self):
        self.f.append()
        heartbeat = self.f.root / "heartbeat"
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "QWEN_READ_FAILED"):
            record_qwen_read(
                self.f.journal, self.reader("hang", heartbeat, timeout=5),
                event_id=uuid4(), expected_revision=1,
            )
        self.assertLess(time.monotonic() - started, 11)
        self.assertTrue(heartbeat.exists(), "Owned descendant must actually start")
        before = heartbeat.read_bytes()
        time.sleep(0.2)
        self.assertEqual(heartbeat.read_bytes(), before)
        self.assertEqual(self.f.open().resume()["revision"], 1)
        self.assertEqual(self.f.open().read_qwen_capture(event_id=self.f.event)["raw"], self.f.raw)

    def test_actual_process_failure_does_not_export_stderr(self):
        with self.assertRaisesRegex(ValueError, "QWEN_READER_PROCESS_FAILED") as caught:
            self.reader("failure")()
        self.assertNotIn("sensitive-marker", str(caught.exception))
        self.assertIsNone(caught.exception.__context__)

    def test_actual_process_output_limit_stops_without_unbounded_buffer(self):
        with self.assertRaisesRegex(ValueError, "QWEN_READER_OUTPUT_OVERSIZED"):
            self.reader("flood")()
        self.assertEqual(self.f.open().resume()["revision"], 0)

    def test_invalid_output_base64_duplicates_versions_and_depth_are_rejected(self):
        for raw in (b"", b"\xff", b'{"schema_version":1,"schema_version":1}', b"[" * 70 + b"0" + b"]" * 70):
            with self.assertRaisesRegex(ValueError, "QWEN_READER_OUTPUT_INVALID") as caught:
                decode_reader_output(raw)
            self.assertIsNone(caught.exception.__context__)
        for change in (
            {"schema_version": True}, {"schema_version": 2},
            {"raw_capture_base64": "%%sensitive-marker"}, {"trusted_live": True},
        ):
            with self.assertRaisesRegex(ValueError, "QWEN_READER_OUTPUT_INVALID"):
                decode_reader_output(json.dumps({**self.value, **change}).encode())

    def test_invalid_command_and_budget_fail_before_start(self):
        for command, seconds in (
            ([], 1), ((), 1), (("bad\0command",), 1),
            (("python",), True), (("python",), float("nan")),
            (("python",), 0), (("python",), 61),
        ):
            with self.assertRaisesRegex(ValueError, "QWEN_READER_CONFIGURATION_INVALID"):
                QwenProcessReader(command, timeout_seconds=seconds)
