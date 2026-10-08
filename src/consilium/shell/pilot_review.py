"""Immutable private review material, atomically registered with the pilot journal."""
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from consilium.core.pilot import PilotCall
from consilium.core.pilot_review import (
    blinded_material,
    decoded,
    digest,
    encoded,
    judge_references,
    validate_scores,
)
from consilium.shell.pilot import PilotJournal


class PilotReviewStore:
    def __init__(self, journal: PilotJournal):
        self.journal = journal
        with journal._connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS review_artifacts '
                '(name TEXT PRIMARY KEY, digest TEXT NOT NULL)')

    def _register(self, artifacts: dict[str, bytes], observation_sha256: str) -> None:
        hashes = {name: self.journal.objects.put(content) for name, content in artifacts.items()}
        with self.journal._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            rows = connection.execute('SELECT observation FROM calls ORDER BY sequence').fetchall()
            current = [asdict(PilotCall(**json.loads(row[0]))) for row in rows]
            if digest(encoded(current)) != observation_sha256:
                raise ValueError('Journal changed before review registration could commit')
            for name, sha in hashes.items():
                prior = connection.execute('SELECT digest FROM review_artifacts WHERE name=?', (name,)).fetchone()
                if prior and prior[0] != sha:
                    raise ValueError('A registered review artifact cannot be replaced')
                connection.execute('INSERT OR IGNORE INTO review_artifacts VALUES(?,?)', (name, sha))
            connection.commit()

    def _read(self, name: str) -> bytes:
        with self.journal._connect() as connection:
            row = connection.execute('SELECT digest FROM review_artifacts WHERE name=?', (name,)).fetchone()
        if row is None:
            raise ValueError('Review artifact has not been atomically registered')
        return self.journal.objects.read(row[0])

    def _export(self, name: str) -> None:
        content = self._read(name)
        target = self.journal.workspace / name
        if target.is_symlink():
            raise ValueError('Private review export cannot be a symlink')
        fd, pending = tempfile.mkstemp(dir=self.journal.workspace, prefix='review-pending-')
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(pending, target)
            except FileExistsError:
                if target.is_symlink() or target.read_bytes() != content:
                    raise ValueError('Existing private export differs from its frozen original') from None
        finally:
            Path(pending).unlink(missing_ok=True)

    def _material(self, plan: dict, dataset: bytes) -> dict[str, bytes]:
        calls = self.journal.calls()
        for call in calls:
            self.journal.objects.read(call.prompt_sha256)
            self.journal.objects.read(call.response_sha256)
        responses = {call.response_sha256: self.journal.objects.read(call.response_sha256)
                     for call in calls if call.final}
        packet, mapping, template = blinded_material(calls, plan, responses)
        return {'BLINDED.json': encoded(packet), 'PRIVATE_BLIND_MAP.json': encoded(mapping),
                'SCORING_TEMPLATE.json': encoded(template), 'JUDGE_REFERENCES.json': judge_references(plan, dataset)}

    def prepare(self, plan: dict, dataset: bytes) -> None:
        artifacts = self._material(plan, dataset)
        self._register(artifacts, json.loads(artifacts['BLINDED.json'])['observation_manifest_sha256'])
        for name in artifacts:
            self._export(name)

    def _validate_material(self, plan: dict, dataset: bytes) -> tuple[dict, dict]:
        for name, expected in self._material(plan, dataset).items():
            if self._read(name) != expected:
                raise ValueError('Frozen review material differs from the current journal or preregistration')
            if (self.journal.workspace / name).is_symlink() or (
                    self.journal.workspace / name).read_bytes() != expected:
                raise ValueError('Private review export was modified or not fully resumed')
        return json.loads(self._read('BLINDED.json')), json.loads(self._read('PRIVATE_BLIND_MAP.json'))

    def register_scores(self, content: bytes, plan: dict, dataset: bytes) -> dict:
        packet, mapping = self._validate_material(plan, dataset)
        report = validate_scores(decoded(content), packet, mapping)
        report['original_score_bytes_sha256'] = digest(content)
        self._register({'VALIDATED_SCORES.json': content, 'SCORE_REVIEW.json': encoded(report)},
                       packet['observation_manifest_sha256'])
        self._export('VALIDATED_SCORES.json')
        self._export('SCORE_REVIEW.json')
        return report

    def score_report(self, plan: dict, dataset: bytes) -> dict:
        packet, mapping = self._validate_material(plan, dataset)
        content = self._read('VALIDATED_SCORES.json')
        report = validate_scores(decoded(content), packet, mapping)
        report['original_score_bytes_sha256'] = digest(content)
        if self._read('SCORE_REVIEW.json') != encoded(report):
            raise ValueError('Registered score report differs from the exact validated score bytes')
        for name, expected in {'VALIDATED_SCORES.json': content, 'SCORE_REVIEW.json': encoded(report)}.items():
            target = self.journal.workspace / name
            if target.is_symlink() or target.read_bytes() != expected:
                raise ValueError('Registered score export was changed or has not fully resumed')
        return report
