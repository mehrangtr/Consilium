import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from consilium.core.pilot import PilotCall
from consilium.core.pilot_review import digest
from consilium.core.pilot_review import encoded
from consilium.core.pilot_three_stage import (
    ThreeStageCall, ThreeStagePlan, protocol_steps, summarize_three_stage,
)
from consilium.shell.pilot_three_stage import ThreeStageJournal


class ThreeStageTests(unittest.TestCase):
    def setUp(self):
        self.plan = ThreeStagePlan(tuple(f'T{i}' for i in range(6)), 'selected', 'A', 'peer', 'B', 'a' * 64)

    def obs(self, stage='ARCHITECT', number=0, slot=0, peers=(), method='COUNCIL', suffix='', **changes):
        peer = method == 'COUNCIL' and slot == 1
        call = PilotCall('call' + suffix, 'T0', method, 'peer' if peer else 'selected',
            digest(b'prompt'), digest(b'response'), 'MANUAL', 1, 0, stage,
            'B' if peer else 'A', final=stage in ('SINGLE', 'SYNTHESIS'),
            shared_architect_call_id='physical-architect' if stage == 'ARCHITECT' else None)
        return replace(ThreeStageCall(call, self.plan.sha256, number, slot,
            ('c' if peer else 'b') * 64, 'd' * 64, peers), **changes)

    def complete_group(self):
        group = []
        for index, (stage, number, slot) in enumerate(protocol_steps('COUNCIL')):
            peers = tuple(o.call.call_id for o in group if o.round_number == number - 1) if number >= 2 else ()
            group.append(self.obs(stage, number, slot, peers, suffix=str(index)))
        return tuple(group)

    def test_three_rounds_required_before_judgment(self):
        group = self.complete_group()
        with self.assertRaises(ValueError):
            summarize_three_stage(group[:5] + (group[-1],), self.plan)
        report = summarize_three_stage(group, self.plan)
        self.assertEqual(report['real_manual_final_outputs'], 1)
        self.assertFalse(report['phase_accepted'])
        self.assertEqual(report['required_final_outputs'], 18)

    def test_missing_peer_rejected(self):
        group = self.complete_group()
        with self.assertRaises(ValueError):
            summarize_three_stage(group[:3] + (replace(group[3], peer_call_ids=()),), self.plan)

    def test_changed_conversation_or_account_rejected(self):
        group = self.complete_group()
        for field in ('conversation_sha256', 'account_binding_sha256'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                summarize_three_stage(group[:3] + (replace(group[3], **{field: 'e' * 64}),), self.plan)

    def test_wrong_judge_rejected(self):
        group = self.complete_group()
        with self.assertRaises(ValueError):
            summarize_three_stage(group[:-1] + (replace(group[-1], call=replace(
                group[-1].call, provider='peer', model_id='B')),), self.plan)

    def test_unknown_delivery_does_not_authorize_repair(self):
        first = self.obs()
        failed = replace(first, call=replace(first.call, outcome='UNKNOWN', failure_reason='timeout'))
        retry = replace(first, call=replace(first.call, call_id='retry', repair_of='call'))
        with self.assertRaises(ValueError):
            summarize_three_stage((failed, retry), self.plan)

    def test_definite_failed_attempt_consumes_budget(self):
        first = self.obs()
        failed = replace(first, call=replace(first.call, outcome='FAILED', failure_reason='invalid'))
        retry = replace(first, call=replace(first.call, call_id='retry', repair_of='call',
            shared_architect_call_id='physical-repair'))
        report = summarize_three_stage((failed, retry), self.plan)
        self.assertEqual(report['unique_model_attempts'], 2)
        self.assertEqual(report['per_task_method'][0]['remaining_call_allowance'], 8)

    def test_legacy_protocol_and_mock_final_not_promoted(self):
        with self.assertRaises(ValueError):
            summarize_three_stage((replace(self.obs(), plan_sha256='f' * 64),), self.plan)
        group = self.complete_group()
        mocked = group[:-1] + (replace(group[-1], call=replace(group[-1].call, origin='MOCK')),)
        self.assertEqual(summarize_three_stage(mocked, self.plan)['real_manual_final_outputs'], 0)

    def test_immutable_plan_and_exact_bytes_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            journal = ThreeStageJournal(workspace, self.plan)
            journal.append(self.obs(), b'prompt', b'response')
            self.assertEqual(len(ThreeStageJournal(workspace, self.plan).calls()), 1)
            with self.assertRaises(ValueError):
                ThreeStageJournal(workspace, replace(self.plan, selected_model='changed'))
            with self.assertRaises(ValueError):
                journal.append(replace(self.obs(), call=replace(self.obs().call, call_id='other')), b'changed', b'response')
            self.assertEqual(len(journal.calls()), 1)

    def test_original_workspace_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'pilot.sqlite3').touch()
            with self.assertRaises(ValueError):
                ThreeStageJournal(Path(tmp), self.plan)

    def test_shared_architect_batch_is_atomic_and_review_freezes_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = ThreeStageJournal(Path(tmp), self.plan)
            first = self.obs()
            second = replace(first, call=replace(first.call, call_id='single-arch', method='SINGLE'))
            third = replace(first, call=replace(first.call, call_id='repeat-arch', method='REPEATED_SINGLE'))
            invalid = replace(third, conversation_sha256='e' * 64)
            with self.assertRaises(ValueError):
                journal.append_batch((first, second, invalid), b'prompt', b'response')
            self.assertEqual(journal.calls(), ())
            journal.append_batch((first, second, third), b'prompt', b'response')
            self.assertEqual(len(journal.calls()), 3)
            with journal._connect() as conn:
                conn.execute('CREATE TABLE review_artifacts (content TEXT)')
                conn.execute("INSERT INTO review_artifacts VALUES('frozen')")
            next_call = self.obs('SINGLE', 1, 0, method='SINGLE', suffix='next')
            with self.assertRaises(ValueError):
                journal.append(next_call, b'prompt', b'response')
            self.assertEqual(len(journal.calls()), 3)

    def test_judge_requires_both_final_round_opinions(self):
        group = self.complete_group()
        with self.assertRaises(ValueError):
            summarize_three_stage(group[:-1] + (replace(group[-1],
                peer_call_ids=group[-1].peer_call_ids[:1]),), self.plan)

    def test_timing_amendment_preserves_original_and_rejects_replacement(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            journal = ThreeStageJournal(Path(tmp), self.plan)
            obs = self.obs()
            journal.append(obs, b'prompt', b'response')
            start = encoded({'started_utc': '2026-10-09T18:00:00+00:00'})
            capture = encoded({'response': 'response', 'elapsed_seconds': 1})
            evidence = {'physical_call_id': 'physical-architect',
                'started_utc': '2026-10-09T18:00:00+00:00',
                'captured_utc': '2026-10-09T18:00:10+00:00',
                'metric': 'HOST_INTENT_TO_CAPTURE_FILE_MTIME_INCLUDES_OPERATOR_OVERHEAD',
                'start_record_sha256': digest(start), 'capture_record_sha256': digest(capture)}
            journal.correct_timing(evidence, start, capture)
            self.assertEqual(journal.calls()[0].call.elapsed_seconds, 10)
            with journal._connect() as conn:
                raw = json.loads(conn.execute('SELECT content FROM calls').fetchone()[0])
            self.assertEqual(raw['call']['elapsed_seconds'], 1)
            with self.assertRaises(ValueError):
                journal.correct_timing({**evidence, 'captured_utc': '2026-10-09T18:00:11+00:00'}, start, capture)

    def test_timing_amendment_requires_exact_sources_and_ordered_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = ThreeStageJournal(Path(tmp), self.plan)
            journal.append(self.obs(), b'prompt', b'response')
            start = encoded({'started_utc': '2026-10-09T18:00:00+00:00'})
            evidence = {'physical_call_id': 'physical-architect',
                'started_utc': '2026-10-09T18:00:00+00:00',
                'captured_utc': '2026-10-09T17:00:00+00:00',
                'metric': 'HOST_INTENT_TO_CAPTURE_FILE_MTIME_INCLUDES_OPERATOR_OVERHEAD',
                'start_record_sha256': digest(start), 'capture_record_sha256': digest(b'capture')}
            with self.assertRaises(ValueError):
                journal.correct_timing(evidence, start, b'capture')
            with self.assertRaises(ValueError):
                journal.correct_timing({**evidence, 'captured_utc': '2026-10-09T18:00:10+00:00'}, b'wrong', b'capture')


if __name__ == '__main__':
    unittest.main()
