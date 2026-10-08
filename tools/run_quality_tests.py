#!/usr/bin/env python3
"""Fresh source-bound tests for the approved improvements."""
import datetime as dt
import json
from pathlib import Path
import platform
import sys
import unittest
import xml.etree.ElementTree as ET

import qualityctl as q
from run_architect_tests import RecordingResult

ROOT = Path(__file__).resolve().parents[1]


def main():
    before = q.source_digest(ROOT)
    sys.path.insert(0, str(ROOT / 'src'))
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests/quality'))
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    after = q.source_digest(ROOT)
    counts = {'tests': len(result.rows), **{field: sum(r['kind'] == kind for r in result.rows)
        for field, kind in [('failures', 'failure'), ('errors', 'error'), ('skipped', 'skipped')]}}
    passed = result.wasSuccessful() and counts['tests'] > 0 and before == after and not any(counts[k] for k in ('failures', 'errors', 'skipped'))
    report = {'scope': 'APPROVED_QUALITY_IMPROVEMENTS_OFFLINE_NOT_MODEL_QUALITY', 'status': 'PASS' if passed else 'FAIL',
        'source_digest_before': before, 'source_digest_after': after, 'counts': counts,
        'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'host': {'system': platform.system(), 'python': platform.python_version()},
        'live_provider_calls': 0, 'property_testing': {'dispatch_sequences': 30, 'max_steps_each': 20,
            'unicode_span_examples': 80, 'scope': 'BOUNDED_GENERATED_EXAMPLES_NOT_PROOF'},
        'cases': [{'id': r['id'], 'status': r['kind'].upper() if r['kind'] else 'PASS'} for r in result.rows]}
    folder = ROOT / 'evidence/quality-tests'; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'RUN.json').write_bytes(q.encoded(report))
    xml = ET.Element('testsuite', **{k: str(v) for k, v in counts.items()})
    for row in result.rows:
        case = ET.SubElement(xml, 'testcase', name=row['id'])
        if row['kind']:
            ET.SubElement(case, row['kind']).text = '\n'.join(row['details'])
    ET.ElementTree(xml).write(folder / 'JUNIT.xml', encoding='utf-8', xml_declaration=True)
    print(json.dumps({k: report[k] for k in ('scope', 'status', 'counts')}))
    return int(not passed)


if __name__ == '__main__':
    raise SystemExit(main())
