import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import UUID

import test_context_preparation as fixtures
from consilium.core.admission_bundle import AdmissionBundle
from consilium.core.contracts import AdapterRequest, OperationIntent
from consilium.core.dispatch_policy import evaluate_dispatch_policy
from consilium.shell.storage import SQLiteStore, Conflict, SchemaError, APPLICATION_ID, V1_STATEMENTS
from consilium.shell.schema_v2 import V2_STATEMENTS
from consilium.shell.schema_v3 import V3_STATEMENTS


class AdmissionStorageTests(unittest.TestCase):
    setUp = fixtures.ContextPreparationTests.setUp
    tearDown = fixtures.ContextPreparationTests.tearDown
    prepare = fixtures.ContextPreparationTests.prepare

    def bundle(self):
        return AdmissionBundle(context=self.context, connection=self.connection, connection_revision=0,
            privacy=self.privacy, budget=self.budget, history=self.history,
            admission=evaluate_dispatch_policy(context=self.context, connection=self.connection,
                privacy=self.privacy, budget=self.budget, history=self.history, expected_revision=3))

    def intent(self):
        return OperationIntent(identity=self.identity, debate_id=self.debate.debate_id,
            round_id=self.round.round_id, participant_id=UUID(int=2), connection_id=self.connection.connection_id,
            expected_revision=3, connection_revision=0, frozen_input=self.context.frozen_input,
            request_hash=self.context.frozen_input.content_hash)

    def test_full_policy_facts_survive_reopen_and_export(self):
        self.prepare()
        expected = self.bundle()
        self.store.close()
        self.store = SQLiteStore(self.path)
        saved = self.store.admissions.get(self.identity.logical_operation_id)
        self.assertEqual(saved, expected)
        self.assertEqual(saved.privacy.trusted_user_action_id, UUID(int=6))
        self.assertEqual(saved.budget.input_tokens, 60)
        self.assertEqual(saved.history.state, "NO_REMOTE_HISTORY")
        self.assertEqual(self.store.admissions.require_current(self.identity.attempt_id, expected_revision=4), expected)
        exported = self.store.export_debate(self.debate.debate_id)["context_admissions"]
        self.assertEqual(exported, [{"logical_operation_id": str(self.identity.logical_operation_id),
                                    "bundle": expected.model_dump(mode="json")}])

    def test_final_evidence_insert_failure_rolls_back_intent_event_and_revision(self):
        self.store._db.execute("CREATE TEMP TRIGGER refuse_admission BEFORE INSERT ON context_admissions "
            "BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Conflict): self.prepare()
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 3)
        for table in ("operations", "attempts", "context_admissions"):
            self.assertEqual(self.store._db.execute("SELECT count(*) FROM " + table).fetchone()[0], 0)

    def crash_case(self, before_commit):
        bundle_json = self.bundle().model_dump_json()
        self.store.close()
        script = '''
import os,sys
from pathlib import Path
from uuid import UUID
from consilium.core.admission_bundle import AdmissionBundle
from consilium.core.contracts import OperationIntent,OperationIdentity
from consilium.shell.storage import SQLiteStore
s=SQLiteStore(Path(sys.argv[1]))
b=AdmissionBundle.model_validate_json(sys.argv[2])
c=b.context
i=OperationIntent(identity=OperationIdentity(logical_operation_id=UUID(int=7),attempt_id=UUID(int=8)),
 debate_id=c.debate_id,round_id=c.round_id,participant_id=c.participant_id,
 connection_id=b.connection.connection_id,connection_revision=b.connection_revision,expected_revision=3,
 frozen_input=c.frozen_input,request_hash=c.frozen_input.content_hash)
if sys.argv[3]=='before':
 s._db.create_function('stop_process',0,lambda:os._exit(93))
 s._db.execute("CREATE TEMP TRIGGER interrupt_evidence BEFORE INSERT ON context_admissions BEGIN SELECT stop_process(); END")
s.prepare_intent(i,admission_bundle=b)
os._exit(94)
'''
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, "-c", script, str(self.path), bundle_json,
            "before" if before_commit else "after"], stdin=subprocess.DEVNULL, capture_output=True,
            timeout=15, env={**os.environ, "PYTHONPATH": str(root / "src")})
        self.assertEqual(result.returncode, 93 if before_commit else 94, result.stderr.decode())
        self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 3 if before_commit else 4)
        if before_commit:
            self.assertEqual(self.store.prepared_intents(self.debate.debate_id), ())
            self.assertIsNone(self.store.admissions.get(self.identity.logical_operation_id))
        else:
            self.assertEqual(self.store.get_intent(self.identity.attempt_id), self.intent())
            self.assertEqual(self.store.admissions.get(self.identity.logical_operation_id), self.bundle())

    def test_process_exit_after_event_before_evidence_rolls_back_all(self):
        self.crash_case(True)

    def test_process_exit_after_commit_preserves_intent_and_all_evidence(self):
        self.crash_case(False)

    def test_deleted_evidence_is_detected_from_preparation_event(self):
        self.prepare()
        self.store._db.execute("DELETE FROM context_admissions")
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_modified_policy_fact_is_rejected_on_reopen(self):
        self.prepare()
        data = self.bundle().model_dump(mode="json")
        data["budget"]["context_capacity"] = 99
        self.store._db.execute("UPDATE context_admissions SET bundle_json=?", (json.dumps(data),))
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_forged_input_with_consistent_hashes_cannot_replace_authorized_reconstruction(self):
        bundle = self.bundle()
        frozen = self.context.frozen_input.model_copy(update={"messages": (
            self.context.frozen_input.messages[0],
            self.context.frozen_input.messages[1].model_copy(update={"content": "PEER_LEAK_SENTINEL"}))})
        context = self.context.model_copy(update={"frozen_input": frozen})
        binding = dict(view_hash=context.content_hash, request_hash=frozen.content_hash)
        privacy = self.privacy.model_copy(update=binding)
        budget = self.budget.model_copy(update=binding)
        history = self.history.model_copy(update=binding)
        admission = evaluate_dispatch_policy(context=context, connection=self.connection, privacy=privacy,
            budget=budget, history=history, expected_revision=3)
        forged = bundle.model_copy(update=dict(context=context, privacy=privacy, budget=budget,
            history=history, admission=admission))
        forged_intent = self.intent().model_copy(update={"frozen_input": frozen, "request_hash": frozen.content_hash})
        with self.assertRaises(ValueError): self.store.prepare_intent(forged_intent, admission_bundle=forged)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 3)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id), ())

    def test_bundle_event_hash_mismatch_is_rejected(self):
        self.prepare()
        self.store._db.execute("UPDATE events SET payload_json=json_set(payload_json,'$.admission_bundle_hash',?) "
            "WHERE kind='OPERATION_PREPARED'", ("0" * 64,))
        with self.assertRaises(SchemaError): self.store.admissions.get(self.identity.logical_operation_id)

    def test_historical_facts_remain_readable_after_binding_change_but_cannot_continue(self):
        self.prepare()
        self.store.bind_connection(self.debate.debate_id, UUID(int=2),
            self.connection.model_copy(update={"model_id": "changed"}), expected_revision=4,
            expected_connection_revision=0, actor="LOCAL_USER_FIXTURE", reason="explicit fixture replacement")
        self.store.close()
        self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.admissions.get(self.identity.logical_operation_id), self.bundle())
        with self.assertRaises(Conflict):
            self.store.admissions.require_current(self.identity.attempt_id, expected_revision=5)

    def test_missing_evidence_cannot_use_old_prepare_path_for_adopted_question(self):
        with self.assertRaises(Conflict): self.store.prepare_intent(self.intent())
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 3)

    def test_synthetic_attestations_never_enable_live_transport(self):
        self.prepare()
        request = AdapterRequest(intent=self.intent(), connection=self.connection, timeout_seconds=10)
        with self.assertRaises(Conflict): self.store.ledger.begin_send(request, expected_revision=4)
        self.assertEqual(self.store.ledger.get_attempt(self.identity.attempt_id).state.value, "PREPARED")
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 4)

    def test_stale_revision_rejected_without_mutation(self):
        self.prepare()
        with self.assertRaises(Conflict):
            self.store.admissions.require_current(self.identity.attempt_id, expected_revision=3)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 4)


class AdmissionMigrationTests(unittest.TestCase):
    def create_v3(self, path):
        db = sqlite3.connect(path, autocommit=True)
        db.execute("BEGIN")
        for version, statements in ((1, V1_STATEMENTS), (2, V2_STATEMENTS), (3, V3_STATEMENTS)):
            for sql in statements: db.execute(sql)
            checksum = hashlib.sha256(json.dumps(statements, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            db.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (version, checksum, "historic"))
        db.execute("PRAGMA application_id=" + str(APPLICATION_ID))
        db.execute("PRAGMA user_version=3")
        db.execute("COMMIT")
        db.close()

    def test_v3_upgrade_preserves_all_published_migration_checksums(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v3.sqlite3"
            self.create_v3(path)
            with sqlite3.connect(path) as before:
                recorded = before.execute("SELECT * FROM schema_migrations ORDER BY version").fetchall()
            with SQLiteStore(path) as upgraded:
                self.assertEqual(upgraded._db.execute("PRAGMA user_version").fetchone()[0], 4)
                self.assertEqual([tuple(r) for r in upgraded._db.execute(
                    "SELECT * FROM schema_migrations WHERE version<=3 ORDER BY version")], recorded)
                self.assertEqual(upgraded._db.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_failed_v4_upgrade_leaves_v3_unchanged(self):
        import tempfile
        import consilium.shell.storage as storage_module
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v3.sqlite3"
            self.create_v3(path)
            with patch.object(storage_module, "V4_STATEMENTS", storage_module.V4_STATEMENTS + ("INVALID SQL",)):
                with self.assertRaises(SchemaError): SQLiteStore(path)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='context_admissions'").fetchone()[0], 0)
