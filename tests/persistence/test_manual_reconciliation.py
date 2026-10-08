"""Manual abandonment cannot turn ambiguity into delivery proof or resend authority."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_ledger as fixtures
from consilium.adapters.mock import MockAdapter, Scenario
from consilium.core.contracts import ConnectionSpec, OperationIdentity
from consilium.core.operation_states import AttemptState, ResumeAction
from consilium.shell.storage import Conflict, SchemaError, SQLiteStore
from consilium.shell.manual_reconciliation_review import review_manual_reconciliation


class ManualReconciliationTests(unittest.TestCase):
    setUp = fixtures.LedgerTests.setUp
    tearDown = fixtures.LedgerTests.tearDown
    revision = fixtures.LedgerTests.revision
    attempt = fixtures.LedgerTests.attempt
    reopen = fixtures.LedgerTests.reopen
    send_and_record = fixtures.LedgerTests.send_and_record

    def review(self, **updates):
        self.manual = getattr(self, "manual", ConnectionSpec(connection_id=uuid4(), provider_id="copied-service",
            model_id="unverified-model", mode="MANUAL"))
        args = dict(debate_id=self.debate.debate_id, round_id=self.round.round_id,
            participant_id=self.participant, expected_revision=self.revision, manual_connection=self.manual)
        return self.store.manual_reconciliation.review(**{**args, **updates})

    def accept(self, review=None, **updates):
        review = review or self.review()
        args = dict(review=review, review_hash=review.content_hash, user_action_id=uuid4(),
            actor="LOCAL_USER_FIXTURE", reason="Continue with separately entered manual content",
            confirmed=True, expected_revision=self.revision)
        return self.store.manual_reconciliation.accept(**{**args, **updates})

    def test_unknown_delivery_survives_manual_continuation_and_restart_without_resend(self):
        self.send_and_record(Scenario.TIMEOUT_AFTER_SEND)
        before = self.store.ledger.get_attempt(self.attempt)
        record = self.accept(); self.reopen()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt), before)
        self.assertEqual(before.state, AttemptState.UNKNOWN)
        self.assertEqual(self.store.manual_reconciliation.get(self.round.round_id, self.participant), record)
        plan = self.store.ledger.resume(self.attempt)
        self.assertEqual(plan.action, ResumeAction.WAIT_FOR_DECISION)
        self.assertEqual(plan.reason, "MANUAL_CONTINUATION_PRIOR_DELIVERY_UNCHANGED")
        self.assertFalse(plan.automatic_send)
        exported = self.store.export_debate(self.debate.debate_id)
        self.assertEqual(exported["manual_operation_reconciliations"], [record.model_dump(mode="json")])
        self.assertEqual(exported["canonical_results"], [])
        self.assertFalse(exported["debate_completed"])

    def test_prepared_attempt_is_retired_without_becoming_not_sent_or_disappearing(self):
        before = self.store.ledger.get_attempt(self.attempt); self.accept()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt), before)
        self.assertIn(self.intent, self.store.prepared_intents(self.debate.debate_id))
        with self.assertRaises(Conflict): self.store.ledger.begin_send(self.request, expected_revision=self.revision)

    def test_pending_login_allows_explicit_manual_choice_but_keeps_original_state(self):
        self.send_and_record(Scenario.SESSION_EXPIRED)
        before = self.store.ledger.get_attempt(self.attempt); self.accept()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt), before)
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["wait_state"], "ACTIVE")

    def test_nonmanual_or_reused_connection_cannot_replace_the_binding(self):
        for connection in (self.connection, self.connection.model_copy(update={"mode":"MANUAL"})):
            with self.subTest(connection=connection), self.assertRaises(ValueError):self.review(manual_connection=connection)

    def test_unrelated_wait_checkpoint_cannot_be_cleared(self):
        self.send_and_record(Scenario.SESSION_EXPIRED)
        self.store.bind_connection(self.debate.debate_id,self.participant,self.connection,expected_revision=self.revision,
            expected_connection_revision=0,actor="LOCAL_USER_FIXTURE",reason="A separate binding change")
        with self.assertRaises(Conflict):self.review()

    def test_terminal_cli_accepts_only_explicit_choice_at_the_current_hash_and_revision(self):
        review=self.review(); config=self.path.with_name("manual-connection.json")
        config.write_bytes(self.manual.model_dump_json().encode("utf-8"))
        root=Path(__file__).resolve().parents[2]
        command=[sys.executable,str(root/"tools/reconcile_manual.py"),"--database",str(self.path),
            "--revision",str(self.revision),"--debate-id",str(self.debate.debate_id),"--round-id",str(self.round.round_id),
            "--participant-id",str(self.participant),"--manual-connection-file",str(config)]
        cancelled=subprocess.run(command,input=b"yes\n",capture_output=True,timeout=15)
        self.assertEqual(cancelled.returncode,0,cancelled.stderr.decode())
        self.assertEqual(json.loads(cancelled.stdout.decode().splitlines()[-1])["status"],"CANCELLED_NOT_RECONCILED")
        accepted=subprocess.run(command,input=("CONTINUE MANUALLY "+review.content_hash+" R"+str(self.revision)+"\nLogin unavailable\n").encode(),capture_output=True,timeout=15)
        self.assertEqual(accepted.returncode,0,accepted.stderr.decode())
        self.assertEqual(json.loads(accepted.stdout.decode().splitlines()[-1])["status"],"MANUAL_CONTINUATION_PRIOR_DELIVERY_UNCHANGED")

    def test_hash_revision_actor_reason_and_confirmation_are_required_without_partial_write(self):
        review = self.review(); before = self.store.export_debate(self.debate.debate_id)
        for updates in ({"review_hash":"0"*64}, {"expected_revision":self.revision-1},
                {"confirmed":False}, {"actor":" "}, {"reason":" "}):
            with self.subTest(updates=updates), self.assertRaises(ValueError): self.accept(review, **updates)
            self.assertEqual(self.store.export_debate(self.debate.debate_id), before)

    def test_changed_attempt_after_review_requires_fresh_review(self):
        review = self.review(); self.store.ledger.begin_send(self.request, expected_revision=self.revision)
        with self.assertRaises(Conflict): self.accept(review)

    def test_received_validated_and_confirmed_results_cannot_be_replaced(self):
        self.send_and_record()
        for action in (None, "validate_response", "confirm_result"):
            if action: getattr(self.store.ledger, action)(self.attempt, expected_revision=self.revision)
            with self.assertRaises(ValueError): self.review()

    def test_late_response_is_quarantined_without_changing_retired_attempt(self):
        self.store.ledger.begin_send(self.request, expected_revision=self.revision)
        before = self.store.ledger.get_attempt(self.attempt); self.accept()
        late = MockAdapter().send(self.request)
        with self.assertRaises(Conflict): self.store.ledger.record_result(late, expected_revision=self.revision)
        self.reopen()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt), before)
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["rejected_results"][0]["reason"],
            "MANUALLY_RECONCILED_OPERATION")

    def test_second_attempt_or_generation_cannot_reopen_a_manually_retired_slot(self):
        self.accept()
        extra = self.intent.model_copy(update={"identity":OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
            "connection_id":self.manual.connection_id, "connection_revision":1, "expected_revision":self.revision})
        with self.assertRaises(Conflict): self.store.prepare_intent(extra)

    def test_all_prior_operations_in_the_slot_are_reviewed_together(self):
        extra = self.intent.model_copy(update={"identity":OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
            "expected_revision":self.revision})
        self.store.prepare_intent(extra)
        review = self.review(); self.assertEqual(len(review.attempts), 2)
        record = self.accept(review)
        for intent in (self.intent, extra):
            self.assertEqual(self.store.manual_reconciliation.for_operation(intent.identity.logical_operation_id), record)

    def test_deleted_record_and_tampered_record_are_detected_on_restart(self):
        self.accept(); backup = self.path.with_name("valid.sqlite3"); self.store.backup(backup)
        for sql in ("DELETE FROM manual_operation_reconciliations", "UPDATE manual_operation_reconciliations SET record_hash='"+"0"*64+"'"):
            with self.subTest(sql=sql):
                with SQLiteStore(backup) as good: good.backup(self.path.with_name("bad.sqlite3"))
                bad = self.path.with_name("bad.sqlite3")
                with closing(sqlite3.connect(bad, autocommit=True)) as db: db.execute(sql)
                with self.assertRaises(SchemaError): SQLiteStore(bad)
                bad.unlink()

    def test_final_insert_failure_rolls_back_binding_event_wait_state_and_record(self):
        before = self.store.export_debate(self.debate.debate_id)
        self.store._db.execute("CREATE TEMP TRIGGER reject_reconciliation BEFORE INSERT ON manual_operation_reconciliations BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Conflict): self.accept()
        self.assertEqual(self.store.export_debate(self.debate.debate_id), before)

    def test_terminal_eof_wrong_hash_and_blank_reason_cancel_without_mutation(self):
        review = self.review(); before = self.store.export_debate(self.debate.debate_id)
        command = "CONTINUE MANUALLY "+review.content_hash+" R"+str(self.revision)
        for lines in ((),("yes",),(command," ")):
            with self.subTest(lines=lines):
                it=iter(lines)
                result=review_manual_reconciliation(self.store,debate_id=self.debate.debate_id,
                    round_id=self.round.round_id,participant_id=self.participant,expected_revision=self.revision,
                    manual_connection=self.manual,read_line=lambda:next(it),write=lambda x:None)
                self.assertEqual(result["status"],"CANCELLED_NOT_RECONCILED")
                self.assertEqual(self.store.export_debate(self.debate.debate_id),before)

    def test_terminal_explicit_choice_and_reason_create_no_transport_call(self):
        review=self.review(); it=iter(("CONTINUE MANUALLY "+review.content_hash+" R"+str(self.revision),"Login unavailable"))
        result=review_manual_reconciliation(self.store,debate_id=self.debate.debate_id,
            round_id=self.round.round_id,participant_id=self.participant,expected_revision=self.revision,
            manual_connection=self.manual,read_line=lambda:next(it),write=lambda x:None)
        self.assertEqual(result["status"],"MANUAL_CONTINUATION_PRIOR_DELIVERY_UNCHANGED")
        self.assertEqual(result["provider_calls"],0)

    def v8_fixture(self):
        from consilium.shell.schema_v8 import V8_STATEMENTS
        from consilium.shell.schema_v2 import V2_STATEMENTS
        old=[tuple(r) for r in self.store._db.execute("SELECT * FROM schema_migrations WHERE version<=8")]
        self.store.close()
        with closing(sqlite3.connect(self.path,autocommit=True)) as db:
            db.execute("PRAGMA foreign_keys=OFF");db.execute("BEGIN")
            db.execute("DROP TABLE council_records")
            db.execute("DROP TABLE manual_operation_reconciliations")
            for statement in V8_STATEMENTS[:4]:db.execute(statement)
            statement=next(s for s in V2_STATEMENTS if s.startswith("CREATE TABLE rejected_results("))
            db.execute(statement.replace("CREATE TABLE rejected_results(","CREATE TABLE rejected_results_old("))
            db.execute("INSERT INTO rejected_results_old SELECT * FROM rejected_results")
            db.execute("DROP TABLE rejected_results");db.execute("ALTER TABLE rejected_results_old RENAME TO rejected_results")
            db.execute("DELETE FROM schema_migrations WHERE version>=9");db.execute("PRAGMA user_version=8");db.execute("COMMIT")
        return old

    def test_v8_upgrade_preserves_attempt_and_every_published_migration_record(self):
        self.send_and_record(Scenario.TIMEOUT_AFTER_SEND)
        before=self.store.ledger.get_attempt(self.attempt);old=self.v8_fixture();self.store=SQLiteStore(self.path)
        self.assertEqual([tuple(r) for r in self.store._db.execute("SELECT * FROM schema_migrations WHERE version<=8")],old)
        self.assertEqual(self.store.ledger.get_attempt(self.attempt),before)
        self.accept();self.reopen()

    def test_failed_v9_migration_rolls_back_without_changing_v8_history(self):
        from consilium.shell.schema_v9 import V9_STATEMENTS
        old=self.v8_fixture()
        with patch("consilium.shell.storage.V9_STATEMENTS",(*V9_STATEMENTS,"INVALID SQL FIXTURE")),self.assertRaises(SchemaError):SQLiteStore(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0],8)
            self.assertEqual(db.execute("SELECT * FROM schema_migrations").fetchall(),old)
        self.store=SQLiteStore(self.path)

    def crash(self, before_commit):
        review = self.review(); old_revision = self.revision; self.store.close()
        script = '''
import os,sys
from pathlib import Path
from uuid import UUID
from consilium.core.manual_reconciliation import ManualReconciliationReview
from consilium.shell.storage import SQLiteStore
s=SQLiteStore(Path(sys.argv[1])); review=ManualReconciliationReview.model_validate_json(sys.argv[2])
if sys.argv[3]=='before':
 s._db.create_function('stop_process',0,lambda:os._exit(117))
 s._db.execute("CREATE TEMP TRIGGER interrupt_manual_reconciliation BEFORE INSERT ON manual_operation_reconciliations BEGIN SELECT stop_process(); END")
s.manual_reconciliation.accept(review=review,review_hash=review.content_hash,user_action_id=UUID(int=991),actor='LOCAL_USER_FIXTURE',reason='manual fallback',confirmed=True,expected_revision=review.expected_revision)
os._exit(118)
'''
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable,"-c",script,str(self.path),review.model_dump_json(),
            "before" if before_commit else "after"], stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
            env={**os.environ,"PYTHONPATH":str(root/"src")})
        self.assertEqual(result.returncode,117 if before_commit else 118,result.stderr.decode())
        self.store=SQLiteStore(self.path)
        self.assertEqual(self.revision,old_revision if before_commit else old_revision+1)
        record=self.store.manual_reconciliation.get(self.round.round_id,self.participant)
        self.assertEqual(record is None,before_commit)
        binding=self.store.export_debate(self.debate.debate_id)["bindings"][0]
        self.assertEqual(binding["revision"],0 if before_commit else 1)

    def test_process_exit_before_record_commit_rolls_back_entire_manual_reconciliation(self): self.crash(True)
    def test_process_exit_after_commit_preserves_manual_reconciliation_and_prior_attempt(self): self.crash(False)
