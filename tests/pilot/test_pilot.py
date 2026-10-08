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
    return PilotCall(call_id=identifier, task_id='task', method=method, provider='declared',
        model_id=model, prompt_sha256=hashlib.sha256(b'prompt').hexdigest(),
        response_sha256=hashlib.sha256(b'response').hexdigest(), origin=origin,
        elapsed_seconds=1, cost=0, stage=stage, final=stage in {'SINGLE', 'SYNTHESIS'}, **kw)


def protocol(method, second_model='baseline'):
    stages = ['ARCHITECT', 'SINGLE'] if method == 'SINGLE' else [
        'ARCHITECT', 'INDEPENDENT', 'INDEPENDENT', 'REVIEW', 'REVIEW', 'SYNTHESIS']
    return tuple(call(method + str(i), method, stage,
        second_model if i in {2, 4} else 'baseline') for i, stage in enumerate(stages))


class PilotTests(unittest.TestCase):
    def test_complete_three_protocols_are_ready_but_never_accepted(self):
        calls = protocol('SINGLE') + protocol('REPEATED_SINGLE') + protocol('COUNCIL', 'other')
        report = summarize(calls, ('task',))
        self.assertEqual(report['status'], 'READY_FOR_BLINDED_REVIEW')
        self.assertEqual(report['real_manual_final_outputs'], 3)
        self.assertEqual(report['recorded_calls'], 14)
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


if __name__ == '__main__':
    unittest.main()
