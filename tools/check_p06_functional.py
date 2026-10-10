"""Validate the user-authorized functional exit, without completing the benchmark."""
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import UUID

import qualityctl as q

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from consilium.core.pilot_three_stage import ThreeStagePlan, summarize_three_stage
from consilium.shell.pilot_three_stage import ThreeStageJournal
from consilium.shell.storage import SQLiteStore


def validate_groups(summary, tasks):
    rows = {(r['task_id'], r['method']): r for r in summary['per_task_method']}
    for task in tasks:
        for method in ('SINGLE', 'COUNCIL', 'REPEATED_SINGLE'):
            row = rows.get((task, method))
            if not row or not row['protocol_complete'] or row['unresolved_outcome']:
                raise ValueError('An accepted task needs all three complete real methods')


def inspect(workspace):
    scope = q.load(ROOT / 'docs/p06/FUNCTIONAL_EXIT.json')
    q.require(scope['authorization_kind'] == 'EXPLICIT_USER_SCOPE_REVISION'
              and scope['benchmark_completed'] is False
              and scope['model_superiority_claimed'] is False,
              'Functional exit must disclose its authorized scope')
    registration = q.load(ROOT / 'docs/p06/THREE_STAGE_PREREGISTRATION.json')
    value = registration['profile']
    plan = ThreeStagePlan(**{**value, 'task_ids': tuple(value['task_ids'])})
    q.require(workspace.is_dir() and not workspace.is_relative_to(ROOT), 'Private runtime required')
    q.require((workspace / 'three-stage.sqlite3').is_file(), 'Actual journal missing')
    journal = ThreeStageJournal(workspace, plan)
    observations = journal.calls()  # Rechecks CAS bytes, peers, budgets and conversation bindings.
    summary = summarize_three_stage(observations, plan)
    validate_groups(summary, scope['accepted_task_ids'])
    products = []
    for task in scope['accepted_task_ids']:
        for method in ('SINGLE', 'COUNCIL', 'REPEATED_SINGLE'):
            path = workspace / 'product' / (task + '-' + method + '.sqlite3')
            q.require(path.is_file(), 'Product database missing')
            with SQLiteStore(path) as store:
                q.require([r[0] for r in store._db.execute('PRAGMA quick_check')] == ['ok'], 'Damaged product')
                q.require(not store._db.execute('PRAGMA foreign_key_check').fetchall(), 'Orphan product record')
                store.council.check_integrity()
                dids = store._db.execute('SELECT debate_id FROM debates').fetchall()
                q.require(len(dids) == 1, 'One topic per product database required')
                did = UUID(dids[0][0])
                sources = store.sources.context_sources(did, through_revision=store.checkpoint(did).revision)
                accepted = [json.loads(r[0]) for r in store._db.execute(
                    'SELECT c.candidate_json FROM manual_round_candidates c '
                    'JOIN manual_round_acceptances a ON a.candidate_id=c.candidate_id')]
                accepted += [{'content': s.item.content, 'actual_prompt': s.item.used_prompt}
                             for s in sources if hasattr(s.item, 'content')]
                for observation in observations:
                    call = observation.call
                    if (call.task_id, call.method, call.outcome) != (task, method, 'SUCCESS') or call.stage == 'ARCHITECT':
                        continue
                    matches = [s for s in accepted if hashlib.sha256(s['content'].encode()).hexdigest()
                               == call.response_sha256]
                    q.require(matches and any(hashlib.sha256(s['actual_prompt'].encode()).hexdigest()
                                              == call.prompt_sha256 for s in matches),
                              'Captured response/prompt pair is not accepted in the actual product')
                if method != 'SINGLE':
                    finals = store._db.execute("SELECT round_id FROM council_records WHERE kind='FINAL'").fetchall()
                    q.require(len(finals) == 1, 'Exactly one persisted final required')
                    final = store.council.get('FINAL', UUID(finals[0][0]))
                    final_call = next(o.call for o in observations if o.call.task_id == task
                                      and o.call.method == method and o.call.stage == 'SYNTHESIS'
                                      and o.call.outcome == 'SUCCESS')
                    sources = store.sources.context_sources(final.debate_id,
                        through_revision=store.council.revision(final.debate_id))
                    source = next(s for s in sources if s.content_hash == final.judge_source_hash)
                    q.require(hashlib.sha256(source.item.content.encode()).hexdigest()
                              == final_call.response_sha256,
                              'Product final differs from the captured judge response')
            products.append({'task_id': task, 'method': method, 'integrity': 'PASS',
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    review = q.load(workspace / 'FUNCTIONAL_REVIEW.json')
    q.require(review['status'] == 'PASS' and review['profile_sha256'] == plan.sha256
              and review['accepted_task_ids'] == scope['accepted_task_ids']
              and review['reviewer_independent'] is False, 'Fresh scoped review required')
    for row in review['answer_checks']:
        call = next(o.call for o in observations if o.call.call_id == row['call_id'])
        q.require(call.outcome == 'SUCCESS' and call.response_sha256 == row['response_sha256']
                  and row['status'] == 'PASS' and row['reason'], 'Answer review lost its source')
    expected = {o.call.call_id for o in observations if o.call.task_id in scope['accepted_task_ids']
                and o.call.outcome == 'SUCCESS' and o.call.stage in ('SINGLE', 'SYNTHESIS')}
    q.require(len(review['answer_checks']) == len(expected) == 9
              and {r['call_id'] for r in review['answer_checks']} == expected,
              'All nine unique finals require review')
    q.require(review['open_functional_defects'] == [] and review['findings']
              and review['reestimate']['historical_hours'] is None
              and review['reestimate']['measured_hours_claimed'] is False,
              'Findings and honest treatment of unmeasured engineering hours required')
    return {'status': 'PASS', 'scope': 'USER_AUTHORIZED_FUNCTIONAL_P06_EXIT',
            'benchmark_completed': False, 'benchmark': summary, 'products': products,
            'review_sha256': q.digest((workspace / 'FUNCTIONAL_REVIEW.json').read_bytes()),
            'model_superiority_claimed': False, 'phase_accepted': False}


def main():
    before = q.source_digest(ROOT)
    try:
        location = os.environ.get('CONSILIUM_P06_THREE_STAGE_WORKSPACE')
        q.require(location, 'Private real runtime not supplied')
        report = inspect(Path(location).resolve())
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
        report = {'status': 'BLOCKED', 'reason': str(exc), 'phase_accepted': False}
    report.update(source_digest_before=before, source_digest_after=q.source_digest(ROOT))
    folder = ROOT / 'evidence/p06/functional-exit'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'RUN.json').write_bytes(q.encoded(report))
    print(q.encoded(report).decode())
    return int(report['status'] != 'PASS' or before != report['source_digest_after'])


if __name__ == '__main__':
    raise SystemExit(main())
