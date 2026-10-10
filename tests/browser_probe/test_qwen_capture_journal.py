"""Atomic captured bytes with synthetic provenance and real commit-boundary exits."""

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import test_qwen_page_reader

from consilium.shell.browser_watch_journal import BrowserWatchJournal
from consilium.shell.private import PublicBoundaryError


class QwenCaptureJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.f = test_qwen_page_reader.QwenPageReaderTests()
        self.f.setUp()
        self.arguments = {
            "operation_id": uuid4(),
            "request_hash": "e" * 64,
            "binding": self.f.f.binding,
            "baseline": self.f.f.base,
            "prompt_hash": self.f.f.watch.prompt_hash,
        }
        self.path = self.root / "journal.sqlite3"
        self.journal = self.open()
        self.event = uuid4()
        self.raw = (
            json.dumps(self.f.capture, ensure_ascii=False, indent=2)
            .replace("\n", "\r\n")
            .encode()
        )

    def tearDown(self):
        self.temp.cleanup()

    def open(self, **changes):
        return BrowserWatchJournal(self.path, **self.arguments, **changes)

    def append(self, raw=None, **changes):
        return self.journal.append_qwen_capture(
            self.raw if raw is None else raw,
            event_id=changes.get("event_id", self.event),
            expected_revision=changes.get("expected_revision", 0),
        )

    def test_exact_utf8_bytes_newlines_hash_and_partial_reopen(self):
        self.append()
        journal = self.open()
        stored = journal.read_qwen_capture(event_id=self.event)
        self.assertEqual(stored["raw"], self.raw)
        self.assertEqual(stored["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertFalse(stored["live_origin_verified"])
        self.assertEqual(journal.resume()["content"], "پاسخ\n")

    def test_exact_duplicate_replay_but_changed_encoding_is_rejected(self):
        self.append()
        self.assertEqual(self.append(), 1)
        with self.assertRaises(ValueError):
            self.append(self.f.raw())
        self.assertEqual(
            self.open().read_qwen_capture(event_id=self.event)["raw"], self.raw
        )
        self.assertEqual(self.open().resume()["revision"], 1)

    def test_stale_writer_cannot_append_capture(self):
        self.append()
        self.f.capture["sequence"] = 2
        with self.assertRaises(ValueError):
            self.append(self.f.raw(), event_id=uuid4(), expected_revision=0)
        self.assertEqual(self.open().resume()["revision"], 1)

    def test_malformed_and_deep_capture_preserve_previous_raw_and_partial(self):
        self.append()
        for raw in (b"{}", b"\xff", b"[" * 2000 + b"0" + b"]" * 2000):
            with self.assertRaises(ValueError):
                self.append(raw, event_id=uuid4(), expected_revision=1)
        self.assertEqual(self.open().resume()["revision"], 1)
        self.assertEqual(
            self.open().read_qwen_capture(event_id=self.event)["raw"], self.raw
        )

    def test_private_unicode_escaped_in_raw_json_is_rejected_before_commit(self):
        protected = self.open(forbidden_values=("محرمانه",))
        self.f.capture["response"]["raw_rendered_text"] = "محرمانه"
        raw = json.dumps(self.f.capture, ensure_ascii=True).encode()
        self.assertNotIn("محرمانه".encode(), raw)
        with self.assertRaises(PublicBoundaryError):
            protected.append_qwen_capture(raw, event_id=self.event, expected_revision=0)
        self.assertEqual(self.open().resume()["revision"], 0)

    def test_encoded_event_and_total_limits_apply_to_raw_capture(self):
        self.append()
        self.f.capture["sequence"] = 2
        for limit in ("MAX_EVENT_BYTES", "MAX_TOTAL_BYTES"):
            with (
                patch(
                    "consilium.shell.browser_watch_journal." + limit, len(self.raw) // 2
                ),
                self.assertRaises(ValueError),
            ):
                self.append(self.f.raw(), event_id=uuid4(), expected_revision=1)
        self.assertEqual(self.open().resume()["revision"], 1)

    def test_completion_keeps_original_capture_without_live_promotion(
        self,
    ):
        self.append()
        self.f.complete()
        self.f.capture["sequence"] = 2
        final = uuid4()
        self.append(self.f.raw(), event_id=final, expected_revision=1)
        result = self.open().resume()
        self.assertEqual(result["state"], "COMPLETE")
        self.assertFalse(result["live_origin_verified"])
        self.assertEqual(
            self.open().read_qwen_capture(event_id=self.event)["raw"], self.raw
        )
        self.assertEqual(
            self.open().read_qwen_capture(event_id=final)["raw"], self.f.raw()
        )

    def test_tampered_capture_blocks_both_raw_retrieval_and_replay(self):
        self.append()
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute("SELECT payload FROM events").fetchone()
            value = json.loads(row[0])
            value["raw_capture_utf8"] = value["raw_capture_utf8"].replace(
                "پاسخ", "تغییر"
            )
            db.execute("UPDATE events SET payload=?", (json.dumps(value),))
        for read in (
            lambda: self.journal.resume(),
            lambda: self.journal.read_qwen_capture(event_id=self.event),
        ):
            with self.assertRaises(ValueError):
                read()

    def test_missing_event_or_other_kind_has_no_capture(self):
        with self.assertRaises(ValueError):
            self.journal.read_qwen_capture(event_id=uuid4())
        self.journal.interrupt(event_id=self.event, expected_revision=0)
        with self.assertRaises(ValueError):
            self.journal.read_qwen_capture(event_id=self.event)

    def crash(self, stage, code, revision):
        config = {
            **self.journal.spec,
            "raw_capture_utf8": self.raw.decode(),
            "event_id": str(self.event),
        }
        fixture = self.root / "fixture.json"
        fixture.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        worker = Path(__file__).with_name("browser_watch_crash_worker.py")
        process = subprocess.run(
            [sys.executable, str(worker), str(self.path), str(fixture), stage],
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(process.returncode, code, process.stderr.decode())
        journal = self.open()
        self.assertEqual(journal.resume()["revision"], revision)
        if revision:
            self.assertEqual(
                journal.read_qwen_capture(event_id=self.event)["raw"], self.raw
            )
            self.assertEqual(journal.resume()["content"], "پاسخ\n")
        else:
            with self.assertRaises(ValueError):
                journal.read_qwen_capture(event_id=self.event)

    def test_actual_process_exit_before_raw_capture_commit_rolls_back_both(self):
        self.crash("before", 73, 0)

    def test_actual_process_exit_after_raw_capture_commit_recovers_both(self):
        self.crash("after", 74, 1)
