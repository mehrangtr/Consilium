"""Transactional local storage; transport I/O is always outside its transactions."""
from __future__ import annotations

from contextlib import closing, contextmanager
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator
from uuid import UUID

from consilium.core.contracts import ConnectionSpec, DebateSpec, OperationIntent, RoundSpec
from consilium.core.storage_contracts import StorageCheckpoint
from consilium.shell.private import ensure_public_payload
from consilium.shell.schema_v2 import V2_STATEMENTS, V2_TABLES
from consilium.shell.schema_v3 import V3_STATEMENTS, V3_TABLES
from consilium.shell.schema_v4 import V4_STATEMENTS, V4_TABLES

APPLICATION_ID = 0x434F4E53
SCHEMA_VERSION = 4
V1_STATEMENTS = (
    """CREATE TABLE schema_migrations(
        version INTEGER PRIMARY KEY, checksum TEXT NOT NULL CHECK(length(checksum)=64),
        applied_at TEXT NOT NULL) STRICT""",
    """CREATE TABLE debates(
        debate_id TEXT PRIMARY KEY, spec_json TEXT NOT NULL CHECK(json_valid(spec_json)),
        revision INTEGER NOT NULL CHECK(revision>=0),
        checkpoint_event INTEGER REFERENCES events(sequence) DEFERRABLE INITIALLY DEFERRED) STRICT""",
    """CREATE TABLE rounds(
        round_id TEXT PRIMARY KEY, debate_id TEXT NOT NULL REFERENCES debates(debate_id),
        number INTEGER NOT NULL CHECK(number>=1), spec_json TEXT NOT NULL CHECK(json_valid(spec_json)),
        UNIQUE(debate_id,number)) STRICT""",
    """CREATE TABLE bindings(
        debate_id TEXT NOT NULL REFERENCES debates(debate_id), participant_id TEXT NOT NULL,
        connection_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=0),
        spec_json TEXT NOT NULL CHECK(json_valid(spec_json)),
        PRIMARY KEY(debate_id,participant_id), UNIQUE(debate_id,connection_id)) STRICT""",
    """CREATE TABLE operations(
        logical_operation_id TEXT PRIMARY KEY, debate_id TEXT NOT NULL REFERENCES debates(debate_id),
        round_id TEXT NOT NULL REFERENCES rounds(round_id), participant_id TEXT NOT NULL,
        generation_id TEXT, request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
        frozen_input_json TEXT NOT NULL CHECK(json_valid(frozen_input_json))) STRICT""",
    """CREATE TABLE attempts(
        attempt_id TEXT PRIMARY KEY, logical_operation_id TEXT NOT NULL UNIQUE REFERENCES operations(logical_operation_id),
        state TEXT NOT NULL CHECK(state='PREPARED'), intent_json TEXT NOT NULL CHECK(json_valid(intent_json))) STRICT""",
    """CREATE TABLE events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, debate_id TEXT NOT NULL REFERENCES debates(debate_id),
        revision INTEGER NOT NULL CHECK(revision>=0), kind TEXT NOT NULL CHECK(kind IN
            ('DEBATE_CREATED','ROUND_REGISTERED','CONNECTION_BOUND','OPERATION_PREPARED')),
        payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), created_at TEXT NOT NULL,
        UNIQUE(debate_id,revision)) STRICT""",
)
_TABLES = {"schema_migrations", "debates", "rounds", "bindings", "operations", "attempts", "events"}


class SchemaError(ValueError):
    """Unknown, inconsistent or incomplete storage must not be silently repaired."""


class Conflict(ValueError):
    """A stale revision or incompatible identity prevented the whole write."""


def _identifier(value: UUID) -> str:
    if not isinstance(value, UUID) or value.int == 0:
        raise ValueError("A non-nil UUID is required")
    return str(value)


def _revision(value: int) -> int:
    if type(value) is not int or not 0 <= value < 2**63 - 1:
        raise ValueError("A bounded nonnegative revision is required")
    return value


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class SQLiteStore:
    """One connection per worker; local filesystem only, explicit short transactions."""

    def __init__(self, path: Path, *, forbidden_values: tuple[str, ...] = (), require_new: bool = False):
        if not isinstance(path, Path) or path.name == ":memory:":
            raise ValueError("A persistent filesystem path is required")
        if not isinstance(forbidden_values, tuple) or not all(isinstance(x, str) and x for x in forbidden_values):
            raise ValueError("Private values must be explicit nonempty strings")
        self.path = path.resolve()
        self._forbidden_values = forbidden_values
        if type(require_new) is not bool:
            raise ValueError("Creation policy must be explicit")
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
        except FileExistsError:
            if require_new:
                raise
        self._db = sqlite3.connect(self.path, timeout=5.0, autocommit=True)
        self._db.row_factory = sqlite3.Row
        try:
            initial_version = self._check_owner()
            self._db.execute("PRAGMA foreign_keys=ON")
            if self._db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise SchemaError("Persistent WAL mode is unavailable")
            self._db.execute("PRAGMA synchronous=FULL")
            # SQLite's generalized table rebuild disables FK enforcement outside
            # the transaction, checks all references before commit, then reenables.
            # DROP TABLE's deferred-delete counter cannot validate a recreated table.
            if initial_version < SCHEMA_VERSION:
                self._db.execute("PRAGMA foreign_keys=OFF")
            with self._transaction():
                version = self._check_owner()
                migrations = {1: V1_STATEMENTS, 2: V2_STATEMENTS, 3: V3_STATEMENTS, 4: V4_STATEMENTS}
                checksums = {v: hashlib.sha256(_json(sql).encode("utf-8")).hexdigest() for v, sql in migrations.items()}
                if version == 0:
                    # executescript() is deliberately excluded from this transaction.
                    for statement in V1_STATEMENTS:
                        self._db.execute(statement)
                    self._db.execute("INSERT INTO schema_migrations VALUES(1,?,?)", (checksums[1], self._now()))
                    self._db.execute("PRAGMA application_id=" + str(APPLICATION_ID))
                    self._db.execute("PRAGMA user_version=1")
                    version = 1
                recorded = self._db.execute("SELECT version,checksum FROM schema_migrations ORDER BY version").fetchall()
                if [(r["version"], r["checksum"]) for r in recorded] != [(v, checksums[v]) for v in range(1, version+1)]:
                    raise SchemaError("Migration history does not match this schema")
                if self._table_names() != {1: _TABLES, 2: V2_TABLES, 3: V3_TABLES, 4: V4_TABLES}[version]:
                    raise SchemaError("Storage schema is incomplete or has unknown tables")
                # Validate the old checkpoint before touching its schema.
                for row in self._db.execute("SELECT debate_id FROM debates").fetchall():
                    self.checkpoint(UUID(row["debate_id"]))
                for target in range(version+1, SCHEMA_VERSION+1):
                    for statement in migrations[target]:
                        self._db.execute(statement)
                    self._db.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (target, checksums[target], self._now()))
                    self._db.execute("PRAGMA user_version=" + str(target))
                if self._table_names() != V4_TABLES:
                    raise SchemaError("Migrated schema is inconsistent")
                if self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or self._db.execute("PRAGMA foreign_key_check").fetchall():
                    raise SchemaError("Storage integrity check failed")
                for row in self._db.execute("SELECT debate_id FROM debates").fetchall():
                    self.checkpoint(UUID(row["debate_id"]))
                from consilium.shell.ledger import OperationLedger
                self.ledger = OperationLedger(self)
                self.ledger.check_integrity()
                from consilium.shell.questions import QuestionLedger
                self.questions = QuestionLedger(self)
                self.questions.check_integrity()
                from consilium.shell.admissions import AdmissionLedger
                self.admissions = AdmissionLedger(self)
                self.admissions.check_integrity()
            self._db.execute("PRAGMA foreign_keys=ON")
            if self._db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise SchemaError("Runtime foreign key enforcement is unavailable")
        except BaseException as exc:
            self._db.close()
            if isinstance(exc, sqlite3.Error):
                raise SchemaError("Storage initialization failed") from None
            raise

    @staticmethod
    def _now() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def _table_names(self) -> set[str]:
        return {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

    def _check_owner(self) -> int:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        owner = self._db.execute("PRAGMA application_id").fetchone()[0]
        if version not in range(SCHEMA_VERSION + 1) or owner not in {0, APPLICATION_ID}:
            raise SchemaError("Storage belongs to another application or schema version")
        if version == 0 and (owner != 0 or self._table_names()):
            raise SchemaError("Unversioned existing data cannot be adopted")
        if version != 0 and owner != APPLICATION_ID:
            raise SchemaError("Versioned storage has no matching application identity")
        return version

    @contextmanager
    def _transaction(self, *, write: bool = True) -> Iterator[None]:
        self._db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException as exc:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            if isinstance(exc, sqlite3.IntegrityError):
                raise Conflict("Persistent identity or state conflict") from None
            raise

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._db.close()

    def _public(self, payload: dict) -> str:
        ensure_public_payload(payload, self._forbidden_values)
        return _json(payload)

    def get_debate(self, debate_id: UUID) -> DebateSpec:
        row = self._db.execute("SELECT spec_json FROM debates WHERE debate_id=?", (_identifier(debate_id),)).fetchone()
        if row is None:
            raise Conflict("Debate is not registered")
        spec = DebateSpec.model_validate_json(row["spec_json"])
        if spec.debate_id != debate_id or spec.revision != 0:
            raise SchemaError("Stored debate identity is inconsistent")
        return spec

    def checkpoint(self, debate_id: UUID) -> StorageCheckpoint:
        if not self._db.in_transaction:
            with self._transaction(write=False):
                return self.checkpoint(debate_id)
        row = self._db.execute("""SELECT d.revision,e.sequence,e.kind,e.debate_id AS event_debate,e.revision AS event_revision
            FROM debates d LEFT JOIN events e ON e.sequence=d.checkpoint_event WHERE d.debate_id=?""",
            (_identifier(debate_id),)).fetchone()
        if row is None:
            raise Conflict("Debate is not registered")
        if row["sequence"] is None or row["event_debate"] != str(debate_id) or row["revision"] != row["event_revision"]:
            raise SchemaError("Checkpoint does not match its committed event")
        history = self._db.execute("""SELECT COUNT(*) AS total,MIN(revision) AS first,MAX(revision) AS latest,
            MAX(sequence) AS last_sequence FROM events WHERE debate_id=?""", (str(debate_id),)).fetchone()
        if (history["first"], history["latest"], history["total"], history["last_sequence"]) != (
                0, row["revision"], row["revision"] + 1, row["sequence"]):
            raise SchemaError("Checkpoint is not the complete latest event history")
        return StorageCheckpoint(debate_id=debate_id, revision=row["revision"], event_sequence=row["sequence"], event_kind=row["kind"])

    def _checked_debate(self, debate_id: UUID, expected_revision: int) -> DebateSpec:
        if self.checkpoint(debate_id).revision != _revision(expected_revision):
            raise Conflict("Debate revision is stale")
        return self.get_debate(debate_id)

    def _event(self, debate_id: UUID, revision: int, kind: str, payload: dict) -> int:
        return self._db.execute("INSERT INTO events(debate_id,revision,kind,payload_json,created_at) VALUES(?,?,?,?,?)",
                                (str(debate_id), revision, kind, self._public(payload), self._now())).lastrowid

    def _advance(self, debate_id: UUID, previous: int, kind: str, payload: dict) -> StorageCheckpoint:
        sequence = self._event(debate_id, previous + 1, kind, payload)
        updated = self._db.execute("UPDATE debates SET revision=?,checkpoint_event=? WHERE debate_id=? AND revision=?",
                                   (previous + 1, sequence, str(debate_id), previous))
        if updated.rowcount != 1:
            raise Conflict("Debate revision changed")
        return self.checkpoint(debate_id)

    def create_debate(self, spec: DebateSpec) -> StorageCheckpoint:
        spec = DebateSpec.model_validate(spec.model_dump(mode="python"))
        if spec.revision != 0:
            raise ValueError("New debates must start at revision zero")
        public = self._public(spec.model_dump(mode="json"))
        with self._transaction():
            self._db.execute("INSERT INTO debates(debate_id,spec_json,revision,checkpoint_event) VALUES(?,?,0,NULL)", (str(spec.debate_id), public))
            sequence = self._event(spec.debate_id, 0, "DEBATE_CREATED", {"debate_id": str(spec.debate_id)})
            self._db.execute("UPDATE debates SET checkpoint_event=? WHERE debate_id=?", (sequence, str(spec.debate_id)))
            return self.checkpoint(spec.debate_id)

    def register_round(self, spec: RoundSpec, *, expected_revision: int) -> StorageCheckpoint:
        spec = RoundSpec.model_validate(spec.model_dump(mode="python"))
        public = self._public(spec.model_dump(mode="json"))
        with self._transaction():
            debate = self._checked_debate(spec.debate_id, expected_revision)
            if not set(spec.participant_ids).issubset(debate.participant_ids):
                raise Conflict("Round participants do not belong to the debate")
            previous_number = self._db.execute("SELECT COALESCE(MAX(number),0) FROM rounds WHERE debate_id=?", (str(spec.debate_id),)).fetchone()[0]
            if spec.number != previous_number + 1:
                raise Conflict("Round number is not the next registered round")
            wait = self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(spec.debate_id),)).fetchone()[0]
            if wait != ("ACTIVE" if previous_number == 0 else "READY_NEXT_ROUND"):
                raise Conflict("A next round requires a current explicit continuation decision")
            if previous_number:
                decision = self._db.execute("SELECT decision_json,event_sequence FROM user_decisions WHERE debate_id=? ORDER BY event_sequence DESC LIMIT 1",
                                            (str(spec.debate_id),)).fetchone()
                from consilium.core.contracts import UserDecision
                previous = self._db.execute("SELECT round_id FROM rounds WHERE debate_id=? AND number=?",
                                            (str(spec.debate_id), previous_number)).fetchone()[0]
                parsed = None if decision is None else UserDecision.model_validate_json(decision[0])
                if (parsed is None or parsed.kind not in {"CONTINUE", "CUSTOM"} or str(parsed.round_id) != previous
                        or parsed.expected_revision+1 != expected_revision):
                    raise Conflict("No continuation decision for the previous round")
            self._db.execute("INSERT INTO rounds VALUES(?,?,?,?)", (str(spec.round_id), str(spec.debate_id), spec.number, public))
            self._db.execute("UPDATE debates SET wait_state='ACTIVE' WHERE debate_id=?", (str(spec.debate_id),))
            return self._advance(spec.debate_id, expected_revision, "ROUND_REGISTERED", {"round_id": str(spec.round_id)})

    def bind_connection(self, debate_id: UUID, participant_id: UUID, connection: ConnectionSpec, *,
                        expected_revision: int, expected_connection_revision: int | None,
                        actor: str = "SYSTEM", reason: str = "initial connection binding") -> StorageCheckpoint:
        connection = ConnectionSpec.model_validate(connection.model_dump(mode="python"))
        participant = _identifier(participant_id)
        if expected_connection_revision is not None:
            _revision(expected_connection_revision)
            if actor == "SYSTEM" or reason == "initial connection binding":
                raise ValueError("Connection replacement requires an explicit actor and reason")
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError("A nonblank actor and reason are required")
        public = self._public(connection.model_dump(mode="json"))
        with self._transaction():
            debate = self._checked_debate(debate_id, expected_revision)
            if participant_id not in debate.participant_ids:
                raise Conflict("Participant does not belong to the debate")
            old = self._db.execute("SELECT revision FROM bindings WHERE debate_id=? AND participant_id=?", (str(debate_id), participant)).fetchone()
            if (None if old is None else old["revision"]) != expected_connection_revision:
                raise Conflict("Connection revision is stale")
            revision = 0 if old is None else old["revision"] + 1
            invalidated = False
            if old is not None and self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(debate_id),)).fetchone()[0] == "READY_NEXT_ROUND":
                self._db.execute("UPDATE debates SET wait_state='WAITING_DECISION' WHERE debate_id=?", (str(debate_id),))
                invalidated = True
            self._db.execute("""INSERT INTO bindings VALUES(?,?,?,?,?) ON CONFLICT(debate_id,participant_id)
                DO UPDATE SET connection_id=excluded.connection_id,revision=excluded.revision,spec_json=excluded.spec_json""",
                (str(debate_id), participant, str(connection.connection_id), revision, public))
            return self._advance(debate_id, expected_revision, "CONNECTION_BOUND",
                                 {"participant_id": participant, "connection_id": str(connection.connection_id), "connection_revision": revision,
                                  "actor": actor, "reason": reason, "continuation_decision_invalidated": invalidated})

    def prepare_intent(self, intent: OperationIntent, *, admission_bundle=None) -> StorageCheckpoint:
        intent = OperationIntent.model_validate(intent.model_dump(mode="python"))
        public = self._public(intent.model_dump(mode="json"))
        if admission_bundle is not None:
            from consilium.core.admission_bundle import AdmissionBundle
            admission_bundle = AdmissionBundle.model_validate(admission_bundle)
            admission_bundle.require_intent(intent)
            bundle_json = self._public(admission_bundle.model_dump(mode="json"))
        with self._transaction():
            self._checked_debate(intent.debate_id, intent.expected_revision)
            if self._db.execute("SELECT wait_state FROM debates WHERE debate_id=?", (str(intent.debate_id),)).fetchone()[0] != "ACTIVE":
                raise Conflict("A wait gate cannot authorize a new operation")
            row = self._db.execute("SELECT round_id,spec_json FROM rounds WHERE debate_id=? ORDER BY number DESC LIMIT 1",
                                   (str(intent.debate_id),)).fetchone()
            if row is None or row["round_id"] != str(intent.round_id) or intent.participant_id not in RoundSpec.model_validate_json(row["spec_json"]).participant_ids:
                raise Conflict("Intent does not belong to the registered round")
            binding = self._db.execute("SELECT connection_id,revision,spec_json FROM bindings WHERE debate_id=? AND participant_id=?",
                                       (str(intent.debate_id), str(intent.participant_id))).fetchone()
            if binding is None or (binding["connection_id"], binding["revision"]) != (str(intent.connection_id), intent.connection_revision):
                raise Conflict("Intent refers to a stale connection")
            if admission_bundle is not None:
                if ConnectionSpec.model_validate_json(binding["spec_json"]) != admission_bundle.connection:
                    raise Conflict("Admission destination differs from the stored connection")
                self.admissions.validate_preparation(admission_bundle, intent)
            elif self.questions.get_adopted(intent.debate_id) is not None:
                raise Conflict("Adopted-question operations require durable policy evidence")
            ids = intent.identity
            self._db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,?)", (str(ids.logical_operation_id), str(intent.debate_id),
                str(intent.round_id), str(intent.participant_id), None if ids.generation_id is None else str(ids.generation_id),
                intent.request_hash, intent.frozen_input.canonical_bytes().decode("utf-8")))
            self._db.execute("""INSERT INTO attempts(attempt_id,logical_operation_id,state,intent_json,active_revision)
                VALUES(?,?,'PREPARED',?,?)""", (str(ids.attempt_id), str(ids.logical_operation_id), public, intent.expected_revision+1))
            payload = {"logical_operation_id": str(ids.logical_operation_id), "attempt_id": str(ids.attempt_id)}
            if admission_bundle is not None:
                payload["admission_bundle_hash"] = admission_bundle.content_hash
            checkpoint = self._advance(intent.debate_id, intent.expected_revision, "OPERATION_PREPARED", payload)
            if admission_bundle is not None:
                self._db.execute("INSERT INTO context_admissions VALUES(?,?,?,?,?)",
                    (str(ids.logical_operation_id), str(ids.attempt_id), bundle_json,
                     admission_bundle.content_hash, checkpoint.event_sequence))
            return checkpoint

    def get_intent(self, attempt_id: UUID) -> OperationIntent:
        row = self._db.execute("""SELECT a.*,o.request_hash,o.frozen_input_json,o.debate_id,o.round_id,o.participant_id,o.generation_id
            FROM attempts a JOIN operations o USING(logical_operation_id) WHERE a.attempt_id=?""", (_identifier(attempt_id),)).fetchone()
        if row is None:
            raise Conflict("Attempt is not registered")
        intent = OperationIntent.model_validate_json(row["intent_json"])
        expected = (str(intent.identity.attempt_id), str(intent.identity.logical_operation_id), intent.request_hash,
                    intent.frozen_input.canonical_bytes().decode("utf-8"), str(intent.debate_id), str(intent.round_id),
                    str(intent.participant_id), None if intent.identity.generation_id is None else str(intent.identity.generation_id))
        actual = tuple(row[key] for key in ("attempt_id", "logical_operation_id", "request_hash", "frozen_input_json",
                                           "debate_id", "round_id", "participant_id", "generation_id"))
        if actual != expected:
            raise SchemaError("Stored intent does not match its operation")
        return intent

    def prepared_intents(self, debate_id: UUID) -> tuple[OperationIntent, ...]:
        self.get_debate(debate_id)
        rows = self._db.execute("""SELECT a.attempt_id FROM attempts a JOIN operations o USING(logical_operation_id)
            WHERE o.debate_id=? AND a.state='PREPARED' ORDER BY a.rowid""", (str(debate_id),)).fetchall()
        return tuple(self.get_intent(UUID(row["attempt_id"])) for row in rows)

    def export_debate(self, debate_id: UUID) -> dict:
        with self._transaction(write=False):
            debate = self.get_debate(debate_id)
            rounds = [RoundSpec.model_validate_json(row["spec_json"]).model_dump(mode="json") for row in self._db.execute(
                "SELECT spec_json FROM rounds WHERE debate_id=? ORDER BY number", (str(debate_id),))]
            bindings = [{"participant_id": row["participant_id"], "revision": row["revision"],
                         "connection": ConnectionSpec.model_validate_json(row["spec_json"]).model_dump(mode="json")}
                        for row in self._db.execute("SELECT * FROM bindings WHERE debate_id=? ORDER BY participant_id", (str(debate_id),))]
            events = [{"sequence": row["sequence"], "revision": row["revision"], "kind": row["kind"],
                       "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}
                      for row in self._db.execute("SELECT * FROM events WHERE debate_id=? ORDER BY revision", (str(debate_id),))]
            payload = {"schema_version": 2, "scope": "P02_DURABLE_MOCK_PATH_NOT_FULL_COUNCIL_EXPORT", "debate_completed": False,
                       "debate": debate.model_dump(mode="json"), "rounds": rounds, "bindings": bindings,
                       "prepared_intents": [x.model_dump(mode="json") for x in self.prepared_intents(debate_id)],
                       "events": events, "checkpoint": self.checkpoint(debate_id).model_dump(mode="json")}
            payload.update(self.ledger.export_fields(debate_id))
            payload.update(self.questions.export_fields(debate_id))
            payload.update(self.admissions.export_fields(debate_id))
            self._public(payload)
            return payload

    def backup(self, destination: Path) -> None:
        destination = destination.resolve()
        if destination == self.path or self._db.in_transaction:
            raise ValueError("Backup must use a separate path outside any transaction")
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(destination, autocommit=True)) as copy:
                self._db.backup(copy)
                if copy.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise SchemaError("Backup integrity check failed")
                if copy.execute("PRAGMA foreign_key_check").fetchall():
                    raise SchemaError("Backup references are inconsistent")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
