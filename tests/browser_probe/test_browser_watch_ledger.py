"""Real SQLite ledger correlation; synthetic pages never become live results."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import test_browser_watch

from consilium.core.contracts import (
    AdapterRequest,
    ConnectionSpec,
    DebateSpec,
    FrozenInput,
    Message,
    OperationIdentity,
    OperationIntent,
    RoundSpec,
)
from consilium.shell.browser_watch_journal import BrowserWatchJournal
from consilium.shell.browser_watch_ledger import BrowserLedgerView
from consilium.shell.storage import Conflict, SQLiteStore


class BrowserLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.f = test_browser_watch.BrowserWatchTests()
        self.f.setUp()
        self.store = SQLiteStore(self.root / "ledger.sqlite3")
        participant = uuid4()
        self.debate = DebateSpec(
            debate_id=uuid4(),
            original_request=self.f.user.text,
            participant_ids=(participant,),
        )
        self.round = RoundSpec(
            round_id=uuid4(),
            debate_id=self.debate.debate_id,
            number=1,
            kind="INDEPENDENT",
            participant_ids=(participant,),
        )
        self.connection = ConnectionSpec(
            connection_id=self.f.binding.connection_id,
            account_binding_id=self.f.binding.account_binding_id,
            provider_id="fixture",
            model_id=self.f.binding.model_id,
            mode="BROWSER",
        )
        self.store.create_debate(self.debate)
        self.store.register_round(self.round, expected_revision=0)
        self.store.bind_connection(
            self.debate.debate_id,
            participant,
            self.connection,
            expected_revision=1,
            expected_connection_revision=None,
        )
        frozen = FrozenInput(messages=(Message(role="USER", content=self.f.user.text),))
        self.intent = OperationIntent(
            identity=OperationIdentity(
                logical_operation_id=uuid4(), attempt_id=uuid4()
            ),
            debate_id=self.debate.debate_id,
            round_id=self.round.round_id,
            participant_id=participant,
            connection_id=self.connection.connection_id,
            expected_revision=2,
            connection_revision=0,
            frozen_input=frozen,
            request_hash=frozen.content_hash,
        )
        self.request = AdapterRequest(
            intent=self.intent,
            connection=self.connection,
            timeout_seconds=2.0,
            transport_binding_hash=self.f.binding.content_hash,
        )
        self.store.prepare_intent(self.intent)
        self.arguments = {
            "operation_id": self.intent.identity.attempt_id,
            "request_hash": self.intent.request_hash,
            "binding": self.f.binding,
            "baseline": self.f.base,
            "prompt_hash": hashlib.sha256(self.f.user.text.encode()).hexdigest(),
        }
        self.journal = self.open_journal()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def open_journal(self, **changes):
        return BrowserWatchJournal(
            self.root / "journal.sqlite3", **{**self.arguments, **changes}
        )

    def read(self, journal=None, revision=4):
        return BrowserLedgerView(journal or self.journal).resume(
            self.store.ledger,
            attempt_id=self.intent.identity.attempt_id,
            expected_revision=revision,
        )

    def start(self):
        self.store.ledger.begin_send(self.request, expected_revision=3)

    def partial(self):
        self.journal.append(
            self.f.page(1, (self.f.old, self.f.user, self.f.answer)),
            event_id=uuid4(),
            expected_revision=0,
        )

    def test_prepared_attempt_cannot_observe_as_started(self):
        with self.assertRaises(Conflict):
            self.read(revision=3)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 3)

    def test_partial_reopen_does_not_record_result_or_send(self):
        self.start()
        self.partial()
        self.store.close()
        self.store = SQLiteStore(self.root / "ledger.sqlite3")
        result = self.read(self.open_journal())
        self.assertEqual(result["content"], self.f.answer.text)
        self.assertEqual(result["next_action"], "OBSERVE_ONLY_NO_RESEND")
        self.assertFalse(result["result_admitted"])
        self.assertIsNone(
            self.store.ledger.get_attempt(self.intent.identity.attempt_id).result
        )
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 4)

    def test_synthetic_complete_requires_reconciliation(self):
        self.start()
        final = self.f.answer.model_copy(
            update={"complete": True, "completion_evidence": ("c" * 64,)}
        )
        self.journal.append(
            self.f.page(1, (self.f.old, self.f.user, final)),
            event_id=uuid4(),
            expected_revision=0,
        )
        result = self.read()
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(result["next_action"], "STOP_REQUIRES_RECONCILIATION")
        self.assertFalse(result["live_origin_verified"])
        self.assertIsNone(
            self.store.ledger.canonical_result(
                self.intent.identity.logical_operation_id
            )
        )

    def test_interrupted_dispatch_only_observes_no_resend(self):
        self.start()
        self.partial()
        self.store.ledger.mark_interrupted(
            self.intent.identity.attempt_id, expected_revision=4
        )
        self.assertEqual(self.read(revision=5)["next_action"], "OBSERVE_ONLY_NO_RESEND")
        with self.assertRaises(Conflict):
            self.store.ledger.begin_send(self.request, expected_revision=5)

    def test_stale_ledger_and_changed_connection_block_correlation(self):
        self.start()
        with self.assertRaises(Conflict):
            self.read(revision=3)
        replacement = self.connection.model_copy(update={"connection_id": uuid4()})
        self.store.bind_connection(
            self.debate.debate_id,
            self.intent.participant_id,
            replacement,
            expected_revision=4,
            expected_connection_revision=0,
            actor="user-fixture",
            reason="explicit test replacement",
        )
        with self.assertRaises(Conflict):
            self.read(revision=5)

    def test_foreign_operation_request_prompt_and_conversation_rejected(self):
        self.start()
        for field, value in [
            ("operation_id", uuid4()),
            ("request_hash", "f" * 64),
            ("prompt_hash", "f" * 64),
            (
                "binding",
                self.f.binding.model_copy(update={"conversation_binding_id": uuid4()}),
            ),
        ]:
            arguments = {**self.arguments, field: value}
            if field == "binding":
                context = self.f.context.model_copy(
                    update={"conversation_binding_id": value.conversation_binding_id}
                )
                arguments["baseline"] = self.f.base.model_copy(
                    update={"context": context}
                )
            other = BrowserWatchJournal(self.root / (field + ".sqlite3"), **arguments)
            with self.assertRaises(Conflict):
                self.read(other)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 4)

    def test_mutated_in_memory_spec_cannot_relabel_journal(self):
        self.start()
        self.journal.spec["request_hash"] = "f" * 64
        with self.assertRaises(ValueError):
            self.read()

    def test_explicit_wait_gate_blocks_observation_without_losing_partial(self):
        self.start()
        self.partial()
        with self.store._transaction():
            self.store._db.execute("UPDATE debates SET wait_state='WAITING_DECISION' WHERE debate_id=?",
                                   (str(self.debate.debate_id),))
        result = self.read()
        self.assertEqual(result["content"], self.f.answer.text)
        self.assertEqual(result["next_action"], "STOP_REQUIRES_RECONCILIATION")
        self.assertFalse(result["may_dispatch"])

    def test_closed_journal_stops_even_if_ledger_delivery_unknown(self):
        self.start()
        self.partial()
        self.journal.interrupt(event_id=uuid4(), expected_revision=1)
        self.store.ledger.mark_interrupted(self.intent.identity.attempt_id, expected_revision=4)
        result = self.read(revision=5)
        self.assertEqual(result["next_action"], "STOP_REQUIRES_RECONCILIATION")
        self.assertEqual(result["content"], self.f.answer.text)

    def test_corrupt_journal_blocks_ledger_view_without_ledger_mutation(self):
        import sqlite3
        from contextlib import closing
        self.start()
        self.partial()
        with closing(sqlite3.connect(self.journal.database)) as db, db:
            db.execute("UPDATE events SET payload='{}'")
        with self.assertRaises(ValueError):
            self.read()
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 4)
        self.assertIsNone(self.store.ledger.get_attempt(self.intent.identity.attempt_id).result)
