"""Offline accounting tests; synthetic responses never prove model quality."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from consilium.core.pilot import PilotCall, summarize
from consilium.shell.pilot import PilotJournal


def call(identifier, method='SINGLE', stage='ARCHITECT', model='baseline', origin='MANUAL', **kw):
    kw.setdefault('final', kw.get('outcome', 'SUCCESS') == 'SUCCESS' and stage in {'SINGLE', 'SYNTHESIS'})
    return PilotCall(call_id=identifier, task_id='task', method=method, provider='declared',
        model_id=model, prompt_sha256=hashlib.sha256(b'prompt').hexdigest(),
        response_sha256=hashlib.sha256(b'response').hexdigest(), origin=origin,
        elapsed_seconds=1, cost=0, stage=stage, **kw)


def protocol(method, second_model='baseline'):
    stages = ['ARCHITECT', 'SINGLE'] if method == 'SINGLE' else [
        'ARCHITECT', 'INDEPENDENT', 'INDEPENDENT', 'REVIEW', 'REVIEW', 'SYNTHESIS']
    return tuple(call(method + str(i), method, stage,
        second_model if i in {2, 4} else 'baseline',
        shared_architect_call_id='common-task' if stage == 'ARCHITECT' else None)
        for i, stage in enumerate(stages))


class PilotTests(unittest.TestCase):
    def test_complete_three_protocols_are_ready_but_never_accepted(self):
        calls = protocol('SINGLE') + protocol('REPEATED_SINGLE') + protocol('COUNCIL', 'other')
        report = summarize(calls, ('task',))
        self.assertEqual(report['status'], 'READY_FOR_BLINDED_REVIEW')
        self.assertEqual(report['real_manual_final_outputs'], 3)
        self.assertEqual(report['recorded_calls'], 14)
        self.assertEqual(report['unique_observed_model_calls'], 12)
        self.assertEqual(report['shared_architect_reuses'], 2)
        self.assertEqual(report['observed_elapsed_seconds'], 12)
        self.assertFalse(report['phase_accepted'])
        self.assertFalse(report['external_origin_authenticated'])
        self.assertEqual(report['output_budget_verification'], 'PARTIAL_UNKNOWN_TOKENS')

    def test_different_judge_does_not_make_answers_independent_models(self):
        calls = list(protocol('COUNCIL'))
        calls[-1] = replace(calls[-1], model_id='judge-only')
        self.assertEqual(summarize(tuple(calls), ('task',))['real_manual_final_outputs'], 0)

    def test_mock_intermediate_blocks_quality_evidence(self):
        calls = list(protocol('SINGLE'))
        calls[0] = replace(calls[0], origin='MOCK')
        self.assertEqual(summarize(tuple(calls), ('task',))['real_manual_final_outputs'], 0)

    def test_selected_baseline_model_cannot_change_across_methods(self):
        repeated = tuple(replace(c, model_id='switched') if c.stage != 'ARCHITECT' else c
                         for c in protocol('REPEATED_SINGLE'))
        with self.assertRaises(ValueError):
            summarize(protocol('SINGLE') + repeated, ('task',))

    def test_common_architect_must_have_identical_prompt_and_output(self):
        other = list(protocol('REPEATED_SINGLE'))
        other[0] = replace(other[0], response_sha256='a' * 64)
        with self.assertRaises(ValueError):
            summarize(protocol('SINGLE') + tuple(other), ('task',))

    def test_stage_order_and_unplanned_duplicate_are_rejected(self):
        calls = protocol('REPEATED_SINGLE')
        with self.assertRaises(ValueError):
            summarize((calls[0], calls[3], calls[1]), ('task',))
        with self.assertRaises(ValueError):
            summarize(calls + (replace(calls[3], call_id='extra-review'),), ('task',))

    def test_per_call_and_total_budget_are_enforced(self):
        for changed in [replace(protocol('SINGLE')[-1], output_tokens=2001),
                        replace(protocol('SINGLE')[0], output_tokens=401),
                        replace(protocol('SINGLE')[-1], elapsed_seconds=601)]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                summarize((changed,), ('task',))

    def test_missing_calls_and_unknown_tokens_are_explicit(self):
        report = summarize((call('one'),), ('task',))
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertIsNone(report['per_task_method'][0]['output_tokens'])
        self.assertEqual(report['token_accounting'], 'UNKNOWN_OR_PARTIAL')

    def test_empty_tasks_and_boolean_budget_do_not_certify_empty_pilot(self):
        for tasks, budget in [((), 6), (('task', 'task'), 6), (('task',), True)]:
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                summarize((), tasks, budget)

    def test_identity_requires_text_and_authentication_cannot_be_asserted(self):
        for changes in [{'model_id': True}, {'task_id': ' '}, {'cost': 1},
                        {'elapsed_seconds': float('nan')}, {'external_origin_verified': True}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(call('one'), **changes)

    def test_journal_reopen_preserves_exact_calls_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = PilotJournal(Path(directory), ('task',))
            first = call('one')
            journal.append(first, b'prompt', b'response')
            reopened = PilotJournal(Path(directory), ('task',))
            self.assertEqual(reopened.calls(), (first,))
            with self.assertRaises(ValueError):
                reopened.append(first, b'prompt', b'response')
            self.assertEqual(reopened.calls(), (first,))

    def test_two_concurrent_imports_do_not_lose_an_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = PilotJournal(Path(directory), ('task',))
            journal.append(call('architect', 'REPEATED_SINGLE'), b'prompt', b'response')
            def append(identifier):
                PilotJournal(Path(directory), ('task',)).append(
                    call(identifier, 'REPEATED_SINGLE', 'INDEPENDENT'), b'prompt', b'response')
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(append, ('independent-a', 'independent-b')))
            self.assertEqual({c.call_id for c in journal.calls()},
                {'architect', 'independent-a', 'independent-b'})

    def test_legacy_index_is_migrated_without_rewriting_original(self):
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as directory:
            journal = PilotJournal(Path(directory), ('task',))
            journal.objects.put(b'prompt'); journal.objects.put(b'response')
            legacy = Path(directory) / 'CALLS.json'
            raw = json.dumps([asdict(call('legacy'))]).encode()
            legacy.write_bytes(raw)
            self.assertEqual(PilotJournal(Path(directory), ('task',)).calls(), (call('legacy'),))
            self.assertEqual(legacy.read_bytes(), raw)

    def test_crash_before_observation_commit_preserves_prior_records(self):
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as directory:
            journal = PilotJournal(Path(directory), ('task',))
            journal.append(call('prior'), b'prompt', b'response')
            code = '''import json, os, sqlite3, sys
from pathlib import Path
from consilium.core.pilot import PilotCall
from consilium.shell.pilot import PilotJournal
journal = PilotJournal(Path(sys.argv[1]), ('task',))
original = sqlite3.connect
class CrashConnection(sqlite3.Connection):
 def execute(self, sql, *args):
  result = super().execute(sql, *args)
  if sql.startswith('INSERT INTO calls'): os._exit(73)
  return result
sqlite3.connect = lambda *a, **k: original(*a, factory=CrashConnection, **k)
journal.append(PilotCall(**json.loads(sys.argv[2])), b'prompt', b'response')
'''
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'src'))
            result = subprocess.run([sys.executable, '-c', code, directory,
                json.dumps(asdict(call('interrupted', stage='SINGLE')))], env=env,
                capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 73, result.stderr.decode())
            self.assertEqual(journal.calls(), (call('prior'),))

    def test_digest_mismatch_does_not_register_an_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = PilotJournal(Path(directory), ('task',))
            with self.assertRaises(ValueError):
                journal.append(call('wrong'), b'changed', b'response')
            self.assertEqual(journal.calls(), ())

    def test_generation_packets_withhold_reference_answers_and_refuse_overwrite(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            argv = [sys.executable, str(root / 'tools/p06_pilot.py'), 'prepare', '--workspace', directory]
            result = subprocess.run(argv, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            packet = Path(directory) / 'GENERATION_TASKS.json'
            raw = packet.read_bytes()
            tasks = json.loads(raw)
            self.assertEqual(len(tasks), 8)
            self.assertTrue(all(set(t) == {'task_id', 'prompt'} for t in tasks))
            self.assertNotEqual(subprocess.run(argv, capture_output=True, timeout=10).returncode, 0)
            self.assertEqual(packet.read_bytes(), raw)

    def test_incomplete_pilot_cannot_emit_a_blinded_scoring_file(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(root / 'tools/p06_pilot.py'),
                'blind', '--workspace', directory], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((Path(directory) / 'BLINDED.json').exists())

    def test_definite_failure_and_linked_repair_consume_original_allowance(self):
        architect, final = protocol('SINGLE')
        failure = call('failed', stage='SINGLE', outcome='FAILED', failure_reason='Observed UI error')
        report = summarize((architect, failure, replace(final, repair_of='failed')), ('task',))
        self.assertEqual(report['failed_attempts'], 1)
        self.assertEqual(report['repair_attempts'], 1)
        row = report['per_task_method'][0]
        self.assertEqual((row['calls'], row['remaining_call_allowance']), (3, 3))
        self.assertTrue(row['protocol_complete'])

    def test_failure_without_success_never_counts_as_final_output(self):
        failed = call('failed', stage='SINGLE', outcome='FAILED', failure_reason='No answer arrived')
        report = summarize((protocol('SINGLE')[0], failed), ('task',))
        self.assertEqual(report['real_manual_final_outputs'], 0)
        self.assertEqual(report['unresolved_failure_groups'], 1)

    def test_unknown_delivery_blocks_resend_even_with_a_repair_label(self):
        unknown = call('ambiguous', stage='SINGLE', outcome='UNKNOWN', failure_reason='Delivery cannot be determined')
        before = (protocol('SINGLE')[0], unknown)
        self.assertEqual(summarize(before, ('task',))['unknown_attempts'], 1)
        for link in (None, 'ambiguous'):
            with self.subTest(link=link), self.assertRaises(ValueError):
                summarize(before + (replace(protocol('SINGLE')[-1], repair_of=link),), ('task',))

    def test_failed_attempt_cannot_be_skipped_or_repaired_by_another_model(self):
        failed = call('failed', stage='SINGLE', outcome='FAILED', failure_reason='Observed error')
        for changes in ({}, {'repair_of': 'absent'}, {'repair_of': 'failed', 'model_id': 'switched'},
                        {'repair_of': 'failed', 'provider': 'other-provider'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                summarize((protocol('SINGLE')[0], failed,
                    replace(protocol('SINGLE')[-1], **changes)), ('task',))

    def test_repair_chain_must_bind_latest_failed_attempt(self):
        first = call('first', stage='SINGLE', outcome='FAILED', failure_reason='First error')
        second = call('second', stage='SINGLE', outcome='FAILED', failure_reason='Second error', repair_of='first')
        start = (protocol('SINGLE')[0], first, second)
        repaired = replace(protocol('SINGLE')[-1], repair_of='second')
        self.assertEqual(summarize(start + (repaired,), ('task',))['repair_attempts'], 2)
        with self.assertRaises(ValueError):
            summarize(start + (replace(repaired, repair_of='first'),), ('task',))

    def test_multiround_failure_does_not_raise_the_six_call_ceiling(self):
        calls = protocol('REPEATED_SINGLE')
        failed = replace(calls[-1], call_id='failed', outcome='FAILED', final=False, failure_reason='Observed error')
        prior = calls[:-1] + (failed,)
        row = summarize(prior, ('task',))['per_task_method'][0]
        self.assertEqual(row['remaining_call_allowance'], 0)
        self.assertFalse(row['protocol_complete'])
        self.assertEqual(row['remaining_required_successes'], 1)
        self.assertFalse(row['call_budget_feasible'])
        self.assertEqual(row['completion_blocker'], 'ORIGINAL_CALL_CEILING')
        with self.assertRaises(ValueError):
            summarize(prior + (replace(calls[-1], repair_of='failed'),), ('task',))

    def test_architect_repair_exposes_impossible_completion_before_more_calls(self):
        architect = protocol('REPEATED_SINGLE')[0]
        failed = replace(architect, call_id='failed-architect', outcome='FAILED',
                         failure_reason='Invalid architect output', shared_architect_call_id=None)
        repaired = replace(architect, repair_of=failed.call_id)
        report = summarize((failed, repaired), ('task',))
        row = report['per_task_method'][0]
        self.assertEqual(row['remaining_call_allowance'], 4)
        self.assertEqual(row['remaining_required_successes'], 5)
        self.assertFalse(row['call_budget_feasible'])
        self.assertEqual(report['call_budget_blocked_groups'], 1)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertFalse(report['phase_accepted'])

    def test_single_repair_and_clean_multiround_keep_feasible_budgets(self):
        architect = protocol('SINGLE')[0]
        failed = replace(architect, call_id='failed-architect', outcome='FAILED',
                         failure_reason='Invalid architect output', shared_architect_call_id=None)
        report = summarize((failed, replace(architect, repair_of=failed.call_id)), ('task',))
        self.assertTrue(report['per_task_method'][0]['call_budget_feasible'])
        self.assertIsNone(report['per_task_method'][0]['completion_blocker'])
        clean = summarize(protocol('COUNCIL', 'other'), ('task',))
        self.assertEqual(clean['call_budget_blocked_groups'], 0)
        self.assertEqual(clean['per_task_method'][0]['remaining_required_successes'], 0)

    def test_failed_attempts_still_obey_output_and_time_ceilings(self):
        failed = call('failed', stage='SINGLE', outcome='FAILED', failure_reason='Partial output then error')
        for changes in ({'output_tokens': 2001}, {'elapsed_seconds': 601}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                summarize((replace(failed, **changes),), ('task',))

    def test_outcome_and_attempt_link_fields_reject_fabricated_combinations(self):
        for changes in ({'outcome': 'MAYBE'}, {'outcome': []}, {'outcome': 'FAILED'},
                        {'failure_reason': 'unexpected'}, {'repair_of': ''},
                        {'shared_architect_call_id': True}, {'prompt_sha256': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(call('one'), **changes)
        with self.assertRaises(ValueError):
            call('one', stage='SINGLE', shared_architect_call_id='not-architect')
        with self.assertRaises(ValueError):
            call('one', stage='SINGLE', outcome='FAILED', failure_reason='Error', final=True)

    def test_failure_at_a_foreign_protocol_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize((call('foreign', method='COUNCIL', stage='SINGLE',
                outcome='FAILED', failure_reason='Error'),), ('task',))

    def test_legacy_complete_calls_need_explicit_physical_architect_link(self):
        calls = protocol('SINGLE') + protocol('REPEATED_SINGLE') + protocol('COUNCIL', 'other')
        legacy = tuple(replace(c, shared_architect_call_id=None) for c in calls)
        report = summarize(legacy, ('task',))
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertFalse(report['shared_architect_links_complete'])

    def test_shared_architect_cannot_disagree_on_actual_time_or_usage(self):
        first = protocol('SINGLE')[0]
        second = protocol('COUNCIL', 'other')[0]
        for changes in ({'elapsed_seconds': 2}, {'input_tokens': 10}, {'origin': 'MOCK'},
                        {'shared_architect_call_id': 'a-different-call'}):
            changed = replace(second, **changes)
            if 'shared_architect_call_id' in changes:
                self.assertFalse(summarize((first, changed), ('task',))['shared_architect_links_complete'])
            else:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    summarize((first, changed), ('task',))

    def test_journal_reopens_failed_attempt_and_repair_without_losing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = PilotJournal(Path(directory), ('task',))
            failed = call('failed', stage='SINGLE', outcome='FAILED', failure_reason='Observed failure')
            for observation in (protocol('SINGLE')[0], failed):
                journal.append(observation, b'prompt', b'response')
            reopened = PilotJournal(Path(directory), ('task',))
            repaired = replace(protocol('SINGLE')[-1], repair_of='failed')
            reopened.append(repaired, b'prompt', b'response')
            self.assertEqual(reopened.calls(), (protocol('SINGLE')[0], failed, repaired))
            self.assertEqual(summarize(reopened.calls(), ('task',))['repair_attempts'], 1)


if __name__ == '__main__':
    unittest.main()
