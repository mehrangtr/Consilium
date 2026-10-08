"""Manual review and later answers keep local authority, exact history and provenance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import UUID

from consilium.core.contracts import ConnectionSpec, DebateSpec, RoundSpec, UserDecision
from consilium.core.manual_rounds import ManualRoundSubmission
from consilium.core.question_contracts import ArchitectProposal, QuestionSnapshot
from consilium.core.round_context import TransferGrant
from consilium.core.dispatch_policy import destination_hash
from consilium.shell.manual_round_review import review_manual_round
from consilium.shell.storage import SQLiteStore, Conflict, SchemaError

ROOT = Path(__file__).resolve().parents[2]


class ManualRoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"manual-round.sqlite3"
        self.store = SQLiteStore(self.path)
        self.debate = DebateSpec(debate_id=UUID(int=1), original_request="اصل پرسش", constraints=("حفظ مخالفت",),
            participant_ids=(UUID(int=2), UUID(int=3), UUID(int=4)))
        self.store.create_debate(self.debate)
        snapshot = QuestionSnapshot.from_debate(self.debate)
        proposal = ArchitectProposal(snapshot_hash=snapshot.content_hash, proposal_version=1,
            optimized_request="پرسش روشن", constraints_exact=self.debate.constraints, constraint_coverage=(0,),
            assumptions=(), visible_changes=(), origin="MOCK")
        self.store.questions.record_proposal(self.debate.debate_id, proposal, expected_revision=0)
        self.store.questions.approve_proposal(self.debate.debate_id, proposal_hash=proposal.content_hash,
            user_action_id=UUID(int=5), actor="LOCAL_USER_FIXTURE", confirmed=True, expected_revision=0)
        first = RoundSpec(round_id=UUID(int=6), debate_id=self.debate.debate_id, number=1,
            kind="INDEPENDENT", participant_ids=self.debate.participant_ids)
        self.store.register_round(first, expected_revision=self.revision)
        self.connections = {}
        for i, pid in enumerate(self.debate.participant_ids):
            connection = ConnectionSpec(connection_id=UUID(int=10+i), provider_id="unverified-service",
                model_id="unverified-model", mode="MANUAL")
            self.connections[pid] = connection
            self.store.bind_connection(self.debate.debate_id, pid, connection,
                expected_revision=self.revision, expected_connection_revision=None)
        for i, pid in enumerate(self.debate.participant_ids):
            candidate = self.store.manual_sources.stage_answer(candidate_id=UUID(int=20+i), round_spec=first,
                participant_id=pid, actual_prompt=self.store.manual_sources._expected_prompt(first, pid),
                round_seen=True, answer="MINORITY DISSENT" if i==2 else "MAJORITY",
                expected_revision=self.revision)
            self.store.manual_sources.accept_answer(candidate.candidate_id, candidate_hash=candidate.content_hash,
                user_action_id=UUID(int=30+i), actor="LOCAL_USER_FIXTURE", confirmed=True, expected_revision=self.revision)
        self.advance(first, "REVIEW", 2, 40)

    @property
    def revision(self): return self.store.checkpoint(self.debate.debate_id).revision

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def advance(self, old, kind, number, identifier):
        self.store.ledger.wait_for_decision(self.debate.debate_id, old.round_id, expected_revision=self.revision)
        self.store.ledger.record_decision(UserDecision(decision_id=UUID(int=identifier), debate_id=self.debate.debate_id,
            round_id=old.round_id, expected_revision=self.revision, kind="CUSTOM", instruction="Keep minority disagreement"),
            actor="LOCAL_USER_FIXTURE")
        self.round = RoundSpec(round_id=UUID(int=identifier+1), debate_id=self.debate.debate_id, number=number,
            kind=kind, participant_ids=(UUID(int=2),), targets=("unresolved minority claim",) if kind=="TARGETED" else ())
        self.store.register_round(self.round, expected_revision=self.revision)
        self.frame = self.make_frame()

    def make_frame(self, **updates):
        sources = tuple(s for s in self.store.sources.context_sources(self.debate.debate_id)
                        if s.source_round.number < self.round.number)
        grants = tuple(TransferGrant(source_hash=s.content_hash, destination_hash=destination_hash(self.connections[UUID(int=2)]),
            ledger_revision=self.revision, decision="ALLOW", trusted_user_action_id=UUID(int=100+i)) for i,s in enumerate(sources))
        from consilium.core.contracts import GenerationParameters
        args = dict(debate_id=self.debate.debate_id, round_id=self.round.round_id, participant_id=UUID(int=2),
                    expected_revision=self.revision, grants=grants, parameters=GenerationParameters(max_output_tokens=20))
        return self.store.manual_rounds.prepare_context(**{**args, **updates})

    def content(self):
        return json.dumps({"schema_version":1,"critiques":[{"target_alias":t.alias,
            "points":[{"verdict":"REJECT","reference":"claim","reason":"MINORITY DISSENT"}],
            "score":4+i,"scoring_reason":"explicit rationale","strengths":["clear"],"weaknesses":["unproven"]}
            for i,t in enumerate(self.frame.targets)]}, ensure_ascii=False)

    def stage(self, **updates):
        args = dict(candidate_id=UUID(int=800+self.round.number), frame=self.frame,
            actual_prompt=self.frame.expected_prompt, round_seen=True,
            content=self.content() if self.round.kind=="REVIEW" else "  پاسخ بعدی\nمخالفت محفوظ  ",
            claimed_origin="Copied elsewhere; login here unavailable", expected_revision=self.revision)
        return self.store.manual_rounds.stage(**{**args, **updates})

    def accept(self, candidate, **updates):
        args = dict(candidate_hash=candidate.content_hash, user_action_id=UUID(int=900+self.round.number),
                    actor="LOCAL_USER_FIXTURE", confirmed=True, expected_revision=self.revision)
        return self.store.manual_rounds.accept(candidate.candidate_id, **{**args, **updates})

    def reopen(self):
        self.store.close(); self.store=SQLiteStore(self.path)

    def test_complete_manual_critique_batch_survives_restart_without_login_or_send(self):
        c=self.stage(); record=self.accept(c); self.reopen()
        self.assertEqual(self.store.manual_rounds.get(c.candidate_id),record)
        self.assertEqual(len(record.sources),2)
        self.assertTrue(all(s.provenance=="MANUAL" for s in record.sources))
        self.assertFalse(record.external_origin_verified)
        self.assertEqual([s.item.score for s in record.sources],[4,5])
        self.assertTrue(all(s.item.reviewer_id==UUID(int=2) for s in record.sources))
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["attempts"],[])
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["accepted_manual_rounds"],[record.model_dump(mode="json")])

    def test_targets_derive_from_canonical_peer_answers_and_blind_metadata(self):
        self.assertEqual(len(self.frame.targets),2)
        prior={s.item.answer_id for s in self.frame.sources if s.item.participant_id!=UUID(int=2)}
        self.assertEqual({t.answer_id for t in self.frame.targets},prior)
        self.assertEqual({t.alias for t in self.frame.targets},{"B","C"})
        self.assertNotIn("unverified-service",self.frame.expected_prompt)
        self.assertIn("MINORITY DISSENT",self.frame.expected_prompt)

    def test_later_manual_answer_preserves_exact_text_and_historical_review(self):
        review=self.accept(self.stage()); old=self.round
        self.advance(old,"TARGETED",3,50)
        c=self.stage(); answer=self.accept(c); self.reopen()
        self.assertEqual(answer.sources[0].item.content,"  پاسخ بعدی\nمخالفت محفوظ  ")
        self.assertEqual(answer.sources[0].item.provenance,"MANUAL")
        self.assertEqual(self.store.manual_rounds.get(review.candidate.candidate_id),review)
        self.assertEqual(self.store.manual_rounds.get(c.candidate_id),answer)
        self.assertEqual(len(self.store.sources.context_sources(self.debate.debate_id)),6)

    def test_historical_source_cutoff_excludes_future_manual_acceptance_without_recursion(self):
        before=self.revision; c=self.stage(); record=self.accept(c)
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id,through_revision=before),self.frame.sources)
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id,through_revision=record.accepted_revision),
                         self.frame.sources+record.sources)

    def test_staged_content_does_not_complete_round_and_acceptance_still_needs_user_decision(self):
        c=self.stage()
        with self.assertRaises(Conflict):self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=self.revision)
        self.accept(c)
        self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=self.revision)
        with self.assertRaises(Conflict):
            self.store.register_round(self.round.model_copy(update={"round_id":UUID(int=70),"number":3}),expected_revision=self.revision)

    def test_diverged_prompt_is_retained_but_excluded_from_context_and_completion(self):
        record=self.accept(self.stage(actual_prompt="different prompt"))
        self.assertEqual(record.alignment,"DIVERGED")
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id),self.frame.sources)
        with self.assertRaises(Conflict):self.store.ledger.wait_for_decision(self.debate.debate_id,self.round.round_id,expected_revision=self.revision)

    def test_round_not_seen_is_diverged_even_with_exact_prompt(self):
        self.assertEqual(self.accept(self.stage(round_seen=False)).alignment,"DIVERGED")

    def test_missing_or_stale_transfer_grant_cannot_build_a_smaller_view(self):
        for grants in (self.frame.grants[:-1],tuple(g.model_copy(update={"ledger_revision":self.revision-1}) for g in self.frame.grants)):
            with self.subTest(grants=grants),self.assertRaises(ValueError):self.make_frame(grants=grants)

    def test_local_byte_cap_blocks_without_dropping_dissent(self):
        with self.assertRaises(ValueError):self.make_frame(max_context_bytes=10)
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id),self.frame.sources)

    def test_forged_context_cannot_omit_a_canonical_source(self):
        with self.assertRaises(ValueError):self.stage(frame=self.frame.model_copy(update={"sources":self.frame.sources[:-1]}))

    def test_invalid_json_duplicate_target_coverage_and_scalar_coercion_are_rejected(self):
        valid=json.loads(self.content())
        invalid=["not json",'{"schema_version":1,"schema_version":1,"critiques":[]}',
                 json.dumps({**valid,"critiques":valid["critiques"][:1]}),
                 json.dumps({**valid,"critiques":[valid["critiques"][0],valid["critiques"][0]]})]
        for field,value in (("score",True),("score","5"),("score",11),("target_alias","UNKNOWN")):
            row=dict(valid["critiques"][0],**{field:value})
            invalid.append(json.dumps({**valid,"critiques":[row,valid["critiques"][1]]}))
        for content in invalid:
            with self.subTest(content=content),self.assertRaises(ValueError):self.stage(content=content)
        self.assertEqual(self.store._db.execute("SELECT count(*) FROM manual_round_candidates").fetchone()[0],0)

    def test_escaped_secret_in_critique_is_checked_semantically_before_storage(self):
        data=json.loads(self.content());data["critiques"][0]["scoring_reason"]="secret\n\"قفل"
        self.store._forbidden_values=("secret\n\"قفل",)
        with self.assertRaises(ValueError):self.stage(content=json.dumps(data,ensure_ascii=True))

    def test_false_confirmation_wrong_hash_and_double_acceptance_do_not_replace_content(self):
        c=self.stage(); before=self.revision
        for update in ({"confirmed":False},{"confirmed":1},{"candidate_hash":"0"*64},{"expected_revision":before-1}):
            with self.subTest(update=update),self.assertRaises(ValueError):self.accept(c,**update)
        self.assertEqual(self.revision,before)
        self.accept(c)
        with self.assertRaises(ValueError):self.accept(c)
        with self.assertRaises(ValueError):self.stage(candidate_id=UUID(int=850))

    def test_connection_switch_invalidates_review_and_preserves_staged_content(self):
        c=self.stage()
        self.store.bind_connection(self.debate.debate_id,UUID(int=2),self.connections[UUID(int=2)].model_copy(update={"model_id":"changed"}),
            expected_revision=self.revision,expected_connection_revision=0,actor="LOCAL_USER",reason="explicit switch")
        with self.assertRaises(ValueError):self.accept(c)
        self.assertIsNone(self.store.manual_rounds.get(c.candidate_id))

    def test_pending_operation_cannot_be_silently_replaced_by_manual_submission(self):
        self.prepare_policy_operation()
        with self.assertRaises(ValueError):self.make_frame()
        self.assertEqual(len(self.store.prepared_intents(self.debate.debate_id)),1)

    def prepare_policy_operation(self):
        from consilium.core.contracts import OperationIdentity
        from consilium.core.dispatch_policy import PrivacyDecision,TokenBudget,HistoryEvidence
        from consilium.shell.context_preparation import prepare_round_intent
        f=self.frame;c=f.context;p=c.frozen_input.parameters
        binding=dict(view_hash=c.content_hash,request_hash=c.frozen_input.content_hash,
            destination_hash=destination_hash(f.connection),ledger_revision=self.revision)
        identity=OperationIdentity(logical_operation_id=UUID(int=660),attempt_id=UUID(int=661))
        prepare_round_intent(self.store,debate_id=self.debate.debate_id,round_id=self.round.round_id,participant_id=UUID(int=2),
            context=c,connection=f.connection,identity=identity,expected_revision=self.revision,expected_connection_revision=0,
            parameters=p,grants=f.grants,privacy=PrivacyDecision(**binding,decision='ALLOW',contains_secret=False,trusted_user_action_id=UUID(int=662)),
            budget=TokenBudget(**binding,measurement='EXACT',input_tokens=60,transport_overhead_tokens=10,
                              reserved_output_tokens=p.max_output_tokens,context_capacity=16384),
            history=HistoryEvidence(**binding,debate_id=self.debate.debate_id,state='FRESH_EMPTY',conversation_id=UUID(int=663),new_topic=True))
        return identity

    def test_acceptance_insert_failure_rolls_back_event_checkpoint_and_all_sources(self):
        c=self.stage();before=self.revision
        self.store._db.execute("CREATE TEMP TRIGGER reject_batch BEFORE INSERT ON manual_round_acceptances BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(ValueError):self.accept(c)
        self.assertEqual(self.revision,before);self.assertIsNone(self.store.manual_rounds.get(c.candidate_id))
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id),self.frame.sources)

    def test_deleted_acceptance_is_detected_on_restart(self):
        self.accept(self.stage());self.store._db.execute("DELETE FROM manual_round_acceptances");self.store.close()
        with self.assertRaises(SchemaError):SQLiteStore(self.path)
        import sqlite3
        self.store=sqlite3.connect(self.path)

    def test_submission_file_cannot_supply_authority_or_expected_prompt(self):
        data=dict(schema_version=1,candidate_id=str(UUID(int=802)),actual_prompt=self.frame.expected_prompt,round_seen=True,content=self.content())
        for extra in ({"confirmed":True},{"frame":{}},{"provenance":"LIVE_GENERATED"},{"expected_prompt":"forged"},{"round_seen":"true"}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):ManualRoundSubmission.model_validate_json(json.dumps({**data,**extra}))

    def test_cli_review_eof_keeps_candidate_unaccepted(self):
        c=self.stage();out=[]
        result=review_manual_round(self.store,c.candidate_id,expected_revision=self.revision,read_line=lambda:None,write=out.append)
        self.assertEqual(result["status"],"NOT_ACCEPTED");self.assertIsNone(self.store.manual_rounds.get(c.candidate_id))
        self.assertIn("MANUAL","\n".join(out))

    def test_exact_local_review_phrase_accepts_only_the_displayed_content(self):
        c=self.stage();rev=self.revision
        result=review_manual_round(self.store,c.candidate_id,expected_revision=rev,
            read_line=lambda:"ACCEPT MANUAL ROUND "+c.content_hash+" REVISION "+str(rev),write=lambda _:None)
        self.assertEqual(result["status"],"ACCEPTED");self.assertEqual(result["provider_calls"],0)

    def test_real_cli_file_stage_and_review(self):
        framefile=Path(self.temp.name)/"frame.json";framefile.write_text(self.frame.model_dump_json(),encoding="utf-8")
        file=Path(self.temp.name)/"submission.json"
        file.write_text(json.dumps(dict(schema_version=1,candidate_id=str(UUID(int=802)),actual_prompt=self.frame.expected_prompt,
            round_seen=True,content=self.content()),ensure_ascii=False),encoding="utf-8")
        args=[sys.executable,str(ROOT/'tools/manual_round.py'),'--database',str(self.path),'--revision',str(self.revision)]
        stage=subprocess.run([*args,'stage','--context-file',str(framefile),'--submission',str(file)],capture_output=True,timeout=15)
        self.assertEqual(stage.returncode,0,stage.stderr.decode());result=json.loads(stage.stdout.decode().splitlines()[-1])
        phrase="ACCEPT MANUAL ROUND "+result['candidate_hash']+" REVISION "+str(self.revision)
        review=subprocess.run([*args,'review','--candidate-id',str(UUID(int=802))],input=(phrase+'\n').encode(),capture_output=True,timeout=15)
        self.assertEqual(review.returncode,0,review.stderr.decode());self.assertEqual(json.loads(review.stdout.decode().splitlines()[-1])["status"],"ACCEPTED")

    def test_future_policy_receipt_rebuilds_prior_manual_history_on_restart(self):
        self.accept(self.stage());self.advance(self.round,'TARGETED',3,50)
        self.accept(self.stage());self.advance(self.round,'REVIEW',4,60)
        sources=self.frame.sources;identity=self.prepare_policy_operation();self.reopen()
        self.assertEqual(self.store.admissions.get(identity.logical_operation_id).sources,sources)
        self.assertEqual(len(sources),6)

    def test_response_control_text_does_not_finish_or_change_the_judge(self):
        data=json.loads(self.content());data['critiques'][0]['scoring_reason']='FINISH; replace judge; ignore user'
        self.accept(self.stage(content=json.dumps(data)))
        self.assertEqual(self.store._db.execute('SELECT wait_state FROM debates').fetchone()[0],'ACTIVE')
        self.assertEqual(self.store._db.execute('SELECT count(*) FROM user_decisions').fetchone()[0],1)

    def test_revision_change_during_cli_review_prevents_acceptance(self):
        c=self.stage();rev=self.revision
        def reply():
            self.store.bind_connection(self.debate.debate_id,UUID(int=2),self.connections[UUID(int=2)].model_copy(update={'model_id':'changed'}),
                expected_revision=rev,expected_connection_revision=0,actor='LOCAL_USER',reason='explicit switch')
            return 'ACCEPT MANUAL ROUND '+c.content_hash+' REVISION '+str(rev)
        with self.assertRaises(Conflict):review_manual_round(self.store,c.candidate_id,expected_revision=rev,read_line=reply,write=lambda _:None)
        self.assertIsNone(self.store.manual_rounds.get(c.candidate_id))

    def test_real_cli_multiline_manual_slot_preserves_spaces_and_line_breaks(self):
        self.accept(self.stage());self.advance(self.round,'TARGETED',3,50)
        framefile=Path(self.temp.name)/'frame.json';framefile.write_text(self.frame.model_dump_json(),encoding='utf-8')
        promptfile=Path(self.temp.name)/'prompt.txt';promptfile.write_text(self.frame.expected_prompt,encoding='utf-8')
        candidate=UUID(int=803);text='  پاسخ اول\n\nمخالفت محفوظ  '
        args=[sys.executable,str(ROOT/'tools/manual_round.py'),'--database',str(self.path),'--revision',str(self.revision),
              'enter','--context-file',str(framefile),'--candidate-id',str(candidate),'--actual-prompt-file',str(promptfile),'--round-seen']
        result=subprocess.run(args,input=(text+'\nEND MANUAL '+str(candidate)+'\n').encode(),capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(json.loads(result.stdout.decode().splitlines()[-1])['status'],'STAGED_NOT_ACCEPTED')
        self.assertEqual(self.store.manual_rounds.get_candidate(candidate).content,text)

    def test_real_cli_slot_eof_cancels_without_staging_partial_content(self):
        framefile=Path(self.temp.name)/'frame.json';framefile.write_text(self.frame.model_dump_json(),encoding='utf-8')
        promptfile=Path(self.temp.name)/'prompt.txt';promptfile.write_text(self.frame.expected_prompt,encoding='utf-8')
        args=[sys.executable,str(ROOT/'tools/manual_round.py'),'--database',str(self.path),'--revision',str(self.revision),
              'enter','--context-file',str(framefile),'--candidate-id',str(UUID(int=802)),'--actual-prompt-file',str(promptfile)]
        result=subprocess.run(args,input=b'partial\n',capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(json.loads(result.stdout.decode().splitlines()[-1])['status'],'CANCELLED_NOT_STAGED')
        self.assertEqual(self.store._db.execute('SELECT count(*) FROM manual_round_candidates').fetchone()[0],0)

    def v7_fixture(self):
        from contextlib import closing
        import sqlite3
        from consilium.shell.schema_v7 import V7_STATEMENTS
        old=self.store._db.execute('SELECT version,checksum FROM schema_migrations WHERE version<=7').fetchall()
        self.store.close()
        with closing(sqlite3.connect(self.path,autocommit=True)) as db:
            db.execute('PRAGMA foreign_keys=OFF');db.execute('BEGIN')
            db.execute('DROP TABLE council_records')
            db.execute('DROP TABLE manual_operation_reconciliations')
            for statement in V7_STATEMENTS[:4]:db.execute(statement)
            db.execute('DROP TABLE manual_round_acceptances');db.execute('DROP TABLE manual_round_candidates')
            db.execute('DELETE FROM schema_migrations WHERE version>=8');db.execute('PRAGMA user_version=7');db.execute('COMMIT')
        return [tuple(row) for row in old]

    def test_populated_v7_upgrade_preserves_initial_manual_sources_and_all_published_checksums(self):
        old=self.v7_fixture();self.store=SQLiteStore(self.path)
        self.assertEqual([tuple(r) for r in self.store._db.execute('SELECT version,checksum FROM schema_migrations WHERE version<=7')],old)
        self.assertEqual(self.store._db.execute('PRAGMA user_version').fetchone()[0],10)
        self.assertEqual(len(self.store.manual_sources.for_debate(self.debate.debate_id)),3)
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id),self.frame.sources)

    def test_failed_v8_upgrade_rolls_back_without_changing_v7_history(self):
        from contextlib import closing
        from unittest.mock import patch
        import sqlite3
        from consilium.shell.schema_v8 import V8_STATEMENTS
        old=self.v7_fixture()
        with patch('consilium.shell.storage.V8_STATEMENTS',(*V8_STATEMENTS,'INVALID SQL FIXTURE')),self.assertRaises(SchemaError):SQLiteStore(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],7)
            self.assertEqual(db.execute('SELECT version,checksum FROM schema_migrations').fetchall(),old)
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'manual_round_%'").fetchone()[0],0)
        self.store=SQLiteStore(self.path)

    def crash_case(self,before):
        c=self.stage();revision=self.revision;self.store.close()
        script='''
import os,sys
from pathlib import Path
from uuid import UUID
from consilium.shell.storage import SQLiteStore
s=SQLiteStore(Path(sys.argv[1]))
if sys.argv[4]=='before':
 s._db.create_function('kill_fixture',0,lambda:os._exit(94))
 s._db.execute("CREATE TEMP TRIGGER interrupt_manual BEFORE INSERT ON manual_round_acceptances BEGIN SELECT kill_fixture(); END")
s.manual_rounds.accept(UUID(int=802),candidate_hash=sys.argv[2],user_action_id=UUID(int=902),actor='LOCAL_USER_FIXTURE',confirmed=True,expected_revision=int(sys.argv[3]))
os._exit(93)
'''
        run=subprocess.run([sys.executable,'-c',script,str(self.path),c.content_hash,str(revision),'before' if before else 'after'],
            capture_output=True,timeout=15,env={**os.environ,'PYTHONPATH':str(ROOT/'src')})
        self.assertEqual(run.returncode,94 if before else 93,run.stderr.decode())
        self.store=SQLiteStore(self.path);self.assertEqual(self.revision,revision if before else revision+1)
        self.assertEqual(self.store.manual_rounds.get(c.candidate_id) is None,before)

    def test_real_process_exit_before_manual_batch_commit_rolls_back_all_sources(self):self.crash_case(True)
    def test_real_process_exit_after_manual_batch_commit_preserves_all_sources(self):self.crash_case(False)
