"""Small offline demonstration using the product pipeline, not test fixtures."""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from consilium.adapters.mock import MockAdapter
from consilium.core.contracts import (
    ConnectionSpec,
    DebateSpec,
    OperationIdentity,
    UserDecision,
)
from consilium.core.question_contracts import ArchitectProposal, QuestionSnapshot
from consilium.shell.council_export import export_council
from consilium.shell.evidence_store import EvidenceStore
from consilium.shell.storage import SQLiteStore


def run_demo(output: Path | None = None, *, scripted: bool = False) -> dict:
    destination = Path(tempfile.mkdtemp(prefix='consilium-demo-')) if output is None else output.resolve()
    if output is not None:
        destination.mkdir(parents=True, exist_ok=False)
    actor = 'EXPLICIT_SCRIPTED_DEMO_USER' if scripted else 'INTERACTIVE_DEMO_USER'
    started = time.monotonic()
    decisions = []

    def confirm(label: str) -> None:
        if not scripted and input(label + ' [yes/no]: ').strip().lower() != 'yes':
            raise ValueError('Demo stopped by the user; local files are retained')
        decisions.append({'action': label, 'origin': 'SCRIPTED_DEMO' if scripted else 'USER_INPUT'})

    with SQLiteStore(destination / 'demo.sqlite3') as store:
        participants = (uuid4(), uuid4())
        debate = DebateSpec(debate_id=uuid4(), participant_ids=participants,
            original_request='Compare two free research methods and preserve uncertainty.',
            constraints=('No paid calls', 'Preserve minority objections'))
        store.create_debate(debate)
        snapshot = QuestionSnapshot.from_debate(debate)
        proposal = ArchitectProposal(snapshot_hash=snapshot.content_hash, proposal_version=1,
            optimized_request=debate.original_request, constraints_exact=debate.constraints,
            constraint_coverage=(0, 1), assumptions=(), visible_changes=(), origin='MOCK')
        store.questions.record_proposal(debate.debate_id, proposal, expected_revision=0)
        confirm('Adopt the synthetic question')
        store.questions.approve_proposal(debate.debate_id, proposal_hash=proposal.content_hash,
            user_action_id=uuid4(), actor=actor, confirmed=True, expected_revision=0)
        def revision():
            return store.checkpoint(debate.debate_id).revision
        for participant in participants:
            store.bind_connection(debate.debate_id, participant,
                ConnectionSpec(connection_id=uuid4(), provider_id='mock', model_id='mock-v1', mode='API'),
                expected_revision=revision(), expected_connection_revision=None)
        def decide(kind):
            confirm('Authorize ' + kind)
            spec = store.council.current_round(debate.debate_id)
            store.council.decide(UserDecision(decision_id=uuid4(), debate_id=debate.debate_id,
                round_id=spec.round_id, expected_revision=revision(), kind=kind), actor=actor, confirmed=True)
        def submit(participant, answer=None):
            request = store.council.prepare_mock(debate_id=debate.debate_id, participant_id=participant,
                identity=OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
                expected_revision=revision(), user_action_id=uuid4(), actor=actor, confirmed=True)
            contract = store.artifacts.get_contract(request.intent)
            if contract.kind == 'CRITIQUES':
                data = json.loads(request.intent.frozen_input.messages[1].content)
                by_hash = {s['source_hash']: s for s in data['sources'] if s['kind'] == 'ANSWER'}
                critiques = []
                for target in contract.targets:
                    raw = by_hash[target.source_hash]['content'].encode('utf-8')
                    critiques.append({'target_alias': target.alias, 'score': 6,
                        'scoring_reason': 'Synthetic rubric example: evidence 4, reasoning 8, constraints 8, coverage 6; rounded score 6.',
                        'points': [{'verdict': 'PARTIALLY_ACCEPT', 'reference': 'Complete answer',
                            'reason': 'The independent evidence gap remains unresolved.',
                            'span': {'answer_text_hash': hashlib.sha256(raw).hexdigest(), 'start_byte': 0,
                                'end_byte': len(raw), 'quote_hash': hashlib.sha256(raw).hexdigest()}}],
                        'strengths': ['Free approach'], 'weaknesses': ['Missing independent evidence']})
                wire = {'schema_version': 1, 'critiques': critiques}
            else:
                wire = {'schema_version': 1, 'answer': answer or (
                    'Method A may be useful.' if participant == participants[0]
                    else 'Method B deserves attention; independent evidence is missing.')}
            store.council.execute_mock(request, MockAdapter(response_content=json.dumps(wire)), expected_revision=revision())
        for kind in ('INDEPENDENT', 'REVIEW'):
            if kind == 'REVIEW':
                decide('CONTINUE')
            store.council.start_round(debate_id=debate.debate_id, round_id=uuid4(), kind=kind,
                expected_revision=revision())
            for participant in participants:
                submit(participant)
            store.council.seal_round(debate_id=debate.debate_id, expected_revision=revision())
            export_council(store, debate.debate_id, destination / 'exports')
        decide('FINISH')
        confirm('Select participant A as the synthetic judge')
        selected = store.council.select_judge(debate_id=debate.debate_id, participant_id=participants[0],
            round_id=uuid4(), expected_revision=revision(), user_action_id=uuid4(), actor=actor, confirmed=True)
        submit(selected.participant_id, json.dumps({'schema_version': 1, 'conclusion': 'Compare both methods in a real pilot.',
            'evidence': ['Synthetic example only'], 'uncertainty': ['No live model evidence'],
            'unresolved_issues': ['Independent evidence gap'], 'dissent': ['Method B deserves attention'],
            'agreement_is_truth_probability': False}))
        final = store.council.finalize(debate_id=debate.debate_id, expected_revision=revision())
        exported = export_council(store, debate.debate_id, destination / 'exports')
        canonical = store.export_debate(debate.debate_id)
    with SQLiteStore(destination / 'demo.sqlite3') as reopened:
        if reopened.export_debate(debate.debate_id) != canonical:
            raise ValueError('Restart changed canonical state')
    receipt = {'scope': 'SCRIPTED_MOCK_DEMO' if scripted else 'INTERACTIVE_MOCK_DEMO',
        'live_provider_calls': 0, 'paid_calls': 0, 'elapsed_seconds': round(time.monotonic() - started, 3),
        'restart_exact': True, 'preserved_objections': len(final.preserved_objections),
        'decisions': decisions, 'export': str(exported), 'output': str(destination)}
    raw = json.dumps(receipt, sort_keys=True, indent=2).encode()
    digest = EvidenceStore(destination / 'objects').put(raw)
    (destination / 'RECEIPT.json').write_text(json.dumps({'sha256': digest, 'scope': receipt['scope']}) + '\n')
    return receipt
