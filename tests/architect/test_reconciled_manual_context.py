"""Policy-prepared initial and review slots can continue manually only after explicit retirement."""
import unittest
from uuid import UUID

import test_context_preparation as initial
import test_manual_rounds as later
from consilium.core.contracts import ConnectionSpec
from consilium.shell.storage import Conflict, SQLiteStore


class ReconciledInitialContextTests(unittest.TestCase):
    setUp = initial.ContextPreparationTests.setUp
    tearDown = initial.ContextPreparationTests.tearDown
    prepare = initial.ContextPreparationTests.prepare

    def test_manual_initial_acceptance_replaces_no_transport_fact_and_opens_only_user_gate(self):
        self.prepare()
        prompt = self.store.manual_sources._expected_prompt(self.round, UUID(int=2))
        args = dict(candidate_id=UUID(int=90),round_spec=self.round,participant_id=UUID(int=2),
            actual_prompt=prompt,round_seen=True,answer="MANUAL MINORITY DISSENT",expected_revision=4)
        with self.assertRaises(ValueError): self.store.manual_sources.stage_answer(**args)
        before = self.store.ledger.get_attempt(self.identity.attempt_id)
        manual = ConnectionSpec(connection_id=UUID(int=91),provider_id="claimed-service",model_id="claimed-model",mode="MANUAL")
        review = self.store.manual_reconciliation.review(debate_id=self.debate.debate_id,round_id=self.round.round_id,
            participant_id=UUID(int=2),expected_revision=4,manual_connection=manual)
        self.store.manual_reconciliation.accept(review=review,review_hash=review.content_hash,user_action_id=UUID(int=92),
            actor="LOCAL_USER_FIXTURE",reason="Cannot use the connected service",confirmed=True,expected_revision=4)
        with self.assertRaises(Conflict): self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=5)
        candidate = self.store.manual_sources.stage_answer(**{**args,"expected_revision":5})
        record = self.store.manual_sources.accept_answer(candidate.candidate_id,candidate_hash=candidate.content_hash,
            user_action_id=UUID(int=93),actor="LOCAL_USER_FIXTURE",confirmed=True,expected_revision=5)
        self.store.close();self.store=SQLiteStore(self.path)
        self.assertEqual(self.store.ledger.get_attempt(self.identity.attempt_id),before)
        self.assertFalse(record.external_origin_verified)
        self.assertEqual(record.source.item.provenance,"MANUAL")
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id),(record.source,))
        self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=6)
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["wait_state"],"WAITING_DECISION")


class ReconciledReviewContextTests(unittest.TestCase):
    setUp = later.ManualRoundTests.setUp
    tearDown = later.ManualRoundTests.tearDown
    revision = later.ManualRoundTests.revision
    advance = later.ManualRoundTests.advance
    make_frame = later.ManualRoundTests.make_frame
    content = later.ManualRoundTests.content
    stage = later.ManualRoundTests.stage
    accept = later.ManualRoundTests.accept
    prepare_policy_operation = later.ManualRoundTests.prepare_policy_operation

    def test_manual_critique_rebuilds_grants_and_history_after_explicit_retirement(self):
        identity = self.prepare_policy_operation()
        before = self.store.ledger.get_attempt(identity.attempt_id)
        with self.assertRaises(Conflict): self.make_frame()
        new_connection = self.connections[UUID(int=2)].model_copy(update={"connection_id":UUID(int=950)})
        review = self.store.manual_reconciliation.review(debate_id=self.debate.debate_id,round_id=self.round.round_id,
            participant_id=UUID(int=2),expected_revision=self.revision,manual_connection=new_connection)
        self.store.manual_reconciliation.accept(review=review,review_hash=review.content_hash,user_action_id=UUID(int=951),
            actor="LOCAL_USER_FIXTURE",reason="Continue the review manually",confirmed=True,expected_revision=self.revision)
        with self.assertRaises(Conflict): self.stage()
        self.connections[UUID(int=2)] = new_connection
        self.frame = self.make_frame()
        self.assertEqual(self.frame.connection_revision,1)
        self.assertIn("MINORITY DISSENT",self.frame.expected_prompt)
        record = self.accept(self.stage())
        self.store.close();self.store=SQLiteStore(self.path)
        self.assertEqual(self.store.ledger.get_attempt(identity.attempt_id),before)
        self.assertEqual(self.store.manual_rounds.get(record.candidate.candidate_id),record)
        self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=self.revision)
