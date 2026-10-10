"""Plan-bound append-only journal, separate from the original pilot database."""
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from consilium.core.pilot import PilotCall
from consilium.core.pilot_review import digest, encoded
from consilium.core.pilot_three_stage import (
    ThreeStageCall,
    ThreeStagePlan,
    summarize_three_stage,
)
from consilium.shell.evidence_store import EvidenceStore


class ThreeStageJournal:
    def __init__(self, workspace: Path, plan: ThreeStagePlan):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        if (self.workspace / 'pilot.sqlite3').exists() or (self.workspace / 'CALLS.json').exists():
            raise ValueError('An original pilot workspace cannot become a new protocol')
        self.database = self.workspace / 'three-stage.sqlite3'
        self.objects = EvidenceStore(self.workspace / 'objects')
        self.plan = plan
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE IF NOT EXISTS plan (id INTEGER PRIMARY KEY CHECK(id=1), content BLOB NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS calls (sequence INTEGER PRIMARY KEY, call_id TEXT UNIQUE NOT NULL, content TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS timing_corrections '
                '(call_id TEXT PRIMARY KEY REFERENCES calls(call_id), original_sha256 TEXT NOT NULL, '
                'elapsed_seconds REAL NOT NULL, evidence_sha256 TEXT NOT NULL)')
            content = encoded(asdict(plan))
            previous = conn.execute('SELECT content FROM plan WHERE id=1').fetchone()
            if previous and previous[0] != content:
                raise ValueError('Registered plan cannot be changed after journal creation')
            conn.execute('INSERT OR IGNORE INTO plan VALUES(1,?)', (content,))

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.database, timeout=5)
        try:
            conn.execute('PRAGMA synchronous=FULL')
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _decode(rows) -> tuple[ThreeStageCall, ...]:
        values = []
        for row in rows:
            value = json.loads(row[0])
            value['call'] = PilotCall(**value['call'])
            value['peer_call_ids'] = tuple(value['peer_call_ids'])
            values.append(ThreeStageCall(**value))
        return tuple(values)

    def calls(self) -> tuple[ThreeStageCall, ...]:
        with self._connect() as conn:
            values = self._project(conn)
        for obs in values:
            self.objects.read(obs.call.prompt_sha256)
            self.objects.read(obs.call.response_sha256)
        summarize_three_stage(values, self.plan)
        return values

    def _project(self, conn) -> tuple[ThreeStageCall, ...]:
        raw = self._decode(conn.execute('SELECT content FROM calls ORDER BY sequence').fetchall())
        corrections = {row[0]: row[1:] for row in conn.execute('SELECT * FROM timing_corrections')}
        if not set(corrections) <= {o.call.call_id for o in raw}:
            raise ValueError('Timing correction lost its original observation')
        projected = []
        for obs in raw:
            change = corrections.get(obs.call.call_id)
            if change:
                original_sha, elapsed, evidence_sha = change
                evidence = json.loads(self.objects.read(evidence_sha))
                start_source = self.objects.read(evidence['start_record_sha256'])
                capture_source = self.objects.read(evidence['capture_record_sha256'])
                if (original_sha != digest(encoded(asdict(obs)))
                        or evidence['physical_call_id'] != (obs.call.shared_architect_call_id or obs.call.call_id)
                        or elapsed != self._corrected_elapsed(evidence)
                        or json.loads(start_source)['started_utc'] != evidence['started_utc']
                        or digest(json.loads(capture_source)['response'].encode('utf-8')) != obs.call.response_sha256):
                    raise ValueError('Timing amendment does not bind original bytes and evidence')
                obs = replace(obs, call=replace(obs.call, elapsed_seconds=elapsed))
            projected.append(obs)
        return tuple(projected)

    @staticmethod
    def _corrected_elapsed(evidence: dict) -> float:
        if set(evidence) != {'physical_call_id', 'started_utc', 'captured_utc', 'metric',
                'start_record_sha256', 'capture_record_sha256'} or evidence['metric'] != (
                    'HOST_INTENT_TO_CAPTURE_FILE_MTIME_INCLUDES_OPERATOR_OVERHEAD'):
            raise ValueError('Timing evidence must disclose its endpoints and metric')
        from consilium.core.pilot_three_stage import valid_hash
        if any(not valid_hash(evidence[k]) for k in ('start_record_sha256', 'capture_record_sha256')):
            raise ValueError('Original timing source hashes required')
        start, finish = (datetime.fromisoformat(evidence[k]) for k in ('started_utc', 'captured_utc'))
        if start.tzinfo is None or finish.tzinfo is None or finish < start:
            raise ValueError('Timing endpoints must be ordered timezone-aware observations')
        return (finish - start).total_seconds()

    def correct_timing(self, evidence: dict, start_record: bytes, capture_record: bytes) -> None:
        """Append an auditable correction to operator timing; never rewrite a call."""
        elapsed = self._corrected_elapsed(evidence)
        if (digest(start_record) != evidence['start_record_sha256']
                or digest(capture_record) != evidence['capture_record_sha256']
                or json.loads(start_record)['started_utc'] != evidence['started_utc']):
            raise ValueError('Correction sources do not match their registered hashes')
        self.objects.put(start_record)
        self.objects.put(capture_record)
        evidence_sha = self.objects.put(encoded(evidence))
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if (conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_artifacts'").fetchone()
                    and conn.execute("SELECT 1 FROM review_artifacts LIMIT 1").fetchone()):
                raise ValueError('A frozen review cannot change its accounting')
            raw = self._decode(conn.execute('SELECT content FROM calls ORDER BY sequence').fetchall())
            matched = [o for o in raw if (o.call.shared_architect_call_id or o.call.call_id) == evidence['physical_call_id']]
            if not matched:
                raise ValueError('Timing correction requires an existing physical call')
            if any(digest(json.loads(capture_record)['response'].encode('utf-8')) !=
                   obs.call.response_sha256 for obs in matched):
                raise ValueError('Timing capture does not belong to the observed response')
            for obs in matched:
                record = (obs.call.call_id, digest(encoded(asdict(obs))), elapsed, evidence_sha)
                prior = conn.execute('SELECT * FROM timing_corrections WHERE call_id=?', (obs.call.call_id,)).fetchone()
                if prior and prior != record:
                    raise ValueError('A timing amendment cannot be replaced')
                conn.execute('INSERT OR IGNORE INTO timing_corrections VALUES(?,?,?,?)', record)
            summarize_three_stage(self._project(conn), self.plan)

    def append(self, observation: ThreeStageCall, prompt: bytes, response: bytes) -> None:
        self.append_batch((observation,), prompt, response)

    def append_batch(self, observations: tuple[ThreeStageCall, ...], prompt: bytes, response: bytes) -> None:
        """Commit all method projections of one physical call together."""
        prompt_sha, response_sha = self.objects.put(prompt), self.objects.put(response)
        if (not observations or any(prompt_sha != o.call.prompt_sha256
                or response_sha != o.call.response_sha256 for o in observations)):
            raise ValueError('Exact prompt/response bytes do not match')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if (conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_artifacts'").fetchone()
                    and conn.execute('SELECT 1 FROM review_artifacts LIMIT 1').fetchone()):
                raise ValueError('A frozen review cannot receive more observations')
            previous = self._project(conn)
            summarize_three_stage(previous + observations, self.plan)
            conn.executemany('INSERT INTO calls(call_id,content) VALUES(?,?)',
                ((o.call.call_id, encoded(asdict(o)).decode('utf-8')) for o in observations))
