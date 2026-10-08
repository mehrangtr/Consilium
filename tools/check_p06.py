"""P06 preflight and missing-evidence barrier; never infer quality from mocks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from consilium.core.pilot import METHODS, summarize
from consilium.core.rubrics import get_rubric
from consilium.shell.pilot import PilotJournal


def preflight():
    plan = q.load(ROOT / 'docs/p06/PREREGISTRATION.json')
    data = (ROOT / plan['dataset']).read_bytes()
    if hashlib.sha256(data).hexdigest() != plan['dataset_sha256']:
        raise ValueError('Preregistered dataset changed')
    tasks = {t['task_id'] for t in json.loads(data)['tasks']}
    selected = plan['task_ids']
    if not 6 <= len(selected) <= 10 or len(set(selected)) != len(selected) or not set(selected) <= tasks:
        raise ValueError('Pilot must retain six to ten unique preregistered tasks')
    if (set(plan['methods']) != METHODS or plan['max_calls_per_task_method'] != 6
            or plan['max_output_tokens_per_task_method'] != 2400
            or plan['single_output_token_cap'] != 2000
            or plan['multiround_output_token_cap_each'] != 400
            or plan['max_elapsed_seconds_per_task_method'] != 600
            or plan['max_cost'] != 0 or plan['paid_calls_authorized'] is not False
            or plan['mock_outputs_are_quality_evidence'] is not False):
        raise ValueError('Pilot budgets or evidence policy differ from the preregistration')
    get_rubric(plan['rubric_id'])
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight', 'evidence'))
    args = parser.parse_args()
    before = q.source_digest(ROOT)
    plan = preflight()
    blockers = []
    summary = summarize((), tuple(plan['task_ids']))
    if args.mode == 'evidence':
        location = os.environ.get('CONSILIUM_P06_WORKSPACE')
        if not location:
            blockers.append('NO_RECORDED_PRIVATE_REAL_PILOT_WORKSPACE')
        else:
            workspace = Path(location).resolve()
            if workspace.is_relative_to(ROOT) or not workspace.is_dir():
                raise ValueError('Observed pilot workspace must exist outside the source checkout')
            if not (workspace / 'pilot.sqlite3').is_file():
                blockers.append('NO_REAL_OBSERVATION_JOURNAL')
            else:
                journal = PilotJournal(workspace, tuple(plan['task_ids']))
                calls = journal.calls()
                for call in calls:
                    journal.objects.read(call.prompt_sha256)
                    journal.objects.read(call.response_sha256)
                summary = summarize(calls, tuple(plan['task_ids']))
            # Raw text and judge mapping are private. Their existence alone
            # cannot certify scores, repairs, product flow or actual hours.
        if summary['status'] != 'READY_FOR_BLINDED_REVIEW':
            blockers.append('REAL_THREE_METHOD_OUTPUTS_AND_INTERMEDIATE_CALLS_INCOMPLETE')
        blockers += ['BLINDED_SCORING_AND_PRODUCT_FLOW_REVIEW_NOT_REGISTERED',
                     'ERROR_FINDINGS_AND_REESTIMATE_NOT_REGISTERED']
    after = q.source_digest(ROOT)
    report = {'phase': 'P06', 'mode': args.mode,
        'status': 'BLOCKED' if blockers else 'PASS',
        'scope': 'PILOT_PREFLIGHT_ONLY' if args.mode == 'preflight' else 'REAL_PILOT_EVIDENCE_BARRIER',
        'source_digest_before': before, 'source_digest_after': after,
        'task_count': len(plan['task_ids']), 'method_count': len(plan['methods']),
        'required_final_outputs': summary['required_final_outputs'],
        'recorded_final_outputs': summary['real_manual_final_outputs'],
        'blockers': blockers, 'phase_accepted': False, 'model_superiority_claimed': False}
    folder = ROOT / 'evidence/p06'; folder.mkdir(parents=True, exist_ok=True)
    (folder / (args.mode.upper() + '.json')).write_bytes(q.encoded(report))
    print(q.encoded(report).decode())
    return 2 if blockers else int(before != after)


if __name__ == '__main__':
    raise SystemExit(main())
