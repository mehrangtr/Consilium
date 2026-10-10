"""Bounded, read-only output imports. Hash integrity is not origin authenticity."""
import hashlib
import json

from .contracts import DebateSpec, UserDecision
from .council_contracts import FinalCouncilResult, RoundAnalysis
from .round_context import ContextSource

MAX_JSON_BYTES = 32 * 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON member')
        result[key] = value
    return result


def read_json(raw):
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('Export JSON exceeds size limit')
    def reject_constant(value):
        raise ValueError('Nonfinite JSON constant')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid UTF-8 or excessive JSON nesting') from exc


def validate_snapshot(snapshot):
    """Validate renderable identities/references, preserving all machine history."""
    if not isinstance(snapshot, dict) or type(snapshot.get('schema_version')) is not int or snapshot['schema_version'] != 2:
        raise ValueError('Unsupported debate snapshot schema')
    required = ('debate', 'checkpoint', 'council_sources', 'user_decisions',
                'round_analyses', 'final_council_result', 'wait_state', 'debate_completed')
    if any(key not in snapshot for key in required):
        raise ValueError('Incomplete council snapshot')
    # JSON validation preserves strict UUID/tuple semantics of the product contracts.
    def model(cls, value):
        return cls.model_validate_json(json.dumps(value, ensure_ascii=False, allow_nan=False))
    debate = model(DebateSpec, snapshot['debate'])
    checkpoint = snapshot['checkpoint']
    revision = checkpoint.get('revision')
    if checkpoint.get('debate_id') != str(debate.debate_id) or type(revision) is not int or revision < 0:
        raise ValueError('Checkpoint identity/revision mismatch')
    if not isinstance(snapshot['wait_state'], str) or type(snapshot['debate_completed']) is not bool:
        raise ValueError('Invalid completion state')
    hashes = set()
    for row in snapshot['council_sources']:
        source = model(ContextSource, {k: v for k, v in row.items() if k != 'content_hash'})
        author = getattr(source.item, 'participant_id', getattr(source.item, 'reviewer_id', None))
        if (source.source_round.debate_id != debate.debate_id or author not in debate.participant_ids
                or source.source_revision > revision or source.content_hash != row.get('content_hash')
                or source.content_hash in hashes):
            raise ValueError('Source identity/hash/revision mismatch')
        hashes.add(source.content_hash)
    for row in snapshot['round_analyses']:
        analysis = model(RoundAnalysis, row)
        if analysis.debate_id != debate.debate_id or not set(analysis.source_hashes) <= hashes:
            raise ValueError('Analysis source mismatch')
    for row in snapshot['user_decisions']:
        decision = model(UserDecision, row['decision'])
        if decision.debate_id != debate.debate_id or decision.expected_revision > revision:
            raise ValueError('User decision identity/revision mismatch')
    final = snapshot['final_council_result']
    if bool(final) != snapshot['debate_completed']:
        raise ValueError('Completion requires final result')
    if final:
        result = model(FinalCouncilResult, final)
        if (result.debate_id != debate.debate_id or result.completed_revision > revision
                or result.judge.participant_id not in debate.participant_ids
                or result.judge_source_hash not in hashes
                or snapshot['wait_state'] != 'COMPLETED'
                or not set(result.input_source_hashes) <= hashes):
            raise ValueError('Final identity/reference mismatch')
    return snapshot


def import_snapshot(raw, *, expected_sha256, confirmed):
    """Explicit hash-bound import returns data only; never dispatches or mutates DB."""
    if confirmed is not True or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Explicit confirmation and matching expected hash required')
    return validate_snapshot(read_json(raw))
