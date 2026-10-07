import tempfile
import os
import subprocess
import sys
import sqlite3
import hashlib
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from uuid import UUID
from consilium.core.contracts import DebateSpec
from consilium.core.question_contracts import QuestionSnapshot, ArchitectProposal
from consilium.shell.storage import SQLiteStore, Conflict, SchemaError, APPLICATION_ID, V1_STATEMENTS
from consilium.shell.schema_v2 import V2_STATEMENTS


class QuestionStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "question.sqlite3"
        self.store = SQLiteStore(self.path)
        self.debate = DebateSpec(debate_id=UUID(int=1), original_request="  اصل\n  ",
            constraints=("بدون هزینه",), participant_ids=(UUID(int=2),))
        self.store.create_debate(self.debate)
        self.snapshot = QuestionSnapshot.from_debate(self.debate)
        self.proposal = ArchitectProposal(snapshot_hash=self.snapshot.content_hash, proposal_version=1,
            optimized_request="پرسش بهبود یافته", constraints_exact=self.debate.constraints,
            constraint_coverage=(0,), assumptions=(), visible_changes=("توضیح",), origin="MOCK")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def record(self):
        return self.store.questions.record_proposal(self.debate.debate_id, self.proposal, expected_revision=0)

    def approve(self, **updates):
        args=dict(proposal_hash=self.proposal.content_hash, user_action_id=UUID(int=3),
            actor="local-user", confirmed=True, expected_revision=0)
        args.update(updates)
        return self.store.questions.approve_proposal(self.debate.debate_id, **args)

    def test_candidate_does_not_approve_itself_or_change_original(self):
        self.record()
        self.assertIsNone(self.store.questions.get_adopted(self.debate.debate_id))
        self.assertEqual(self.store.get_debate(self.debate.debate_id), self.debate)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 0)

    def test_approval_survives_reopen_and_advances_checkpoint(self):
        self.record()
        adopted = self.approve()
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 1)
        self.store.close()
        self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.questions.get_adopted(self.debate.debate_id), adopted)
        self.assertEqual(self.store.get_debate(self.debate.debate_id), self.debate)

    def test_false_confirmation_and_stale_revision_do_not_write(self):
        self.record()
        for update in ({"confirmed": False}, {"confirmed": 1}, {"expected_revision": 1},
                       {"actor": "  "}, {"user_action_id": UUID(int=0)}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.approve(**update)
        self.assertIsNone(self.store.questions.get_adopted(self.debate.debate_id))
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 0)

    def test_missing_candidate_and_second_adoption_rejected(self):
        with self.assertRaises(Conflict): self.approve()
        self.record()
        self.approve()
        with self.assertRaises(Conflict): self.approve(expected_revision=1)

    def test_wrong_snapshot_and_changed_constraint_not_recorded(self):
        for update in ({"snapshot_hash": "0"*64}, {"constraints_exact": ("replacement",)}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.store.questions.record_proposal(self.debate.debate_id,
                    self.proposal.model_copy(update=update), expected_revision=0)

    def test_duplicate_version_cannot_replace_candidate(self):
        self.record()
        with self.assertRaises(Conflict):
            self.store.questions.record_proposal(self.debate.debate_id,
                self.proposal.model_copy(update={"optimized_request":"replacement"}), expected_revision=0)

    def test_event_failure_rolls_back_adoption_and_revision(self):
        self.record()
        self.store._db.execute("CREATE TEMP TRIGGER refuse_adoption BEFORE INSERT ON events "
            "WHEN NEW.kind='QUESTION_ADOPTED' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(Conflict): self.approve()
        self.assertIsNone(self.store.questions.get_adopted(self.debate.debate_id))
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 0)

    def test_tampered_candidate_prevents_reopen(self):
        self.record()
        self.store._db.execute("UPDATE architect_proposals SET proposal_json=?",
            (self.proposal.model_copy(update={"optimized_request":"replacement"}).model_dump_json(),))
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_export_keeps_candidate_and_exact_original_after_adoption(self):
        self.record()
        adopted=self.approve()
        exported=self.store.export_debate(self.debate.debate_id)
        self.assertEqual(exported["adopted_question"],adopted.model_dump(mode="json"))
        self.assertEqual(exported["debate"]["original_request"],self.debate.original_request)
        self.assertEqual(exported["architect_candidates"][0]["proposal_hash"],self.proposal.content_hash)

    def test_orphan_adoption_event_prevents_reopen(self):
        self.record()
        self.approve()
        self.store._db.execute("DELETE FROM question_adoptions")
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_adoption_after_round_registration_rejected(self):
        from consilium.core.contracts import RoundSpec
        self.record()
        self.store.register_round(RoundSpec(round_id=UUID(int=5), debate_id=self.debate.debate_id,
            number=1, kind="INDEPENDENT", participant_ids=self.debate.participant_ids), expected_revision=0)
        with self.assertRaises(Conflict): self.approve(expected_revision=1)

    def crash_case(self, before_commit):
        self.record()
        self.store.close()
        script = '''
import os,sys
from pathlib import Path
from uuid import UUID
from consilium.shell.storage import SQLiteStore
s=SQLiteStore(Path(sys.argv[1]))
if sys.argv[3]=='before':
 s._db.create_function('stop_process',0,lambda:os._exit(92))
 s._db.execute("CREATE TEMP TRIGGER interrupt_adoption BEFORE INSERT ON question_adoptions BEGIN SELECT stop_process(); END")
s.questions.approve_proposal(UUID(int=1),proposal_hash=sys.argv[2],user_action_id=UUID(int=3),actor='local-user',confirmed=True,expected_revision=0)
os._exit(91)
'''
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, "-c", script, str(self.path), self.proposal.content_hash,
            "before" if before_commit else "after"], stdin=subprocess.DEVNULL, capture_output=True,
            timeout=15, env={**os.environ, "PYTHONPATH": str(root/"src")})
        self.assertEqual(result.returncode, 92 if before_commit else 91, result.stderr.decode())
        self.store = SQLiteStore(self.path)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, 0 if before_commit else 1)
        self.assertEqual(self.store.questions.get_adopted(self.debate.debate_id) is None, before_commit)

    def test_process_exit_before_commit_rolls_back_event_and_adoption(self):
        self.crash_case(True)

    def test_process_exit_after_commit_preserves_adoption(self):
        self.crash_case(False)

    def create_v2(self, path):
        db=sqlite3.connect(path,autocommit=True)
        db.execute("BEGIN")
        for version, statements in ((1,V1_STATEMENTS),(2,V2_STATEMENTS)):
            for sql in statements: db.execute(sql)
            checksum=hashlib.sha256(json.dumps(statements,ensure_ascii=False,sort_keys=True,
                separators=(",",":"),allow_nan=False).encode()).hexdigest()
            db.execute("INSERT INTO schema_migrations VALUES(?,?,?)",(version,checksum,"historic"))
        db.execute("PRAGMA application_id="+str(APPLICATION_ID))
        db.execute("PRAGMA user_version=2")
        db.execute("INSERT INTO debates(debate_id,spec_json,revision,checkpoint_event) VALUES(?,?,0,NULL)",
            (str(self.debate.debate_id),self.debate.model_dump_json()))
        db.execute("INSERT INTO events(debate_id,revision,kind,payload_json,created_at) VALUES(?,0,'DEBATE_CREATED','{}','historic')",
            (str(self.debate.debate_id),))
        db.execute("UPDATE debates SET checkpoint_event=1")
        db.execute("COMMIT")
        db.close()

    def test_v2_upgrade_preserves_original_and_history(self):
        path=self.path.with_name("v2.sqlite3")
        self.create_v2(path)
        with SQLiteStore(path) as upgraded:
            self.assertEqual(upgraded.get_debate(self.debate.debate_id),self.debate)
            self.assertEqual(upgraded.checkpoint(self.debate.debate_id).revision,0)
            self.assertEqual(upgraded._db.execute("PRAGMA user_version").fetchone()[0],4)
            self.assertEqual(upgraded._db.execute("SELECT COUNT(*) FROM schema_migrations WHERE applied_at='historic'").fetchone()[0],2)

    def test_failed_v3_upgrade_preserves_v2(self):
        import consilium.shell.storage as storage_module
        path=self.path.with_name("v2.sqlite3")
        self.create_v2(path)
        with patch.object(storage_module,"V3_STATEMENTS",storage_module.V3_STATEMENTS+("INVALID SQL",)):
            with self.assertRaises(SchemaError): SQLiteStore(path)
        db=sqlite3.connect(path)
        try:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0],2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='architect_proposals'").fetchone()[0],0)
        finally: db.close()
