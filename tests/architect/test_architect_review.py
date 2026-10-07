import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import UUID

from consilium.core.contracts import DebateSpec
from consilium.core.question_contracts import ArchitectProposal, QuestionSnapshot
from consilium.shell.architect_review import review_candidate
from consilium.shell.storage import SQLiteStore, Conflict

ROOT = Path(__file__).resolve().parents[2]


class ArchitectReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"review.sqlite3"
        self.store = SQLiteStore(self.path)
        self.debate = DebateSpec(debate_id=UUID(int=1), original_request="  پرسش اصلی\n ",
            constraints=("بدون هزینه",), participant_ids=(UUID(int=2),))
        self.store.create_debate(self.debate)
        snapshot = QuestionSnapshot.from_debate(self.debate)
        self.proposal = ArchitectProposal(snapshot_hash=snapshot.content_hash, proposal_version=1,
            optimized_request="پرسش روشن‌تر", constraints_exact=self.debate.constraints,
            constraint_coverage=(0,), assumptions=("فرض آشکار",), visible_changes=("رفع ابهام",), origin="MOCK")
        self.store.questions.record_proposal(self.debate.debate_id, self.proposal, expected_revision=0)
        self.outputs = []

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def phrase(self):
        return "APPROVE "+self.proposal.content_hash+" REVISION 0"

    def review(self, response):
        return review_candidate(self.store, self.debate.debate_id, self.proposal.content_hash,
            expected_revision=0, read_line=lambda:response, write=self.outputs.append)

    def test_exact_confirmation_persists_and_displays_full_comparison(self):
        result=self.review(self.phrase())
        self.assertEqual(result["status"],"ADOPTED")
        display="\n".join(self.outputs)
        self.assertIn("پرسش اصلی",display)
        self.assertIn("پرسش روشن‌تر",display)
        self.assertIn("بدون هزینه",display)
        self.assertIn("فرض آشکار",display)
        self.assertIn('"origin": "MOCK"',display)
        self.assertEqual(self.store.get_debate(self.debate.debate_id).original_request,self.debate.original_request)
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision,1)

    def test_decline_eof_ambiguous_or_wrong_revision_never_approves(self):
        for response in ("", "yes", "APPROVE", "NO", self.phrase().replace("REVISION 0","REVISION 1")):
            with self.subTest(response=response):
                self.assertEqual(self.review(response)["status"],"NOT_ADOPTED")
                self.assertIsNone(self.store.questions.get_adopted(self.debate.debate_id))
                self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision,0)

    def test_terminal_and_bidi_control_characters_are_visible_not_executed(self):
        proposal=self.proposal.model_copy(update={"proposal_version":2,
            "optimized_request":"\x1b[2J\u202e\u009b hidden approval"})
        self.store.questions.record_proposal(self.debate.debate_id,proposal,expected_revision=0)
        review_candidate(self.store,self.debate.debate_id,proposal.content_hash,expected_revision=0,
            read_line=lambda:"",write=self.outputs.append)
        display="\n".join(self.outputs)
        for char in ("\x1b","\u202e","\u009b"):self.assertNotIn(char,display)
        self.assertIn("\\u001b",display)
        self.assertIn("\\u202e",display)

    def test_revision_change_during_review_is_rejected(self):
        from consilium.core.contracts import ConnectionSpec
        def response():
            self.store.bind_connection(self.debate.debate_id,UUID(int=2),
                ConnectionSpec(connection_id=UUID(int=9),provider_id="mock",model_id="mock",mode="API"),
                expected_revision=0,expected_connection_revision=None)
            return self.phrase()
        with self.assertRaises(Conflict):
            review_candidate(self.store,self.debate.debate_id,self.proposal.content_hash,
                expected_revision=0,read_line=response,write=self.outputs.append)
        self.assertIsNone(self.store.questions.get_adopted(self.debate.debate_id))

    def cli(self,response,**updates):
        values=dict(database=str(self.path),debate_id=str(self.debate.debate_id),
                    proposal_hash=self.proposal.content_hash,expected_revision="0")
        values.update(updates)
        argv=[sys.executable,str(ROOT/"tools/review_architect.py")]
        for key,value in values.items():argv.extend(["--"+key.replace("_","-"),value])
        return subprocess.run(argv,input=response.encode("utf-8"),capture_output=True,cwd=ROOT,
            timeout=15,env=os.environ|{"PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"})

    def test_cli_uses_real_sqlite_and_user_input_after_display(self):
        proc=self.cli(self.phrase()+"\n")
        self.assertEqual(proc.returncode,0,proc.stderr.decode())
        result=json.loads(proc.stdout.decode().splitlines()[-1])
        self.assertEqual(result["status"],"ADOPTED")
        self.assertEqual(result["live_provider_calls"],0)
        self.assertIsNotNone(self.store.questions.get_adopted(self.debate.debate_id))

    def test_cli_eof_leaves_state_unchanged(self):
        proc=self.cli("")
        self.assertEqual(proc.returncode,2)
        self.assertIsNone(self.store.questions.get_adopted(self.debate.debate_id))

    def test_cli_invalid_identity_does_not_echo_private_input(self):
        proc=self.cli("",debate_id="PRIVATE_SENTINEL")
        self.assertEqual(proc.returncode,2)
        self.assertNotIn(b"PRIVATE_SENTINEL",proc.stdout+proc.stderr)

    def test_cli_missing_database_is_not_created(self):
        missing=self.path.with_name("missing.sqlite3")
        proc=self.cli("",database=str(missing))
        self.assertEqual(proc.returncode,2)
        self.assertFalse(missing.exists())
