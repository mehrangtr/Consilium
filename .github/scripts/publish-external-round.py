"""Verify exact native-tested payload; publish only delivery metadata afterwards."""
import base64
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(os.environ['PAYLOAD_ROOT']).resolve()
CODE = os.environ['TESTED_CODE_SHA']
SOURCE = os.environ['TESTED_SOURCE_DIGEST']
RUN = int(os.environ['NATIVE_RUN_ID'])
BRANCH = os.environ['DELIVERY_BRANCH']
JOURNAL = os.environ['PUBLICATION_JOURNAL_SHA']
sys.path.insert(0, str(ROOT/'tools'))
import qualityctl as q


def command(args, timeout=120):
    subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL, check=True, timeout=timeout)


def github(path):
    request = urllib.request.Request('https://api.github.com/repos/mehrangtr/Consilium/'+path,
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=25) as response:
        return json.load(response)


def snapshots():
    results=[]
    for path in sorted((ROOT/'evidence/development-supervisor').glob('*/STATE.json')):
        state=q.load(path)
        if state['source_digest']!=SOURCE: continue
        assert state['status']=='PASS' and not state['phase_advanced'] and not state['remaining_steps']
        for step in state['steps']:
            assert step['status'] in {'COMPLETE','RECOVERED_COMPLETE'}
            assert step['reconciliation']['status']=='VERIFIED_COMPLETE'
            receipt=q.load(q.artifact(ROOT,{'path':step['reconciliation']['receipt'],'sha256':step['reconciliation']['sha256']}))
            assert receipt['development_step_id']==step['nonce'] and receipt['status']=='PASS'
            assert receipt['source_digest_before']==receipt['source_digest_after']==SOURCE
            assert not step['retained_proof']['errors']
            for ref in step['retained_proof']['artifacts']:
                q.artifact(ROOT,{'path':ref['path'],'sha256':ref['sha256']})
        results.append({'path':path.relative_to(ROOT).as_posix(),'sha256':q.digest(path.read_bytes()),'state':state})
    return results


assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==CODE
assert q.source_digest(ROOT)==SOURCE
run=github('actions/runs/'+str(RUN))
assert run['head_sha']==CODE and run['status']=='completed' and run['conclusion']=='success'
command([sys.executable,'tools/check_target_matrix.py'])
_,native=q.target_evidence_files(ROOT)
assert {r['target'] for r in native}=={'Windows','Linux'}
assert all(r['status']=='PASS' and r['source_matches_current'] for r in native)
for record in native:
    report=q.load(ROOT/record['report']['path'])
    counts={role:q.load(q.artifact(ROOT,ref))['counts']['tests'] for role,ref in report['artifacts'].items()
        if role in {'control_report','foundation_report','persistence_report','browser_probe_report','architect_report'}}
    assert counts=={'control_report':112,'foundation_report':60,'persistence_report':80,'browser_probe_report':44,'architect_report':188},counts
    assert sum(counts.values())==484
assert len([r for r in snapshots() if r['state']['steps'][0]['step']=='native'])==2
runtime=q.load(ROOT/'evidence/p04/CONNECTOR_WAIT_RUNTIME_TESTS.json')
assert runtime['status']=='PASS' and len(runtime['tests'])==5
assert runtime['source_sha256']==q.digest((ROOT/'tools/connector_wait.js').read_bytes())
blob=github('git/blobs/'+JOURNAL)
encoded=base64.b64decode(blob['content'])
assert hashlib.sha1(b'blob '+str(len(encoded)).encode()+b'\0'+encoded).hexdigest()==JOURNAL
packed=json.loads(encoded)
assert packed['encoding']=='gzip+base64'
raw=gzip.decompress(base64.b64decode(packed['data']))
assert hashlib.sha256(raw).hexdigest()==packed['uncompressed_sha256']
publication=json.loads(raw)
assert publication['code_commit']==CODE and publication['bulk_tree']=='3295d57f44cdd09182555580164c4b3cf2282dd7'
assert all(r['plan']['source_digest']==SOURCE for r in publication['operations'])
assert len(publication['retired_operations'])==1

progress=q.load(ROOT/'PROGRESS.json')
accepted={p['id']:q.encoded(p) for p in progress['phases'] if p['id'] in {'P00','P01','P02','P03'}}
assert progress['current_phase']=='P04' and progress['verified_application_requirements']==0
phase=next(p for p in progress['phases'] if p['id']=='P04')
assert phase['status']=='IN_PROGRESS'
next_action='در P04-002 نقد دستی و پاسخ دستی دورهای بعد و تطبیق صریح عملیات قبلی را تکمیل کن؛ منشأ زنده و مشاهده و اندازه‌گیری معتبر اتصال را آماده و همهٔ معیارهای P04 را بازبینی کن. نمای پایدار دور بعد اکنون موجود است؛ آن را دوباره نساز. P05 و ارسال زنده هنوز آغاز نشوند.'
now=dt.datetime.now(dt.timezone.utc).isoformat()
resume=progress['resume']
resume['working_changes']=[]
resume['completed_work'].append('Bounded external connector waits, durable publication permits, canonical later-round input/policies and manual-first-round decision gate verified: 484 tests and 27 product process exits per actual OS, plus 5 Work Mode JS wait cases. Full P04 remains open.')
resume['next_action']=next_action
resume['next_command']='python tools/development_supervisor.py local'
resume['next_task'].update(status='DURABLE_LATER_ROUND_NATIVE_VERIFIED',
    completed_fa='ورودی دور بعد با منابع رسمی و مجوز انتقال و بودجه و دستور سفارشی کاربر همراه قصد اتمیک ثبت می‌شود. گیت پاسخ دستی اولیهٔ هم‌راستا و کنترل انتظار و تطبیق انتشار نیز آزموده شدند؛ ۴۸۴ آزمون و ۲۷ قطع پردازهٔ محصول در هر دو محیط واقعی موفق‌اند.',
    remaining_fa='نقد دستی و پاسخ دستی دورهای بعد، تطبیق صریح عملیات قبلی، منشأ زنده و مشاهده و اندازه‌گیری معتبر اتصال و بازبینی کامل P04.',next_action_fa=next_action)
resume['unfinished_work']['updated_at_utc']=now
resume['unfinished_work']['items'][0]=resume['next_task'].copy()
resume['unfinished_work']['continuation_instruction']='Continue remaining P04-002 only; canonical later-round intent/admission and bounded publication guard are verified for '+SOURCE+'. Keep P00-P03 acceptance intact. Do not replay accepted browser probes or rebuild completed source/admission slices.'
resume['native_evidence']={'run_id':str(RUN),'code_commit':CODE,'source_digest':SOURCE,'tests_per_target':484,'process_exit_cases_per_target':27,'target_reports':native}
resume['transfer_reviewed_file_count']=None
resume['developer_supervisor']['native_verified']=True
resume['external_publication_guard']={'bounded_wait_ms':25000,'maximum_permitted_wait_ms':60000,'actual_alternate_path_wait_ms':45000,'journal_blob':JOURNAL,'cancels_mcp_or_chat':False,'mutable_replay':'NEVER_AUTOMATIC_AFTER_UNKNOWN','immutable_retry':'ONE_PER_REQUEST_PLAN_AFTER_INDEPENDENT_ABSENCE_PROOF','current_source_tree_verified':True}
resume['known_quirks']=[('HISTORICAL: '+x) if 'Manual/LIVE acceptance and durable later-round admission remain open' in x else x for x in resume['known_quirks']]
resume['known_quirks'].append('Later-round durable receipt now rebuilds all aligned prior canonical sources and the stored continuation decision. Live budget/history facts remain unverified; policy-managed send stays blocked. Manual critiques and later-round manual answers still pending.')
progress['application_source_commit']=CODE
progress['updated_at_utc']=now
progress['governance_check_note']='مرحله‌های P00 تا P03 پذیرفته شده‌اند؛ P04 در جریان است. ۳۰ خواسته محفوظ‌اند و پذیرش کامل اجرایی محصول 0/30 است.'
phase['source_commit']=CODE
phase['notes']=[('HISTORICAL: '+x) if x.startswith('CURRENT') else x for x in phase['notes']]
phase['notes'].append('CURRENT: bounded external waits and durable canonical later-round input verified for '+SOURCE+'; 484 tests and 27 product process exits per actual OS. Full P04 remains open; no live provider calls.')
phase['outputs']=sorted(set(phase['outputs'])|{'tools/publication_guard.py','tools/connector_wait.js','src/consilium/core/round_admission.py','tests/architect/test_round_admission.py','tests/test_publication_guard.py','docs/EXTERNAL_OPERATIONS_FA.md','evidence/p04/EXTERNAL_ROUND_CHECKPOINT.json','evidence/p04/EXTERNAL_ROUND_REVIEW.json'})
(ROOT/'PROGRESS.json').write_bytes(q.encoded(progress))
q.navigation(ROOT)
command([sys.executable,'tools/development_supervisor.py','phase'],timeout=180)
latest,_=q.latest_phase_run(ROOT,'P04',progress['plan_version'])
assert latest['status']=='PASS' and latest['source_matches_current']
phase['tests']=[latest['receipt']]
states=snapshots()
assert len([r for r in states if r['state']['steps'][0]['step']=='phase'])>=1
cp=ROOT/'evidence/p04/EXTERNAL_ROUND_CHECKPOINT.json'
checkpoint=q.load(cp)
checkpoint.update(status='EXTERNAL_GUARD_AND_DURABLE_ROUND_NATIVE_VERIFIED_NOT_PHASE_ACCEPTED',source_digest=SOURCE,
    code_commit=CODE,native_run_id=str(RUN),target_reports=native,configured_phase_run=latest,
    tests_per_native_target=484,product_process_exit_cases_per_native_target=27,development_supervisor_snapshots=states,
    publication_journal={'blob':JOURNAL,'uncompressed_sha256':packed['uncompressed_sha256'],'snapshot':publication},
    native_evidence='ACTUAL_WINDOWS_AND_LINUX_GRAPH_VERIFIED',phase_accepted=False,next_action=next_action,
    publication_scope='VERIFIED_DELIVERY_BRANCH_PRIMARY_MAIN_PUBLICATION_PENDING')
cp.write_bytes(q.encoded(checkpoint))
resume['last_verified_in_phase_checkpoint']={'phase':'P04','path':cp.relative_to(ROOT).as_posix(),'sha256':q.digest(cp.read_bytes()),'source_digest':SOURCE,'phase_accepted':False}
resume['developer_supervisor']['latest_state_snapshots']={'path':cp.relative_to(ROOT).as_posix(),'sha256':q.digest(cp.read_bytes())}
review=q.load(ROOT/'evidence/p04/EXTERNAL_ROUND_REVIEW.json')
review.update(status='PASS_IMPLEMENTED_SLICE_NATIVE_VERIFIED',source_digest=SOURCE,code_commit=CODE,native_run_id=str(RUN),
    target_reports=native,configured_phase_run=latest,tests_per_native_target=484,product_process_exit_cases_per_native_target=27,phase_accepted=False)
for criterion in review['criteria']:
    if criterion['id']=='native_windows_linux':criterion.update(result='PASS',reason='Fresh exact-source immutable native graphs and all configured checks verified')
(ROOT/'evidence/p04/EXTERNAL_ROUND_REVIEW.json').write_bytes(q.encoded(review))
(ROOT/'PROGRESS.json').write_bytes(q.encoded(progress))
assert accepted=={p['id']:q.encoded(p) for p in progress['phases'] if p['id'] in accepted}
q.navigation(ROOT)
assert q.source_digest(ROOT)==SOURCE
output=ROOT.parent/'delivery';output.mkdir(exist_ok=True)
preview=output/'P04_EXTERNAL_ROUND_PREVIEW.zip'
q.handoff(ROOT,preview);preview_result=q.verify(preview)
resume['transfer_reviewed_file_count']=preview_result['files']
(ROOT/'PROGRESS.json').write_bytes(q.encoded(progress));q.navigation(ROOT)
archive=output/'P04_EXTERNAL_ROUND_HANDOFF.zip'
info=q.handoff(ROOT,archive);verified=q.verify(archive)
assert verified['files']==preview_result['files']
assert info['source_snapshot_digest']==SOURCE and info['state_label']=='INCOMPLETE'
assert info['current_phase']=='P04' and info['last_accepted_phase']=='P03'
assert info['latest_current_phase_run']['status']=='PASS' and info['latest_current_phase_run']['source_matches_current']
assert all(r['status']=='PASS' and r['source_matches_current'] for r in info['native_target_runs'])
with zipfile.ZipFile(archive) as z:
    for name in ('HANDOFF.json','MANIFEST.json'):(ROOT/name).write_bytes(z.read(name))
command(['git','add','PROGRESS.json','HANDOFF.json','MANIFEST.json','evidence'])
changed=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT).decode().splitlines()
assert all(n in {'PROGRESS.json','HANDOFF.json','MANIFEST.json'} or n.startswith('evidence/') for n in changed)
assert q.source_digest(ROOT)==SOURCE
command(['git','config','user.name','Consilium verified delivery'])
command(['git','config','user.email','consilium-delivery@users.noreply.github.com'])
command(['git','commit','-m','Record native external-guard and later-round admission evidence with precise P04 continuation'])
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT).decode().strip()
command(['git','push','origin','HEAD:refs/heads/'+BRANCH],timeout=45)
result={'status':'VERIFIED_DELIVERY_BRANCH_PUSHED','commit':commit,'tree':tree,'source_digest':SOURCE,'code_commit':CODE,
    'native_run_id':str(RUN),'configured_receipt':latest['receipt'],'files':verified['files'],'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'tests_per_target':484,'product_process_exit_cases_per_target':27,'phase_accepted':False,'supervisor_snapshots':len(states),
    'changed_paths':len(changed),'product_source_changes':0,'publication_journal_blob':JOURNAL,'primary_main_publication':'PENDING_PRIMARY_REF_CHECK'}
(output/'PUBLICATION_RESULT.json').write_bytes(q.encoded(result))
print(json.dumps(result))
