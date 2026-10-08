#!/usr/bin/env python3
"""Executable traceability, not a substitute for final product acceptance."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate(root: Path) -> dict:
    manifest = json.loads((root / 'governance/PROJECTION.json').read_text())
    package = root / manifest['package']
    if sha(package.read_bytes()) != manifest['package_sha256']:
        raise ValueError('Protected governance package changed')
    with zipfile.ZipFile(package) as archive:
        for projection in manifest['files']:
            canonical = archive.read(projection['member'])
            if sha(canonical) != projection['sha256'] or (root / projection['path']).read_bytes() != canonical:
                raise ValueError('Protected projection differs from its canonical package')
    mapping = json.loads((root / 'CONFORMANCE_MAP.yaml').read_text())
    rows = mapping['requirements']
    if {r['id'] for r in rows} != {f'UR-{i:03}' for i in range(1, 31)} or len(rows) != 30:
        raise ValueError('Traceability must cover exactly the thirty protected requirements')
    for row in rows:
        if (row['protection'] != 'LOCKED' or row['contract'] not in {'PRESENT', 'PARTIAL', 'MISSING'}
                or row['implementation'] not in {'IMPLEMENTED', 'PARTIAL', 'MISSING', 'UNVERIFIED'}
                or row['verification'] not in {'PASS', 'FAIL', 'NOT_RUN'}):
            raise ValueError('Invalid four-dimensional conformance status')
        for path in row['code']:
            candidate = (root / path).resolve()
            if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
                raise ValueError('Missing or outside-root implementation reference')
        for test in row['tests']:
            path, _, symbol = test.partition('::')
            candidate = (root / path).resolve()
            if (not candidate.is_relative_to(root.resolve()) or not candidate.is_file()
                    or not symbol or ('def ' + symbol + '(') not in candidate.read_text()):
                raise ValueError('Missing test selector')
        for reference in row.get('historical_evidence', []):
            if sha((root / reference['path']).read_bytes()) != reference['sha256']:
                raise ValueError('Historical evidence bytes changed')
        if row['verification'] == 'PASS':
            # Final V1 results need a separate source-bound acceptance; this
            # initial registry deliberately does not provide that authority.
            raise ValueError('Final PASS requires the future P13 conformance verifier')
    return {'scope': 'TRACEABILITY_INTEGRITY_NOT_FINAL_V1_VERIFICATION', 'status': 'PASS',
            'protected_requirements': len(rows), 'final_verified': 0,
            'implementation': dict(Counter(r['implementation'] for r in rows)),
            'verification': dict(Counter(r['verification'] for r in rows))}


def main() -> int:
    report = validate(ROOT)
    folder = ROOT / 'evidence/conformance'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'DASHBOARD.json').write_text(json.dumps(report, indent=2) + '\n')
    rows = json.loads((ROOT / 'CONFORMANCE_MAP.yaml').read_text())['requirements']
    lines = ['# Conformance dashboard', '', 'Generated from CONFORMANCE_MAP.yaml. Historical phase acceptance is not current final V1 verification.', '',
             '| Requirement | Protection | Contract | Implementation | Final verification |', '|---|---|---|---|---|']
    lines.extend(f"| {r['id']} | {r['protection']} | {r['contract']} | {r['implementation']} | {r['verification']} |" for r in rows)
    (folder / 'DASHBOARD.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
