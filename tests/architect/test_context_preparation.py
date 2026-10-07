import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from uuid import UUID
from consilium.core.contracts import (
    DebateSpec, RoundSpec, ConnectionSpec, GenerationParameters, OperationIdentity,
)
from consilium.core.question_contracts import QuestionSnapshot, ArchitectProposal
from consilium.core.independent_context import build_independent_context
from consilium.core.dispatch_policy import PrivacyDecision, TokenBudget, HistoryEvidence, destination_hash
from consilium.shell.context_preparation import prepare_independent_intent
from consilium.shell.storage import SQLiteStore


class ContextPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"context.sqlite3"
        self.store=SQLiteStore(self.path)
        self.debate=DebateSpec(debate_id=UUID(int=1),participant_ids=(UUID(int=2),),
            original_request='اصل پرسش\nخط "دوم"',constraints=("بدون هزینه",))
        self.store.create_debate(self.debate)
        snapshot=QuestionSnapshot.from_debate(self.debate)
        proposal=ArchitectProposal(snapshot_hash=snapshot.content_hash,proposal_version=1,
            optimized_request="پرسش روشن",constraints_exact=self.debate.constraints,constraint_coverage=(0,),
            assumptions=(),visible_changes=(),origin="MOCK")
        self.store.questions.record_proposal(self.debate.debate_id,proposal,expected_revision=0)
        self.question=self.store.questions.approve_proposal(self.debate.debate_id,proposal_hash=proposal.content_hash,
            user_action_id=UUID(int=3),actor="LOCAL_USER_FIXTURE",confirmed=True,expected_revision=0)
        self.round=RoundSpec(round_id=UUID(int=4),debate_id=self.debate.debate_id,number=1,
            kind="INDEPENDENT",participant_ids=self.debate.participant_ids)
        self.store.register_round(self.round,expected_revision=1)
        self.connection=ConnectionSpec(connection_id=UUID(int=5),provider_id="mock",model_id="mock-v1",mode="API")
        self.store.bind_connection(self.debate.debate_id,UUID(int=2),self.connection,
            expected_revision=2,expected_connection_revision=None)
        self.parameters=GenerationParameters(max_output_tokens=20)
        self.context=build_independent_context(question=self.question,round_spec=self.round,
            participant_id=UUID(int=2),revision=1,parameters=self.parameters)
        binding=dict(view_hash=self.context.content_hash,request_hash=self.context.frozen_input.content_hash,
            destination_hash=destination_hash(self.connection),ledger_revision=3)
        self.privacy=PrivacyDecision(**binding,decision="ALLOW",contains_secret=False,trusted_user_action_id=UUID(int=6))
        self.budget=TokenBudget(**binding,measurement="EXACT",input_tokens=60,transport_overhead_tokens=10,
            reserved_output_tokens=20,context_capacity=100)
        self.history=HistoryEvidence(**binding,debate_id=self.debate.debate_id,state="NO_REMOTE_HISTORY",
            conversation_id=None,new_topic=True)
        self.identity=OperationIdentity(logical_operation_id=UUID(int=7),attempt_id=UUID(int=8))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def prepare(self,**updates):
        args=dict(context=self.context,connection=self.connection,identity=self.identity,expected_revision=3,
            expected_connection_revision=0,parameters=self.parameters,privacy=self.privacy,
            budget=self.budget,history=self.history)
        args.update(updates)
        return prepare_independent_intent(self.store,**args)

    def test_distinct_adoption_and_ledger_revisions_prepare_exact_input_without_send(self):
        checkpoint,admission=self.prepare()
        self.assertEqual(checkpoint.revision,4)
        self.assertEqual(admission.ledger_revision,3)
        self.assertEqual(self.context.revision,1)
        intent=self.store.get_intent(self.identity.attempt_id)
        self.assertEqual(intent.expected_revision,3)
        self.assertEqual(intent.frozen_input.canonical_bytes(),self.context.frozen_input.canonical_bytes())
        self.assertEqual(self.store.ledger.get_attempt(self.identity.attempt_id).state.value,"PREPARED")
        self.store.close()
        self.store=SQLiteStore(self.path)
        self.assertEqual(self.store.get_intent(self.identity.attempt_id),intent)

    def test_stale_state_or_connection_never_creates_operation(self):
        for updates in ({"expected_revision":1},{"expected_connection_revision":1},
                        {"connection":self.connection.model_copy(update={"model_id":"different"})}):
            with self.subTest(updates=updates),self.assertRaises(ValueError):self.prepare(**updates)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision,3)

    def test_forged_or_unrelated_context_never_creates_operation(self):
        for update in ({"proposal_hash":"0"*64},{"round_id":UUID(int=10)},{"participant_id":UUID(int=11)}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                self.prepare(context=self.context.model_copy(update=update))
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_privacy_unknown_or_budget_overflow_blocks_before_intent(self):
        for update in ({"privacy":self.privacy.model_copy(update={"decision":"UNKNOWN"})},
                       {"budget":self.budget.model_copy(update={"context_capacity":89})}):
            with self.subTest(update=update),self.assertRaises(ValueError):self.prepare(**update)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_known_private_material_blocks_even_with_allow_attestation(self):
        self.store._forbidden_values=("اصل پرسش",)
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_multiline_quoted_secret_is_checked_before_json_escaping(self):
        self.store._forbidden_values=(self.debate.original_request,)
        self.assertNotIn(self.debate.original_request,self.context.frozen_input.messages[1].content)
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_duplicate_logical_operation_never_rewrites_frozen_input(self):
        self.prepare()
        intent=self.store.get_intent(self.identity.attempt_id)
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.store.get_intent(self.identity.attempt_id),intent)

    def test_state_change_between_policy_read_and_intent_write_is_rejected(self):
        original=self.store.prepare_intent
        def advance_before_write(intent):
            self.store.bind_connection(self.debate.debate_id,UUID(int=2),
                self.connection.model_copy(update={"model_id":"changed"}),
                expected_revision=3,expected_connection_revision=0,
                actor="LOCAL_USER_FIXTURE",reason="explicit test change during preparation")
            return original(intent)
        with patch.object(self.store,"prepare_intent",side_effect=advance_before_write):
            with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision,4)
