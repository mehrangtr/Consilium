#!/usr/bin/env python3
"""Executed synthetic council traces; manual origins are unverified fixtures."""
import datetime as dt
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4
import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'tests/council')]
from test_council import CouncilCase, ACTOR
from consilium.shell.council_export import export_council


def execute_examples(destination):
    examples = []
    for mode in ('mock','mixed','manual'):
        case = CouncilCase(); case.setUp()
        try:
            if mode != 'mock':
                for pid in (case.pid[1:] if mode=='mixed' else case.pid):
                    c,r = case.council.binding(case.debate.debate_id,pid)
                    case.store.bind_connection(case.debate.debate_id,pid,c.model_copy(update={'mode':'MANUAL','provider_id':'unverified-fixture'}),
                        expected_revision=case.revision,expected_connection_revision=r,actor=ACTOR,reason='Explicit synthetic manual fixture')
            checkpoints=[]
            local=Path(case.temp.name)/'exports'
            case.complete_round(); checkpoints.append(export_council(case.store,case.debate.debate_id,local))
            case.decide('PAUSE');case.reopen()
            assert case.council.recover(case.debate.debate_id)['automatic_send'] is False
            case.council.resume_pause(debate_id=case.debate.debate_id,expected_revision=case.revision,
                user_action_id=uuid4(),actor=ACTOR,confirmed=True)
            case.decide('CONTINUE');case.start('REVIEW');case.complete_round()
            checkpoints.append(export_council(case.store,case.debate.debate_id,local))
            case.decide('CUSTOM');case.start('TARGETED',('Resolve evidence gap only',));case.complete_round()
            checkpoints.append(export_council(case.store,case.debate.debate_id,local))
            final=case.finish();checkpoints.append(export_council(case.store,case.debate.debate_id,local))
            before=case.store.export_debate(case.debate.debate_id);case.reopen()
            assert before==case.store.export_debate(case.debate.debate_id)
            assert final.preserved_objections and final.judge.participated_in_rounds
            assert {d['decision']['kind'] for d in before['user_decisions']} == {'PAUSE','CONTINUE','CUSTOM','FINISH'}
            folder=destination/mode
            for checkpoint in checkpoints:
                target=folder/checkpoint.name
                shutil.copytree(checkpoint,target,dirs_exist_ok=True)
            examples.append({'mode':mode,'fixture_scope':'SCRIPTED_MOCK_AND_USER_ACCEPTED_SYNTHETIC_MANUAL_TEXT',
                'external_origin_verified':False,'restart_exact':True,'automatic_send':False,
                'final_revision':case.revision,'round_kinds':[r['kind'] for r in before['rounds']],
                'canonical_provenance':sorted({s.provenance for s in case.store.sources.context_sources(case.debate.debate_id)}),
                'preserved_objection_count':len(final.preserved_objections),
                'artifacts':{p.relative_to(destination).as_posix():q.digest(p.read_bytes()) for p in sorted(folder.rglob('*')) if p.is_file()}})
        finally:case.tearDown()
    return examples


def main():
    before=q.source_digest(ROOT)
    destination=ROOT/'evidence/p05/council-examples';destination.mkdir(parents=True,exist_ok=True)
    examples=execute_examples(destination)
    after=q.source_digest(ROOT)
    q.require(before==after,'Source changed during P05 examples')
    report={'phase':'P05','status':'PASS','scope':'EXECUTED_P05_OFFLINE_COUNCIL_EXIT_EXAMPLES',
        'host':{'system':__import__('platform').system(),'python':__import__('platform').python_version()},
        'date_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source_digest_before':before,'source_digest_after':after,
        'live_provider_calls':0,'paid_calls':0,'full_v1_conformance_claimed':False,'examples':examples}
    (destination/'RUN.json').write_bytes(q.encoded(report))
    print(json.dumps({'status':'PASS','examples':len(examples),'receipt':'evidence/p05/council-examples/RUN.json'}))


if __name__=='__main__':main()
