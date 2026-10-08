"""Private pilot observations with atomic, append-only SQLite accounting."""
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from consilium.core.pilot import PilotCall, summarize
from consilium.shell.evidence_store import EvidenceStore


class PilotJournal:
    def __init__(self, workspace: Path, task_ids: tuple[str, ...], max_calls: int = 6):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.objects = EvidenceStore(self.workspace / 'objects')
        self.task_ids = task_ids
        self.max_calls = max_calls
        self.database = self.workspace / 'pilot.sqlite3'
        with self._connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS calls '
                '(sequence INTEGER PRIMARY KEY, call_id TEXT NOT NULL UNIQUE, observation TEXT NOT NULL)')
            connection.execute('BEGIN IMMEDIATE')
            legacy = self.workspace / 'CALLS.json'
            if not connection.execute('SELECT 1 FROM calls LIMIT 1').fetchone() and legacy.exists():
                calls = tuple(PilotCall(**r) for r in json.loads(legacy.read_text(encoding='utf-8')))
                summarize(calls, task_ids, max_calls)
                for call in calls:
                    self.objects.read(call.prompt_sha256)
                    self.objects.read(call.response_sha256)
                    connection.execute('INSERT INTO calls(call_id,observation) VALUES(?,?)',
                        (call.call_id, json.dumps(asdict(call))))
            connection.commit()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=5)
        try:
            connection.execute('PRAGMA synchronous=FULL')
            with connection:
                yield connection
        finally:
            connection.close()

    def calls(self) -> tuple[PilotCall, ...]:
        with self._connect() as connection:
            rows = connection.execute('SELECT observation FROM calls ORDER BY sequence').fetchall()
        return tuple(PilotCall(**json.loads(row[0])) for row in rows)

    def append(self, call: PilotCall, prompt: bytes, response: bytes) -> None:
        # Orphan objects after an interrupted transaction are safe; a committed
        # observation never precedes its verified object bytes.
        if self.objects.put(prompt) != call.prompt_sha256 or self.objects.put(response) != call.response_sha256:
            raise ValueError('Observation digest differs from its exact bytes')
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if (connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_artifacts'").fetchone()
                    and connection.execute("SELECT 1 FROM review_artifacts WHERE name='BLINDED.json'").fetchone()):
                raise ValueError('A frozen blinded journal cannot receive additional observations')
            rows = connection.execute('SELECT observation FROM calls ORDER BY sequence').fetchall()
            calls = tuple(PilotCall(**json.loads(row[0])) for row in rows)
            summarize(calls + (call,), self.task_ids, self.max_calls)
            connection.execute('INSERT INTO calls(call_id,observation) VALUES(?,?)',
                (call.call_id, json.dumps(asdict(call))))
            connection.commit()
