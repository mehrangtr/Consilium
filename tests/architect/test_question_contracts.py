import unittest
from uuid import UUID

from pydantic import ValidationError
from consilium.core.contracts import DebateSpec
from consilium.core.question_contracts import (
    QuestionSnapshot, ArchitectProposal, PromptAdoption, adopt_proposal,
)


class QuestionContractsTests(unittest.TestCase):
    def setUp(self):
        self.debate = DebateSpec(debate_id=UUID(int=1), participant_ids=(UUID(int=2),),
                                original_request="  پرسش\nدقیق؟  ", constraints=(" فارسی ", "بدون هزینه"))
        self.snapshot = QuestionSnapshot.from_debate(self.debate)
        self.proposal = ArchitectProposal(snapshot_hash=self.snapshot.content_hash,
            proposal_version=1, optimized_request="پرسش روشن‌تر", constraints_exact=self.debate.constraints,
            constraint_coverage=(0, 1), assumptions=(), visible_changes=("رفع ابهام",), origin="MOCK")

    def test_exact_original_and_constraints_survive_json(self):
        restored = QuestionSnapshot.model_validate_json(self.snapshot.model_dump_json())
        self.assertEqual(restored.original_request_exact.encode(), self.debate.original_request.encode())
        self.assertEqual(restored.constraints_exact, self.debate.constraints)
        self.assertEqual(restored.content_hash, self.snapshot.content_hash)

    def test_snapshot_is_immutable(self):
        with self.assertRaises(ValidationError):
            self.snapshot.original_request_exact = "replacement"

    def test_hash_binds_identity_revision_and_exact_whitespace(self):
        for update in ({"source_revision": 1}, {"original_request_exact": "پرسش\nدقیق؟"},
                       {"debate_id": UUID(int=9)}):
            self.assertNotEqual(self.snapshot.content_hash, self.snapshot.model_copy(update=update).content_hash)

    def test_missing_duplicate_and_out_of_range_coverage_rejected(self):
        for coverage in ((0,), (0, 0), (0, 2), (1, 0)):
            with self.subTest(coverage=coverage), self.assertRaises(ValidationError):
                self.proposal.model_copy(update={"constraint_coverage": coverage})

    def test_extra_fields_and_bool_version_rejected(self):
        for update in ({"approved": True}, {"proposal_version": True}, {"proposal_version": 0}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                self.proposal.model_copy(update=update)

    def approval(self):
        return PromptAdoption(proposal_hash=self.proposal.content_hash, trusted_user_action_id=UUID(int=3),
                              adopted_revision=1)

    def test_explicit_adoption_preserves_original(self):
        adopted = adopt_proposal(self.snapshot, self.proposal, self.approval(), expected_revision=0)
        self.assertEqual(adopted.original, self.snapshot)
        self.assertEqual(adopted.effective_request, self.proposal.optimized_request)
        self.assertEqual(adopted.constraints_exact, self.debate.constraints)
        self.assertEqual(self.debate.original_request, "  پرسش\nدقیق؟  ")

    def test_no_implicit_adoption(self):
        with self.assertRaises(TypeError):
            adopt_proposal(self.snapshot, self.proposal, expected_revision=0)

    def test_stale_revision_and_wrong_proposal_hash_rejected(self):
        with self.assertRaises(ValueError):
            adopt_proposal(self.snapshot, self.proposal, self.approval(), expected_revision=1)
        with self.assertRaises(ValueError):
            adopt_proposal(self.snapshot, self.proposal,
                self.approval().model_copy(update={"proposal_hash": "0" * 64}), expected_revision=0)

    def test_changed_constraints_and_wrong_snapshot_rejected(self):
        for update in ({"constraints_exact": ("changed", "بدون هزینه")}, {"snapshot_hash": "0" * 64}):
            proposal = self.proposal.model_copy(update=update)
            approval = self.approval().model_copy(update={"proposal_hash": proposal.content_hash})
            with self.subTest(update=update), self.assertRaises(ValueError):
                adopt_proposal(self.snapshot, proposal, approval, expected_revision=0)

    def test_revision_must_advance_exactly_once(self):
        with self.assertRaises(ValueError):
            adopt_proposal(self.snapshot, self.proposal,
                self.approval().model_copy(update={"adopted_revision": 2}), expected_revision=0)
