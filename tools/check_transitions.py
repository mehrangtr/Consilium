#!/usr/bin/env python3
"""Check a readable projection against the single trusted runtime table."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from consilium.core.operation_states import TRANSITIONS


def validate(path: Path) -> None:
    specification = json.loads(path.read_text())
    expected = {(state.value, event, target.value) for state, events in TRANSITIONS.items() for event, target in events.items()}
    actual = {(r['from'], r['event'], r['to']) for r in specification['operation_transitions']}
    if expected != actual or len(actual) != len(specification['operation_transitions']):
        raise ValueError('Transition projection drifted from trusted runtime code')
    if specification['recovery_automatic_send'] is not False or specification['recommendation_authorizes_round'] is not False:
        raise ValueError('Projection cannot grant sending or user authority')
    if any(r['guard'] not in {'PREPARED_REVISION_AND_BINDING', 'SENT_ATTEMPT_IDENTITY', 'STORED_SCHEMA_VALIDATION', 'VALIDATED_CURRENT_BINDING'} for r in specification['operation_transitions']):
        raise ValueError('Only named, trusted-code guards are allowed')


if __name__ == '__main__':
    validate(ROOT / 'transitions.yaml')
    print('Transition projection: PASS (runtime guards remain in trusted code)')
