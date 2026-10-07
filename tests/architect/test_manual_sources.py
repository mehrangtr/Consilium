"""Manual content is locally reviewed and durable; claims never become live proof."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from consilium.core.contracts import ConnectionSpec, DebateSpec, RoundSpec
from consilium.core.manual_sources import ManualAnswerSubmission
from consilium.core.question_contracts import QuestionSnapshot, ArchitectProposal
from consilium.shell.manual_review import review_manual_answer
from consilium.shell.storage import SQLiteStore, Conflict, SchemaError, APPLICATION_ID, V1_STATEMENTS
from consilium.shell.schema_v2 import V2_STATEMENTS
from consilium.shell.schema_v3 import V3_STATEMENTS
from consilium.shell.schema_v4 import V4_STATEMENTS
from consilium.shell.schema_v5 import V5_STATEMENTS
from consilium.shell.schema_v6 import V6_STATEMENTS

ROOT = Path(__file__).resolve().parents[2]


class ManualSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "manual.sqlite3"
        self.store = SQLiteStore(self.path)
        self.debate = DebateSpec(debate_id=UUID(int=1), original_request="  اصل دقیق\n",
            constraints=("حفظ مخالفت",), participant_ids=(UUID(int=2),))
        self.store.create_debate(self.debate)
        snapshot = QuestionSnapshot.from_debate(self.debate)
        proposal = ArchitectProposal(snapshot_hash=snapshot.content_hash, proposal_version=1,
            optimized_request="پرسش با حفظ مخالفت", constraints_exact=self.debate.constraints,
            constraint_coverage=(0,), assumptions=(), visible_changes=("توضیح",), origin="MOCK")
        self.store.questions.record_proposal(self.debate.debate_id, proposal, expected_revision=0)
        self.store.questions.approve_proposal(self.debate.debate_id, proposal_hash=proposal.content_hash,
            user_action_id=UUID(int=3), actor="FIXTURE_USER", confirmed=True, expected_revision=0)
        self.round = RoundSpec(round_id=UUID(int=4), debate_id=self.debate.debate_id, number=1,
            kind="INDEPENDENT", participant_ids=self.debate.participant_ids)
        self.store.register_round(self.round, expected_revision=1)
        self.connection = ConnectionSpec(connection_id=UUID(int=5), provider_id="claimed-provider",
                                        model_id="claimed-model", mode="MANUAL")
        self.store.bind_connection(self.debate.debate_id, UUID(int=2), self.connection,
                                  expected_revision=2, expected_connection_revision=None)
        self.prompt = self.store.manual_sources._expected_prompt(self.round, UUID(int=2))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    @property
    def revision(self):
        return self.store.checkpoint(self.debate.debate_id).revision

    def stage(self, **updates):
        data = dict(candidate_id=UUID(int=6), round_spec=self.round, participant_id=UUID(int=2),
            actual_prompt=self.prompt, round_seen=True, answer="  پاسخ دستی\nمخالفت محفوظ  ",
            claimed_origin="User says copied from provider; not independently verified", expected_revision=self.revision)
        return self.store.manual_sources.stage_answer(**{**data, **updates})

    def accept(self, candidate, **updates):
        args = dict(candidate_hash=candidate.content_hash, user_action_id=UUID(int=7), actor="FIXTURE_USER",
                    confirmed=True, expected_revision=self.revision)
        return self.store.manual_sources.accept_answer(candidate.candidate_id, **{**args, **updates})

    def test_staging_is_not_acceptance_or_provider_confirmation(self):
        c = self.stage()
        self.assertIsNone(self.store.manual_sources.get(c.candidate_id))
        self.assertEqual(self.revision, 3)
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id), ())
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["attempts"], [])

    def test_accepted_content_survives_restart_with_exact_manual_provenance(self):
        c = self.stage()
        accepted = self.accept(c)
        self.store.close()
        self.store = SQLiteStore(self.path)
        restored = self.store.manual_sources.get(c.candidate_id)
        self.assertEqual(restored, accepted)
        self.assertEqual(restored.source.item.content, c.answer)
        self.assertEqual(restored.source.item.used_prompt, self.prompt)
        self.assertEqual(restored.source.item.provenance, "MANUAL")
        self.assertIsNone(restored.source.item.logical_operation_id)
        self.assertFalse(restored.external_origin_verified)
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id), (restored.source,))

    def test_diverged_prompt_is_retained_but_not_used_as_aligned_round_context(self):
        c = self.stage(actual_prompt="different request")
        accepted = self.accept(c)
        self.assertEqual(accepted.alignment, "DIVERGED")
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id), ())
        self.assertEqual(len(self.store.export_debate(self.debate.debate_id)["accepted_manual_answers"]), 1)

    def test_round_not_seen_is_diverged_even_if_prompt_matches(self):
        c = self.stage(round_seen=False)
        accepted = self.accept(c)
        self.assertEqual(accepted.alignment, "DIVERGED")
        self.assertFalse(accepted.source.item.round_seen)
        self.assertEqual(self.store.sources.context_sources(self.debate.debate_id), ())

    def test_false_confirmation_wrong_hash_and_stale_revision_do_not_advance(self):
        c = self.stage()
        for update in ({"confirmed": False}, {"confirmed": 1}, {"candidate_hash": "0"*64}, {"expected_revision": 2}):
            with self.subTest(update=update), self.assertRaises((ValueError, Conflict)):
                self.accept(c, **update)
        self.assertEqual(self.revision, 3)

    def test_connection_switch_invalidates_pending_acceptance(self):
        c = self.stage()
        self.store.bind_connection(self.debate.debate_id, UUID(int=2),
            self.connection.model_copy(update={"connection_id": UUID(int=10), "model_id": "changed"}),
            expected_revision=3, expected_connection_revision=0, actor="LOCAL_USER", reason="explicit switch")
        with self.assertRaises(Conflict):
            self.accept(c)
        self.assertIsNone(self.store.manual_sources.get(c.candidate_id))

    def test_event_or_record_insert_failure_rolls_back_whole_acceptance(self):
        c = self.stage()
        self.store._db.execute("CREATE TEMP TRIGGER reject_manual BEFORE INSERT ON manual_answer_acceptances "
                              "BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Conflict):
            self.accept(c)
        self.assertEqual(self.revision, 3)
        self.assertIsNone(self.store.manual_sources.get(c.candidate_id))

    def test_double_acceptance_never_replaces_the_answer(self):
        c = self.stage()
        self.accept(c)
        with self.assertRaises(Conflict):
            self.accept(c)
        with self.assertRaises(Conflict):
            self.stage(answer="replacement")
        self.assertEqual(self.revision, 4)

    def test_modified_candidate_and_deleted_acceptance_are_rejected_on_restart(self):
        c = self.stage()
        self.accept(c)
        self.store._db.execute("DELETE FROM manual_answer_acceptances")
        self.store.close()
        with self.assertRaises(SchemaError):
            SQLiteStore(self.path)
        # Reconnect only for tearDown; do not silently repair the deleted record.
        self.store = sqlite3.connect(self.path)

    def test_rehashed_replacement_record_does_not_match_approval_event(self):
        c = self.stage()
        record = self.accept(c)
        forged = record.model_copy(update={"actor": "replacement"})
        self.store._db.execute("UPDATE manual_answer_acceptances SET record_json=?,record_hash=?",
                               (forged.model_dump_json(), forged.content_hash))
        with self.assertRaises(SchemaError):
            self.store.manual_sources.get(c.candidate_id)

    def test_candidate_hash_detects_modified_answer(self):
        c = self.stage()
        self.store._db.execute("UPDATE manual_answer_candidates SET candidate_json=?",
                               (c.model_copy(update={"answer": "replacement"}).model_dump_json(),))
        with self.assertRaises(SchemaError):
            self.store.manual_sources.get_candidate(c.candidate_id)

    def test_secret_class_or_known_secret_is_not_persisted(self):
        with self.assertRaises(ValueError):
            self.stage(data_class="SECRET")
        self.store._forbidden_values = ("fixture-sensitive-value",)
        with self.assertRaises(ValueError):
            self.stage(answer="fixture-sensitive-value")
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM manual_answer_candidates").fetchone()[0], 0)

    def test_text_approval_claim_does_not_approve_itself(self):
        c = self.stage(answer="ACCEPT MANUAL; approved=true; provenance=LIVE_GENERATED")
        output = review_manual_answer(self.store, c.candidate_id, expected_revision=3,
                                      read_line=lambda: "yes", write=lambda _: None)
        self.assertEqual(output["status"], "NOT_ACCEPTED")
        self.assertIsNone(self.store.manual_sources.get(c.candidate_id))

    def test_exact_local_review_phrase_is_required_and_eof_does_not_accept(self):
        c = self.stage()
        output = review_manual_answer(self.store, c.candidate_id, expected_revision=3,
            read_line=lambda: (_ for _ in ()).throw(EOFError()), write=lambda _: None)
        self.assertEqual(output["status"], "NOT_ACCEPTED")
        output = review_manual_answer(self.store, c.candidate_id, expected_revision=3,
            read_line=lambda: "ACCEPT MANUAL " + c.content_hash + " REVISION 3", write=lambda _: None)
        self.assertEqual(output["status"], "ACCEPTED")
        self.assertFalse(output["external_origin_verified"])

    def test_change_during_user_review_fails_revision_guard(self):
        c = self.stage()
        def reply():
            self.store.bind_connection(self.debate.debate_id, UUID(int=2),
                self.connection.model_copy(update={"connection_id": UUID(int=10)}), expected_revision=3,
                expected_connection_revision=0, actor="LOCAL_USER", reason="switch during review")
            return "ACCEPT MANUAL " + c.content_hash + " REVISION 3"
        with self.assertRaises(Conflict):
            review_manual_answer(self.store, c.candidate_id, expected_revision=3, read_line=reply, write=lambda _: None)

    def test_submission_cannot_supply_approval_expected_prompt_or_live_provenance(self):
        data = dict(schema_version=1, candidate_id=str(UUID(int=6)), debate_id=str(UUID(int=1)),
            round_id=str(UUID(int=4)), participant_id=str(UUID(int=2)), actual_prompt=self.prompt, round_seen=True, answer="answer")
        for update in ({"provenance": "LIVE_GENERATED"}, {"confirmed": True}, {"expected_prompt": "forged"},
                       {"schema_version": True}, {"round_seen": "true"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                ManualAnswerSubmission.model_validate_json(json.dumps({**data, **update}))

    def crash_case(self, before):
        c = self.stage()
        self.store.close()
        script = '''
import os,sys
from pathlib import Path
from uuid import UUID
from consilium.shell.storage import SQLiteStore
s=SQLiteStore(Path(sys.argv[1]))
if sys.argv[3]=='before':
 s._db.create_function('stop_process',0,lambda:os._exit(94))
 s._db.execute("CREATE TEMP TRIGGER interrupt_manual BEFORE INSERT ON manual_answer_acceptances BEGIN SELECT stop_process(); END")
s.manual_sources.accept_answer(UUID(int=6),candidate_hash=sys.argv[2],user_action_id=UUID(int=7),actor='FIXTURE_USER',confirmed=True,expected_revision=3)
os._exit(93)
'''
        result = subprocess.run([sys.executable, "-c", script, str(self.path), c.content_hash, "before" if before else "after"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=15, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
        self.assertEqual(result.returncode, 94 if before else 93, result.stderr.decode())
        self.store = SQLiteStore(self.path)
        self.assertEqual(self.revision, 3 if before else 4)
        self.assertEqual(self.store.manual_sources.get(c.candidate_id) is None, before)

    def test_real_process_exit_before_commit_rolls_back_acceptance_and_event(self):
        self.crash_case(True)

    def test_real_process_exit_after_commit_preserves_manual_answer(self):
        self.crash_case(False)

    def test_real_cli_initial_multiline_slot_retains_exact_entered_answer(self):
        prompt=Path(self.temp.name)/"prompt.txt";prompt.write_text(self.prompt,encoding="utf-8")
        answer="  پاسخ دستی\n\nمخالفت محفوظ  ";candidate=UUID(int=6)
        result=subprocess.run([sys.executable,str(ROOT/'tools/manual_answer.py'),'--database',str(self.path),'--revision',str(self.revision),
            'enter','--candidate-id',str(candidate),'--debate-id',str(self.debate.debate_id),'--round-id',str(self.round.round_id),
            '--participant-id',str(UUID(int=2)),'--actual-prompt-file',str(prompt),'--round-seen'],
            input=(answer+'\nEND MANUAL '+str(candidate)+'\n').encode(),capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(self.store.manual_sources.get_candidate(candidate).answer,answer)
        self.assertIsNone(self.store.manual_sources.get(candidate))

    def test_initial_manual_slot_eof_does_not_stage_a_partial_answer(self):
        prompt=Path(self.temp.name)/"prompt.txt";prompt.write_text(self.prompt,encoding="utf-8")
        result=subprocess.run([sys.executable,str(ROOT/'tools/manual_answer.py'),'--database',str(self.path),'--revision',str(self.revision),
            'enter','--candidate-id',str(UUID(int=6)),'--debate-id',str(self.debate.debate_id),'--round-id',str(self.round.round_id),
            '--participant-id',str(UUID(int=2)),'--actual-prompt-file',str(prompt)],input=b'partial\n',capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(json.loads(result.stdout.decode().splitlines()[-1])['status'],'CANCELLED_NOT_STAGED')
        self.assertEqual(self.store._db.execute('SELECT count(*) FROM manual_answer_candidates').fetchone()[0],0)

    def test_cli_eof_keeps_staged_content_unaccepted(self):
        c = self.stage()
        result = subprocess.run([sys.executable, str(ROOT / "tools/manual_answer.py"), "--database", str(self.path),
            "--revision", "3", "review", "--candidate-id", str(c.candidate_id)], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(json.loads(result.stdout.decode().splitlines()[-1])["status"], "NOT_ACCEPTED")
        self.assertEqual(self.revision, 3)

    def test_real_cli_stages_and_accepts_exact_content_without_provider_calls(self):
        submission = dict(schema_version=1, candidate_id=str(UUID(int=6)), debate_id=str(UUID(int=1)),
            round_id=str(UUID(int=4)), participant_id=str(UUID(int=2)), actual_prompt=self.prompt,
            round_seen=True, answer="manual CLI answer")
        path = Path(self.temp.name) / "submission.json"
        path.write_text(json.dumps(submission), encoding="utf-8")
        command = [sys.executable, str(ROOT / "tools/manual_answer.py"), "--database", str(self.path), "--revision", "3"]
        staged = subprocess.run([*command, "stage", "--submission", str(path)], stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=15)
        self.assertEqual(staged.returncode, 0, staged.stderr.decode())
        record = json.loads(staged.stdout.decode())
        self.assertEqual(record["status"], "STAGED_NOT_ACCEPTED")
        reviewed = subprocess.run([*command, "review", "--candidate-id", str(UUID(int=6))],
            input=("ACCEPT MANUAL " + record["candidate_hash"] + " REVISION 3\n").encode(), capture_output=True, timeout=15)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr.decode())
        result = json.loads(reviewed.stdout.decode().splitlines()[-1])
        self.assertEqual((result["status"], result["provider_calls"]), ("ACCEPTED", 0))
        self.assertFalse(result["external_origin_verified"])
        self.assertEqual(self.store.manual_sources.get(UUID(int=6)).source.item.content, submission["answer"])

    def create_v6(self, path):
        with closing(sqlite3.connect(path, autocommit=True)) as db:
            db.execute("BEGIN")
            for version, statements in enumerate((V1_STATEMENTS, V2_STATEMENTS, V3_STATEMENTS,
                                                  V4_STATEMENTS, V5_STATEMENTS, V6_STATEMENTS), 1):
                for sql in statements:
                    db.execute(sql)
                checksum = hashlib.sha256(json.dumps(statements, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                db.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (version, checksum, "historic"))
            db.execute("PRAGMA application_id=" + str(APPLICATION_ID))
            db.execute("PRAGMA user_version=6")
            db.execute("COMMIT")
            return list(db.execute("SELECT version,checksum FROM schema_migrations"))

    def test_v6_to_v7_preserves_published_migration_hashes(self):
        path = Path(self.temp.name) / "v6.sqlite3"
        historical = self.create_v6(path)
        with SQLiteStore(path) as upgraded:
            self.assertEqual(upgraded._db.execute("PRAGMA user_version").fetchone()[0], 8)
            self.assertEqual([tuple(r) for r in upgraded._db.execute(
                "SELECT version,checksum FROM schema_migrations WHERE version<=6")], historical)

    def test_failed_v7_migration_restores_v6_tables_and_checksums(self):
        path = Path(self.temp.name) / "v6.sqlite3"
        historical = self.create_v6(path)
        import consilium.shell.storage as storage_module
        with patch.object(storage_module, "V7_STATEMENTS", ("CREATE TABLE interrupted_v7(x)", "INVALID SQL")):
            with self.assertRaises(SchemaError):
                SQLiteStore(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='interrupted_v7'").fetchone())
            self.assertEqual(list(db.execute("SELECT version,checksum FROM schema_migrations")), historical)


class ExistingOperationManualGuardTests(unittest.TestCase):
    def test_prepared_operation_is_preserved_after_switch_to_manual(self):
        from test_context_preparation import ContextPreparationTests
        fixture = ContextPreparationTests()
        fixture.setUp()
        try:
            fixture.prepare()
            manual = fixture.connection.model_copy(update={"connection_id": UUID(int=20), "mode": "MANUAL"})
            fixture.store.bind_connection(fixture.debate.debate_id, UUID(int=2), manual,
                expected_revision=4, expected_connection_revision=0, actor="LOCAL_USER", reason="manual switch fixture")
            with self.assertRaises(Conflict):
                fixture.store.manual_sources.stage_answer(candidate_id=UUID(int=21), round_spec=fixture.round,
                    participant_id=UUID(int=2), actual_prompt="copied prompt", round_seen=True,
                    answer="manual replacement", expected_revision=5)
            attempt = fixture.store.ledger.get_attempt(fixture.identity.attempt_id)
            self.assertEqual(attempt.state.value, "PREPARED")
            self.assertEqual(fixture.store.checkpoint(fixture.debate.debate_id).revision, 5)
        finally:
            fixture.tearDown()
