"""Local interactive user boundary; never invoked by provider text parsing."""
from __future__ import annotations

import difflib
import json
import unicodedata
from uuid import UUID, uuid4
from typing import Callable


def _display(data: dict) -> str:
    # JSON quotes C0/newlines. Also expose C1, bidi and invisible format controls
    # so candidate text cannot erase or visually replace the trusted UI prompt.
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    return "".join(json.dumps(c, ensure_ascii=True)[1:-1] if (0x7f <= ord(c) <= 0x9f or
        c in "\u2028\u2029" or (unicodedata.category(c) == "Cf" and c not in "\u200c\u200d")) else c for c in text)


def review_candidate(store, debate_id: UUID, proposal_hash: str, *, expected_revision: int,
                     read_line: Callable[[], str], write: Callable[[str], None]) -> dict:
    snapshot, proposal = store.questions.review_snapshot(debate_id, proposal_hash,
                                                         expected_revision=expected_revision)
    diff = tuple(difflib.unified_diff(snapshot.original_request_exact.splitlines(keepends=True),
        proposal.optimized_request.splitlines(keepends=True), fromfile="original", tofile="candidate"))
    write(_display({"original_request_exact": snapshot.original_request_exact,
        "optimized_request": proposal.optimized_request, "constraints_exact": snapshot.constraints_exact,
        "assumptions": proposal.assumptions, "visible_changes": proposal.visible_changes,
        "origin": proposal.origin, "proposal_version": proposal.proposal_version,
        "text_diff": diff}))
    phrase = "APPROVE " + proposal.content_hash + " REVISION " + str(expected_revision)
    write("To adopt this exact candidate, type: " + phrase)
    write("Any other response or end of input keeps the original question unchanged.")
    if read_line() != phrase:
        return {"status": "NOT_ADOPTED", "live_provider_calls": 0, "phase_accepted": False}
    adopted = store.questions.approve_proposal(debate_id, proposal_hash=proposal.content_hash,
        user_action_id=uuid4(), actor="LOCAL_CLI", confirmed=True, expected_revision=expected_revision)
    return {"status": "ADOPTED", "proposal_hash": proposal.content_hash,
            "adopted_revision": adopted.adoption.adopted_revision,
            "live_provider_calls": 0, "phase_accepted": False}
