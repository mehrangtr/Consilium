"""Synthetic offline review tests; no real model quality evidence is produced."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from consilium.core.pilot_review import blinded_material, decoded, digest, encoded, validate_scores
from consilium.shell.pilot import PilotJournal
from consilium.shell.pilot_review import PilotReviewStore
from test_pilot import protocol


def fixture():
    calls = protocol('SINGLE') + protocol('REPEATED_SINGLE') + protocol('COUNCIL', 'other')
    dataset = encoded({'tasks': [{'task_id': 'task', 'prompt': 'Synthetic prompt',
        'reference': 'Held-out synthetic reference', 'reference_type': 'TEST_ONLY'}]})
    plan = {'task_ids': ['task'], 'max_calls_per_task_method': 6,
            'dataset_sha256': digest(dataset), 'rubric_id': 'p06-quality.v1', 'blinding_seed': 'test-only'}
    return calls, plan, dataset


def scored(template, score=6):
    result = deepcopy(template)
    result['evaluator'] = {'id': 'synthetic-test-evaluator', 'origin': 'HUMAN_MANUAL', 'relationship': 'SAME_AUTHOR'}
    for row in result['scores']:
        for judgment in row['dimensions'].values():
            judgment.update(score=score, reason='Synthetic test reason against held-out reference')
    return result


def setup_store(directory):
    calls, plan, dataset = fixture()
    journal = PilotJournal(Path(directory), ('task',))
    for call in calls:
        journal.append(call, b'prompt', b'response')
    return PilotReviewStore(journal), plan, dataset


class PilotReviewTests(unittest.TestCase):
    def material(self):
        calls, plan, _ = fixture()
        return blinded_material(calls, plan, {digest(b'response'): b'response'})

    def test_packet_hides_method_labels_and_template_is_unscored(self):
        packet, mapping, template = self.material()
        self.assertEqual(len(packet['outputs']), 3)
        for row in packet['outputs']:
            self.assertEqual(set(row), {'blind_id', 'task_id', 'response_sha256', 'response'})
        self.assertEqual({row['method'] for row in mapping.values()}, {'SINGLE', 'REPEATED_SINGLE', 'COUNCIL'})
        self.assertTrue(all(j['score'] is None and j['reason'] == ''
            for row in template['scores'] for j in row['dimensions'].values()))
        self.assertNotIn('reference', encoded(packet).decode())

    def test_complete_scoring_reports_pairs_without_quality_acceptance(self):
        packet, mapping, template = self.material()
        report = validate_scores(scored(template), packet, mapping)
        self.assertEqual(report['scored_outputs'], 3)
        self.assertEqual(len(report['paired_differences']), 3)
        self.assertTrue(all(pair['mean_difference'] == 0 for pair in report['paired_differences']))
        self.assertFalse(report['phase_accepted'])
        self.assertFalse(report['reviewer_independence_verified'])
        self.assertFalse(report['model_superiority_claimed'])

    def test_paired_difference_sign_and_weighted_rubric_are_exact(self):
        packet, mapping, template = self.material()
        record = scored(template, 5)
        for row in record['scores']:
            if mapping[row['blind_id']]['method'] == 'COUNCIL':
                row['dimensions']['evidence']['score'] = 10
        report = validate_scores(record, packet, mapping)
        pair = next(p for p in report['paired_differences'] if p['second_method'] == 'SINGLE')
        self.assertEqual(pair['first_method'], 'COUNCIL')
        self.assertEqual(pair['per_task'][0]['difference'], 2)

    def test_incomplete_null_boolean_nonfinite_or_out_of_range_scores_fail(self):
        packet, mapping, template = self.material()
        for score in (None, True, float('nan'), float('inf'), 0, 11, '7'):
            with self.subTest(score=score), self.assertRaises(ValueError):
                validate_scores(scored(template, score), packet, mapping)

    def test_every_dimension_requires_a_nonempty_reason(self):
        packet, mapping, template = self.material()
        for reason in ('', ' ', None, False):
            record = scored(template)
            record['scores'][0]['dimensions']['evidence']['reason'] = reason
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                validate_scores(record, packet, mapping)

    def test_missing_duplicate_foreign_and_identity_leaking_rows_fail(self):
        packet, mapping, template = self.material()
        base = scored(template)
        candidates = []
        missing = deepcopy(base); missing['scores'].pop(); candidates.append(missing)
        duplicate = deepcopy(base); duplicate['scores'][1] = duplicate['scores'][0]; candidates.append(duplicate)
        foreign = deepcopy(base); foreign['scores'][0]['blind_id'] = 'FOREIGN'; candidates.append(foreign)
        leaked = deepcopy(base); leaked['scores'][0]['method'] = 'SINGLE'; candidates.append(leaked)
        dimension = deepcopy(base); dimension['scores'][0]['dimensions'].pop('reasoning'); candidates.append(dimension)
        for record in candidates:
            with self.subTest(record=record), self.assertRaises(ValueError):
                validate_scores(record, packet, mapping)

    def test_packet_dataset_rubric_and_response_bindings_cannot_change(self):
        packet, mapping, template = self.material()
        for field in ('packet_sha256', 'dataset_sha256', 'rubric_id'):
            record = scored(template); record[field] = 'changed'
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_scores(record, packet, mapping)
        for field in ('task_id', 'response_sha256'):
            record = scored(template); record['scores'][0][field] = 'changed'
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_scores(record, packet, mapping)

    def test_evaluator_claims_are_explicit_but_never_authenticated(self):
        packet, mapping, template = self.material()
        for changes in ({'id': ''}, {'origin': 'AUTOMATIC_VERIFIED'}, {'origin': []},
                        {'relationship': 'INDEPENDENT_VERIFIED'}, {'authenticated': True}):
            record = scored(template); record['evaluator'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_scores(record, packet, mapping)

    def test_blind_map_cannot_assign_two_answers_to_one_method(self):
        packet, mapping, template = self.material()
        changed = deepcopy(mapping)
        for row in changed.values(): row['method'] = 'SINGLE'
        with self.assertRaises(ValueError):
            validate_scores(scored(template), packet, changed)

    def test_duplicate_json_fields_and_nonfinite_constants_are_rejected(self):
        for content in (b'{"version": 1, "version": 2}', b'{"score": NaN}', b'{"score": Infinity}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                decoded(content)

    def test_final_bytes_and_intermediate_observation_binding_are_checked(self):
        calls, plan, _ = fixture()
        with self.assertRaises(ValueError):
            blinded_material(calls, plan, {digest(b'response'): b'altered'})
        packet, _, _ = self.material()
        changed = tuple(replace(call, elapsed_seconds=2) if call.stage != 'ARCHITECT' else call for call in calls)
        after, _, _ = blinded_material(changed, plan, {digest(b'response'): b'response'})
        self.assertNotEqual(packet['observation_manifest_sha256'], after['observation_manifest_sha256'])

    def test_preparation_is_immutable_and_exactly_resumable(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory)
            store.prepare(plan, dataset)
            originals = {p.name: p.read_bytes() for p in Path(directory).glob('*.json')}
            PilotReviewStore(store.journal).prepare(plan, dataset)
            self.assertEqual(originals, {p.name: p.read_bytes() for p in Path(directory).glob('*.json')})
            changed = dict(plan, blinding_seed='changed')
            with self.assertRaises(ValueError): store.prepare(changed, dataset)
            self.assertEqual((Path(directory) / 'BLINDED.json').read_bytes(), originals['BLINDED.json'])

    def test_held_out_references_are_separate_and_exact_dataset_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory)
            with self.assertRaises(ValueError): store.prepare(plan, dataset + b' ')
            store.prepare(plan, dataset)
            references = json.loads((Path(directory) / 'JUDGE_REFERENCES.json').read_bytes())
            self.assertEqual(references['tasks'][0]['reference'], 'Held-out synthetic reference')
            self.assertNotIn('Held-out', (Path(directory) / 'BLINDED.json').read_text())

    def test_modified_or_partial_export_blocks_score_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory); store.prepare(plan, dataset)
            record = scored(json.loads((Path(directory) / 'SCORING_TEMPLATE.json').read_bytes()))
            target = Path(directory) / 'BLINDED.json'; original = target.read_bytes()
            target.write_bytes(original + b' ')
            with self.assertRaises(ValueError): store.register_scores(encoded(record), plan, dataset)
            target.unlink()
            with self.assertRaises(OSError): store.register_scores(encoded(record), plan, dataset)
            store.prepare(plan, dataset)
            self.assertEqual(store.register_scores(encoded(record), plan, dataset)['scored_outputs'], 3)

    def test_score_receipt_preserves_original_bytes_and_refuses_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory); store.prepare(plan, dataset)
            template = json.loads((Path(directory) / 'SCORING_TEMPLATE.json').read_bytes())
            raw = json.dumps(scored(template), ensure_ascii=False).encode() + b'\r\n'
            report = store.register_scores(raw, plan, dataset)
            self.assertEqual(report['original_score_bytes_sha256'], digest(raw))
            self.assertEqual((Path(directory) / 'VALIDATED_SCORES.json').read_bytes(), raw)
            self.assertEqual(PilotReviewStore(store.journal).score_report(plan, dataset), report)
            with self.assertRaises(ValueError): store.register_scores(encoded(scored(template, 7)), plan, dataset)
            self.assertEqual(store.score_report(plan, dataset), report)

    def test_score_report_rejects_modified_export_even_when_cas_is_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory); store.prepare(plan, dataset)
            template = json.loads((Path(directory) / 'SCORING_TEMPLATE.json').read_bytes())
            raw = encoded(scored(template)); store.register_scores(raw, plan, dataset)
            export = Path(directory) / 'VALIDATED_SCORES.json'; export.write_bytes(raw + b' ')
            with self.assertRaises(ValueError): store.score_report(plan, dataset)
            export.unlink()
            with self.assertRaises(OSError): store.score_report(plan, dataset)
            store.register_scores(raw, plan, dataset)
            self.assertEqual(store.score_report(plan, dataset)['scored_outputs'], 3)

    def test_damaged_intermediate_cas_object_blocks_blinding(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory)
            (store.journal.objects.root / digest(b'prompt')).write_bytes(b'changed')
            with self.assertRaises(ValueError): store.prepare(plan, dataset)

    def test_frozen_journal_refuses_new_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory); store.prepare(plan, dataset)
            before = store.journal.calls()
            failed = replace(protocol('SINGLE')[-1], call_id='late', outcome='FAILED', final=False,
                             failure_reason='Late attempt is outside frozen experiment')
            with self.assertRaises(ValueError): store.journal.append(failed, b'prompt', b'response')
            self.assertEqual(store.journal.calls(), before)

    def test_registration_checks_the_journal_inside_the_commit_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory)
            original = store._register
            def racing(artifacts, expected):
                # Reproduce a writer winning between projection and registration.
                store.journal.append(replace(protocol('SINGLE')[-1], call_id='late',
                    outcome='FAILED', final=False, failure_reason='Observed failure'), b'prompt', b'response')
                original(artifacts, expected)
            store._register = racing
            with self.assertRaises(ValueError): store.prepare(plan, dataset)
            with store.journal._connect() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM review_artifacts').fetchone()[0], 0)

    def test_cli_records_twenty_four_scores_but_never_accepts_a_phase(self):
        root = Path(__file__).resolve().parents[2]
        plan = json.loads((root / 'docs/p06/PREREGISTRATION.json').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            journal = PilotJournal(Path(directory), tuple(plan['task_ids']))
            for task in plan['task_ids']:
                for method in plan['methods']:
                    for call in protocol(method, 'other' if method == 'COUNCIL' else 'baseline'):
                        journal.append(replace(call, task_id=task, call_id=task + '-' + call.call_id,
                            shared_architect_call_id=task + '-architect' if call.stage == 'ARCHITECT' else None),
                            b'prompt', b'response')
            cli = [sys.executable, str(root / 'tools/p06_pilot.py')]
            result = subprocess.run(cli + ['blind', '--workspace', directory], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            template = json.loads((Path(directory) / 'SCORING_TEMPLATE.json').read_bytes())
            scores = Path(directory) / 'COMPLETED_SCORES.json'; scores.write_bytes(encoded(scored(template)))
            result = subprocess.run(cli + ['score', '--workspace', directory, '--scores', str(scores)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            report = json.loads(result.stdout)
            self.assertEqual(report['blinded_score_review']['scored_outputs'], 24)
            self.assertFalse(report['phase_accepted'])
            self.assertFalse(report['blinded_score_review']['phase_accepted'])
            self.assertEqual(report['unique_observed_model_calls'], 96)
            self.assertEqual(report['recorded_calls'], 112)

    def test_complete_scores_cannot_bypass_product_flow_and_hours_barriers(self):
        import importlib.util
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / 'tools'))
        try:
            spec = importlib.util.spec_from_file_location('p06_barrier_test', root / 'tools/check_p06.py')
            checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        finally:
            sys.path.remove(str(root / 'tools'))
        packet, mapping, template = self.material()
        report = validate_scores(scored(template), packet, mapping)
        blockers = checker.evidence_blockers({'status': 'READY_FOR_BLINDED_REVIEW'}, report)
        self.assertIn('PRODUCT_FLOW_REVIEW_NOT_REGISTERED', blockers)
        self.assertIn('ERROR_FINDINGS_AND_REESTIMATE_NOT_REGISTERED', blockers)
        missing = checker.evidence_blockers({'status': 'INCOMPLETE'}, None)
        self.assertIn('REAL_THREE_METHOD_OUTPUTS_AND_INTERMEDIATE_CALLS_INCOMPLETE', missing)
        self.assertIn('BLINDED_SCORE_RECEIPT_MISSING_OR_INVALID', missing)

    def test_concurrent_score_writers_cannot_split_the_score_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory); store.prepare(plan, dataset)
            template = json.loads((Path(directory) / 'SCORING_TEMPLATE.json').read_bytes())
            def register(value):
                try:
                    return PilotReviewStore(store.journal).register_scores(encoded(scored(template, value)), plan, dataset)
                except ValueError:
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                reports = list(pool.map(register, (5, 7)))
            self.assertEqual(sum(report is not None for report in reports), 1)
            self.assertIn(store.score_report(plan, dataset), reports)

    def test_real_process_exit_during_registration_leaves_no_partial_manifest(self):
        self._crash_and_resume('transaction', 74)

    def test_real_process_exit_during_export_resumes_frozen_material(self):
        self._crash_and_resume('export', 75)

    def _crash_and_resume(self, mode, expected_code):
        with tempfile.TemporaryDirectory() as directory:
            store, plan, dataset = setup_store(directory)
            code = '''import json, os, sqlite3, sys
from pathlib import Path
from consilium.shell.pilot import PilotJournal
from consilium.shell.pilot_review import PilotReviewStore
store = PilotReviewStore(PilotJournal(Path(sys.argv[1]), ('task',)))
if sys.argv[4] == 'transaction':
 original = sqlite3.connect
 class CrashConnection(sqlite3.Connection):
  def execute(self, sql, *args):
   result = super().execute(sql, *args)
   if sql.startswith('INSERT OR IGNORE INTO review_artifacts'): os._exit(74)
   return result
 sqlite3.connect = lambda *a, **k: original(*a, factory=CrashConnection, **k)
else:
 original = store._export
 def interrupted(name):
  original(name)
  os._exit(75)
 store._export = interrupted
store.prepare(json.loads(sys.argv[2]), sys.argv[3].encode())
'''
            root = Path(__file__).resolve().parents[2]
            result = subprocess.run([sys.executable, '-c', code, directory,
                json.dumps(plan), dataset.decode(), mode],
                env=dict(os.environ, PYTHONPATH=str(root / 'src')), capture_output=True, timeout=10)
            self.assertEqual(result.returncode, expected_code, result.stderr.decode())
            if mode == 'transaction':
                with store.journal._connect() as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM review_artifacts').fetchone()[0], 0)
                self.assertFalse((Path(directory) / 'BLINDED.json').exists())
            PilotReviewStore(store.journal).prepare(plan, dataset)
            template = json.loads((Path(directory) / 'SCORING_TEMPLATE.json').read_bytes())
            self.assertEqual(store.register_scores(encoded(scored(template)), plan, dataset)['scored_outputs'], 3)


if __name__ == '__main__':
    unittest.main()
