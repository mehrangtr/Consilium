#!/usr/bin/env python3
"""Bounded lint/type/coverage checks with an explicit, limited scope."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import qualityctl as q
from development_progress import milestone

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ['src/consilium/core/evidence_provenance.py', 'src/consilium/core/rubrics.py',
           'src/consilium/shell/evidence_store.py']


def main():
    before = q.source_digest(ROOT)
    folder = ROOT / 'evidence/quality-tooling'; folder.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), COVERAGE_FILE=str(folder / '.coverage'))
    commands = [
        ('lint', [sys.executable, '-m', 'ruff', 'check', '--no-cache', *TARGETS,
                  'src/consilium/core/pilot.py', 'src/consilium/core/pilot_review.py',
                  'src/consilium/shell/pilot.py', 'src/consilium/shell/pilot_review.py',
                  'tools/p06_pilot.py', 'tools/check_p06.py',
                  'src/consilium/core/output_contract.py', 'src/consilium/shell/council_export.py',
                  'tools/p07_output.py', 'tools/render_p07_visual.py', 'tools/check_p07_evidence.py', 'tests/council/test_output.py', 'tests/council/output_crash_worker.py',
                  'src/consilium/core/analyzers.py', 'src/consilium/core/council_repository.py',
                  'src/consilium/shell/council_repository.py', 'src/consilium/shell/demo.py', 'src/consilium/__main__.py']),
        ('types', [sys.executable, '-m', 'mypy', '--strict', '--follow-imports=skip', *TARGETS]),
        ('conformance', [sys.executable, 'tools/check_conformance.py']),
        ('transitions', [sys.executable, 'tools/check_transitions.py']),
        ('properties_and_regressions', [sys.executable, '-m', 'coverage', 'run', '--branch',
            '--source=consilium.core.evidence_provenance,consilium.core.rubrics,consilium.shell.evidence_store', 'tools/run_quality_tests.py']),
        ('targeted_coverage', [sys.executable, '-m', 'coverage', 'report', '--fail-under=70']),
    ]
    results = []
    for name, argv in commands:
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=ROOT, env=environment, capture_output=True, timeout=45, stdin=subprocess.DEVNULL)
            (folder / (name + '.log')).write_bytes(proc.stdout + proc.stderr)
            row = {'id': name, 'status': 'PASS' if proc.returncode == 0 else 'FAIL', 'returncode': proc.returncode}
            if proc.returncode:
                print((proc.stdout + proc.stderr).decode('utf-8', errors='replace'))
        except (OSError, subprocess.TimeoutExpired) as exc:
            row = {'id': name, 'status': 'FAIL', 'error': type(exc).__name__}
        row['elapsed_seconds'] = round(time.monotonic() - started, 3)
        results.append(row); milestone('quality_' + name + '_finished')
    after = q.source_digest(ROOT)
    report = {'scope': 'TARGETED_DEV_QUALITY_NOT_FULL_STATIC_VERIFICATION',
        'status': 'PASS' if before == after and all(r['status'] == 'PASS' for r in results) else 'FAIL',
        'source_digest_before': before, 'source_digest_after': after, 'checks': results,
        'strict_type_targets': TARGETS, 'coverage_targets': TARGETS, 'coverage_minimum': 70,
        'whole_product_type_checked': False}
    (folder / 'RUN.json').write_bytes(q.encoded(report)); print(json.dumps(report))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
