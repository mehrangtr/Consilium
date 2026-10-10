"""Captured rendered UI fixtures, never current-site/browser certification."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import test_browser_watch

from consilium.adapters.qwen_page_reader import read_qwen_capture
from consilium.shell.browser_watch_journal import BrowserWatchJournal


class QwenPageReaderTests(unittest.TestCase):
    def setUp(self):
        self.f = test_browser_watch.BrowserWatchTests()
        self.f.setUp()
        self.capture = {
            "schema_version": 1,
            "capture_kind": "QWEN_RENDERED_TEXT_V1",
            "sequence": 1,
            "context": self.f.context.model_dump(mode="json"),
            "full_history": True,
            "prior_messages": [self.f.old.model_dump(mode="json")],
            "submitted_user": self.f.user.model_dump(mode="json"),
            "response": {
                "message_id": str(self.f.answer.message_id),
                "reply_to": str(self.f.user.message_id),
                "raw_rendered_text": "پاسخ\n",
                "thinking_completed": False,
                "stop_visible": True,
                "response_actions": [],
            },
        }

    def raw(self):
        return json.dumps(self.capture, ensure_ascii=False).encode()

    def complete(self):
        self.capture["response"].update(
            raw_rendered_text="Thinking completed\nپاسخ\n",
            thinking_completed=True,
            stop_visible=False,
            response_actions=["GOOD_RESPONSE", "BAD_RESPONSE", "REGENERATE"],
        )

    def test_partial_preserves_exact_unicode_and_trailing_newline(self):
        raw = self.raw()
        page = read_qwen_capture(raw)
        self.assertEqual(page.messages[-1].text, "پاسخ\n")
        self.assertFalse(page.messages[-1].complete)
        self.assertEqual(page.evidence_hash, hashlib.sha256(raw).hexdigest())

    def test_complete_removes_exact_prefix_once_only(self):
        self.complete()
        self.capture["response"]["raw_rendered_text"] = (
            "Thinking completed\nThinking completed\nپاسخ"
        )
        page = read_qwen_capture(self.raw())
        self.assertEqual(page.messages[-1].text, "Thinking completed\nپاسخ")
        self.assertTrue(page.messages[-1].complete)
        self.assertEqual(page.messages[-1].completion_evidence, (page.evidence_hash,))

    def test_body_action_names_cannot_complete_response(self):
        self.capture["response"].update(
            raw_rendered_text="Thinking completed\nGood Response Bad Response Regenerate",
            stop_visible=False,
        )
        self.assertFalse(read_qwen_capture(self.raw()).messages[-1].complete)

    def test_missing_control_or_visible_stop_stays_partial(self):
        self.complete()
        self.capture["response"]["response_actions"].pop()
        self.assertFalse(read_qwen_capture(self.raw()).messages[-1].complete)
        self.complete()
        self.capture["response"]["stop_visible"] = True
        self.assertFalse(read_qwen_capture(self.raw()).messages[-1].complete)

    def test_claimed_completion_without_exact_prefix_is_rejected(self):
        self.complete()
        self.capture["response"]["raw_rendered_text"] = "Thinking completed پاسخ"
        with self.assertRaises(ValueError):
            read_qwen_capture(self.raw())

    def test_wrong_reply_duplicate_ids_and_duplicate_actions_rejected(self):
        self.capture["response"]["reply_to"] = str(uuid4())
        with self.assertRaises(ValueError):
            read_qwen_capture(self.raw())
        self.capture["response"]["reply_to"] = str(self.f.user.message_id)
        self.capture["response"]["message_id"] = str(self.f.old.message_id)
        with self.assertRaises(ValueError):
            read_qwen_capture(self.raw())
        self.capture["response"]["message_id"] = str(self.f.answer.message_id)
        self.capture["response"]["response_actions"] = ["REGENERATE", "REGENERATE"]
        with self.assertRaises(ValueError):
            read_qwen_capture(self.raw())

    def test_bounds_bad_utf8_duplicate_keys_unknown_fields_rejected(self):
        for raw in (
            b"",
            b"\xff",
            b'{"schema_version":1,"schema_version":1}',
            self.raw().decode(),
        ):
            with self.assertRaises(ValueError):
                read_qwen_capture(raw)
        with (
            patch("consilium.adapters.qwen_page_reader.MAX_CAPTURE_BYTES", 10),
            self.assertRaises(ValueError),
        ):
            read_qwen_capture(self.raw())
        self.capture["trusted_live"] = True
        with self.assertRaises(ValueError):
            read_qwen_capture(self.raw())

    def test_no_response_and_full_history_loss_are_preserved(self):
        self.capture["response"] = None
        self.capture["full_history"] = False
        page = read_qwen_capture(self.raw())
        self.assertEqual(len(page.messages), 2)
        self.assertFalse(page.full_history)
        self.assertEqual(self.f.watch.observe(page), "NONE")
        self.assertTrue(self.f.watch.stopped)

    def test_changed_context_stops_watch_without_losing_partial(self):
        self.f.watch.observe(read_qwen_capture(self.raw()))
        self.capture["sequence"] = 2
        self.capture["context"]["model_id"] = "other"
        self.f.watch.observe(read_qwen_capture(self.raw()))
        self.assertTrue(self.f.watch.stopped)
        self.assertEqual(self.f.watch.content, "پاسخ\n")

    def test_stale_sequence_is_not_fresh_delivery(self):
        page = read_qwen_capture(self.raw())
        self.f.watch.observe(page)
        self.f.watch.observe(page)
        self.assertEqual(self.f.watch.failure, "STALE_PAGE_OBSERVATION")

    def test_reader_journal_reopen_completion_remains_synthetic(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = {
                "operation_id": uuid4(),
                "request_hash": "a" * 64,
                "binding": self.f.binding,
                "baseline": self.f.base,
                "prompt_hash": self.f.watch.prompt_hash,
            }
            path = Path(directory) / "journal.sqlite3"
            journal = BrowserWatchJournal(path, **arguments)
            journal.append(
                read_qwen_capture(self.raw()), event_id=uuid4(), expected_revision=0
            )
            self.complete()
            self.capture["sequence"] = 2
            journal.append(
                read_qwen_capture(self.raw()), event_id=uuid4(), expected_revision=1
            )
            result = BrowserWatchJournal(path, **arguments).resume()
            self.assertEqual(result["state"], "COMPLETE")
            self.assertEqual(result["content"], "پاسخ\n")
            self.assertFalse(result["live_origin_verified"])
            self.assertEqual(result["next_action"], "STOP")

    def test_schema_boolean_and_numeric_strings_are_not_valid_versions(self):
        for version in (True, "1", 2):
            self.capture["schema_version"] = version
            with self.assertRaises(ValueError):
                read_qwen_capture(self.raw())

    def test_deep_json_rejection_preserves_committed_partial_response(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = {
                "operation_id": uuid4(),
                "request_hash": "a" * 64,
                "binding": self.f.binding,
                "baseline": self.f.base,
                "prompt_hash": self.f.watch.prompt_hash,
            }
            path = Path(directory) / "journal.sqlite3"
            journal = BrowserWatchJournal(path, **arguments)
            journal.append(
                read_qwen_capture(self.raw()), event_id=uuid4(), expected_revision=0
            )
            with self.assertRaisesRegex(ValueError, "QWEN_CAPTURE_NESTING_TOO_DEEP"):
                read_qwen_capture(b"[" * 2000 + b"0" + b"]" * 2000)
            result = BrowserWatchJournal(path, **arguments).resume()
            self.assertEqual(result["revision"], 1)
            self.assertEqual(result["content"], "پاسخ\n")
            self.assertEqual(result["state"], "PARTIAL")
            text = 'quoted \\" ' + "[" * 2000
            self.capture["response"]["raw_rendered_text"] = text
            self.assertEqual(read_qwen_capture(self.raw()).messages[-1].text, text)

    def test_decoder_errors_do_not_retain_private_document_or_exception_chain(self):
        for raw in (b'{"private":"sensitive-marker",', b'\xffsensitive-marker'):
            with self.assertRaisesRegex(ValueError, "QWEN_CAPTURE_JSON_INVALID") as caught:
                read_qwen_capture(raw)
            error = caught.exception
            self.assertIs(type(error), ValueError)
            self.assertIsNone(error.__context__)
            self.assertIsNone(error.__cause__)
            self.assertFalse(hasattr(error, "doc"))
            self.assertNotIn("sensitive-marker", str(error))

    def test_nonfinite_numbers_and_unpaired_surrogates_are_rejected(self):
        for token in (b"NaN", b"Infinity", b"-Infinity", b"1e9999"):
            raw = self.raw().replace(b'"sequence": 1', b'"sequence": ' + token)
            with self.assertRaisesRegex(ValueError, "QWEN_CAPTURE_JSON_INVALID"):
                read_qwen_capture(raw)
        for text in (r"\ud800", r"\udfff"):
            value = dict(self.capture)
            value["response"] = dict(value["response"], raw_rendered_text="PLACEHOLDER")
            raw = json.dumps(value).encode().replace(b"PLACEHOLDER", text.encode())
            with self.assertRaisesRegex(ValueError, "QWEN_CAPTURE_JSON_INVALID"):
                read_qwen_capture(raw)
        self.capture["response"]["raw_rendered_text"] = "پاسخ 😀"
        raw = json.dumps(self.capture, ensure_ascii=True).encode()
        self.assertEqual(read_qwen_capture(raw).messages[-1].text, "پاسخ 😀")

    def test_schema_errors_have_no_input_bearing_validation_details(self):
        self.capture["private"] = "sensitive-marker"
        with self.assertRaisesRegex(ValueError, "QWEN_CAPTURE_SCHEMA_INVALID") as caught:
            read_qwen_capture(self.raw())
        self.assertIs(type(caught.exception), ValueError)
        self.assertIsNone(caught.exception.__context__)
        self.assertFalse(hasattr(caught.exception, "errors"))

    def test_duplicate_page_error_does_not_expose_validated_message_details(self):
        self.capture["response"]["message_id"] = str(self.f.old.message_id)
        with self.assertRaisesRegex(ValueError, "QWEN_CAPTURE_PAGE_INVALID") as caught:
            read_qwen_capture(self.raw())
        self.assertIs(type(caught.exception), ValueError)
        self.assertIsNone(caught.exception.__context__)
        self.assertFalse(hasattr(caught.exception, "errors"))
        self.capture["response"]["message_id"] = str(self.f.answer.message_id)
        self.complete()
        self.capture["response"]["raw_rendered_text"] = "Thinking completed\n"
        with self.assertRaisesRegex(ValueError, "QWEN_CAPTURE_PAGE_INVALID") as caught:
            read_qwen_capture(self.raw())
        self.assertIs(type(caught.exception), ValueError)
        self.assertIsNone(caught.exception.__context__)
        self.assertFalse(hasattr(caught.exception, "errors"))
