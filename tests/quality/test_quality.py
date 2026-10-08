"""Independent invariants for approved reliability and traceability changes."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from hypothesis import given, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from consilium.adapters.mock import MockAdapter, Scenario
from consilium.core.contracts import PeerPoint, ReviewSpan
from consilium.core.evidence_provenance import EvidenceSource, primary_sources
from consilium.core.rubrics import get_rubric
from consilium.shell.evidence_store import EvidenceStore
from consilium.shell.private import ensure_public_payload, redact_diagnostic
from consilium.shell.runner import DurableRunner
from consilium.shell.storage import Conflict

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tests/council'), str(ROOT / 'tests/persistence'), str(ROOT / 'tools')]
import test_council as council_fixture
import test_ledger as ledger_fixture
import check_conformance
import check_transitions


class QualityTests(unittest.TestCase):
    @settings(max_examples=80, database=None, derandomize=True)
    @given(st.text(min_size=1).filter(lambda text: not any(0xD800 <= ord(c) <= 0xDFFF for c in text)))
    def test_unicode_span_binds_exact_bytes_and_rejects_modified_text(self, text):
        raw = text.encode('utf-8')
        digest = hashlib.sha256(raw).hexdigest()
        span = ReviewSpan(answer_text_hash=digest, start_byte=0, end_byte=len(raw), quote_hash=digest)
        span.validate_text(text)
        with self.assertRaises(ValueError):
            span.validate_text(text + 'changed')

    def test_multibyte_cut_and_forged_quote_are_rejected(self):
        raw = 'سلام'.encode()
        digest = hashlib.sha256(raw).hexdigest()
        for start, end, quote in ((1, 2, hashlib.sha256(raw[1:2]).hexdigest()), (0, 2, '0' * 64)):
            with self.subTest(start=start), self.assertRaises(ValueError):
                ReviewSpan(answer_text_hash=digest, start_byte=start, end_byte=end, quote_hash=quote).validate_text('سلام')

    def test_old_points_keep_the_original_serialization(self):
        old = {'verdict': 'ACCEPT', 'reference': 'text', 'reason': 'reason'}
        self.assertEqual(PeerPoint(**old).model_dump(mode='json'), old)

    def test_rubric_has_explicit_dimensions_without_truth_probability(self):
        rubric = get_rubric('research-review.v1')
        self.assertEqual(rubric.score({'usefulness': 9, 'accuracy': 6.5, 'user_constraints': 9, 'practicality': 8}), 8.22)
        for values in ({'usefulness': 9}, {k: True for k in rubric.dimensions}, {k: float('nan') for k in rubric.dimensions}):
            with self.assertRaises(ValueError):
                rubric.score(values)
        with self.assertRaises(ValueError):
            get_rubric('unregistered')

    def test_echoes_are_one_primary_source_and_cycles_are_errors(self):
        sources = {'run': EvidenceSource('run', 'EXECUTED'),
                   'GP': EvidenceSource('GP', 'REPORTED', ('run',)),
                   'GR': EvidenceSource('GR', 'REPORTED', ('GP',)),
                   'QW': EvidenceSource('QW', 'REPORTED', ('GR',))}
        self.assertEqual(primary_sources(('GP', 'GR', 'QW'), sources), frozenset({'run'}))
        sources['GP'] = EvidenceSource('GP', 'REPORTED', ('QW',))
        with self.assertRaises(ValueError):
            primary_sources(('QW',), sources)
        with self.assertRaises(ValueError):
            primary_sources(('missing',), {})

    def test_review_fixture_preserves_reported_count_and_single_lineage(self):
        fixture = json.loads((ROOT / 'fixtures/review_claims.json').read_text())
        sources = {r['identifier']: EvidenceSource(**{**r, 'parents': tuple(r['parents'])}) for r in fixture['sources']}
        self.assertEqual(primary_sources(('GP', 'GR', 'QW'), sources), frozenset(fixture['expected_primary_sources']))
        self.assertNotEqual(fixture['reported_test_count'], fixture['historical_verified_test_count'])
        self.assertFalse(fixture['model_superiority_claimed'])

    def test_provider_registry_preserves_scope_without_mock_live_claim(self):
        registry = json.loads((ROOT / 'PROVIDER_CAPABILITIES.json').read_text())
        self.assertEqual({p['id'] for p in registry['providers']}, {'openai', 'anthropic', 'google', 'deepseek', 'qwen'})
        self.assertTrue(all(set(p['modes']) == {'API', 'BROWSER', 'MANUAL'} for p in registry['providers']))
        self.assertTrue(all(v['live_verification'] == 'NOT_RUN' for p in registry['providers'] for v in p['modes'].values()))
        self.assertFalse(registry['mock']['certifies_live_providers'])

    def test_pilot_mock_or_missing_intermediates_never_certify_quality(self):
        from consilium.core.pilot import PilotCall, summarize
        args = dict(call_id='one', task_id='PILOT-001', method='SINGLE', provider='declared', model_id='model',
            prompt_sha256='a' * 64, response_sha256='b' * 64, origin='MOCK',
            elapsed_seconds=1, cost=0, stage='SINGLE', final=True)
        call = PilotCall(**args)
        self.assertEqual(summarize((call,), ('PILOT-001',))['real_manual_final_outputs'], 0)
        manual = PilotCall(**{**args, 'origin': 'MANUAL'})
        self.assertEqual(summarize((manual,), ('PILOT-001',))['real_manual_final_outputs'], 0)
        for changes in ({'cost': 1}, {'cost': True}, {'elapsed_seconds': float('nan')},
                        {'external_origin_verified': True}, {'output_tokens': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                PilotCall(**{**args, **changes})
        with self.assertRaises(ValueError):
            summarize((call, call), ('PILOT-001',))
        with self.assertRaises(ValueError):
            summarize((PilotCall(**{**args, 'output_tokens': 2401}),), ('PILOT-001',))

    def test_content_addressed_evidence_deduplicates_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(Path(directory))
            digest = store.put(b'exact\r\nbytes')
            self.assertEqual(store.put(b'exact\r\nbytes'), digest)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            self.assertEqual(store.read(digest), b'exact\r\nbytes')
            (Path(directory) / digest).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                store.read(digest)
            with self.assertRaises(ValueError):
                store.put(b'exact\r\nbytes')

    def test_diagnostic_redaction_copies_without_altering_canonical_data(self):
        raw = {'API-Key': 'secret-value', 'error': 'Bearer abc123; secret-value'}
        cleaned = redact_diagnostic(raw, ('secret-value',))
        self.assertEqual(raw['API-Key'], 'secret-value')
        self.assertNotIn('abc123', json.dumps(cleaned))
        self.assertNotIn('secret-value', json.dumps(cleaned))
        ensure_public_payload({'diagnostic': cleaned['error']}, ('secret-value',))

    def test_conformance_and_transition_projections_check_real_sources(self):
        self.assertEqual(check_conformance.validate(ROOT)['protected_requirements'], 30)
        check_transitions.validate(ROOT / 'transitions.yaml')
        bad = json.loads((ROOT / 'transitions.yaml').read_text())
        bad['operation_transitions'][0]['to'] = 'CONFIRMED'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                check_transitions.validate(path)

    def test_forged_review_span_cannot_become_confirmed_or_complete_round(self):
        case = council_fixture.CouncilCase()
        case.setUp()
        try:
            case.complete_round(); case.decide('CONTINUE'); case.start('REVIEW')
            request = case.prepare()
            contract = case.store.artifacts.get_contract(request.intent)
            data = json.loads(case.review_content(contract.targets))
            data['critiques'][0]['points'][0]['span'] = {'answer_text_hash': '0' * 64,
                'start_byte': 0, 'end_byte': 1, 'quote_hash': '0' * 64}
            plan = case.council.execute_mock(request, MockAdapter(response_content=json.dumps(data)), expected_revision=case.revision)
            self.assertEqual(plan.attempt.state.value, 'INVALID_RESPONSE')
            self.assertIsNone(case.store.ledger.canonical_result(request.intent.identity.logical_operation_id))
            with self.assertRaises(Conflict):
                case.council.seal_round(debate_id=case.debate.debate_id, expected_revision=case.revision)
        finally:
            case.tearDown()

    def test_review_aliases_balance_and_replay_preserves_seed_and_rubric(self):
        case = council_fixture.CouncilCase(); case.setUp()
        try:
            case.complete_round(); case.decide('CONTINUE'); case.start('REVIEW')
            first = case.prepare(case.pid[0]); second = case.prepare(case.pid[1])
            inputs = [json.loads(r.intent.frozen_input.messages[1].content) for r in (first, second)]
            mapping = [{s['source_hash']: s['author'] for s in data['sources']} for data in inputs]
            self.assertEqual(set(mapping[0]), set(mapping[1]))
            self.assertTrue(all(mapping[0][key] != mapping[1][key] for key in mapping[0]))
            self.assertEqual(inputs[0]['review_presentation']['seed'], inputs[1]['review_presentation']['seed'])
            self.assertEqual(inputs[0]['scoring_rubric']['id'], 'council-rubric.v1')
            case.reopen()
            self.assertEqual(case.store.ledger.get_attempt(first.intent.identity.attempt_id).intent, first.intent)
        finally:
            case.tearDown()

    def test_demo_requires_explicit_scripted_mode_and_never_overwrites(self):
        from consilium.shell.demo import run_demo
        with tempfile.TemporaryDirectory() as directory:
            with patch('builtins.input', return_value='no'), self.assertRaises(ValueError):
                run_demo(Path(directory) / 'declined')
            destination = Path(directory) / 'approved'
            result = run_demo(destination, scripted=True)
            self.assertEqual(result['paid_calls'], 0)
            self.assertTrue(result['restart_exact'])
            self.assertGreater(result['preserved_objections'], 0)
            with self.assertRaises(FileExistsError):
                run_demo(destination, scripted=True)


class DurableDispatchMachine(RuleBasedStateMachine):
    """Oracle tracks authorization and external call count, not TRANSITIONS."""
    def __init__(self):
        super().__init__()
        self.case = ledger_fixture.LedgerTests(); self.case.setUp()
        self.started = False
        self.invalidated = False
        self.external_calls = 0

    @rule(scenario=st.sampled_from([Scenario.SUCCESS, Scenario.TIMEOUT_AFTER_SEND, Scenario.PARTIAL]))
    def execute(self, scenario):
        adapter = MockAdapter(scenario=scenario)
        permitted = not self.started and not self.invalidated
        try:
            DurableRunner(self.case.store).execute(self.case.request, adapter, expected_revision=self.case.revision)
            assert permitted, 'An old or dispatched authorization was reused'
            self.started = True
        except Conflict:
            assert not permitted, 'A currently permitted first dispatch was refused'
        self.external_calls += len(adapter.calls)
        assert len(adapter.calls) == int(permitted)

    @rule()
    def reopen(self):
        before = self.case.store.export_debate(self.case.debate.debate_id)
        self.case.reopen()
        assert self.case.store.export_debate(self.case.debate.debate_id) == before

    @rule()
    def recover_without_sending(self):
        before = self.case.revision
        plan = self.case.store.ledger.resume(self.case.attempt)
        assert plan.automatic_send is False
        assert self.case.revision == before

    @rule()
    def replace_binding(self):
        if not self.invalidated:
            self.case.replace_binding()
            self.invalidated = True

    @invariant()
    def one_authorization_never_dispatches_twice(self):
        assert self.external_calls <= 1

    def teardown(self):
        self.case.tearDown()


TestDurableDispatch = DurableDispatchMachine.TestCase
TestDurableDispatch.settings = settings(max_examples=30, stateful_step_count=20, deadline=None,
                                       database=None, derandomize=True)
