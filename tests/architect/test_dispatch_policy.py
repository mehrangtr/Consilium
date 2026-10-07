import unittest
from uuid import UUID
from pydantic import ValidationError
from consilium.core.contracts import DebateSpec, RoundSpec, ConnectionSpec, GenerationParameters
from consilium.core.question_contracts import QuestionSnapshot, ArchitectProposal, PromptAdoption, adopt_proposal
from consilium.core.independent_context import build_independent_context, recover_independent_context
from consilium.core.dispatch_policy import (
    PrivacyDecision, TokenBudget, HistoryEvidence, PolicyBlocked, evaluate_dispatch_policy, destination_hash,
)


class DispatchPolicyTests(unittest.TestCase):
    def setUp(self):
        debate=DebateSpec(debate_id=UUID(int=1),participant_ids=(UUID(int=2),),
            original_request="اصل پرسش",constraints=("بدون هزینه",))
        snapshot=QuestionSnapshot.from_debate(debate)
        proposal=ArchitectProposal(snapshot_hash=snapshot.content_hash,proposal_version=1,
            optimized_request="پرسش روشن",constraints_exact=debate.constraints,constraint_coverage=(0,),
            assumptions=(),visible_changes=(),origin="MOCK")
        self.question=adopt_proposal(snapshot,proposal,PromptAdoption(proposal_hash=proposal.content_hash,
            trusted_user_action_id=UUID(int=3),adopted_revision=1),expected_revision=0)
        self.round=RoundSpec(round_id=UUID(int=4),debate_id=debate.debate_id,number=1,
            kind="INDEPENDENT",participant_ids=debate.participant_ids)
        self.parameters=GenerationParameters(max_output_tokens=20)
        self.context=build_independent_context(question=self.question,round_spec=self.round,
            participant_id=UUID(int=2),revision=1,parameters=self.parameters)
        self.connection=ConnectionSpec(connection_id=UUID(int=5),provider_id="mock",model_id="mock-v1",
            mode="BROWSER",account_binding_id=UUID(int=6))
        binding=dict(view_hash=self.context.content_hash,request_hash=self.context.frozen_input.content_hash,
            destination_hash=destination_hash(self.connection),ledger_revision=4)
        self.privacy=PrivacyDecision(**binding,decision="ALLOW",contains_secret=False,
            trusted_user_action_id=UUID(int=7))
        self.budget=TokenBudget(**binding,measurement="EXACT",input_tokens=60,
            transport_overhead_tokens=10,reserved_output_tokens=20,context_capacity=100)
        self.history=HistoryEvidence(**binding,debate_id=debate.debate_id,state="FRESH_EMPTY",
            conversation_id=UUID(int=8),new_topic=True)

    def evaluate(self,**updates):
        args=dict(context=self.context,connection=self.connection,privacy=self.privacy,
                  budget=self.budget,history=self.history,expected_revision=4)
        args.update(updates)
        return evaluate_dispatch_policy(**args)

    def test_known_permissions_measured_budget_and_fresh_history_pass_local_policy(self):
        admitted=self.evaluate()
        self.assertEqual(admitted.request_hash,self.context.frozen_input.content_hash)
        self.assertEqual(admitted.ledger_revision,4)
        self.assertEqual(admitted.scope,"LOCAL_ATTESTATION_VALIDATION_NOT_LIVE_VERIFICATION")

    def test_unknown_or_denied_privacy_and_any_marked_secret_block(self):
        for update in ({"decision":"UNKNOWN"},{"decision":"BLOCK"},
                       {"contains_secret":None},{"contains_secret":True}):
            with self.subTest(update=update),self.assertRaises(PolicyBlocked):
                self.evaluate(privacy=self.privacy.model_copy(update=update))

    def test_estimated_unknown_and_incomplete_measurements_block(self):
        for update in ({"measurement":"ESTIMATE"},{"measurement":"UNKNOWN"},
                       {"input_tokens":None},{"transport_overhead_tokens":None}):
            with self.subTest(update=update),self.assertRaises(PolicyBlocked):
                self.evaluate(budget=self.budget.model_copy(update=update))

    def test_budget_overflow_does_not_mutate_or_drop_constraints(self):
        before=self.context.frozen_input.canonical_bytes()
        with self.assertRaises(PolicyBlocked):
            self.evaluate(budget=self.budget.model_copy(update={"context_capacity":89}))
        self.assertEqual(before,self.context.frozen_input.canonical_bytes())
        self.assertIn("بدون هزینه",self.context.frozen_input.messages[1].content)

    def test_frozen_output_reserve_must_match_budget(self):
        with self.assertRaises(PolicyBlocked):
            self.evaluate(budget=self.budget.model_copy(update={"reserved_output_tokens":19}))

    def test_unknown_or_peer_contaminated_remote_history_blocks(self):
        for state in ("UNVERIFIED","CONTAINS_PEERS"):
            with self.subTest(state=state),self.assertRaises(PolicyBlocked):
                self.evaluate(history=self.history.model_copy(update={"state":state}))

    def test_new_topic_cannot_reuse_nonempty_history(self):
        with self.assertRaises(PolicyBlocked):
            self.evaluate(history=self.history.model_copy(update={"state":"VERIFIED_AUTHORIZED"}))
        self.evaluate(history=self.history.model_copy(update={"state":"VERIFIED_AUTHORIZED","new_topic":False}))

    def test_browser_requires_conversation_identity_and_matching_debate(self):
        for update in ({"conversation_id":None},{"debate_id":UUID(int=9)},
                       {"state":"NO_REMOTE_HISTORY","conversation_id":None}):
            with self.subTest(update=update),self.assertRaises(PolicyBlocked):
                self.evaluate(history=self.history.model_copy(update=update))

    def test_stale_or_mismatched_evidence_is_rejected(self):
        for field in ("privacy","budget","history"):
            value=getattr(self,field)
            for update in ({"request_hash":"0"*64},{"view_hash":"0"*64},
                           {"destination_hash":"0"*64},{"ledger_revision":3}):
                with self.subTest(field=field,update=update),self.assertRaises(PolicyBlocked):
                    self.evaluate(**{field:value.model_copy(update=update)})

    def test_account_switch_cannot_reuse_prior_privacy_grant(self):
        with self.assertRaises(PolicyBlocked):
            self.evaluate(connection=self.connection.model_copy(update={"account_binding_id":UUID(int=10)}))

    def test_browser_without_account_identity_blocks_even_rebound_attestations(self):
        connection=self.connection.model_copy(update={"account_binding_id":None})
        update={"destination_hash":destination_hash(connection)}
        with self.assertRaises(PolicyBlocked):
            self.evaluate(connection=connection,privacy=self.privacy.model_copy(update=update),
                budget=self.budget.model_copy(update=update),history=self.history.model_copy(update=update))

    def test_explicit_generation_parameters_reconstruct_and_tampering_fails(self):
        recovered=recover_independent_context(self.context,self.question,self.round,
            participant_id=UUID(int=2),expected_revision=1,parameters=self.parameters)
        self.assertEqual(recovered,self.context.frozen_input)
        with self.assertRaises(ValueError):
            recover_independent_context(self.context,self.question,self.round,
                participant_id=UUID(int=2),expected_revision=1,parameters=GenerationParameters(max_output_tokens=21))

    def test_bool_counts_and_extra_self_approval_fields_rejected(self):
        with self.assertRaises(ValidationError):self.budget.model_copy(update={"input_tokens":True})
        with self.assertRaises(ValidationError):self.privacy.model_copy(update={"provider_approved":True})
