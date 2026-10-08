"""Source-bound P06 accounting tests, with no generated model-quality claims."""
from pathlib import Path
import sys

import qualityctl as q
import run_council_tests as runner

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Reuse the report format and recorder, while keeping a distinct suite path.
    import datetime as dt
    import platform
    import unittest
    import xml.etree.ElementTree as ET
    before = q.source_digest(ROOT)
    sys.path.insert(0, str(ROOT / 'src'))
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests/pilot'))
    result = unittest.TextTestRunner(verbosity=2, resultclass=runner.RecordingResult).run(suite)
    counts = {'tests': len(result.rows), **{field: sum(r['kind'] == kind for r in result.rows)
        for field, kind in [('failures', 'failure'), ('errors', 'error'), ('skipped', 'skipped')]}}
    after = q.source_digest(ROOT)
    passed = result.wasSuccessful() and counts['tests'] > 0 and before == after and not any(counts[k] for k in ('failures', 'errors', 'skipped'))
    report = {'phase': 'P06', 'scope': 'OFFLINE_PILOT_ACCOUNTING_NOT_MODEL_QUALITY',
        'status': 'PASS' if passed else 'FAIL', 'counts': counts,
        'source_digest_before': before, 'source_digest_after': after,
        'host': {'system': platform.system(), 'python': platform.python_version()},
        'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'real_model_runs': 0, 'phase_accepted': False}
    folder = ROOT / 'evidence/pilot-tests'; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'RUN.json').write_bytes(q.encoded(report))
    xml = ET.Element('testsuite', **{k: str(v) for k, v in counts.items()})
    for row in result.rows:
        case = ET.SubElement(xml, 'testcase', name=row['id'])
        if row['kind']:
            ET.SubElement(case, row['kind']).text = '\n'.join(row['details'])
    ET.ElementTree(xml).write(folder / 'JUNIT.xml', encoding='utf-8', xml_declaration=True)
    print(q.encoded(report).decode())
    return int(not passed)


if __name__ == '__main__':
    raise SystemExit(main())
