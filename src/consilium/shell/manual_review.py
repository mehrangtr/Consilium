"""Explicit local review phrase bound to content and current revision."""
from uuid import uuid4

from consilium.shell.architect_review import _display


def review_manual_answer(store, candidate_id, *, expected_revision, read_line, write):
    candidate = store.manual_sources.review_snapshot(candidate_id, expected_revision=expected_revision)
    write(_display({"candidate": candidate.model_dump(mode="json"), "candidate_hash": candidate.content_hash,
                    "alignment": candidate.alignment, "provenance": "MANUAL", "external_origin_verified": False,
                    "eligible_for_context": candidate.alignment == "ALIGNED"}))
    phrase = "ACCEPT MANUAL " + candidate.content_hash + " REVISION " + str(expected_revision)
    write("To accept exactly this manual content, type: " + phrase)
    write("External origin remains unverified. DIVERGED content is retained but excluded from round context.")
    try:
        decision = read_line()
    except (EOFError, StopIteration):
        decision = None
    if decision != phrase:
        return {"status": "NOT_ACCEPTED", "provider_calls": 0, "phase_accepted": False}
    record = store.manual_sources.accept_answer(candidate_id, candidate_hash=candidate.content_hash,
        user_action_id=uuid4(), actor="LOCAL_CLI", confirmed=True, expected_revision=expected_revision)
    return {"status": "ACCEPTED", "alignment": record.alignment, "candidate_hash": record.candidate_hash,
            "accepted_revision": record.accepted_revision, "provenance": "MANUAL",
            "external_origin_verified": False, "provider_calls": 0, "phase_accepted": False}
