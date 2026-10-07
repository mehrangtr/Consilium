"""Explicit local review; response text never supplies acceptance authority."""
from uuid import uuid4
from consilium.shell.architect_review import _display

def review_manual_round(store, candidate_id, *, expected_revision, read_line, write):
    candidate = store.manual_rounds.review_snapshot(candidate_id, expected_revision=expected_revision)
    write(_display({'candidate': candidate.model_dump(mode='json'), 'candidate_hash': candidate.content_hash, 'targets': [t.model_dump(mode='json') for t in candidate.frame.targets], 'alignment': candidate.alignment, 'provenance': 'MANUAL', 'external_origin_verified': False, 'remote_token_or_history_verified': False}))
    phrase = 'ACCEPT MANUAL ROUND ' + candidate.content_hash + ' REVISION ' + str(expected_revision)
    write('To accept exactly this manual content, type: ' + phrase)
    try:
        decision = read_line()
    except (EOFError, StopIteration):
        decision = None
    if decision != phrase:
        return {'status': 'NOT_ACCEPTED', 'provider_calls': 0, 'phase_accepted': False}
    record = store.manual_rounds.accept(candidate_id, candidate_hash=candidate.content_hash, user_action_id=uuid4(), actor='LOCAL_CLI', confirmed=True, expected_revision=expected_revision)
    return {'status': 'ACCEPTED', 'alignment': record.alignment, 'accepted_revision': record.accepted_revision, 'candidate_hash': record.candidate_hash, 'source_count': len(record.sources), 'provenance': 'MANUAL', 'external_origin_verified': False, 'provider_calls': 0, 'phase_accepted': False}
