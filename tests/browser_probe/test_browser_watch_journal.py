"""Persistent P09 synthetic observations, including actual process exits."""

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

import test_browser_watch

from consilium.shell.browser_watch_journal import BrowserWatchJournal
from consilium.shell.private import PublicBoundaryError


class BrowserJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.f = test_browser_watch.BrowserWatchTests()
        self.f.setUp()
        self.arguments = {
            "operation_id": uuid4(),
            "request_hash": "e" * 64,
            "binding": self.f.binding,
            "baseline": self.f.base,
            "prompt_hash": self.f.watch.prompt_hash,
        }
        self.database = self.root / "observations.sqlite3"
        self.journal = self.open()
        self.page = self.f.page(1, (self.f.old, self.f.user, self.f.answer))

    def tearDown(self):
        self.temp.cleanup()

    def open(self, **changes):
        return BrowserWatchJournal(self.database, **{**self.arguments, **changes})

    def test_partial_reopens_and_completion_stays_closed(self):
        self.journal.append(self.page, event_id=uuid4(), expected_revision=0)
        self.assertEqual(self.open().resume()["content"], "پاسخ")
        final = self.f.answer.model_copy(
            update={
                "text": "پاسخ کامل",
                "complete": True,
                "completion_evidence": ("c" * 64,),
            }
        )
        self.open().append(
            self.f.page(2, (self.f.old, self.f.user, final)),
            event_id=uuid4(),
            expected_revision=1,
        )
        r = self.open().resume()
        self.assertEqual(r["state"], "COMPLETE")
        self.assertEqual(r["next_action"], "STOP")
        with self.assertRaises(ValueError):
            self.open().interrupt(event_id=uuid4(), expected_revision=2)

    def test_committed_event_replay_is_idempotent_but_id_reuse_is_rejected(self):
        event = uuid4()
        self.journal.append(self.page, event_id=event, expected_revision=0)
        self.assertEqual(
            self.open().append(self.page, event_id=event, expected_revision=0), 1
        )
        with self.assertRaises(ValueError):
            self.open().append(
                self.f.page(2, (self.f.old,)), event_id=event, expected_revision=1
            )
        self.assertEqual(self.open().resume()["revision"], 1)

    def test_two_writers_stale_revision_cannot_overwrite(self):
        other = self.open()
        self.journal.append(self.page, event_id=uuid4(), expected_revision=0)
        with self.assertRaises(ValueError):
            other.interrupt(event_id=uuid4(), expected_revision=0)
        self.assertEqual(other.resume()["state"], "PARTIAL")

    def test_operation_binding_and_frozen_hash_cannot_change(self):
        for changes in (
            {"operation_id": uuid4()},
            {"request_hash": "f" * 64},
            {"binding": self.f.binding.model_copy(update={"connection_revision": 1})},
        ):
            with self.assertRaises(ValueError):
                self.open(**changes)
        self.assertEqual(self.journal.resume()["revision"], 0)

    def test_interrupt_and_context_loss_are_durable_without_resend(self):
        self.journal.append(self.page, event_id=uuid4(), expected_revision=0)
        self.open().interrupt(event_id=uuid4(), expected_revision=1)
        r = self.open().resume()
        self.assertEqual(r["content"], "پاسخ")
        self.assertTrue(r["stopped"])
        self.assertFalse(r["live_origin_verified"])

    def test_tampered_event_hash_or_header_blocks_reconstruction(self):
        self.journal.append(self.page, event_id=uuid4(), expected_revision=0)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE events SET payload='{}'")
        with self.assertRaises(ValueError):
            self.open().resume()

    def test_known_secret_rejected_before_append_and_limits_preserve_prior_state(self):
        protected = self.open(forbidden_values=("SENSITIVE_FIXTURE",))
        answer = self.f.answer.model_copy(update={"text": "SENSITIVE_FIXTURE"})
        with self.assertRaises(PublicBoundaryError):
            protected.append(
                self.f.page(1, (self.f.old, self.f.user, answer)),
                event_id=uuid4(),
                expected_revision=0,
            )
        self.assertEqual(self.journal.resume()["revision"], 0)
        self.journal.append(self.page, event_id=uuid4(), expected_revision=0)
        with (
            patch("consilium.shell.browser_watch_journal.MAX_EVENTS", 1),
            self.assertRaises(ValueError),
        ):
            self.journal.interrupt(event_id=uuid4(), expected_revision=1)
        self.assertEqual(self.journal.resume()["content"], "پاسخ")

    def test_deleted_tail_is_detected_by_committed_head(self):
        self.journal.append(self.page, event_id=uuid4(), expected_revision=0)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("DELETE FROM events WHERE revision=1")
        with self.assertRaises(ValueError):
            self.open().resume()

    def test_changed_header_or_invalid_revision_is_rejected(self):
        with self.assertRaises(ValueError):
            self.journal.append(self.page, event_id=uuid4(), expected_revision=True)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE header SET spec='{}'")
        with self.assertRaises(ValueError):
            self.open()

    def crash(self, stage, expected_code, revision):
        config = {
            **self.journal.spec,
            "snapshot": self.page.model_dump(mode="json"),
            "event_id": str(uuid4()),
        }
        path = self.root / "fixture.json"
        path.write_text(json.dumps(config, ensure_ascii=False))
        worker = Path(__file__).with_name("browser_watch_crash_worker.py")
        proc = subprocess.run(
            [sys.executable, str(worker), str(self.database), str(path), stage],
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, expected_code, proc.stderr.decode())
        r = self.open().resume()
        self.assertEqual(r["revision"], revision)
        self.assertEqual(r["content"], "پاسخ" if revision else None)
        self.assertEqual(r["next_action"], "OBSERVE_ONLY_NO_RESEND")

    def test_actual_process_exit_before_observation_commit_rolls_back(self):
        self.crash("before", 73, 0)

    def test_actual_process_exit_after_observation_commit_recovers_partial(self):
        self.crash("after", 74, 1)
