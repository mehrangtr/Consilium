"""Behavioral storage tests; test names do not imply full P02 acceptance."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from consilium.core.contracts import (
    ConnectionSpec, DebateSpec, FrozenInput, Message, OperationIdentity,
    OperationIntent, RoundSpec,
)
from consilium.shell.private import PublicBoundaryError
from consilium.shell import storage
from consilium.shell.storage import Conflict, SchemaError, SQLiteStore


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.participant = uuid4()
        self.debate = DebateSpec(debate_id=uuid4(), original_request="  سؤال اصلی؛ English\n",
                                 participant_ids=(self.participant,), constraints=("preserve dissent",))
        self.round = RoundSpec(round_id=uuid4(), debate_id=self.debate.debate_id, number=1,
                               kind="INDEPENDENT", participant_ids=(self.participant,))
        self.connection = ConnectionSpec(connection_id=uuid4(), provider_id="mock", model_id="mock-v1", mode="API")
        self.store = SQLiteStore(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def seeded(self):
        self.store.create_debate(self.debate)
        self.store.register_round(self.round, expected_revision=0)
        return self.store.bind_connection(self.debate.debate_id, self.participant, self.connection,
                                          expected_revision=1, expected_connection_revision=None)

    def intent(self, **changes):
        frozen = FrozenInput(messages=(Message(role="USER", content="  frozen سؤال\n"),))
        value = OperationIntent(identity=OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
                                debate_id=self.debate.debate_id, round_id=self.round.round_id,
                                participant_id=self.participant, connection_id=self.connection.connection_id,
                                expected_revision=2, connection_revision=0, frozen_input=frozen,
                                request_hash=frozen.content_hash)
        return value.model_copy(update=changes)

    def test_new_database_has_durable_settings_and_valid_schema(self):
        self.assertEqual(self.store._db.execute("PRAGMA user_version").fetchone()[0], 4)
        self.assertEqual(self.store._db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.store._db.execute("PRAGMA synchronous").fetchone()[0], 2)
        self.assertEqual(self.store._db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.store._db.execute("PRAGMA quick_check").fetchone()[0], "ok")

    def test_migration_is_idempotent_on_reopen(self):
        self.seeded(); original = self.store.export_debate(self.debate.debate_id)
        self.store.close(); self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.export_debate(self.debate.debate_id), original)
        self.assertEqual(self.store._db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 4)

    def test_future_schema_is_refused_without_downgrading_it(self):
        other = self.path.with_name("future.sqlite3")
        with closing(sqlite3.connect(other)) as db:
            db.execute("PRAGMA user_version=999")
        with self.assertRaises(SchemaError): SQLiteStore(other)
        with closing(sqlite3.connect(other)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 999)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")

    def test_unowned_database_is_not_adopted(self):
        other = self.path.with_name("foreign.sqlite3")
        with closing(sqlite3.connect(other)) as db: db.execute("CREATE TABLE unrelated(value TEXT)")
        with self.assertRaises(SchemaError): SQLiteStore(other)
        with closing(sqlite3.connect(other)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("unrelated",)])

    def test_failed_migration_rolls_back_all_ddl(self):
        other = self.path.with_name("failed.sqlite3")
        with patch.object(storage, "V1_STATEMENTS", storage.V1_STATEMENTS + ("INVALID SQL",)):
            with self.assertRaises(SchemaError): SQLiteStore(other)
        with closing(sqlite3.connect(other)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall(), [])

    def test_modified_migration_checksum_is_refused(self):
        self.store._db.execute("UPDATE schema_migrations SET checksum=?", ("0" * 64,))
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_missing_schema_table_is_refused(self):
        self.store._db.execute("DROP TABLE attempts")
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_original_request_and_constraints_survive_reopen_exactly(self):
        self.seeded(); self.store.close(); self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.get_debate(self.debate.debate_id), self.debate)

    def test_debate_cannot_be_created_with_an_imported_revision(self):
        with self.assertRaises(ValueError): self.store.create_debate(self.debate.model_copy(update={"revision": 3}))
        self.assertEqual(self.store._db.execute("SELECT count(*) FROM debates").fetchone()[0], 0)

    def test_duplicate_debate_is_not_silently_replaced(self):
        self.seeded()
        with self.assertRaises(Conflict): self.store.create_debate(self.debate.model_copy(update={"original_request": "new"}))
        self.assertEqual(self.store.get_debate(self.debate.debate_id), self.debate)

    def test_round_cannot_reference_another_debate_or_participant(self):
        self.store.create_debate(self.debate)
        for change in ({"debate_id": uuid4()}, {"participant_ids": (uuid4(),)}):
            with self.assertRaises(Conflict):
                self.store.register_round(self.round.model_copy(update=change), expected_revision=0)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 0)

    def test_connection_cannot_be_bound_to_a_foreign_participant(self):
        self.store.create_debate(self.debate)
        with self.assertRaises(Conflict):
            self.store.bind_connection(self.debate.debate_id, uuid4(), self.connection,
                                       expected_revision=0, expected_connection_revision=None)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 0)

    def test_two_writers_cannot_both_apply_the_same_old_revision(self):
        self.store.create_debate(self.debate)
        with SQLiteStore(self.path) as other:
            self.store.register_round(self.round, expected_revision=0)
            with self.assertRaises(Conflict):
                other.bind_connection(self.debate.debate_id, self.participant, self.connection,
                                      expected_revision=0, expected_connection_revision=None)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 1)

    def test_connection_revision_changes_and_stale_intent_is_refused(self):
        self.seeded()
        replacement = self.connection.model_copy(update={"connection_id": uuid4()})
        self.store.bind_connection(self.debate.debate_id, self.participant, replacement,
                                   expected_revision=2, expected_connection_revision=0,
                                   actor="test-user", reason="explicit connection replacement")
        with self.assertRaises(Conflict): self.store.prepare_intent(self.intent(expected_revision=3))
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 3)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id), ())

    def test_prepare_persists_exact_frozen_input_event_and_checkpoint_together(self):
        self.seeded(); intent = self.intent(); checkpoint = self.store.prepare_intent(intent)
        self.assertEqual(checkpoint.revision, 3)
        self.assertEqual(checkpoint.event_kind, "OPERATION_PREPARED")
        self.store.close(); self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.get_intent(intent.identity.attempt_id), intent)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id), (intent,))
        export = self.store.export_debate(self.debate.debate_id)
        self.assertEqual([e["revision"] for e in export["events"]], [0, 1, 2, 3])
        self.assertEqual(export["checkpoint"]["event_sequence"], export["events"][-1]["sequence"])
        self.assertFalse(export["debate_completed"])

    def test_same_input_hash_allows_two_intentional_logical_operations(self):
        self.seeded(); first = self.intent(); self.store.prepare_intent(first)
        second = self.intent(expected_revision=3); self.store.prepare_intent(second)
        self.assertEqual(first.request_hash, second.request_hash)
        self.assertNotEqual(first.identity.logical_operation_id, second.identity.logical_operation_id)
        self.assertEqual(len(self.store.prepared_intents(self.debate.debate_id)), 2)

    def test_duplicate_logical_operation_does_not_create_another_attempt(self):
        self.seeded(); first = self.intent(); self.store.prepare_intent(first)
        retry = self.intent(expected_revision=3, identity=OperationIdentity(
            logical_operation_id=first.identity.logical_operation_id, attempt_id=uuid4()))
        before = self.store.export_debate(self.debate.debate_id)
        with self.assertRaises(Conflict): self.store.prepare_intent(retry)
        self.assertEqual(self.store.export_debate(self.debate.debate_id), before)

    def test_reused_attempt_id_rolls_back_new_operation_and_event(self):
        self.seeded(); first = self.intent(); self.store.prepare_intent(first)
        second = self.intent(expected_revision=3, identity=OperationIdentity(
            logical_operation_id=uuid4(), attempt_id=first.identity.attempt_id))
        before = self.store.export_debate(self.debate.debate_id)
        with self.assertRaises(Conflict): self.store.prepare_intent(second)
        self.assertEqual(self.store.export_debate(self.debate.debate_id), before)

    def test_old_debate_revision_or_wrong_round_cannot_prepare_intent(self):
        self.seeded()
        for change in ({"expected_revision": 1}, {"round_id": uuid4()}, {"participant_id": uuid4()}):
            with self.assertRaises(Conflict): self.store.prepare_intent(self.intent(**change))
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 2)

    def test_exception_late_in_intent_transaction_leaves_no_half_commit(self):
        self.seeded()
        self.store._db.execute("""CREATE TEMP TRIGGER refuse_prepared_event BEFORE INSERT ON events
            WHEN NEW.kind='OPERATION_PREPARED' BEGIN SELECT RAISE(ABORT, 'test-only fault'); END""")
        with self.assertRaises(Conflict): self.store.prepare_intent(self.intent())
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id), ())
        self.assertEqual(self.store._db.execute("SELECT count(*) FROM operations").fetchone()[0], 0)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 2)

    def test_backup_contains_committed_intent_and_can_be_reopened(self):
        self.seeded(); intent = self.intent(); self.store.prepare_intent(intent)
        backup = self.path.with_name("backup.sqlite3"); self.store.backup(backup)
        with SQLiteStore(backup) as restored:
            self.assertEqual(restored.export_debate(self.debate.debate_id), self.store.export_debate(self.debate.debate_id))

    def test_backup_does_not_overwrite_existing_file_or_database(self):
        for path in (self.path, self.path.with_name("already-exists.sqlite3")):
            if path != self.path: path.write_bytes(b"preserve me")
            before = path.read_bytes()
            with self.assertRaises((FileExistsError, ValueError)): self.store.backup(path)
            self.assertEqual(path.read_bytes(), before)

    def test_known_private_material_is_refused_before_persistence(self):
        secret = "test-private-material-do-not-save"
        other = self.path.with_name("private.sqlite3")
        with SQLiteStore(other, forbidden_values=(secret,)) as store:
            with self.assertRaises(PublicBoundaryError):
                store.create_debate(self.debate.model_copy(update={"original_request": secret}))
            self.assertEqual(store._db.execute("SELECT count(*) FROM debates").fetchone()[0], 0)
        self.assertNotIn(secret.encode(), other.read_bytes())

    def test_intent_for_an_older_registered_round_is_refused(self):
        self.seeded()
        from consilium.adapters.mock import MockAdapter
        from consilium.core.contracts import AdapterRequest, UserDecision
        from consilium.shell.runner import DurableRunner
        first = self.intent(); self.store.prepare_intent(first)
        DurableRunner(self.store).execute(AdapterRequest(intent=first, connection=self.connection, timeout_seconds=2.0),
                                         MockAdapter(), expected_revision=3)
        checkpoint = self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id,
                                                        expected_revision=self.store.checkpoint(self.debate.debate_id).revision)
        checkpoint = self.store.ledger.record_decision(UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=checkpoint.revision, kind="CONTINUE"), actor="test-user")
        next_round = self.round.model_copy(update={"round_id": uuid4(), "number": 2, "kind": "REVIEW"})
        checkpoint = self.store.register_round(next_round, expected_revision=checkpoint.revision)
        with self.assertRaises(Conflict): self.store.prepare_intent(self.intent(expected_revision=checkpoint.revision))
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id), ())

    def test_checkpoint_cannot_be_rewound_while_newer_events_exist(self):
        self.seeded()
        old = self.store._db.execute("SELECT sequence FROM events WHERE revision=0").fetchone()[0]
        self.store._db.execute("UPDATE debates SET revision=0,checkpoint_event=?", (old,))
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_failed_backup_closes_destination_and_removes_partial_file(self):
        destination = self.path.with_name("failed-backup.sqlite3")
        opened = []
        connect = sqlite3.connect
        class TrackedConnection(sqlite3.Connection):
            closed = False
            def close(self):
                self.closed = True
                super().close()
            def backup(self, *args, **kwargs):
                raise sqlite3.OperationalError("test-only backup fault")
        def tracked(*args, **kwargs):
            copy = connect(*args, **kwargs, factory=TrackedConnection)
            opened.append(copy)
            return copy
        self.store.close()
        with patch.object(storage.sqlite3, "connect", side_effect=tracked):
            self.store = SQLiteStore(self.path)
            opened.clear()
            with self.assertRaises(sqlite3.OperationalError): self.store.backup(destination)
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)
        self.assertFalse(destination.exists())

    def crash(self, point, code, *, committed):
        self.seeded(); intent = self.intent()
        intent_path = self.path.with_name("intent.json"); intent_path.write_text(intent.model_dump_json(), encoding="utf-8")
        self.store.close()
        worker = Path(__file__).with_name("crash_worker.py")
        proc = subprocess.run([sys.executable, str(worker), str(self.path), str(intent_path), point],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=15, shell=False)
        self.assertEqual(proc.returncode, code, proc.stderr.decode("utf-8", errors="replace"))
        self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 3 if committed else 2)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id), (intent,) if committed else ())
        self.assertEqual(self.store._db.execute("PRAGMA quick_check").fetchone()[0], "ok")

    def test_actual_process_exit_before_intent_keeps_previous_checkpoint(self):
        self.crash("before_intent", 91, committed=False)

    def test_actual_process_exit_inside_intent_rolls_back_all_partial_writes(self):
        self.crash("during_intent", 92, committed=False)

    def test_actual_process_exit_after_intent_preserves_frozen_input_and_checkpoint(self):
        self.crash("after_intent", 93, committed=True)
