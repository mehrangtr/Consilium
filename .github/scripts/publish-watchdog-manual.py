"""Operational delivery; checkout and preserve exactly the native-tested source."""
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
sys.path.insert(0, str(ROOT / 'tools'))
import qualityctl as q


def command(args, timeout=120):
    subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL, check=True, timeout=timeout)


def github(path):
    request = urllib.request.Request('https://api.github.com/repos/mehrangtr/Consilium/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def supervisor_snapshots():
    snapshots = []
    for path in sorted((ROOT / 'evidence/development-supervisor').glob('*/STATE.json')):
        state = q.load(path)
        if state['source_digest'] != SOURCE:
            continue
        assert state['status'] == 'PASS' and state['idle_seconds'] == 300 and state['hard_seconds'] == 900
        assert state['phase_advanced'] is False and not state['remaining_steps']
        for row in state['steps']:
            assert row['status'] in {'COMPLETE', 'RECOVERED_COMPLETE'}
            assert row['reconciliation']['status'] == 'VERIFIED_COMPLETE'
            assert not row['retained_proof']['errors']
            receipt = q.load(q.artifact(ROOT, {'path': row['reconciliation']['receipt'],
                                               'sha256': row['reconciliation']['sha256']}))
            assert receipt['development_step_id'] == row['nonce']
            assert receipt['status'] == 'PASS'
            assert receipt['source_digest_before'] == receipt['source_digest_after'] == SOURCE
            for ref in row['retained_proof']['artifacts']:
                q.artifact(ROOT, {'path': ref['path'], 'sha256': ref['sha256']})
        snapshots.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': q.digest(path.read_bytes()), 'state': state})
    return snapshots


assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == CODE
assert q.source_digest(ROOT) == SOURCE
run = github('actions/runs/' + str(RUN))
assert run['head_sha'] == CODE and run['status'] == 'completed' and run['conclusion'] == 'success'
command([sys.executable, 'tools/check_target_matrix.py'])
_, native = q.target_evidence_files(ROOT)
assert {x['target'] for x in native} == {'Windows', 'Linux'}
assert all(x['status'] == 'PASS' and x['source_matches_current'] for x in native)
for target in native:
    report = q.load(ROOT / target['report']['path'])
    counts = {role: q.load(q.artifact(ROOT, ref))['counts']['tests'] for role, ref in report['artifacts'].items()
              if role in {'control_report', 'foundation_report', 'persistence_report', 'browser_probe_report', 'architect_report'}}
    assert counts == {'control_report': 99, 'foundation_report': 60, 'persistence_report': 80,
                      'browser_probe_report': 44, 'architect_report': 170}, counts
    assert sum(counts.values()) == 453
snapshots = supervisor_snapshots()
assert len([x for x in snapshots if x['state']['steps'][0]['step'] == 'native']) == 2

progress = q.load(ROOT / 'PROGRESS.json')
accepted_before = {p['id']: q.encoded(p) for p in progress['phases'] if p['id'] in {'P00', 'P01', 'P02', 'P03'}}
assert progress['current_phase'] == 'P04' and progress['verified_application_requirements'] == 0
phase = next(p for p in progress['phases'] if p['id'] == 'P04')
assert phase['status'] == 'IN_PROGRESS'
next_action = 'در P04-002 نقد دستی و دورهای بعد و منشأ زنده و تطبیق صریح عملیات قبلی را تکمیل کن؛ نمای دور بعد را از منابع رسمی با مجوز انتقال و بودجه در یک تراکنش به قصد عملیات وصل کن. بازیابی و حفظ مخالفت و نشت و بودجه را آزمون و تمام معیارهای P04 را بازبینی کن. P05 و ارسال زنده هنوز آغاز نشوند.'
resume = progress['resume']
resume['working_changes'] = []
resume['completed_work'].append('Five-minute owned-process supervisor and P04-002 explicit initial manual-answer acceptance/V7 migration verified: 453 tests and 25 product process-exit cases per actual native OS. Full P04 remains open.')
resume['next_action'] = next_action
resume['next_task'].update(status='PARTIAL_MANUAL_INITIAL_ANSWER_NATIVE_VERIFIED',
    completed_fa='ناظر پنج‌دقیقه‌ای و پذیرش صریح و پایدار پاسخ دستی اولیه همراه با مهاجرت نسخهٔ ۷ پیاده شده‌اند. ۴۵۳ آزمون و ۲۵ مورد قطع پردازهٔ محصول در هر دو محیط بومی موفق‌اند؛ قطع درخت پردازهٔ ناظر نیز در آزمون‌های کنترل اجرا شده است.',
    remaining_fa='نقد دستی و دورهای بعد، تطبیق صریح عملیات قبلی، منشأ زندهٔ معتبر، اتصال پایدار نمای دور بعد به قصد و شواهد مجوز و بودجه و پذیرش کامل P04.', next_action_fa=next_action)
now = dt.datetime.now(dt.timezone.utc).isoformat()
resume['unfinished_work']['updated_at_utc'] = now
resume['unfinished_work']['continuation_instruction'] = 'PR7 and previous main 48b61982442ca9258e4fa6961b98b221fc8927d5 were verified complete. Current watchdog/manual-initial-answer slice is native-verified for ' + SOURCE + '. Continue only remaining P04-002 scope. Preserve accepted P00-P03 and historical failed evidence; do not replay accepted provider probes.'
resume['unfinished_work']['items'][0] = resume['next_task'].copy()
resume['native_evidence'] = {'run_id': str(RUN), 'code_commit': CODE, 'source_digest': SOURCE,
    'tests_per_target': 453, 'process_exit_cases_per_target': 25, 'target_reports': native}
resume['transfer_reviewed_file_count'] = None
progress['application_source_commit'] = CODE
phase['source_commit'] = CODE
phase['notes'] = [('HISTORICAL: ' + x) if x.startswith('CURRENT') else x for x in phase['notes']]
phase['notes'].append('CURRENT: owned-process five-minute supervisor and explicit manual initial-answer acceptance verified for ' + SOURCE + '; 453 tests and 25 product process exits per actual OS. P04 not accepted; manual critiques/later rounds, live provenance and durable later-round admission remain open.')
progress['updated_at_utc'] = now
(ROOT / 'PROGRESS.json').write_bytes(q.encoded(progress))
q.navigation(ROOT)
command([sys.executable, 'tools/development_supervisor.py', 'phase'], timeout=180)
latest, _ = q.latest_phase_run(ROOT, 'P04', progress['plan_version'])
assert latest['status'] == 'PASS' and latest['source_matches_current']
phase['tests'] = [latest['receipt']]
snapshots = supervisor_snapshots()
assert len([x for x in snapshots if x['state']['steps'][0]['step'] == 'phase']) >= 1
checkpoint = q.load(ROOT / 'evidence/p04/WATCHDOG_MANUAL_CHECKPOINT.json')
checkpoint.update(status='WATCHDOG_AND_MANUAL_INITIAL_ANSWER_NATIVE_VERIFIED_NOT_PHASE_ACCEPTED', source_digest=SOURCE,
    code_commit=CODE, native_run_id=str(RUN), target_reports=native, configured_phase_run=latest,
    tests_per_native_target=453, product_process_exit_cases_per_native_target=25,
    development_supervisor_snapshots=snapshots,
    raw_supervisor_journals='Published Git repository and CI artifacts; complete state snapshots embedded here. Retained original native/configured receipts and their artifacts are included in the standard handoff.',
    phase_accepted=False, next_action=next_action, publication_scope='VERIFIED_DELIVERY_BRANCH_PRIMARY_MAIN_PUBLICATION_PENDING')
cp = ROOT / 'evidence/p04/WATCHDOG_MANUAL_CHECKPOINT.json'
cp.write_bytes(q.encoded(checkpoint))
resume['last_verified_in_phase_checkpoint'] = {'phase': 'P04', 'path': cp.relative_to(ROOT).as_posix(),
    'sha256': q.digest(cp.read_bytes()), 'source_digest': SOURCE, 'phase_accepted': False}
resume['developer_supervisor']['native_verified'] = True
resume['developer_supervisor']['latest_state_snapshots'] = {'path': cp.relative_to(ROOT).as_posix(), 'sha256': q.digest(cp.read_bytes())}
review = q.load(ROOT / 'evidence/p04/WATCHDOG_MANUAL_REVIEW.json')
review.update(status='PASS_IMPLEMENTED_SLICE_ONLY', source_digest=SOURCE, code_commit=CODE,
    native_run_id=str(RUN), target_reports=native, configured_phase_run=latest, tests_per_native_target=453,
    product_process_exit_cases_per_native_target=25, phase_accepted=False)
review['remaining'] = [x for x in review['remaining'] if 'Native Windows' not in x]
(ROOT / 'evidence/p04/WATCHDOG_MANUAL_REVIEW.json').write_bytes(q.encoded(review))
(ROOT / 'PROGRESS.json').write_bytes(q.encoded(progress))
assert accepted_before == {p['id']: q.encoded(p) for p in progress['phases'] if p['id'] in accepted_before}
q.navigation(ROOT)
assert q.source_digest(ROOT) == SOURCE

output = ROOT.parent / 'delivery'
output.mkdir(exist_ok=True)
preview = output / 'P04_WATCHDOG_MANUAL_PREVIEW.zip'
q.handoff(ROOT, preview)
preview_result = q.verify(preview)
resume['transfer_reviewed_file_count'] = preview_result['files']
(ROOT / 'PROGRESS.json').write_bytes(q.encoded(progress))
q.navigation(ROOT)
archive = output / 'P04_WATCHDOG_MANUAL_HANDOFF.zip'
info = q.handoff(ROOT, archive)
verification = q.verify(archive)
assert verification['files'] == preview_result['files']
assert info['source_snapshot_digest'] == SOURCE
assert info['state_label'] == 'INCOMPLETE' and info['current_phase'] == 'P04' and info['last_accepted_phase'] == 'P03'
assert info['latest_current_phase_run']['status'] == 'PASS' and info['latest_current_phase_run']['source_matches_current']
assert all(x['source_matches_current'] and x['status'] == 'PASS' for x in info['native_target_runs'])
with zipfile.ZipFile(archive) as z:
    for name in ('HANDOFF.json', 'MANIFEST.json'):
        (ROOT / name).write_bytes(z.read(name))
command(['git', 'add', 'PROGRESS.json', 'HANDOFF.json', 'MANIFEST.json', 'evidence'])
changed = subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=ROOT).decode().splitlines()
assert all(n in {'PROGRESS.json', 'HANDOFF.json', 'MANIFEST.json'} or n.startswith('evidence/') for n in changed), changed
assert q.source_digest(ROOT) == SOURCE
command(['git', 'config', 'user.name', 'Consilium verified delivery'])
command(['git', 'config', 'user.email', 'consilium-delivery@users.noreply.github.com'])
command(['git', 'commit', '-m', 'Record native watchdog and manual-answer verification with precise P04 continuation'])
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT).decode().strip()
command(['git', 'push', 'origin', 'HEAD:refs/heads/' + BRANCH], timeout=45)
receipt = {'status': 'VERIFIED_DELIVERY_BRANCH_PUSHED', 'commit': commit, 'tree': tree, 'source_digest': SOURCE,
    'code_commit': CODE, 'native_run_id': str(RUN), 'configured_receipt': latest['receipt'],
    'files': verification['files'], 'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'tests_per_target': 453, 'product_process_exit_cases_per_target': 25, 'phase_accepted': False,
    'supervisor_snapshots': len(snapshots), 'changed_paths': len(changed), 'product_source_changes': 0,
    'primary_main_publication': 'PENDING_PRIMARY_REF_CHECK'}
(output / 'PUBLICATION_RESULT.json').write_bytes(q.encoded(receipt))
print(json.dumps(receipt))
