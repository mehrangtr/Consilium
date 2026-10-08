"""Bind initial context to actual stored state and prepare intent, without send.

Admission facts and intent are committed atomically. These are local
attestations, not proof of live measurements. Policy-managed transport stays
disabled until trusted live observers are implemented in their later phase.
"""
from consilium.core.contracts import ConnectionSpec, GenerationParameters, OperationIdentity, OperationIntent, RoundSpec
from consilium.core.dispatch_policy import evaluate_dispatch_policy
from consilium.core.admission_bundle import AdmissionBundle
from consilium.core.independent_context import IndependentContext, recover_independent_context
from consilium.shell.private import ensure_public_payload
from consilium.shell.storage import Conflict, _revision


def prepare_independent_intent(store, *, context, connection: ConnectionSpec, identity: OperationIdentity,
                               expected_revision: int, expected_connection_revision: int,
                               parameters: GenerationParameters, privacy, budget, history, observation=None, response_contract=None):
    context = IndependentContext.model_validate(context)
    expected_connection_revision = _revision(expected_connection_revision)
    connection = ConnectionSpec.model_validate(connection)
    parameters = GenerationParameters.model_validate(parameters)
    # No user wait or transport inside this short read transaction. The existing
    # prepare_intent write transaction repeats the revision/round/binding guards.
    with store._transaction(write=False):
        store._checked_debate(context.debate_id, expected_revision)
        question = store.questions.get_adopted(context.debate_id)
        if question is None:
            raise Conflict("Initial context requires the adopted question")
        # Inspect semantic source fields as well as serialized messages. JSON
        # escaping can hide newline/quote/backslash secrets from substring checks.
        ensure_public_payload(question.model_dump(mode="json"), store._forbidden_values)
        row = store._db.execute("SELECT spec_json FROM rounds WHERE debate_id=? AND round_id=?",
                                (str(context.debate_id), str(context.round_id))).fetchone()
        if row is None:
            raise Conflict("Context round is not registered")
        round_spec = RoundSpec.model_validate_json(row["spec_json"])
        frozen = recover_independent_context(context, question, round_spec,
            participant_id=context.participant_id, expected_revision=question.adoption.adopted_revision,
            parameters=parameters)
        binding = store._db.execute("SELECT * FROM bindings WHERE debate_id=? AND participant_id=?",
                                    (str(context.debate_id), str(context.participant_id))).fetchone()
        if (binding is None or binding["revision"] != expected_connection_revision
                or ConnectionSpec.model_validate_json(binding["spec_json"]) != connection):
            raise Conflict("Context destination is not the current stored binding")
        ensure_public_payload(frozen.model_dump(mode="json"), store._forbidden_values)
        admission = evaluate_dispatch_policy(context=context, connection=connection, privacy=privacy,
            budget=budget, history=history, expected_revision=expected_revision)
        intent = OperationIntent(identity=identity, debate_id=context.debate_id, round_id=context.round_id,
            participant_id=context.participant_id, connection_id=connection.connection_id,
            expected_revision=expected_revision, connection_revision=expected_connection_revision,
            frozen_input=frozen, request_hash=frozen.content_hash)
        from consilium.core.round_admission import ObservedAdmissionBundle
        bundle_class = AdmissionBundle if observation is None else ObservedAdmissionBundle
        bundle = bundle_class(context=context, connection=connection,
            connection_revision=expected_connection_revision, privacy=privacy, budget=budget,
            history=history, admission=admission, **({} if observation is None else {"observation": observation}))
    return store.prepare_intent(intent, admission_bundle=bundle, response_contract=response_contract), admission


def prepare_round_intent(store, *, debate_id, round_id, participant_id, context,
                         connection, identity, expected_revision, expected_connection_revision,
                         parameters, grants, privacy, budget, history,
                         judge_selection=None, named_authorization=None, observation=None, response_contract=None):
    """Derive all required sources from storage, then atomically persist receipt."""
    from consilium.core.round_admission import RoundAdmissionBundle
    from consilium.core.round_context import RoundContext, recover_round_context
    from consilium.core.dispatch_policy import evaluate_round_dispatch_policy
    context = RoundContext.model_validate(context)
    connection = ConnectionSpec.model_validate(connection)
    parameters = GenerationParameters.model_validate(parameters)
    expected_connection_revision = _revision(expected_connection_revision)
    with store._transaction(write=False):
        debate = store._checked_debate(debate_id, expected_revision)
        question = store.questions.get_adopted(debate_id)
        if question is None:
            raise Conflict("Round context requires the adopted question")
        ensure_public_payload(question.model_dump(mode="json"), store._forbidden_values)
        row = store._db.execute("SELECT spec_json FROM rounds WHERE debate_id=? AND round_id=?",
                                (str(debate_id), str(round_id))).fetchone()
        if row is None:
            raise Conflict("Context round is not registered")
        round_spec = RoundSpec.model_validate_json(row[0])
        sources = tuple(s for s in store.sources.context_sources(debate_id, through_revision=expected_revision)
                        if s.source_round.number < round_spec.number)
        for source in sources:
            ensure_public_payload(source.model_dump(mode="json"), store._forbidden_values)
        required = tuple(s.content_hash for s in sources)
        decision = store.admissions.continuation_for(round_spec)
        ensure_public_payload(decision.model_dump(mode="json"), store._forbidden_values)
        frozen = recover_round_context(context, question=question, debate=debate, round_spec=round_spec,
            participant_id=participant_id, expected_revision=expected_revision, sources=sources,
            required_source_hashes=required, grants=grants, connection=connection, parameters=parameters,
            judge_selection=judge_selection, named_authorization=named_authorization,
            continuation_decision=decision)
        binding = store._db.execute("SELECT spec_json,revision FROM bindings WHERE debate_id=? AND participant_id=?",
                                    (str(debate_id), str(participant_id))).fetchone()
        if (binding is None or binding["revision"] != expected_connection_revision
                or ConnectionSpec.model_validate_json(binding["spec_json"]) != connection):
            raise Conflict("Context destination is not the current stored binding")
        admission = evaluate_round_dispatch_policy(context=context, connection=connection, privacy=privacy,
            budget=budget, history=history, expected_revision=expected_revision)
        intent = OperationIntent(identity=identity, debate_id=debate_id, round_id=round_id,
            participant_id=participant_id, connection_id=connection.connection_id,
            expected_revision=expected_revision, connection_revision=expected_connection_revision,
            frozen_input=frozen, request_hash=frozen.content_hash)
        from consilium.core.round_admission import ObservedRoundAdmissionBundle
        bundle_class = RoundAdmissionBundle if observation is None else ObservedRoundAdmissionBundle
        bundle = bundle_class(context=context, connection=connection,
            connection_revision=expected_connection_revision, sources=sources, required_source_hashes=required,
            grants=grants, continuation_decision=decision, judge_selection=judge_selection, named_authorization=named_authorization,
            privacy=privacy, budget=budget, history=history, admission=admission,
            **({} if observation is None else {"observation": observation}))
    return store.prepare_intent(intent, admission_bundle=bundle, response_contract=response_contract), admission
