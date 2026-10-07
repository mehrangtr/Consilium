"""Trust-boundary and durable observed-context tests; no live provider claims."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import UUID

import test_context_preparation as initial
import test_round_admission as later
from consilium.core.contracts import AdapterRequest, Message
from consilium.core.context_observations import HistorySnapshot, ObservationReceipt, check_history
from consilium.core.dispatch_policy import PolicyBlocked
from consilium.shell.context_observers import observe_context
from consilium.shell.storage import SQLiteStore, SchemaError, Conflict


class ContextObserverTests(unittest.TestCase):
    setUp = initial.ContextPreparationTests.setUp
    tearDown = initial.ContextPreparationTests.tearDown
    prepare = initial.ContextPreparationTests.prepare

    def snapshot(self, **updates):
        from consilium.core.dispatch_policy import destination_hash
        return HistorySnapshot(debate_id=self.debate.debate_id,
            destination_hash=destination_hash(self.connection), conversation_id=None,
            complete=True, entries=(), **updates)

    def observe(self, **updates):
        args=dict(store=self.store, context=self.context, connection=self.connection,
            expected_revision=3, expected_connection_revision=0, privacy=self.privacy,
            snapshot=self.snapshot(), new_topic=True, preference="PREFER_CURRENT", user_action_id=None)
        args.update(updates)
        return observe_context(**args)

    def prepared(self):
        receipt, budget, history=self.observe()
        self.prepare(budget=budget,history=history,observation=receipt)
        return receipt

    def test_actual_local_measurement_is_exact_for_its_declared_mock_codec(self):
        receipt,budget,history=self.observe()
        self.assertEqual(budget.input_tokens,receipt.token_count)
        self.assertGreater(budget.input_tokens,60)
        self.assertEqual(receipt.tokenizer_id,"mock:utf8-byte-v1")
        self.assertEqual(receipt.scope,"OFFLINE_OBSERVER_NOT_LIVE_CERTIFICATION")
        self.assertEqual(history.state,"NO_REMOTE_HISTORY")
        self.assertEqual(receipt.sources,())

    def test_observed_packet_persists_atomically_and_reconstructs_after_restart(self):
        receipt=self.prepared()
        expected=self.store.admissions.get(self.identity.logical_operation_id)
        self.store.close(); self.store=SQLiteStore(self.path)
        saved=self.store.admissions.get(self.identity.logical_operation_id)
        self.assertEqual(saved,expected)
        self.assertEqual(saved.observation,receipt)
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["context_admissions"][0]["bundle"],
                         saved.model_dump(mode="json"))
        self.assertEqual(self.store.get_intent(self.identity.attempt_id).frozen_input,self.context.frozen_input)

    def test_observation_never_unlocks_live_send_or_automatic_retry(self):
        self.prepared()
        intent=self.store.get_intent(self.identity.attempt_id)
        with self.assertRaises(Conflict):
            self.store.ledger.begin_send(AdapterRequest(intent=intent,connection=self.connection,timeout_seconds=10.0),expected_revision=4)
        self.assertFalse(self.store.ledger.resume(self.identity.attempt_id).automatic_send)

    def test_unregistered_real_provider_cannot_use_mock_tokenizer(self):
        with self.assertRaisesRegex(PolicyBlocked,"OBSERVER_NOT_REGISTERED"):
            self.observe(connection=self.connection.model_copy(update={"provider_id":"anthropic"}))
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_wrong_model_is_not_treated_as_compatible(self):
        with self.assertRaises(PolicyBlocked):
            self.observe(connection=self.connection.model_copy(update={"model_id":"other-model"}))

    def test_unverified_or_nonempty_stateless_history_fails_closed(self):
        for snapshot in (self.snapshot().model_copy(update={"complete":False}),
                         self.snapshot().model_copy(update={"entries":(Message(role="ASSISTANT",content="PEER"),)}),
                         self.snapshot().model_copy(update={"conversation_id":UUID(int=50)})):
            with self.subTest(snapshot=snapshot),self.assertRaises(PolicyBlocked):self.observe(snapshot=snapshot)

    def test_peer_text_cannot_supply_permission_or_observer_fields(self):
        payload={**self.snapshot().model_dump(mode="python"),"decision":"ALLOW","token_count":1,"provider_verified":True}
        with self.assertRaises(ValueError):HistorySnapshot.model_validate(payload)

    def test_known_semantic_secret_blocks_before_measurement_or_intent(self):
        self.store._forbidden_values=(self.debate.original_request,)
        with self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_unknown_privacy_cannot_be_promoted_by_observer(self):
        with self.assertRaises(PolicyBlocked):self.observe(privacy=self.privacy.model_copy(update={"decision":"UNKNOWN"}))

    def test_stale_state_or_binding_is_rejected(self):
        for update in ({"expected_revision":2},{"expected_connection_revision":1}):
            with self.subTest(update=update),self.assertRaises(ValueError):self.observe(**update)

    def test_forged_context_is_not_a_canonical_source(self):
        context=self.context.model_copy(update={"proposal_hash":"0"*64})
        with self.assertRaises(ValueError):self.observe(context=context)

    def test_exact_budget_boundary_and_overflow_preserve_question(self):
        receipt,budget,history=self.observe()
        before=self.context.frozen_input.canonical_bytes()
        from consilium.core.dispatch_policy import evaluate_dispatch_policy
        required=budget.input_tokens+budget.reserved_output_tokens
        evaluate_dispatch_policy(context=self.context,connection=self.connection,privacy=self.privacy,
            budget=budget.model_copy(update={"context_capacity":required}),history=history,expected_revision=3)
        with self.assertRaises(PolicyBlocked):
            evaluate_dispatch_policy(context=self.context,connection=self.connection,privacy=self.privacy,
                budget=budget.model_copy(update={"context_capacity":required-1}),history=history,expected_revision=3)
        self.assertEqual(before,self.context.frozen_input.canonical_bytes())

    def test_forged_count_codec_or_implementation_receipt_cannot_prepare(self):
        receipt,budget,history=self.observe()
        for update in ({"token_count":1},{"tokenizer_id":"provider-claims-exact"},
                       {"observer_implementation_hash":"0"*64},{"request_hash":"0"*64}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                self.prepare(budget=budget,history=history,observation=receipt.model_copy(update=update))
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_final_observed_receipt_failure_rolls_back_intent_and_event(self):
        receipt,budget,history=self.observe()
        self.store._db.execute("CREATE TEMP TRIGGER refuse_receipt BEFORE INSERT ON context_admissions "
            "BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Conflict):self.prepare(budget=budget,history=history,observation=receipt)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision,3)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id),())

    def test_receipt_tampering_is_detected_on_restart(self):
        self.prepared()
        row=self.store._db.execute("SELECT bundle_json FROM context_admissions").fetchone()
        data=json.loads(row[0]);data["observation"]["token_count"]=1
        self.store._db.execute("UPDATE context_admissions SET bundle_json=?",(json.dumps(data),))
        self.store.close()
        with self.assertRaises(SchemaError):SQLiteStore(self.path)

    def test_historical_unobserved_receipts_remain_readable_without_migration(self):
        self.prepare(); expected=self.store.admissions.get(self.identity.logical_operation_id)
        self.store.close();self.store=SQLiteStore(self.path)
        self.assertEqual(expected,self.store.admissions.get(self.identity.logical_operation_id))
        self.assertEqual(self.store._db.execute("PRAGMA user_version").fetchone()[0],9)

    def crash_case(self,before):
        receipt,budget,history=self.observe()
        self.store.close()
        script='''
import os,sys,json
from pathlib import Path
from uuid import UUID
from consilium.core.contracts import OperationIdentity,GenerationParameters
from consilium.core.context_observations import ObservationReceipt
from consilium.core.dispatch_policy import PrivacyDecision,TokenBudget,HistoryEvidence
from consilium.core.independent_context import IndependentContext
from consilium.core.contracts import ConnectionSpec
from consilium.shell.context_preparation import prepare_independent_intent
from consilium.shell.storage import SQLiteStore
s=SQLiteStore(Path(sys.argv[1]));d=json.loads(sys.argv[2])
if sys.argv[3]=='before':
 s._db.create_function('stop_process',0,lambda:os._exit(97))
 s._db.execute("CREATE TEMP TRIGGER stop_receipt BEFORE INSERT ON context_admissions BEGIN SELECT stop_process(); END")
prepare_independent_intent(s,context=IndependentContext.model_validate_json(json.dumps(d['context'])),connection=ConnectionSpec.model_validate_json(json.dumps(d['connection'])),
 identity=OperationIdentity(logical_operation_id=UUID(int=7),attempt_id=UUID(int=8)),expected_revision=3,expected_connection_revision=0,
 parameters=GenerationParameters(max_output_tokens=20),privacy=PrivacyDecision.model_validate_json(json.dumps(d['privacy'])),
 budget=TokenBudget.model_validate_json(json.dumps(d['budget'])),history=HistoryEvidence.model_validate_json(json.dumps(d['history'])),observation=ObservationReceipt.model_validate_json(json.dumps(d['receipt'])))
os._exit(98)
'''
        data={name:value.model_dump(mode="json") for name,value in dict(context=self.context,connection=self.connection,
            privacy=self.privacy,budget=budget,history=history,receipt=receipt).items()}
        root=Path(__file__).resolve().parents[2]
        result=subprocess.run([sys.executable,"-c",script,str(self.path),json.dumps(data),"before" if before else "after"],
            stdin=subprocess.DEVNULL,capture_output=True,timeout=15,env={**os.environ,"PYTHONPATH":str(root/"src")})
        self.assertEqual(result.returncode,97 if before else 98,result.stderr.decode())
        self.store=SQLiteStore(self.path)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision,3 if before else 4)
        self.assertEqual(len(self.store.prepared_intents(self.debate.debate_id)),0 if before else 1)
        if not before:self.assertEqual(self.store.admissions.get(self.identity.logical_operation_id).observation,receipt)

    def test_new_topic_has_new_debate_and_never_rewrites_prior_question(self):
        from consilium.core.contracts import DebateSpec
        before=self.store.export_debate(self.debate.debate_id)
        fresh=DebateSpec(debate_id=UUID(int=100),original_request="A different topic",
                         participant_ids=self.debate.participant_ids,constraints=("New topic constraint",))
        self.store.create_debate(fresh)
        self.assertEqual(self.store.get_debate(fresh.debate_id),fresh)
        self.assertEqual(self.store.export_debate(self.debate.debate_id),before)
        self.assertIsNone(self.store.questions.get_adopted(fresh.debate_id))
        with self.assertRaises(PolicyBlocked):self.observe(snapshot=self.snapshot().model_copy(update={"debate_id":fresh.debate_id}))

    def test_process_exit_before_receipt_commit_leaves_no_partial_packet(self):self.crash_case(True)
    def test_process_exit_after_receipt_commit_recovers_exact_packet(self):self.crash_case(False)


class HistoryAuthorizationTests(unittest.TestCase):
    def setUp(self):
        from consilium.core.contracts import ConnectionSpec
        from consilium.core.dispatch_policy import destination_hash
        self.connection=ConnectionSpec(connection_id=UUID(int=1),provider_id="mock",model_id="mock-v1",mode="BROWSER",account_binding_id=UUID(int=2))
        self.debate=UUID(int=3);self.own=(Message(role="USER",content="Own request"),Message(role="ASSISTANT",content="Own answer"))
        self.snapshot=HistorySnapshot(debate_id=self.debate,destination_hash=destination_hash(self.connection),
            conversation_id=UUID(int=4),complete=True,entries=self.own)

    def check(self,**updates):
        args=dict(snapshot=self.snapshot,connection=self.connection,debate_id=self.debate,authorized_entries=self.own,
            new_topic=False,preference="PREFER_CURRENT",user_action_id=None);args.update(updates)
        return check_history(**args)

    def test_valid_current_conversation_is_preferred(self):self.assertEqual(self.check(),"VERIFIED_AUTHORIZED")
    def test_peer_or_hidden_extra_entry_is_rejected(self):
        with self.assertRaises(PolicyBlocked):self.check(snapshot=self.snapshot.model_copy(update={"entries":self.own+(Message(role="ASSISTANT",content="Peer answer"),)}))
    def test_incomplete_history_is_rejected(self):
        with self.assertRaises(PolicyBlocked):self.check(snapshot=self.snapshot.model_copy(update={"complete":False}))
    def test_new_topic_requires_empty_fresh_conversation(self):
        with self.assertRaises(PolicyBlocked):self.check(new_topic=True)
        self.assertEqual(self.check(new_topic=True,snapshot=self.snapshot.model_copy(update={"entries":()})),"FRESH_EMPTY")
    def test_explicit_new_conversation_requires_local_action_and_empty_history(self):
        with self.assertRaises(PolicyBlocked):self.check(preference="NEW_CONVERSATION")
        with self.assertRaises(PolicyBlocked):self.check(preference="NEW_CONVERSATION",user_action_id=UUID(int=5))
        self.assertEqual(self.check(preference="NEW_CONVERSATION",user_action_id=UUID(int=5),snapshot=self.snapshot.model_copy(update={"entries":()})),"FRESH_EMPTY")
    def test_identity_changes_invalidate_history(self):
        for update in ({"debate_id":UUID(int=7)},{"destination_hash":"0"*64},{"conversation_id":None}):
            with self.subTest(update=update),self.assertRaises(PolicyBlocked):self.check(snapshot=self.snapshot.model_copy(update=update))
    def test_missing_account_or_boolean_choice_cannot_be_authority(self):
        for update in ({"connection":self.connection.model_copy(update={"account_binding_id":None})},{"new_topic":1},
                       {"preference":"model-requested-fresh"},{"user_action_id":True,"preference":"NEW_CONVERSATION"}):
            with self.subTest(update=update),self.assertRaises(ValueError):self.check(**update)


class LaterContextObserverTests(unittest.TestCase):
    setUp=later.RoundAdmissionTests.setUp
    tearDown=later.RoundAdmissionTests.tearDown
    revision=later.RoundAdmissionTests.revision
    refresh=later.RoundAdmissionTests.refresh
    args=later.RoundAdmissionTests.args
    prepare=later.RoundAdmissionTests.prepare

    def observed(self):
        from consilium.core.dispatch_policy import destination_hash
        self.connection=self.connection.model_copy(update={"provider_id":"mock","model_id":"mock-v1","mode":"API"})
        self.store.bind_connection(self.debate.debate_id,UUID(int=2),self.connection,expected_revision=self.revision,
            expected_connection_revision=0,actor="FIXTURE_USER",reason="Offline observer fixture")
        self.refresh()
        snapshot=HistorySnapshot(debate_id=self.debate.debate_id,destination_hash=destination_hash(self.connection),
            conversation_id=None,complete=True,entries=())
        return observe_context(store=self.store,context=self.context,connection=self.connection,expected_revision=self.revision,
            expected_connection_revision=1,privacy=self.privacy,snapshot=snapshot,new_topic=False,
            preference="PREFER_CURRENT",user_action_id=None,grants=self.grants)

    def test_sources_are_observed_from_actual_canonical_manual_records(self):
        receipt,budget,history=self.observed()
        self.assertEqual(tuple(s.source_hash for s in receipt.sources),tuple(s.content_hash for s in self.sources))
        self.assertTrue(all(s.provenance=="MANUAL" and not s.external_origin_verified for s in receipt.sources))
        self.assertIn("MINORITY DISSENT",self.context.frozen_input.messages[1].content)
        self.prepare(budget=budget,history=history,observation=receipt,expected_connection_revision=1)
        self.store.close();self.store=SQLiteStore(self.path)
        self.assertEqual(self.store.admissions.get(self.identity.logical_operation_id).observation,receipt)

    def test_dropped_or_reclassified_source_cannot_be_observer_attestation(self):
        receipt,budget,history=self.observed()
        with self.assertRaises(ValueError):
            self.prepare(budget=budget,history=history,observation=receipt.model_copy(update={"sources":receipt.sources[:1]}),expected_connection_revision=1)
        changed=receipt.sources[1].model_copy(update={"provenance":"MOCK"})
        with self.assertRaises(ValueError):
            self.prepare(budget=budget,history=history,observation=receipt.model_copy(update={"sources":(receipt.sources[0],changed)}),expected_connection_revision=1)

    def test_source_secret_is_blocked_before_an_observed_packet(self):
        self.store._forbidden_values=("MINORITY DISSENT",)
        with self.assertRaises(ValueError):self.observed()
