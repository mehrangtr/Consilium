"""Trusted local user boundary; provider response parsing must not call approval.

Candidates are immutable artifacts bound to an existing checkpoint, not active
debate state. Only adoption changes debate state and advances its event ledger.
"""
from uuid import UUID
import json

from consilium.core.question_contracts import (
    AdoptedQuestion, ArchitectProposal, PromptAdoption, QuestionSnapshot, adopt_proposal,
)
from consilium.shell.storage import Conflict, SchemaError, _identifier


class QuestionLedger:
    def __init__(self, store):
        self.store = store
        self._db = store._db

    def _before_rounds(self, debate_id):
        if self._db.execute("SELECT 1 FROM rounds WHERE debate_id=?", (str(debate_id),)).fetchone():
            raise Conflict("Architect adoption is only allowed before the first round")

    def record_proposal(self, debate_id: UUID, proposal: ArchitectProposal, *, expected_revision: int):
        proposal = ArchitectProposal.model_validate(proposal)
        with self.store._transaction():
            debate = self.store._checked_debate(debate_id, expected_revision)
            self._before_rounds(debate_id)
            if self.get_adopted(debate_id) is not None:
                raise Conflict("Question is already adopted")
            snapshot = QuestionSnapshot.from_debate(debate.model_copy(update={"revision": expected_revision}))
            if proposal.snapshot_hash != snapshot.content_hash or proposal.constraints_exact != snapshot.constraints_exact:
                raise ValueError("Candidate does not preserve its question snapshot")
            checkpoint = self.store.checkpoint(debate_id)
            self._db.execute("INSERT INTO architect_proposals VALUES(?,?,?,?,?,?,?)", (
                proposal.content_hash, str(debate_id), proposal.proposal_version,
                self.store._public(snapshot.model_dump(mode="json")),
                self.store._public(proposal.model_dump(mode="json")), expected_revision, checkpoint.event_sequence))
            return checkpoint

    def _candidate(self, debate_id, proposal_hash):
        row = self._db.execute("SELECT * FROM architect_proposals WHERE debate_id=? AND proposal_hash=?",
                               (_identifier(debate_id), proposal_hash)).fetchone()
        if row is None:
            raise Conflict("Architect candidate is not registered")
        snapshot = QuestionSnapshot.model_validate_json(row["snapshot_json"])
        proposal = ArchitectProposal.model_validate_json(row["proposal_json"])
        debate = self.store.get_debate(debate_id)
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["checkpoint_sequence"],)).fetchone()
        if (snapshot.debate_id != debate_id or snapshot.original_request_exact != debate.original_request
                or snapshot.constraints_exact != debate.constraints or snapshot.source_revision != row["source_revision"]
                or proposal.content_hash != row["proposal_hash"] or proposal.proposal_version != row["proposal_version"]
                or proposal.snapshot_hash != snapshot.content_hash or proposal.constraints_exact != snapshot.constraints_exact
                or event is None or event["debate_id"] != str(debate_id) or event["revision"] != snapshot.source_revision):
            raise SchemaError("Stored architect candidate is inconsistent")
        return snapshot, proposal

    def approve_proposal(self, debate_id: UUID, *, proposal_hash: str, user_action_id: UUID,
                         actor: str, confirmed: bool, expected_revision: int) -> AdoptedQuestion:
        # The caller is a local user action handler, never a model-output parser.
        if confirmed is not True or type(actor) is not str or not actor.strip():
            raise ValueError("Explicit trusted local user confirmation is required")
        _identifier(user_action_id)
        with self.store._transaction():
            self.store._checked_debate(debate_id, expected_revision)
            self._before_rounds(debate_id)
            if self.get_adopted(debate_id) is not None:
                raise Conflict("Question is already adopted")
            snapshot, proposal = self._candidate(debate_id, proposal_hash)
            approval = PromptAdoption(proposal_hash=proposal_hash, trusted_user_action_id=user_action_id,
                                      adopted_revision=expected_revision+1)
            adopted = adopt_proposal(snapshot, proposal, approval, expected_revision=expected_revision)
            payload = self.store._public(adopted.model_dump(mode="json"))
            self.store._public({"actor": actor})
            checkpoint = self.store._advance(debate_id, expected_revision, "QUESTION_ADOPTED",
                {"proposal_hash": proposal_hash, "user_action_id": str(user_action_id), "actor": actor})
            self._db.execute("INSERT INTO question_adoptions VALUES(?,?,?,?,?,?)", (
                str(debate_id), proposal_hash, str(user_action_id), actor, payload, checkpoint.event_sequence))
            return adopted

    def review_snapshot(self, debate_id: UUID, proposal_hash: str, *, expected_revision: int):
        """Read one immutable candidate at the revision the user will approve."""
        with self.store._transaction(write=False):
            self.store._checked_debate(debate_id, expected_revision)
            self._before_rounds(debate_id)
            if self.get_adopted(debate_id) is not None:
                raise Conflict("Question is already adopted")
            snapshot, proposal = self._candidate(debate_id, proposal_hash)
            if snapshot.source_revision != expected_revision:
                raise Conflict("Candidate belongs to a stale question revision")
            return snapshot, proposal

    def get_adopted(self, debate_id: UUID) -> AdoptedQuestion | None:
        if not self._db.in_transaction:
            with self.store._transaction(write=False):
                return self.get_adopted(debate_id)
        row = self._db.execute("SELECT * FROM question_adoptions WHERE debate_id=?", (_identifier(debate_id),)).fetchone()
        if row is None:
            return None
        adopted = AdoptedQuestion.model_validate_json(row["adopted_json"])
        snapshot, proposal = self._candidate(debate_id, row["proposal_hash"])
        event = self._db.execute("SELECT * FROM events WHERE sequence=?", (row["event_sequence"],)).fetchone()
        expected = {"proposal_hash": row["proposal_hash"], "user_action_id": row["user_action_id"], "actor": row["actor"]}
        if (adopted.original != snapshot or adopted.proposal != proposal
                or str(adopted.adoption.trusted_user_action_id) != row["user_action_id"]
                or event is None or event["kind"] != "QUESTION_ADOPTED" or event["debate_id"] != str(debate_id)
                or event["revision"] != adopted.adoption.adopted_revision or json.loads(event["payload_json"]) != expected):
            raise SchemaError("Stored question adoption is inconsistent")
        return adopted

    def check_integrity(self):
        try:
            for row in self._db.execute("SELECT debate_id,proposal_hash FROM architect_proposals").fetchall():
                self._candidate(UUID(row["debate_id"]), row["proposal_hash"])
            for row in self._db.execute("SELECT debate_id FROM question_adoptions").fetchall():
                self.get_adopted(UUID(row["debate_id"]))
            orphan = self._db.execute("SELECT 1 FROM events e LEFT JOIN question_adoptions a "
                "ON a.event_sequence=e.sequence WHERE e.kind='QUESTION_ADOPTED' AND a.debate_id IS NULL").fetchone()
            if orphan:
                raise SchemaError("Adoption event has no committed adoption record")
        except (ValueError, TypeError, KeyError) as exc:
            raise SchemaError("Architect storage integrity check failed") from None

    def export_fields(self, debate_id):
        candidates = []
        for row in self._db.execute("SELECT proposal_hash FROM architect_proposals WHERE debate_id=? "
                "ORDER BY proposal_version", (_identifier(debate_id),)).fetchall():
            snapshot, proposal = self._candidate(debate_id, row["proposal_hash"])
            candidates.append({"snapshot": snapshot.model_dump(mode="json"),
                               "proposal": proposal.model_dump(mode="json"), "proposal_hash": proposal.content_hash})
        adopted = self.get_adopted(debate_id)
        return {"architect_candidates": candidates,
                "adopted_question": None if adopted is None else adopted.model_dump(mode="json")}
