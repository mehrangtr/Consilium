"""Bind initial context to actual stored state and prepare intent, without send.

Admission attestations are checked but not yet durably stored. A live dispatcher
must preserve/revalidate their evidence and remote history before transport.
The existing MOCK-only demo is a separate foundation path.
"""
from consilium.core.contracts import ConnectionSpec, GenerationParameters, OperationIdentity, OperationIntent, RoundSpec
from consilium.core.dispatch_policy import evaluate_dispatch_policy
from consilium.core.independent_context import IndependentContext, recover_independent_context
from consilium.shell.private import ensure_public_payload
from consilium.shell.storage import Conflict, _revision


def prepare_independent_intent(store, *, context, connection: ConnectionSpec, identity: OperationIdentity,
                               expected_revision: int, expected_connection_revision: int,
                               parameters: GenerationParameters, privacy, budget, history):
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
    return store.prepare_intent(intent), admission
