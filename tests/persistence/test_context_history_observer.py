"""History authority comes from actual local confirmation, never provider text."""
import unittest
from types import SimpleNamespace
from uuid import uuid4
import test_ledger as fixtures
from consilium.adapters.mock import Scenario
from consilium.shell.context_observers import authorized_transcript


class CanonicalHistoryObserverTests(unittest.TestCase):
    setUp=fixtures.LedgerTests.setUp
    tearDown=fixtures.LedgerTests.tearDown
    revision=fixtures.LedgerTests.revision
    attempt=fixtures.LedgerTests.attempt
    send_and_record=fixtures.LedgerTests.send_and_record
    confirm=fixtures.LedgerTests.confirm

    def transcript(self, **updates):
        args=dict(store=self.store, context=SimpleNamespace(debate_id=self.debate.debate_id,
            round_id=self.round.round_id,participant_id=self.participant),connection=self.connection,
            through_revision=self.revision)
        args.update(updates)
        return authorized_transcript(**args)

    def test_only_confirmed_own_request_and_response_authorize_history(self):
        result=self.confirm();entries=self.transcript()
        self.assertEqual(entries[:-1],self.intent.frozen_input.messages)
        self.assertEqual(entries[-1].content,result.content)
        self.assertEqual(entries[-1].role,"ASSISTANT")

    def test_ambiguous_delivery_never_authorizes_remembered_history(self):
        self.send_and_record(Scenario.TIMEOUT_AFTER_SEND)
        self.assertEqual(self.transcript(),())

    def test_confirmation_after_snapshot_cannot_rewrite_historical_authorization(self):
        before=self.revision;self.confirm()
        self.assertEqual(self.transcript(through_revision=before),())
        self.assertTrue(self.transcript())

    def test_other_participant_or_new_binding_cannot_borrow_history(self):
        self.confirm()
        self.assertEqual(self.transcript(connection=self.connection.model_copy(update={"account_binding_id":uuid4()})),())
        other=SimpleNamespace(debate_id=self.debate.debate_id,round_id=self.round.round_id,participant_id=uuid4())
        self.assertEqual(self.transcript(context=other),())
