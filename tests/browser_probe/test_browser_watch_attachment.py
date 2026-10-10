"""Read-only attachment to actual SQLite ledger fixtures, never a live send."""

import unittest
from uuid import uuid4

import test_probe

from consilium.core.browser_watch import PageMessage, PageSnapshot
from consilium.shell.browser_watch_journal import BrowserWatchJournal


class JournalAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.f = test_probe.BrowserProbeTests()
        self.f.setUp()
        self.path = self.f.directory / "watch.sqlite3"
        self.baseline = PageSnapshot(
            sequence=0, context=self.f.context, messages=(),
            full_history=True, evidence_hash="a" * 64,
        )

    def tearDown(self):
        self.f.tearDown()

    def attach(self, **changes):
        return BrowserWatchJournal.from_recorded_probe(
            self.path, store=self.f.store, ticket=changes.get("ticket", self.f.ticket),
            baseline=self.baseline,
        )

    def test_prepared_attempt_cannot_be_attached_or_sent_by_journal(self):
        revision = self.f.revision
        with self.assertRaises(ValueError):
            self.attach()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.f.revision, revision)

    def test_exact_sent_request_attaches_and_reopens_without_mutating_ledger(self):
        self.f.start()
        revision = self.f.revision
        journal = self.attach()
        self.f.reopen()
        result = journal.inspect_recorded_probe(store=self.f.store, ticket=self.f.ticket)
        self.assertEqual(result["ledger_state"], "SENT")
        self.assertFalse(result["may_dispatch"])
        self.assertFalse(result["may_confirm_product_response"])
        self.assertEqual(self.f.revision, revision)
        self.assertEqual(journal.spec["operation_id"], str(self.f.attempt_id))

    def test_changed_request_cannot_attach_even_with_same_input_hash(self):
        self.f.start()
        request = self.f.request.model_copy(update={"timeout_seconds": 19.0})
        ticket = self.f.ticket.model_copy(update={"request": request})
        with self.assertRaises(ValueError):
            self.attach(ticket=ticket)
        self.assertFalse(self.path.exists())

    def test_synthetic_complete_does_not_record_or_confirm_product_result(self):
        self.f.start()
        journal = self.attach()
        user = PageMessage(message_id=uuid4(), role="USER", text=self.f.debate.original_request)
        answer = PageMessage(message_id=uuid4(), role="ASSISTANT", text="fixture",
                             reply_to=user.message_id, complete=True,
                             completion_evidence=("b" * 64,))
        journal.append(self.baseline.model_copy(update={"sequence": 1, "messages": (user, answer)}),
                       event_id=uuid4(), expected_revision=0)
        result = journal.inspect_recorded_probe(store=self.f.store, ticket=self.f.ticket)
        self.assertEqual(result["observation"]["state"], "COMPLETE")
        self.assertFalse(result["observation"]["live_origin_verified"])
        self.assertEqual(result["ledger_state"], "SENT")
        record = self.f.store.ledger.get_attempt(self.f.attempt_id)
        self.assertIsNone(record.result)
        self.assertIsNone(self.f.store.ledger.canonical_result(record.intent.identity.logical_operation_id))
