"""Actual manual-source -> user gate -> canonical later-round intent; no transport."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import UUID

from consilium.core.contracts import AdapterRequest, ConnectionSpec, DebateSpec, GenerationParameters, OperationIdentity, UserDecision, RoundSpec
from consilium.core.dispatch_policy import PrivacyDecision, TokenBudget, HistoryEvidence, destination_hash
from consilium.core.question_contracts import QuestionSnapshot, ArchitectProposal
from consilium.core.round_context import TransferGrant, build_round_context
from consilium.shell.context_preparation import prepare_round_intent
from consilium.shell.storage import SQLiteStore, Conflict, SchemaError
from consilium.core.question_contracts import _hash


class RoundAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"round.sqlite3"
        self.store = SQLiteStore(self.path)
        self.debate = DebateSpec(debate_id=UUID(int=1), original_request="Exact original question", constraints=("Preserve dissent",),
                                 participant_ids=(UUID(int=2), UUID(int=3)))
        self.store.create_debate(self.debate)
        snapshot = QuestionSnapshot.from_debate(self.debate)
        proposal = ArchitectProposal(snapshot_hash=snapshot.content_hash, proposal_version=1, optimized_request="Effective question",
            constraints_exact=self.debate.constraints, constraint_coverage=(0,), assumptions=(), visible_changes=(), origin="MOCK")
        self.store.questions.record_proposal(self.debate.debate_id, proposal, expected_revision=0)
        self.question = self.store.questions.approve_proposal(self.debate.debate_id, proposal_hash=proposal.content_hash,
            user_action_id=UUID(int=4), actor="FIXTURE_USER", confirmed=True, expected_revision=0)
        self.first = RoundSpec(round_id=UUID(int=5), debate_id=self.debate.debate_id, number=1,
            kind="INDEPENDENT", participant_ids=self.debate.participant_ids)
        self.store.register_round(self.first, expected_revision=self.revision)
        self.connections = {}
        for i,pid in enumerate(self.debate.participant_ids):
            connection = ConnectionSpec(connection_id=UUID(int=10+i), provider_id="claimed-provider", model_id="claimed-model", mode="MANUAL")
            self.connections[pid] = connection
            self.store.bind_connection(self.debate.debate_id, pid, connection, expected_revision=self.revision, expected_connection_revision=None)
        self.accepted = []
        for i,pid in enumerate(self.debate.participant_ids):
            candidate = self.store.manual_sources.stage_answer(candidate_id=UUID(int=20+i), round_spec=self.first, participant_id=pid,
                actual_prompt=self.store.manual_sources._expected_prompt(self.first,pid), round_seen=True,
                answer="MAJORITY" if i==0 else "MINORITY DISSENT", claimed_origin="unverified user claim", expected_revision=self.revision)
            self.accepted.append(self.store.manual_sources.accept_answer(candidate.candidate_id, candidate_hash=candidate.content_hash,
                user_action_id=UUID(int=30+i), actor="FIXTURE_USER", confirmed=True, expected_revision=self.revision))
        self.store.ledger.wait_for_decision(self.debate.debate_id,self.first.round_id,expected_revision=self.revision)
        self.decision = UserDecision(decision_id=UUID(int=40),debate_id=self.debate.debate_id, round_id=self.first.round_id,
            expected_revision=self.revision,kind="CUSTOM",instruction="Preserve the minority and explain disagreement")
        self.store.ledger.record_decision(self.decision, actor="FIXTURE_USER")
        self.round = RoundSpec(round_id=UUID(int=41),debate_id=self.debate.debate_id,number=2,kind="REVIEW",participant_ids=self.debate.participant_ids)
        self.store.register_round(self.round,expected_revision=self.revision)
        self.connection = self.connections[UUID(int=2)]
        self.parameters = GenerationParameters(max_output_tokens=20)
        self.identity = OperationIdentity(logical_operation_id=UUID(int=50),attempt_id=UUID(int=51))
        self.refresh()

    @property
    def revision(self): return self.store.checkpoint(self.debate.debate_id).revision

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def refresh(self):
        self.sources = self.store.sources.context_sources(self.debate.debate_id)
        self.grants = tuple(TransferGrant(source_hash=s.content_hash,destination_hash=destination_hash(self.connection),
            ledger_revision=self.revision,decision="ALLOW",trusted_user_action_id=UUID(int=60+i)) for i,s in enumerate(self.sources))
        self.context = build_round_context(question=self.question,debate=self.debate,round_spec=self.round,participant_id=UUID(int=2),
            expected_revision=self.revision,sources=self.sources,required_source_hashes=tuple(s.content_hash for s in self.sources),
            grants=self.grants,connection=self.connection,parameters=self.parameters,continuation_decision=self.decision)
        binding=dict(view_hash=self.context.content_hash,request_hash=self.context.frozen_input.content_hash,
                     destination_hash=destination_hash(self.connection),ledger_revision=self.revision)
        self.privacy=PrivacyDecision(**binding,decision="ALLOW",contains_secret=False,trusted_user_action_id=UUID(int=70))
        self.budget=TokenBudget(**binding,measurement="EXACT",input_tokens=60,transport_overhead_tokens=10,reserved_output_tokens=20,context_capacity=100)
        self.history=HistoryEvidence(**binding,debate_id=self.debate.debate_id,state="FRESH_EMPTY",conversation_id=UUID(int=71),new_topic=True)

    def args(self,**updates):
        return dict(dict(debate_id=self.debate.debate_id,round_id=self.round.round_id,participant_id=UUID(int=2),context=self.context,
            connection=self.connection,identity=self.identity,expected_revision=self.revision,expected_connection_revision=0,
            parameters=self.parameters,grants=self.grants,privacy=self.privacy,budget=self.budget,history=self.history),**updates)

    def prepare(self,**updates): return prepare_round_intent(self.store,**self.args(**updates))

    def reopen(self):
        self.store.close(); self.store=SQLiteStore(self.path)

    def test_complete_manual_round_requires_explicit_decision_and_preserves_manual_origin(self):
        self.assertEqual(self.revision,9)
        self.assertEqual(len(self.sources),2)
        self.assertTrue(all(s.provenance=="MANUAL" for s in self.sources))
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["attempts"],[])

    def test_exact_canonical_sources_grants_budget_and_custom_instruction_survive_restart(self):
        before=self.revision; self.prepare(); self.reopen()
        receipt=self.store.admissions.get(self.identity.logical_operation_id)
        self.assertEqual(receipt.sources,self.sources)
        self.assertEqual(receipt.grants,self.grants)
        self.assertEqual(receipt.continuation_decision,self.decision)
        self.assertEqual(receipt.context,self.context)
        self.assertEqual(self.store.admissions.require_current(self.identity.attempt_id,expected_revision=before+1),receipt)
        data=json.loads(receipt.context.frozen_input.messages[1].content)
        self.assertEqual(data["continuation"]["instruction"],self.decision.instruction)
        self.assertIn("MINORITY DISSENT",json.dumps(data))
        self.assertNotIn("claimed-provider",json.dumps(data))
        self.assertEqual(len(self.store.export_debate(self.debate.debate_id)["context_admissions"]),1)

    def test_omitted_dissent_cannot_self_authorize_a_smaller_snapshot(self):
        shortened=build_round_context(question=self.question,debate=self.debate,round_spec=self.round,participant_id=UUID(int=2),
            expected_revision=self.revision,sources=self.sources[:1],required_source_hashes=(self.sources[0].content_hash,),
            grants=self.grants[:1],connection=self.connection,parameters=self.parameters,continuation_decision=self.decision)
        with self.assertRaises(ValueError): self.prepare(context=shortened,grants=self.grants[:1])
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_missing_or_stale_transfer_permission_blocks_before_intent(self):
        for grants in (self.grants[:1],tuple(g.model_copy(update={"ledger_revision":self.revision-1}) for g in self.grants)):
            with self.subTest(grants=grants),self.assertRaises(ValueError): self.prepare(grants=grants)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_budget_privacy_and_history_uncertainty_fail_closed(self):
        for updates in ({"budget":self.budget.model_copy(update={"context_capacity":89})},
                        {"privacy":self.privacy.model_copy(update={"decision":"UNKNOWN"})},
                        {"history":self.history.model_copy(update={"state":"UNVERIFIED"})}):
            with self.subTest(updates=updates),self.assertRaises(ValueError): self.prepare(**updates)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_source_semantic_secret_is_checked_before_json_escaping(self):
        self.store._forbidden_values=("MINORITY DISSENT",)
        with self.assertRaises(ValueError): self.prepare()
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_historical_source_selection_respects_publication_revision(self):
        earlier=self.store.sources.context_sources(self.debate.debate_id,through_revision=self.accepted[0].accepted_revision)
        self.assertEqual(earlier,(self.accepted[0].source,))
        self.assertEqual(self.sources,tuple(r.source for r in self.accepted))

    def test_context_without_stored_custom_instruction_is_rejected(self):
        missing=build_round_context(question=self.question,debate=self.debate,round_spec=self.round,participant_id=UUID(int=2),
            expected_revision=self.revision,sources=self.sources,required_source_hashes=tuple(s.content_hash for s in self.sources),
            grants=self.grants,connection=self.connection,parameters=self.parameters)
        with self.assertRaises(ValueError): self.prepare(context=missing)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_saved_policy_is_not_permission_to_send(self):
        self.prepare(); intent=self.store.get_intent(self.identity.attempt_id)
        with self.assertRaises(Conflict): self.store.ledger.begin_send(AdapterRequest(intent=intent,connection=self.connection,timeout_seconds=2.0),expected_revision=self.revision)
        self.assertEqual(self.store.ledger.get_attempt(self.identity.attempt_id).state.value,"PREPARED")

    def test_binding_change_invalidates_current_receipt_but_preserves_history(self):
        self.prepare()
        self.store.bind_connection(self.debate.debate_id,UUID(int=2),self.connection.model_copy(update={"model_id":"other"}),
            expected_revision=self.revision,expected_connection_revision=0,actor="FIXTURE_USER",reason="explicit replacement")
        self.reopen()
        self.assertIsNotNone(self.store.admissions.get(self.identity.logical_operation_id))
        with self.assertRaises(Conflict): self.store.admissions.require_current(self.identity.attempt_id,expected_revision=self.revision)

    def test_failed_final_insert_rolls_back_all_intent_and_policy_records(self):
        before=self.revision
        self.store._db.execute("CREATE TEMP TRIGGER refuse_admission BEFORE INSERT ON context_admissions BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Conflict): self.prepare()
        self.assertEqual(self.revision,before)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_deleted_admission_is_detected_on_restart(self):
        self.prepare(); self.store._db.execute("DELETE FROM context_admissions"); self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_rehashed_policy_tamper_still_disagrees_with_committed_event(self):
        self.prepare(); receipt=self.store.admissions.get(self.identity.logical_operation_id)
        forged=receipt.model_copy(update={"budget":self.budget.model_copy(update={"context_capacity":101}),
            "admission":receipt.admission.model_copy(update={"budget_hash":_hash(self.budget.model_copy(update={"context_capacity":101}))})})
        self.store._db.execute("UPDATE context_admissions SET bundle_json=?,bundle_hash=?",(forged.model_dump_json(),forged.content_hash))
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def crash_case(self,before):
        args=self.args(); revision=self.revision
        # Rebuild from the complete durable packet in a separate process.
        from consilium.core.round_admission import RoundAdmissionBundle
        from consilium.core.dispatch_policy import evaluate_round_dispatch_policy
        bundle=RoundAdmissionBundle(context=self.context,connection=self.connection,connection_revision=0,sources=self.sources,
            required_source_hashes=tuple(s.content_hash for s in self.sources),grants=self.grants,continuation_decision=self.decision,
            privacy=self.privacy,budget=self.budget,history=self.history,
            admission=evaluate_round_dispatch_policy(context=self.context,connection=self.connection,privacy=self.privacy,budget=self.budget,
                history=self.history,expected_revision=revision))
        self.store.close()
        script="""
import os,sys
from uuid import UUID
from consilium.core.round_admission import RoundAdmissionBundle
from consilium.core.contracts import OperationIntent,OperationIdentity
from consilium.shell.storage import SQLiteStore
from pathlib import Path
s=SQLiteStore(Path(sys.argv[1])); b=RoundAdmissionBundle.model_validate_json(sys.argv[2]); c=b.context
i=OperationIntent(identity=OperationIdentity(logical_operation_id=UUID(int=50),attempt_id=UUID(int=51)),debate_id=c.debate_id,
 round_id=c.round_id,participant_id=c.participant_id,connection_id=b.connection.connection_id,connection_revision=b.connection_revision,
 expected_revision=c.ledger_revision,frozen_input=c.frozen_input,request_hash=c.frozen_input.content_hash)
if sys.argv[3]=='before':
 s._db.create_function('kill_fixture',0,lambda:os._exit(95))
 s._db.execute('CREATE TEMP TRIGGER kill_before_receipt BEFORE INSERT ON context_admissions BEGIN SELECT kill_fixture(); END')
s.prepare_intent(i,admission_bundle=b)
os._exit(96)
"""
        root=Path(__file__).resolve().parents[2]
        result=subprocess.run([sys.executable,"-c",script,str(self.path),bundle.model_dump_json(),"before" if before else "after"],
            stdin=subprocess.DEVNULL,capture_output=True,timeout=15,env={**os.environ,"PYTHONPATH":str(root/"src")})
        self.assertEqual(result.returncode,95 if before else 96,result.stderr.decode())
        self.store=SQLiteStore(self.path)
        self.assertEqual(self.revision,revision if before else revision+1)
        self.assertEqual(self.store.admissions.get(self.identity.logical_operation_id),None if before else bundle)

    def test_process_exit_before_receipt_insert_leaves_no_partial_intent(self): self.crash_case(True)
    def test_process_exit_after_commit_preserves_complete_packet(self): self.crash_case(False)


class ManualRoundGateTests(unittest.TestCase):
    from test_manual_sources import ManualSourceTests as _fixture
    setUp=_fixture.setUp
    tearDown=_fixture.tearDown
    stage=_fixture.stage
    accept=_fixture.accept
    revision=_fixture.revision

    def test_staged_unaccepted_answer_cannot_open_decision_gate(self):
        self.stage()
        with self.assertRaises(Conflict): self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=self.revision)

    def test_accepted_diverged_answer_cannot_complete_aligned_round(self):
        self.accept(self.stage(round_seen=False))
        with self.assertRaises(Conflict): self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=self.revision)

    def test_accepted_aligned_answer_still_needs_explicit_user_continuation(self):
        self.accept(self.stage())
        self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=self.revision)
        next_round=RoundSpec(round_id=UUID(int=80),debate_id=self.debate.debate_id,number=2,kind="REVIEW",participant_ids=self.debate.participant_ids)
        with self.assertRaises(Conflict): self.store.register_round(next_round,expected_revision=self.revision)
        self.assertEqual(self.store._db.execute("SELECT wait_state FROM debates").fetchone()[0],"WAITING_DECISION")
