"""Negative coverage of the functional exit; fixtures are not quality evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_p06_functional import validate_groups


class FunctionalExitTests(unittest.TestCase):
    def summary(self):
        return {'per_task_method': [{'task_id': 'PILOT-001', 'method': m,
            'protocol_complete': True, 'unresolved_outcome': None}
            for m in ('SINGLE', 'COUNCIL', 'REPEATED_SINGLE')]}

    def test_absent_real_groups_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_groups({'per_task_method': []}, ['PILOT-001'])

    def test_two_methods_do_not_substitute_for_three(self):
        value = self.summary()
        value['per_task_method'].pop()
        with self.assertRaises(ValueError):
            validate_groups(value, ['PILOT-001'])

    def test_incomplete_rounds_are_rejected(self):
        value = self.summary()
        value['per_task_method'][1]['protocol_complete'] = False
        with self.assertRaises(ValueError):
            validate_groups(value, ['PILOT-001'])

    def test_unknown_send_prevents_acceptance(self):
        value = self.summary()
        value['per_task_method'][1]['unresolved_outcome'] = 'UNKNOWN'
        with self.assertRaises(ValueError):
            validate_groups(value, ['PILOT-001'])

    def test_different_task_cannot_replace_the_requested_task(self):
        with self.assertRaises(ValueError):
            validate_groups(self.summary(), ['PILOT-003'])
