"""Trusted local reconstruction and a registered OFFLINE observation driver.

No live driver is registered here. P08/P09 must supply real endpoint tokenizers,
full remote-history readers and capabilities before policy-managed sends open.
Provider text is never parsed into an observer, permission or conversation choice.
"""
import hashlib
from uuid import UUID

from consilium.core.contracts import ConnectionSpec, Message, RoundSpec
from consilium.core.context_observations import (
    HistorySnapshot, ObservationReceipt, OBSERVER_ID, TOKENIZER_ID,
    OBSERVER_IMPLEMENTATION_HASH, MOCK_CONTEXT_CAPACITY,
    check_history, mock_wire, observe_sources, validate_observation,
)
from consilium.core.dispatch_policy import HistoryEvidence, PrivacyDecision, TokenBudget, PolicyBlocked, destination_hash
from consilium.core.independent_context import IndependentContext, recover_independent_context
from consilium.core.round_context import RoundContext, recover_round_context
from consilium.shell.private import ensure_public_payload
from consilium.shell.storage import Conflict


def authorized_transcript(store, *, context, connection, through_revision):
    """Only this participant's positively confirmed, same-binding past attempts.

    Missing/ambiguous/partial results do not authorize a remembered transcript.
    A full remote snapshot must match exactly; hidden peers are not tolerated.
    """
    entries = []
    rows = store._db.execute("SELECT a.attempt_id FROM canonical_results c "
        "JOIN attempts a USING(attempt_id) JOIN operations o USING(logical_operation_id) "
        "JOIN rounds r ON r.round_id=o.round_id "
        "WHERE o.debate_id=? AND o.participant_id=? AND c.confirmed_revision<=? "
        "AND r.number<=(SELECT number FROM rounds WHERE round_id=?) ORDER BY c.confirmed_revision",
        (str(context.debate_id), str(context.participant_id), through_revision, str(context.round_id))).fetchall()
    for row in rows:
        record = store.ledger.get_attempt(UUID(row[0]))
        if record.request is None or record.request.connection != connection:
            continue
        result = store.ledger.canonical_result(record.intent.identity.logical_operation_id)
        if result is None or result.content is None:
            raise Conflict("Authorized transcript requires a canonical complete response")
        entries.extend(record.intent.frozen_input.messages)
        entries.append(Message(role="ASSISTANT", content=result.content))
    return tuple(entries)


def validate_stored_observation(store, bundle, intent):
    """Reconstruct local provenance/history; does not re-certify a remote page."""
    receipt = getattr(bundle, "observation", None)
    if receipt is None:
        return
    sources = getattr(bundle, "sources", ())
    validate_observation(receipt, context=bundle.context, connection=bundle.connection,
        privacy=bundle.privacy, budget=bundle.budget, history=bundle.history,
        expected_revision=intent.expected_revision, sources=sources)
    check_history(snapshot=receipt.history_snapshot, connection=bundle.connection, debate_id=intent.debate_id,
        authorized_entries=authorized_transcript(store, context=bundle.context, connection=bundle.connection,
                                                through_revision=intent.expected_revision),
        new_topic=receipt.new_topic, preference=receipt.preference, user_action_id=receipt.user_action_id)


def observe_context(*, store, context, connection, expected_revision, expected_connection_revision,
                    privacy, snapshot, new_topic, preference, user_action_id, grants=(),
                    judge_selection=None, named_authorization=None):
    connection = ConnectionSpec.model_validate(connection)
    # Registration is application code, not supplied by a provider JSON field.
    if connection.provider_id != "mock" or connection.model_id != "mock-v1":
        raise PolicyBlocked("OBSERVER_NOT_REGISTERED")
    context = (IndependentContext if isinstance(context, IndependentContext) else RoundContext).model_validate(context)
    privacy = PrivacyDecision.model_validate(privacy)
    snapshot = HistorySnapshot.model_validate(snapshot)
    with store._transaction(write=False):
        debate = store._checked_debate(context.debate_id, expected_revision)
        question = store.questions.get_adopted(context.debate_id)
        if question is None:
            raise Conflict("Observation requires the adopted question")
        row = store._db.execute("SELECT spec_json FROM rounds WHERE round_id=? AND debate_id=?",
            (str(context.round_id), str(context.debate_id))).fetchone()
        if row is None:
            raise Conflict("Observation requires the registered round")
        round_spec = RoundSpec.model_validate_json(row[0])
        binding = store._db.execute("SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?",
            (str(context.debate_id), str(context.participant_id))).fetchone()
        if (binding is None or binding["revision"] != expected_connection_revision
                or ConnectionSpec.model_validate_json(binding["spec_json"]) != connection):
            raise Conflict("Observation destination is stale")
        sources = ()
        if isinstance(context, IndependentContext):
            frozen = recover_independent_context(context, question, round_spec, participant_id=context.participant_id,
                expected_revision=question.adoption.adopted_revision, parameters=context.frozen_input.parameters)
        else:
            sources = tuple(s for s in store.sources.context_sources(context.debate_id, through_revision=expected_revision)
                            if s.source_round.number < round_spec.number)
            frozen = recover_round_context(context, question=question, debate=debate, round_spec=round_spec,
                participant_id=context.participant_id, expected_revision=expected_revision, sources=sources,
                required_source_hashes=tuple(s.content_hash for s in sources), grants=grants, connection=connection,
                parameters=context.frozen_input.parameters, judge_selection=judge_selection,
                named_authorization=named_authorization, continuation_decision=store.admissions.continuation_for(round_spec))
        for value in (question, frozen, snapshot, *sources):
            ensure_public_payload(value.model_dump(mode="json"), store._forbidden_values)
        expected = dict(view_hash=context.content_hash, request_hash=frozen.content_hash,
            destination_hash=destination_hash(connection), ledger_revision=expected_revision)
        if (any(getattr(privacy, k) != v for k, v in expected.items())
                or privacy.decision != "ALLOW" or privacy.contains_secret is not False):
            raise PolicyBlocked("PRIVACY_NOT_CLEARED")
        state = check_history(snapshot=snapshot, connection=connection, debate_id=context.debate_id,
            authorized_entries=authorized_transcript(store, context=context, connection=connection, through_revision=expected_revision),
            new_topic=new_topic, preference=preference, user_action_id=user_action_id)
        wire = mock_wire(frozen, snapshot)
        receipt = ObservationReceipt(**expected, observer_id=OBSERVER_ID, observer_implementation_hash=OBSERVER_IMPLEMENTATION_HASH,
            tokenizer_id=TOKENIZER_ID, wire_hash=hashlib.sha256(wire).hexdigest(), token_count=len(wire),
            history_snapshot=snapshot, new_topic=new_topic, preference=preference, user_action_id=user_action_id,
            sources=observe_sources(sources))
        budget = TokenBudget(**expected, measurement="EXACT", input_tokens=len(wire), transport_overhead_tokens=0,
            reserved_output_tokens=frozen.parameters.max_output_tokens, context_capacity=MOCK_CONTEXT_CAPACITY)
        history = HistoryEvidence(**expected, debate_id=context.debate_id, state=state,
            conversation_id=snapshot.conversation_id, new_topic=new_topic)
        return receipt, budget, history
