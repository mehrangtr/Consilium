"""Stage a checked architect response; never adopt it or send a request."""
from consilium.core.architect_request import ArchitectRequest, build_architect_request, parse_architect_response
from consilium.core.question_contracts import QuestionSnapshot
from consilium.shell.private import ensure_public_payload
from consilium.shell.storage import Conflict


def stage_architect_response(store, *, request, content, origin, expected_revision):
    request = ArchitectRequest.model_validate(request)
    with store._transaction(write=False):
        debate = store._checked_debate(request.snapshot.debate_id,expected_revision)
        snapshot = QuestionSnapshot.from_debate(debate)
        expected = build_architect_request(snapshot,proposal_version=request.proposal_version,
                                          parameters=request.frozen_input.parameters)
        if request != expected:
            raise Conflict("Architect request differs from its current question snapshot")
        ensure_public_payload(snapshot.model_dump(mode="json"),store._forbidden_values)
        candidate = parse_architect_response(content,request,origin=origin)
        ensure_public_payload(candidate.model_dump(mode="json"),store._forbidden_values)
    store.questions.record_proposal(snapshot.debate_id,candidate,expected_revision=expected_revision)
    return candidate
