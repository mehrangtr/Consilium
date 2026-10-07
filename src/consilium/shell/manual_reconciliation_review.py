"""Trusted terminal choice; model text and reviewed hashes never authorize it."""
from uuid import uuid4

from consilium.shell.architect_review import _display


def review_manual_reconciliation(store, *, read_line, write, **args):
    review = store.manual_reconciliation.review(**args)
    write(_display({"review":review.model_dump(mode="json"), "review_hash":review.content_hash,
        "effect":"Retire these local attempts, switch this slot to manual entry and preserve all prior delivery facts.",
        "prior_delivery_reverified":False, "provider_calls":0, "automatic_send":False}))
    command = "CONTINUE MANUALLY " + review.content_hash + " R" + str(review.expected_revision)
    write("Only an explicit local user choice continues. Type this exact line or cancel: " + command)
    try:
        choice = read_line()
        if choice != command:
            return {"status":"CANCELLED_NOT_RECONCILED", "provider_calls":0, "phase_accepted":False}
        write("Enter the reason for this manual continuation:")
        reason = read_line()
        if type(reason) is not str or not reason.strip():
            return {"status":"CANCELLED_NOT_RECONCILED", "provider_calls":0, "phase_accepted":False}
    except (EOFError, StopIteration):
        return {"status":"CANCELLED_NOT_RECONCILED", "provider_calls":0, "phase_accepted":False}
    record = store.manual_reconciliation.accept(review=review, review_hash=review.content_hash,
        user_action_id=uuid4(), actor="LOCAL_USER_CLI", reason=reason, confirmed=True,
        expected_revision=review.expected_revision)
    return {"status":"MANUAL_CONTINUATION_PRIOR_DELIVERY_UNCHANGED", "record_hash":record.content_hash,
        "accepted_revision":record.accepted_revision, "provider_calls":0, "phase_accepted":False}
