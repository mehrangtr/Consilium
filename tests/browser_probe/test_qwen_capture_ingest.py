"""Injected read packets are fixtures, never certified browser observations."""

import unittest
from unittest.mock import Mock
from uuid import uuid4

import test_qwen_capture_journal

from consilium.shell.qwen_capture_ingest import QwenCaptureRead, record_qwen_read


class QwenCaptureIngestTests(unittest.TestCase):
    def setUp(self):
        self.f = test_qwen_capture_journal.QwenCaptureJournalTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.context = self.f.f.f.context
        self.packet = QwenCaptureRead(self.context, self.f.raw, self.context)
        self.reader = Mock(return_value=self.packet)

    def ingest(self, **changes):
        return record_qwen_read(
            self.f.journal, self.reader,
            event_id=changes.get("event_id", self.f.event),
            expected_revision=changes.get("expected_revision", 0),
        )

    def test_read_once_commits_exact_bytes_and_reopens_without_authority(self):
        result = self.ingest()
        self.reader.assert_called_once_with()
        self.assertEqual(result["raw"], self.f.raw)
        self.assertFalse(result["live_origin_verified"])
        self.assertTrue(result["reader_invoked"])
        self.assertEqual(self.f.open().resume()["content"], "پاسخ\n")

    def test_committed_retry_does_not_read_again_even_after_completion(self):
        self.ingest()
        self.f.f.complete()
        self.f.f.capture["sequence"] = 2
        self.reader.return_value = QwenCaptureRead(
            self.context, self.f.f.raw(), self.context
        )
        self.ingest(event_id=uuid4(), expected_revision=1)
        self.reader.reset_mock()
        result = self.ingest()
        self.reader.assert_not_called()
        self.assertTrue(result["reused"])
        self.assertEqual(result["revision"], 1)
        self.assertEqual(self.f.open().resume()["state"], "COMPLETE")

    def test_stale_or_closed_new_event_never_invokes_reader(self):
        self.f.append()
        with self.assertRaisesRegex(ValueError, "QWEN_READ_CLOSED_OR_STALE"):
            self.ingest(event_id=uuid4())
        self.f.journal.interrupt(event_id=uuid4(), expected_revision=1)
        with self.assertRaisesRegex(ValueError, "QWEN_READ_CLOSED_OR_STALE"):
            self.ingest(event_id=uuid4(), expected_revision=2)
        self.reader.assert_not_called()

    def test_changed_before_after_or_capture_context_cannot_commit(self):
        for field, value in (
            ("model_id", "other"),
            ("account_binding_id", uuid4()),
            ("conversation_binding_id", uuid4()),
        ):
            changed = self.context.model_copy(update={field: value})
            for before, after in ((changed, self.context), (self.context, changed)):
                self.reader.return_value = QwenCaptureRead(before, self.f.raw, after)
                with self.assertRaisesRegex(ValueError, "QWEN_READ_CONTEXT_CHANGED"):
                    self.ingest()
            self.f.f.capture["context"][field] = str(value)
            self.reader.return_value = QwenCaptureRead(
                self.context, self.f.f.raw(), self.context
            )
            with self.assertRaisesRegex(ValueError, "QWEN_READ_CAPTURE_CONTEXT_CHANGED"):
                self.ingest()
            self.f.f.capture["context"] = self.context.model_dump(mode="json")
        self.assertEqual(self.f.open().resume()["revision"], 0)

    def test_private_reader_exception_is_not_exported_and_prior_capture_survives(self):
        self.f.append()
        self.reader.side_effect = RuntimeError("sensitive-marker")
        with self.assertRaisesRegex(ValueError, "QWEN_READ_FAILED") as caught:
            self.ingest(event_id=uuid4(), expected_revision=1)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn("sensitive-marker", str(caught.exception))
        self.assertEqual(self.f.open().read_qwen_capture(event_id=self.f.event)["raw"], self.f.raw)

    def test_invalid_packet_context_or_capture_does_not_mutate_journal(self):
        for packet in (
            object(),
            QwenCaptureRead(None, self.f.raw, self.context),
            QwenCaptureRead(self.context, b'{"private":"sensitive-marker",', self.context),
        ):
            self.reader.return_value = packet
            with self.assertRaises(ValueError):
                self.ingest()
        self.assertEqual(self.f.open().resume()["revision"], 0)

    def test_concurrent_writer_during_read_is_not_overwritten(self):
        def read():
            self.f.append(event_id=uuid4())
            return self.packet
        self.reader.side_effect = read
        with self.assertRaisesRegex(ValueError, "JOURNAL_CLOSED_OR_STALE_REVISION"):
            self.ingest()
        self.assertEqual(self.f.open().resume()["revision"], 1)
        with self.assertRaisesRegex(ValueError, "JOURNAL_QWEN_CAPTURE_NOT_FOUND"):
            self.f.open().read_qwen_capture(event_id=self.f.event)

    def test_invalid_arguments_and_non_capture_id_do_not_invoke_reader(self):
        for changes in ({"event_id": "bad"}, {"expected_revision": True}):
            with self.assertRaisesRegex(ValueError, "QWEN_READ_ARGUMENTS_INVALID"):
                self.ingest(**changes)
        self.f.journal.append(
            self.f.f.f.page(1, (self.f.f.f.old,)),
            event_id=self.f.event, expected_revision=0,
        )
        with self.assertRaisesRegex(ValueError, "JOURNAL_EVENT_IS_NOT_QWEN_CAPTURE"):
            self.ingest()
        self.reader.assert_not_called()
