"""Operational delivery only; check out tested code, never merge this helper."""
import datetime as dt
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
sys.path.insert(0, str(ROOT/'tools'))
import qualityctl as q


def command(args, timeout=180):
    subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL, check=True, timeout=timeout)


def github(path):
    request=urllib.request.Request('https://api.github.com/repos/mehrangtr/Consilium/'+path,
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==CODE
assert q.source_digest(ROOT)==SOURCE
run=github('actions/runs/'+str(RUN))
assert run['head_sha']==CODE and run['status']=='completed' and run['conclusion']=='success'
command([sys.executable,'tools/check_target_matrix.py'])
_, native=q.target_evidence_files(ROOT)
assert {x['target'] for x in native}=={'Windows','Linux'}
assert all(x['status']=='PASS' and x['source_matches_current'] for x in native)
for target in native:
    report=q.load(ROOT/target['report']['path'])
    counts={role:q.load(q.artifact(ROOT, ref))['counts']['tests']
            for role,ref in report['artifacts'].items() if role in
            {'control_report','foundation_report','persistence_report','browser_probe_report','architect_report'}}
    assert counts=={'control_report':88,'foundation_report':60,'persistence_report':80,
                   'browser_probe_report':44,'architect_report':147}, counts
    assert sum(counts.values())==419

progress=q.load(ROOT/'PROGRESS.json')
assert progress['current_phase']=='P04' and progress['verified_application_requirements']==0
phase=next(p for p in progress['phases'] if p['id']=='P04')
assert phase['status']=='IN_PROGRESS'
next_action='در همین P04-002 پذیرش صریح منابع دستی و منشأ آنها را با ثبت قابل بازیابی تعریف کن؛ منشأ زنده از متن یا برچسب اتصال گرفته نشود. سپس نمای دورهای بعد را از منابع رسمی با مجوز انتقال و بودجه به قصد عملیات در یک تراکنش وصل کن. حفظ قیود و مخالفت و بازیابی و عدم نشت را آزمون کن؛ همهٔ معیارهای P04 را بازبینی کن. P05 و ارسال زنده هنوز آغاز نشوند.'
resume=progress['resume']
resume['working_changes']=[]
resume['completed_work'].append('P04-002 frozen output schemas, typed mock answers and multi-target critique batches plus V6 migration verified: 419 tests and 23 real process exits per native OS. Full P04 remains open.')
resume['next_action']=next_action
resume['next_task'].update(status='PARTIAL_TYPED_MOCK_SOURCE_BATCH_NATIVE_VERIFIED',
    completed_fa='قرارداد خروجی پیش از ارسال ثابت است؛ پاسخ یا نقد چندهدفه به نتیجهٔ رسمی و طرح و هدف‌های دقیق متصل می‌شود. ۳۱ آزمون تازه و مجموع ۴۱۹ آزمون با ۲۳ مورد قطع واقعی پردازه در هر محیط بومی موفق‌اند.',
    remaining_fa='پذیرش صریح منابع دستی، شاهد منشأ زنده، اتصال پایدار نمای دور بعد به قصد و شواهد مجوز و بودجه و پذیرش کامل P04.',
    next_action_fa=next_action)
now=dt.datetime.now(dt.timezone.utc).isoformat()
resume['unfinished_work']['updated_at_utc']=now
resume['unfinished_work']['continuation_instruction']='PR6 and prior main d0139378d379302fe2dd16508a52399be3434015 are verified complete. Current typed-source slice is native-verified for '+SOURCE+'. Continue only remaining P04-002 Manual/provenance and durable later-round admission. Original staged checkout is preserved; do not republish it or repeat accepted provider probes.'
resume['unfinished_work']['items'][0]=resume['next_task'].copy()
resume['native_evidence']={'run_id':str(RUN),'code_commit':CODE,'source_digest':SOURCE,
    'tests_per_target':419,'process_exit_cases_per_target':23,'target_reports':native}
resume['transfer_reviewed_file_count']=None
progress['application_source_commit']=CODE
phase['source_commit']=CODE
phase['notes']=[('HISTORICAL: '+x) if x.startswith('CURRENT') else x for x in phase['notes']]
phase['notes'].append('CURRENT: frozen mock output contracts and canonical multi-target source batches verified for '+SOURCE+'; 419 tests and 23 process exits per actual OS. Phase source/tests fields reconciled with resume and current configured run. Manual/LIVE provenance, durable later-round admission and full P04 acceptance remain open.')
progress['updated_at_utc']=now
(ROOT/'PROGRESS.json').write_bytes(q.encoded(progress))
q.navigation(ROOT)
command([sys.executable,'tools/qualityctl.py','run','P04'])
latest, _=q.latest_phase_run(ROOT,'P04',progress['plan_version'])
assert latest['status']=='PASS' and latest['source_matches_current']
phase['tests']=[latest['receipt']]
(ROOT/'PROGRESS.json').write_bytes(q.encoded(progress))
q.navigation(ROOT)

checkpoint=q.load(ROOT/'evidence/p04/TYPED_SOURCE_BATCH_CHECKPOINT.json')
checkpoint.update(status='TYPED_MOCK_SOURCE_BATCH_VERIFIED_NOT_PHASE_ACCEPTED',source_digest=SOURCE,
    code_commit=CODE,native_run_id=str(RUN),target_reports=native,configured_phase_run=latest,
    tests_per_native_target=419,process_exit_cases_per_native_target=23,next_action=next_action,
    previous_phase_row_discrepancy='RESOLVED: P04 source_commit and tests now match the current source, configured receipt and resume.',
    phase_accepted=False,publication_scope='VERIFIED_DELIVERY_BRANCH; PRIMARY_MAIN_REF_REVIEW_FOLLOWS')
(ROOT/'evidence/p04/TYPED_SOURCE_BATCH_CHECKPOINT.json').write_bytes(q.encoded(checkpoint))
review=q.load(ROOT/'evidence/p04/TYPED_SOURCE_BATCH_REVIEW.json')
review.update(status='PASS_IMPLEMENTED_SLICE_ONLY',native_run_id=str(RUN),target_reports=native,
    configured_phase_run=latest,tests_per_native_target=419,phase_accepted=False)
(ROOT/'evidence/p04/TYPED_SOURCE_BATCH_REVIEW.json').write_bytes(q.encoded(review))
assert q.source_digest(ROOT)==SOURCE

output=ROOT.parent/'delivery'
output.mkdir(exist_ok=True)
preview=output/'P04_TYPED_SOURCE_PREVIEW.zip'
q.handoff(ROOT, preview)
preview_result=q.verify(preview)
resume['transfer_reviewed_file_count']=preview_result['files']
(ROOT/'PROGRESS.json').write_bytes(q.encoded(progress))
q.navigation(ROOT)
archive=output/'P04_TYPED_SOURCE_HANDOFF.zip'
info=q.handoff(ROOT,archive)
verification=q.verify(archive)
assert verification['files']==preview_result['files']
assert info['source_snapshot_digest']==SOURCE
assert info['state_label']=='INCOMPLETE' and info['current_phase']=='P04' and info['last_accepted_phase']=='P03'
assert info['latest_current_phase_run']['status']=='PASS' and info['latest_current_phase_run']['source_matches_current']
assert all(x['source_matches_current'] and x['status']=='PASS' for x in info['native_target_runs'])
with zipfile.ZipFile(archive) as z:
    for name in ('HANDOFF.json','MANIFEST.json'):
        (ROOT/name).write_bytes(z.read(name))
command(['git','add','PROGRESS.json','HANDOFF.json','MANIFEST.json','evidence'])
changed=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT).decode().splitlines()
assert all(n in {'PROGRESS.json','HANDOFF.json','MANIFEST.json'} or n.startswith('evidence/') for n in changed),changed
assert q.source_digest(ROOT)==SOURCE
command(['git','config','user.name','Consilium verified delivery'])
command(['git','config','user.email','consilium-delivery@users.noreply.github.com'])
command(['git','commit','-m','Record native P04 typed-source verification and reconcile phase handoff'])
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT).decode().strip()
command(['git','push','origin','HEAD:refs/heads/'+BRANCH],timeout=45)
receipt={'status':'VERIFIED_DELIVERY_BRANCH_PUSHED','commit':commit,'tree':tree,'source_digest':SOURCE,
    'code_commit':CODE,'native_run_id':str(RUN),'configured_receipt':latest['receipt'],
    'files':verification['files'],'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'tests_per_target':419,'process_exit_cases_per_target':23,'phase_accepted':False,
    'changed_paths':len(changed),'product_source_changes':0,'primary_main_publication':'PENDING_PRIMARY_REF_CHECK'}
(output/'PUBLICATION_RESULT.json').write_bytes(q.encoded(receipt))
print(json.dumps(receipt))
