"""Executed council trust boundaries, complete flows and genuine process exits."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from uuid import UUID, uuid4

from consilium.adapters.mock import MockAdapter, Scenario
from consilium.core.contracts import ConnectionSpec, DebateSpec, OperationIdentity, UserDecision
from consilium.core.question_contracts import ArchitectProposal, QuestionSnapshot
from consilium.shell.council_export import export_council
from consilium.shell.storage import SQLiteStore, Conflict, SchemaError, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]
ACTOR = 'EXPLICIT_OFFLINE_TEST_USER'


class CouncilCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name)/'council.sqlite3'
        self.store = SQLiteStore(self.path); self.pid = (UUID(int=2), UUID(int=3))
        self.debate = DebateSpec(debate_id=UUID(int=1), participant_ids=self.pid,
            original_request='  انتخاب روش پژوهش\nبا حفظ محدودیت‌ها  ', constraints=('بدون هزینه', 'حفظ مخالفت'))
        self.store.create_debate(self.debate)
        snap=QuestionSnapshot.from_debate(self.debate)
        proposal=ArchitectProposal(snapshot_hash=snap.content_hash, proposal_version=1,
            optimized_request='روش پژوهش را با شواهد و هزینه مقایسه کن', constraints_exact=self.debate.constraints,
            constraint_coverage=(0,1), assumptions=(), visible_changes=('درخواست شاهد افزوده شد',), origin='MOCK')
        self.store.questions.record_proposal(self.debate.debate_id,proposal,expected_revision=0)
        self.store.questions.approve_proposal(self.debate.debate_id,proposal_hash=proposal.content_hash,
            user_action_id=uuid4(),actor=ACTOR,confirmed=True,expected_revision=0)
        for i,pid in enumerate(self.pid):
            self.store.bind_connection(self.debate.debate_id,pid,ConnectionSpec(connection_id=UUID(int=10+i),
                provider_id='mock',model_id='mock-v1',mode='API'),expected_revision=self.revision,expected_connection_revision=None)
        self.start('INDEPENDENT')

    @property
    def revision(self): return self.store.checkpoint(self.debate.debate_id).revision
    @property
    def council(self): return self.store.council
    @property
    def round(self): return self.council.current_round(self.debate.debate_id)
    def tearDown(self): self.store.close(); self.temp.cleanup()
    def reopen(self): self.store.close(); self.store=SQLiteStore(self.path)

    def start(self,kind,targets=(),participants=None):
        return self.council.start_round(debate_id=self.debate.debate_id,round_id=uuid4(),kind=kind,
            targets=targets,participant_ids=participants,expected_revision=self.revision)

    def decide(self,kind,**changes):
        args=dict(decision_id=uuid4(),debate_id=self.debate.debate_id,round_id=self.round.round_id,
                  expected_revision=self.revision,kind=kind,instruction='Resolve only missing evidence' if kind=='CUSTOM' else None)
        return self.council.decide(UserDecision(**{**args,**changes}),actor=ACTOR,confirmed=True)

    def prepare(self,pid=None,**changes):
        args=dict(debate_id=self.debate.debate_id,participant_id=pid or self.pid[0],
            identity=OperationIdentity(logical_operation_id=uuid4(),attempt_id=uuid4()),expected_revision=self.revision,
            user_action_id=uuid4(),actor=ACTOR,confirmed=True)
        return self.council.prepare_mock(**{**args,**changes})

    def review_content(self,targets,score=6):
        return json.dumps({'schema_version':1,'critiques':[{'target_alias':t.alias,
            'points':[{'verdict':'PARTIALLY_ACCEPT','reference':'evidence','reason':'MINORITY_DISSENT: independent evidence is missing'},
                      {'verdict':'ACCEPT','reference':'cost','reason':'constraint preserved'}],
            'score':score,'scoring_reason':'Explicit rubric; missing evidence reduces confidence',
            'strengths':['constraint preserved'],'weaknesses':['missing evidence']} for t in targets]},ensure_ascii=False)

    def submit(self,pid,content=None,score=6):
        connection,_=self.council.binding(self.debate.debate_id,pid)
        if connection.mode=='MANUAL':
            if self.round.kind=='INDEPENDENT':
                c=self.store.manual_sources.stage_answer(candidate_id=uuid4(),round_spec=self.round,participant_id=pid,
                    actual_prompt=self.store.manual_sources._expected_prompt(self.round,pid),round_seen=True,
                    answer=content or ('MAJORITY' if pid==self.pid[0] else 'MINORITY_DISSENT: missing evidence'),
                    expected_revision=self.revision,claimed_origin='Unverified copied external response')
                return self.store.manual_sources.accept_answer(c.candidate_id,candidate_hash=c.content_hash,
                    user_action_id=uuid4(),actor=ACTOR,confirmed=True,expected_revision=self.revision)
            frame=self.store.manual_rounds.prepare_context(debate_id=self.debate.debate_id,round_id=self.round.round_id,
                participant_id=pid,expected_revision=self.revision,grants=self.council.grants(self.round,pid,self.revision,uuid4()))
            c=self.store.manual_rounds.stage(candidate_id=uuid4(),frame=frame,actual_prompt=frame.expected_prompt,
                round_seen=True,content=content or (self.review_content(frame.targets,score) if self.round.kind=='REVIEW' else 'MINORITY_DISSENT persists'),
                expected_revision=self.revision,claimed_origin='Unverified copied external response')
            return self.store.manual_rounds.accept(c.candidate_id,candidate_hash=c.content_hash,user_action_id=uuid4(),
                actor=ACTOR,confirmed=True,expected_revision=self.revision)
        request=self.prepare(pid)
        contract=self.store.artifacts.get_contract(request.intent)
        output=self.review_content(contract.targets,score) if self.round.kind=='REVIEW' else json.dumps({
            'schema_version':1,'answer':content or ('MAJORITY' if pid==self.pid[0] else 'MINORITY_DISSENT: missing evidence')},ensure_ascii=False)
        return self.council.execute_mock(request,MockAdapter(response_content=output),expected_revision=self.revision)

    def complete_round(self):
        for pid in self.round.participant_ids: self.submit(pid)
        return self.council.seal_round(debate_id=self.debate.debate_id,expected_revision=self.revision)

    def through_review(self):
        self.complete_round(); self.decide('CONTINUE'); self.start('REVIEW'); self.complete_round()

    def select(self,**changes):
        args=dict(debate_id=self.debate.debate_id,participant_id=self.pid[0],round_id=uuid4(),
            expected_revision=self.revision,user_action_id=uuid4(),actor=ACTOR,confirmed=True)
        return self.council.select_judge(**{**args,**changes})

    def judge_output(self,**changes):
        return json.dumps(dict(schema_version=1,conclusion='Recommendation with uncertain evidence',evidence=['local comparison'],
            uncertainty=['not independently verified'],unresolved_issues=['evidence gap'],dissent=['MINORITY_DISSENT'],
            agreement_is_truth_probability=False,**changes),ensure_ascii=False)

    def finish(self):
        self.decide('FINISH'); selected=self.select(); self.submit(selected.participant_id,self.judge_output())
        return self.council.finalize(debate_id=self.debate.debate_id,expected_revision=self.revision)

    def test_full_mock_council_and_targeted_continuation_survive_restart(self):
        self.through_review(); self.decide('CUSTOM'); self.start('TARGETED',('only missing evidence',)); self.complete_round()
        result=self.finish(); before=self.store.export_debate(self.debate.debate_id); self.reopen()
        self.assertEqual(before,self.store.export_debate(self.debate.debate_id))
        self.assertEqual(self.council.recover(self.debate.debate_id)['next_action'],'USE_FINAL')
        self.assertFalse(self.council.recover(self.debate.debate_id)['automatic_send'])
        self.assertTrue(result.preserved_objections); self.assertTrue(result.judge.participated_in_rounds)
        self.assertEqual(result.judge.bias_mitigation,'BLIND_ALL_EVIDENCE_WITH_DISSENT')
        self.assertEqual(before['wait_state'],'COMPLETED');self.assertTrue(before['debate_completed'])
        self.assertEqual(before['debate']['original_request'],self.debate.original_request)
        with self.assertRaises(Conflict): self.start('TARGETED',('another',))

    def test_mixed_mock_manual_answers_and_reviews_share_pipeline(self):
        connection,rev=self.council.binding(self.debate.debate_id,self.pid[1])
        self.store.bind_connection(self.debate.debate_id,self.pid[1],connection.model_copy(update={'mode':'MANUAL','provider_id':'claimed-service'}),
            expected_revision=self.revision,expected_connection_revision=rev,actor=ACTOR,reason='Explicit manual mode')
        self.through_review(); self.decide('CUSTOM');self.start('TARGETED',('missing evidence',));self.complete_round();result=self.finish()
        sources=self.store.sources.context_sources(self.debate.debate_id)
        self.assertEqual({s.provenance for s in sources},{'MOCK','MANUAL'})
        self.assertTrue(all(not r.external_origin_verified for r in self.store.manual_rounds.for_debate(self.debate.debate_id)))
        self.assertTrue(result.preserved_objections)

    def test_all_manual_council_including_selected_judge(self):
        for pid in self.pid:
            connection,rev=self.council.binding(self.debate.debate_id,pid)
            self.store.bind_connection(self.debate.debate_id,pid,connection.model_copy(update={'mode':'MANUAL','provider_id':'unverified-service'}),
                expected_revision=self.revision,expected_connection_revision=rev,actor=ACTOR,reason='Manual fixture')
        self.through_review();result=self.finish();self.reopen()
        self.assertTrue(self.store.export_debate(self.debate.debate_id)['debate_completed'])
        self.assertEqual(self.store.export_debate(self.debate.debate_id)['attempts'],[])
        self.assertEqual({s.provenance for s in self.store.sources.context_sources(self.debate.debate_id)},{'MANUAL'})

    def test_no_next_round_before_user_gate_and_analyst_cannot_decide(self):
        analysis=self.complete_round();before=self.revision
        self.assertFalse(analysis.recommendation_authorizes_round)
        with self.assertRaises(Conflict):self.start('REVIEW')
        d=UserDecision(decision_id=uuid4(),debate_id=self.debate.debate_id,round_id=self.round.round_id,expected_revision=before,kind='CONTINUE')
        for actor in ['SYSTEM','MODEL','ANALYST','JUDGE','']:
            with self.assertRaises(ValueError):self.council.decide(d,actor=actor,confirmed=True)
        self.assertEqual(self.revision,before)
        self.decide('CONTINUE');self.start('REVIEW')
        with self.assertRaises(Conflict):self.start('TARGETED',('scope',))

    def test_finish_requires_peer_review_and_valid_user_selected_judge(self):
        self.complete_round()
        with self.assertRaises(Conflict):self.select()
        with self.assertRaises(Conflict):self.decide('FINISH')
        self.decide('CONTINUE');self.start('REVIEW')

    def test_missing_wrong_stale_or_unconfirmed_judge_rejected(self):
        self.through_review();self.decide('FINISH');before=self.revision
        for changes in ({'participant_id':uuid4()},{'confirmed':False},{'confirmed':1},{'actor':'MODEL'},
                        {'expected_revision':before-1},{'bias_mitigation':'NONE'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.select(**changes)
        self.assertEqual(self.revision,before);self.assertFalse(self.store.export_debate(self.debate.debate_id)['debate_completed'])
        with self.assertRaises(Conflict):self.council.finalize(debate_id=self.debate.debate_id,expected_revision=before)

    def test_pause_reopen_and_resume_require_explicit_fresh_user_choice(self):
        self.complete_round();self.decide('PAUSE');self.reopen()
        self.assertEqual(self.council.recover(self.debate.debate_id)['next_action'],'PAUSED')
        with self.assertRaises(Conflict):self.start('REVIEW')
        self.council.resume_pause(debate_id=self.debate.debate_id,expected_revision=self.revision,user_action_id=uuid4(),actor=ACTOR,confirmed=True)
        with self.assertRaises(Conflict):self.start('REVIEW')
        self.decide('CONTINUE');self.start('REVIEW');self.complete_round();self.finish()

    def test_stale_and_old_round_decisions_leave_state_unchanged(self):
        self.through_review();before=self.revision
        first=self.store._db.execute('SELECT round_id FROM rounds WHERE number=1').fetchone()[0]
        for changes in ({'expected_revision':before-1},{'round_id':UUID(first)}):
            with self.assertRaises(Conflict):self.decide('CONTINUE',**changes)
        self.assertEqual(self.revision,before)

    def test_initial_context_excludes_already_generated_peer_answer(self):
        self.submit(self.pid[0],'PEER_DO_NOT_LEAK');request=self.prepare(self.pid[1])
        self.assertNotIn('PEER_DO_NOT_LEAK',request.intent.frozen_input.canonical_bytes().decode())

    def test_review_metadata_is_blind_by_default(self):
        self.complete_round();self.decide('CONTINUE');self.start('REVIEW');request=self.prepare()
        data=json.loads(request.intent.frozen_input.messages[1].content)
        self.assertEqual({s['author'] for s in data['sources']},{'A','B'})
        self.assertTrue(all('identity' not in s for s in data['sources']))

    def test_unscored_reviews_preserve_explicit_status_without_fabricated_score(self):
        self.complete_round();self.decide('CONTINUE');self.start('REVIEW')
        for pid in self.pid:self.submit(pid,score='NOT_SCORED')
        self.council.seal_round(debate_id=self.debate.debate_id,expected_revision=self.revision)
        self.assertEqual({s.item.score for s in self.store.sources.context_sources(self.debate.debate_id) if hasattr(s.item,'score')},{'NOT_SCORED'})

    def test_incomplete_critique_cannot_complete_round_or_gain_default_score(self):
        self.complete_round();self.decide('CONTINUE');self.start('REVIEW');request=self.prepare()
        plan=self.council.execute_mock(request,MockAdapter(response_content='{"schema_version":1,"critiques":[]}'),expected_revision=self.revision)
        self.assertEqual(plan.attempt.state.value,'INVALID_RESPONSE')
        with self.assertRaises(Conflict):self.council.seal_round(debate_id=self.debate.debate_id,expected_revision=self.revision)
        self.assertIsNone(self.store.artifacts.get(request.intent.identity.logical_operation_id))

    def test_ambiguous_mock_delivery_cannot_resend_replace_or_finish(self):
        request=self.prepare();adapter=MockAdapter(scenario=Scenario.TIMEOUT_AFTER_SEND)
        plan=self.council.execute_mock(request,adapter,expected_revision=self.revision);self.reopen()
        self.assertFalse(plan.automatic_send)
        with self.assertRaises(Conflict):self.prepare()
        with self.assertRaises(Conflict):self.council.execute_mock(request,MockAdapter(),expected_revision=self.revision)
        with self.assertRaises(Conflict):self.council.seal_round(debate_id=self.debate.debate_id,expected_revision=self.revision)
        self.assertEqual(len(adapter.calls),1)

    def test_live_or_subclassed_driver_cannot_use_mock_permissions(self):
        request=self.prepare()
        class PretendDriver(MockAdapter):pass
        with self.assertRaises(Conflict):self.council.execute_mock(request,PretendDriver(),expected_revision=self.revision)
        self.assertEqual(self.store.ledger.get_attempt(request.intent.identity.attempt_id).state.value,'PREPARED')

    def test_final_output_cannot_claim_truth_probability_or_application_authority(self):
        self.through_review();self.decide('FINISH');self.select()
        content=json.loads(self.judge_output());content['agreement_is_truth_probability']=True
        self.submit(self.pid[0],json.dumps(content))
        with self.assertRaises(ValueError):self.council.finalize(debate_id=self.debate.debate_id,expected_revision=self.revision)
        self.assertFalse(self.store.export_debate(self.debate.debate_id)['debate_completed'])

    def test_judge_connection_change_does_not_silently_replace_selected_judge(self):
        self.through_review();self.decide('FINISH');self.select()
        c,r=self.council.binding(self.debate.debate_id,self.pid[0])
        self.store.bind_connection(self.debate.debate_id,self.pid[0],c.model_copy(update={'model_id':'other'}),
            expected_revision=self.revision,expected_connection_revision=r,actor=ACTOR,reason='Changed after selection')
        with self.assertRaises(ValueError):self.prepare()
        with self.assertRaises(ValueError):self.council.finalize(debate_id=self.debate.debate_id,expected_revision=self.revision)

    def test_checkpoint_markdown_json_participant_history_and_assessments_regenerate(self):
        self.through_review();root=Path(self.temp.name)/'exports';early=export_council(self.store,self.debate.debate_id,root)
        self.assertFalse(json.loads((early/'debate.json').read_text())['debate_completed'])
        result=self.finish();out=export_council(self.store,self.debate.debate_id,root)
        self.assertEqual(export_council(self.store,self.debate.debate_id,root),out)
        self.assertTrue((out/'participants/participant-1.md').is_file());self.assertTrue((out/'assessments/participant-2.md').is_file())
        self.assertIn('MINORITY_DISSENT',(out/'final.md').read_text());self.assertIn('BLIND_ALL_EVIDENCE',(out/'final.md').read_text())
        self.assertTrue(early.is_dir());self.reopen()
        self.assertEqual(json.loads((out/'debate.json').read_text())['final_council_result'],result.model_dump(mode='json'))

    def test_literal_export_survives_fence_injection_and_technical_bidi(self):
        from consilium.shell.council_export import literal
        result=literal('فارسی model_id\n```\n# fake heading\n````')
        self.assertTrue(result.startswith('`````text'));self.assertTrue(result.endswith('`````\n'))

    def test_analysis_hash_or_event_tampering_detected_on_reopen(self):
        self.complete_round();self.store._db.execute("UPDATE council_records SET record_hash=?",('0'*64,));self.store.close()
        with self.assertRaises(SchemaError):SQLiteStore(self.path)
        # Restore for tearDown; keep corruption rejection explicit.
        with closing(sqlite3.connect(self.path,autocommit=True)) as db:
            row=db.execute('SELECT record_json FROM council_records').fetchone()
            from consilium.core.council_contracts import RoundAnalysis
            db.execute('UPDATE council_records SET record_hash=?',(RoundAnalysis.model_validate_json(row[0]).content_hash,))
        self.store=SQLiteStore(self.path)

    def test_completed_record_deletion_detected_even_when_row_is_missing(self):
        self.through_review();self.finish();self.store._db.execute("DELETE FROM council_records WHERE kind='FINAL'");self.store.close()
        with self.assertRaises(SchemaError):SQLiteStore(self.path)
        # A close remains safe; do not reopen corrupted data for ordinary use.

    def test_transaction_rolls_back_analysis_or_final_record_failure(self):
        for pid in self.pid:self.submit(pid)
        before=self.revision
        self.store._db.execute("CREATE TEMP TRIGGER fail_council BEFORE INSERT ON council_records BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Conflict):self.council.seal_round(debate_id=self.debate.debate_id,expected_revision=before)
        self.assertEqual(self.revision,before);self.assertEqual(self.council._wait(self.debate.debate_id),'ACTIVE')

    def crash(self, action, committed):
        old=self.revision;self.store.close()
        script='''
from contextlib import contextmanager
import os,sys
from pathlib import Path
from uuid import UUID
from consilium.shell.storage import SQLiteStore
s=SQLiteStore(Path(sys.argv[1]));orig=s._transaction
@contextmanager
def crash_transaction(*,write=True):
    with orig(write=write):
        yield
        if write and sys.argv[3]=='before':os._exit(81)
    if write:os._exit(82)
s._transaction=crash_transaction
d=UUID(int=1);r=s.checkpoint(d).revision
if sys.argv[2]=='analysis':s.council.seal_round(debate_id=d,expected_revision=r)
elif sys.argv[2]=='judge':s.council.select_judge(debate_id=d,participant_id=UUID(int=2),round_id=UUID(int=999),expected_revision=r,user_action_id=UUID(int=998),actor='EXPLICIT_CRASH_TEST_USER',confirmed=True)
else:s.council.finalize(debate_id=d,expected_revision=r)
'''
        environment=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
        p=subprocess.run([sys.executable,'-c',script,str(self.path),action,'after' if committed else 'before'],env=environment,capture_output=True,timeout=15)
        self.assertEqual(p.returncode,82 if committed else 81,p.stderr.decode())
        self.store=SQLiteStore(self.path)
        self.assertEqual(self.revision,old+int(committed))
        self.assertFalse(self.council.recover(self.debate.debate_id)['automatic_send'])

    def test_real_exit_before_analysis_commit(self):
        for pid in self.pid:self.submit(pid)
        self.crash('analysis',False);self.assertEqual(self.council._wait(self.debate.debate_id),'ACTIVE')
    def test_real_exit_after_analysis_commit(self):
        for pid in self.pid:self.submit(pid)
        self.crash('analysis',True);self.assertEqual(self.council._wait(self.debate.debate_id),'WAITING_DECISION')
    def test_real_exit_before_judge_commit(self):
        self.through_review();self.decide('FINISH');self.crash('judge',False)
        self.assertEqual(self.council._wait(self.debate.debate_id),'WAITING_JUDGE_SELECTION')
    def test_real_exit_after_judge_commit(self):
        self.through_review();self.decide('FINISH');self.crash('judge',True)
        self.assertEqual(self.round.kind,'SYNTHESIS')
    def test_real_exit_before_final_commit(self):
        self.through_review();self.decide('FINISH');self.select();self.submit(self.pid[0],self.judge_output());self.crash('final',False)
        self.assertFalse(self.store.export_debate(self.debate.debate_id)['debate_completed'])
    def test_real_exit_after_final_commit(self):
        self.through_review();self.decide('FINISH');self.select();self.submit(self.pid[0],self.judge_output());self.crash('final',True)
        self.assertTrue(self.store.export_debate(self.debate.debate_id)['debate_completed'])

    def test_initial_differences_remain_in_final_with_unscored_accepting_reviews(self):
        self.complete_round();self.decide('CONTINUE');self.start('REVIEW')
        for pid in self.pid:
            request=self.prepare(pid);contract=self.store.artifacts.get_contract(request.intent)
            content=json.loads(self.review_content(contract.targets,'NOT_SCORED'))
            for critique in content['critiques']:
                for point in critique['points']:point['verdict']='ACCEPT'
            self.council.execute_mock(request,MockAdapter(response_content=json.dumps(content)),expected_revision=self.revision)
        self.council.seal_round(debate_id=self.debate.debate_id,expected_revision=self.revision)
        final=self.finish()
        self.assertEqual({o.verdict for o in final.preserved_objections},{'DIFFERENT_ANSWERS'})
        self.assertTrue(any('MINORITY_DISSENT' in o.reason for o in final.preserved_objections))

    def test_judge_schema_rejects_boolean_or_float_version(self):
        from consilium.core.council_contracts import JudgeOutput
        output=json.loads(self.judge_output())
        for version in (True,1.0,'1',2):
            with self.subTest(version=version),self.assertRaises(ValueError):
                JudgeOutput.model_validate_json(json.dumps({**output,'schema_version':version}))

    def test_v9_upgrade_preserves_all_old_migration_records_and_canonical_sources(self):
        from consilium.shell import storage
        self.submit(self.pid[0]);before=self.store.sources.context_sources(self.debate.debate_id)
        old=[tuple(r) for r in self.store._db.execute('SELECT * FROM schema_migrations WHERE version<=9')]
        legacy=Path(self.temp.name)/'legacy.sqlite3'
        with closing(sqlite3.connect(legacy,autocommit=True)) as db:
            db.execute('PRAGMA foreign_keys=OFF');db.execute('BEGIN')
            for version in range(1,10):
                for statement in getattr(storage,'V'+str(version)+'_STATEMENTS'):db.execute(statement)
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for name in tables:
                rows=old if name=='schema_migrations' else self.store._db.execute('SELECT * FROM '+name).fetchall()
                for row in rows:db.execute('INSERT INTO '+name+' VALUES('+','.join('?' for _ in row)+')',tuple(row))
            db.execute('PRAGMA application_id='+str(self.store._db.execute('PRAGMA application_id').fetchone()[0]))
            db.execute('PRAGMA user_version=9');db.execute('COMMIT')
        with SQLiteStore(legacy) as restored:
            self.assertEqual(restored._db.execute('PRAGMA user_version').fetchone()[0],10)
            self.assertEqual([tuple(r) for r in restored._db.execute('SELECT * FROM schema_migrations WHERE version<=9')],old)
            self.assertEqual(restored.sources.context_sources(self.debate.debate_id),before)
            self.assertFalse(restored.council.recover(self.debate.debate_id)['automatic_send'])

    def test_failed_v10_upgrade_rolls_back_with_no_new_records(self):
        from unittest.mock import patch
        from consilium.shell.schema_v9 import V9_STATEMENTS
        from consilium.shell.schema_v10 import V10_STATEMENTS
        self.store.close()
        with closing(sqlite3.connect(self.path,autocommit=True)) as db:
            db.execute('PRAGMA foreign_keys=OFF');db.execute('BEGIN')
            db.execute('DROP TABLE council_records')
            for statement in V9_STATEMENTS[:4]:db.execute(statement)
            db.execute('DELETE FROM schema_migrations WHERE version=10');db.execute('PRAGMA user_version=9');db.execute('COMMIT')
            old=db.execute('SELECT * FROM schema_migrations').fetchall()
        with patch('consilium.shell.storage.V10_STATEMENTS',(*V10_STATEMENTS,'INVALID SQL FIXTURE')):
            with self.assertRaises(SchemaError):SQLiteStore(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],9)
            self.assertEqual(db.execute('SELECT * FROM schema_migrations').fetchall(),old)
        self.store=SQLiteStore(self.path)

    def test_cli_pause_resume_and_checkpoint_exports_use_real_processes(self):
        self.complete_round();out=Path(self.temp.name)/'cli-exports'
        def run(*command,revision=None):
            return subprocess.run([sys.executable,str(ROOT/'tools/council.py'),'--database',str(self.path),
                '--debate-id',str(self.debate.debate_id),'--revision',str(self.revision if revision is None else revision),
                '--exports',str(out),'--actor',ACTOR,'--confirm-user-action',*command],capture_output=True,timeout=15)
        stale=self.revision
        for command in [('decide','--choice','PAUSE'),('resume-pause',),('decide','--choice','CONTINUE'),('start','--kind','REVIEW')]:
            result=run(*command);self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(self.round.kind,'REVIEW');before=self.revision
        result=run('seal',revision=stale);self.assertEqual(result.returncode,1)
        self.assertEqual(self.revision,before)
        pointer=json.loads((out/str(self.debate.debate_id)/'LATEST.json').read_text())
        self.assertEqual(pointer['revision'],before)

    def test_cli_new_preserves_question_and_waits_for_architect_user_review(self):
        config=Path(self.temp.name)/'new-config.json';database=Path(self.temp.name)/'new.sqlite3'
        config.write_text(json.dumps({'debate':self.debate.model_dump(mode='json'),'bindings':[
            {'participant_id':str(pid),'connection':self.council.binding(self.debate.debate_id,pid)[0].model_dump(mode='json')} for pid in self.pid]}))
        result=subprocess.run([sys.executable,str(ROOT/'tools/council.py'),'--database',str(database),
            '--debate-id',str(self.debate.debate_id),'--revision','0','--exports',str(Path(self.temp.name)/'new-exports'),
            '--actor',ACTOR,'--confirm-user-action','new','--config',str(config)],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        with SQLiteStore(database) as s:
            self.assertEqual(s.get_debate(self.debate.debate_id).original_request,self.debate.original_request)
            self.assertIsNone(s.questions.get_adopted(self.debate.debate_id))
            self.assertIsNone(s.council.current_round(self.debate.debate_id))
            self.assertEqual(s.export_debate(self.debate.debate_id)['attempts'],[])

    def test_terminal_state_without_final_is_rejected_on_reopen(self):
        self.store._db.execute("UPDATE debates SET wait_state='COMPLETED'");self.store.close()
        with self.assertRaises(SchemaError):SQLiteStore(self.path)

    def test_final_cannot_reopen_with_active_wait_state(self):
        self.through_review();self.finish()
        self.store._db.execute("UPDATE debates SET wait_state='ACTIVE'");self.store.close()
        with self.assertRaises(SchemaError):SQLiteStore(self.path)

    def test_single_reviewer_round_is_rejected_without_consuming_user_decision(self):
        self.complete_round();self.decide('CONTINUE');before=self.revision
        with self.assertRaises(Conflict):self.start('REVIEW',participants=(self.pid[0],))
        self.assertEqual(self.revision,before)
        self.start('REVIEW')

    def test_late_previous_round_execution_cannot_change_new_round(self):
        request=self.prepare();self.council.execute_mock(request,MockAdapter(response_content='{"schema_version":1,"answer":"first"}'),expected_revision=self.revision)
        self.submit(self.pid[1]);self.council.seal_round(debate_id=self.debate.debate_id,expected_revision=self.revision)
        self.decide('CONTINUE');self.start('REVIEW');before=self.revision
        with self.assertRaises(Conflict):self.council.execute_mock(request,MockAdapter(),expected_revision=before)
        self.assertEqual(self.revision,before)

    def test_selected_judge_receives_frozen_output_schema_and_all_dissent(self):
        self.through_review();self.decide('FINISH');self.select();request=self.prepare()
        data=json.loads(request.intent.frozen_input.messages[1].content)
        self.assertIn('conclusion',data['judge_output_schema']['required'])
        self.assertIn('dissent',data['judge_output_schema']['required'])
        self.assertIn('MINORITY_DISSENT',request.intent.frozen_input.messages[1].content)
        self.assertTrue(all('identity' not in s for s in data['sources']))

    def test_invalid_judge_json_never_becomes_a_canonical_source(self):
        self.through_review();self.decide('FINISH');self.select()
        request=self.prepare();result=self.council.execute_mock(request,MockAdapter(response_content='{"schema_version":1,"answer":"incomplete judge"}'),expected_revision=self.revision)
        self.assertEqual(result.attempt.state.value,'INVALID_RESPONSE')
        self.assertIsNone(self.store.artifacts.get(request.intent.identity.logical_operation_id))
        with self.assertRaises(Conflict):self.council.finalize(debate_id=self.debate.debate_id,expected_revision=self.revision)
