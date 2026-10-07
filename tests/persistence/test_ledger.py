"""P02 durable dispatch, immutable results and revision-bound authorization."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from consilium.adapters.mock import MockAdapter, Scenario
from consilium.core.contracts import (
    AdapterCapabilities, AdapterRequest, ConnectionSpec, DebateSpec, Delivery,
    DeliveryObservation, FrozenInput, Message, OperationIdentity, OperationIntent,
    RoundSpec, UserDecision,
)
from consilium.core.operation_states import AttemptState, CapabilityBinding, ResumeAction, transition
from consilium.shell.runner import DurableRunner
from consilium.shell.storage import Conflict, SchemaError, SQLiteStore, V1_STATEMENTS, APPLICATION_ID


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.participant = uuid4()
        self.debate = DebateSpec(debate_id=uuid4(), original_request="  سؤال؛ original\n",
                                 participant_ids=(self.participant,))
        self.round = RoundSpec(round_id=uuid4(), debate_id=self.debate.debate_id, number=1,
                               kind="INDEPENDENT", participant_ids=(self.participant,))
        self.connection = ConnectionSpec(connection_id=uuid4(), provider_id="mock", model_id="mock-v1", mode="API")
        self.store = SQLiteStore(self.path)
        self.store.create_debate(self.debate)
        self.store.register_round(self.round, expected_revision=0)
        self.store.bind_connection(self.debate.debate_id, self.participant, self.connection,
                                   expected_revision=1, expected_connection_revision=None)
        frozen = FrozenInput(messages=(Message(role="USER", content=self.debate.original_request),))
        self.intent = OperationIntent(identity=OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
            debate_id=self.debate.debate_id, round_id=self.round.round_id, participant_id=self.participant,
            connection_id=self.connection.connection_id, expected_revision=2, connection_revision=0,
            frozen_input=frozen, request_hash=frozen.content_hash)
        self.request = AdapterRequest(intent=self.intent, connection=self.connection, timeout_seconds=2.0)
        self.store.prepare_intent(self.intent)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    @property
    def attempt(self):
        return self.intent.identity.attempt_id

    @property
    def revision(self):
        return self.store.checkpoint(self.debate.debate_id).revision

    def reopen(self):
        self.store.close()
        self.store = SQLiteStore(self.path)

    def send_and_record(self, scenario=Scenario.SUCCESS):
        self.store.ledger.begin_send(self.request, expected_revision=self.revision)
        result = MockAdapter(scenario=scenario).send(self.request)
        self.store.ledger.record_result(result, expected_revision=self.revision)
        return result

    def confirm(self):
        result = self.send_and_record()
        self.store.ledger.validate_response(self.attempt, expected_revision=self.revision)
        self.store.ledger.confirm_result(self.attempt, expected_revision=self.revision)
        return result

    def replace_binding(self):
        replacement = self.connection.model_copy(update={"connection_id": uuid4()})
        self.store.bind_connection(self.debate.debate_id, self.participant, replacement,
            expected_revision=self.revision, expected_connection_revision=0,
            actor="test-user", reason="explicit test connection replacement")
        return replacement

    def test_send_cannot_start_without_a_prepared_intent(self):
        new = self.intent.model_copy(update={"identity": OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4())})
        with self.assertRaises(Conflict):
            self.store.ledger.begin_send(self.request.model_copy(update={"intent": new}), expected_revision=self.revision)

    def test_send_start_is_durable_and_reopen_never_calls_provider(self):
        self.store.ledger.begin_send(self.request, expected_revision=3)
        self.reopen()
        record = self.store.ledger.get_attempt(self.attempt)
        self.assertEqual(record.state, AttemptState.SENT)
        self.assertEqual(record.request, self.request)
        self.assertEqual(self.store.ledger.resume(self.attempt).action, ResumeAction.VERIFY_DELIVERY)
        self.assertEqual(self.store.prepared_intents(self.debate.debate_id), ())

    def test_two_workers_cannot_dispatch_the_same_attempt_twice(self):
        self.store.ledger.begin_send(self.request, expected_revision=3)
        with SQLiteStore(self.path) as other:
            with self.assertRaises(Conflict): other.ledger.begin_send(self.request, expected_revision=4)

    def test_dispatch_refuses_modified_frozen_input_or_connection(self):
        changed = self.connection.model_copy(update={"model_id": "different-model"})
        with self.assertRaises(Conflict):
            self.store.ledger.begin_send(self.request.model_copy(update={"connection": changed}), expected_revision=3)
        self.assertEqual(self.revision, 3)

    def test_complete_raw_result_is_not_canonical_until_validated_and_confirmed(self):
        result = self.send_and_record()
        self.reopen()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt).result, result)
        self.assertEqual(self.store.ledger.get_attempt(self.attempt).state, AttemptState.RESPONSE_RECEIVED)
        self.assertIsNone(self.store.ledger.canonical_result(self.intent.identity.logical_operation_id))
        with self.assertRaises(Conflict): self.store.ledger.confirm_result(self.attempt, expected_revision=self.revision)
        self.store.ledger.validate_response(self.attempt, expected_revision=self.revision)
        self.store.ledger.confirm_result(self.attempt, expected_revision=self.revision)
        self.reopen()
        self.assertEqual(self.store.ledger.canonical_result(self.intent.identity.logical_operation_id), result)
        self.assertEqual(self.store.ledger.resume(self.attempt).action, ResumeAction.USE_CONFIRMED_RESULT)

    def test_recording_the_exact_same_result_again_is_a_noop(self):
        result = self.confirm()
        before = self.store.export_debate(self.debate.debate_id)
        self.store.ledger.record_result(result, expected_revision=4)
        self.assertEqual(self.store.export_debate(self.debate.debate_id), before)

    def test_a_conflicting_second_result_is_quarantined_without_replacing_canonical(self):
        result = self.confirm()
        changed = result.model_copy(update={"content": '{"answer":"silently replaced"}'})
        with self.assertRaises(Conflict): self.store.ledger.record_result(changed, expected_revision=self.revision)
        self.assertEqual(self.store.ledger.canonical_result(self.intent.identity.logical_operation_id), result)
        rejected = self.store.export_debate(self.debate.debate_id)["rejected_results"]
        self.assertEqual(rejected[-1]["result"], changed.model_dump(mode="json"))

    def test_late_result_after_connection_change_is_quarantined(self):
        self.store.ledger.begin_send(self.request, expected_revision=3)
        result = MockAdapter().send(self.request)
        replacement = self.replace_binding()
        with self.assertRaises(Conflict): self.store.ledger.record_result(result, expected_revision=4)
        self.assertEqual(self.store.ledger.get_attempt(self.attempt).state, AttemptState.SENT)
        self.assertIsNone(self.store.ledger.canonical_result(self.intent.identity.logical_operation_id))
        exported = self.store.export_debate(self.debate.debate_id)
        self.assertEqual(exported["bindings"][0]["connection"]["connection_id"], str(replacement.connection_id))
        self.assertEqual(exported["rejected_results"][-1]["reason"], "STALE_RESULT")

    def test_new_current_revision_does_not_make_an_old_dispatch_result_current(self):
        self.store.ledger.begin_send(self.request, expected_revision=3)
        result = MockAdapter().send(self.request)
        self.replace_binding()
        with self.assertRaises(Conflict): self.store.ledger.record_result(result, expected_revision=self.revision)

    def test_result_with_foreign_identity_or_hash_is_refused(self):
        self.store.ledger.begin_send(self.request, expected_revision=3)
        result = MockAdapter().send(self.request)
        for change in ({"request_hash": "0"*64}, {"connection_revision": 1},
                       {"identity": OperationIdentity(logical_operation_id=uuid4(), attempt_id=self.attempt)}):
            with self.assertRaises(Conflict):
                self.store.ledger.record_result(result.model_copy(update=change), expected_revision=4)
        self.assertEqual(self.revision, 4)

    def test_response_pending_unknown_partial_invalid_and_login_are_distinct(self):
        expectations = [(Scenario.TIMEOUT_AFTER_SEND, AttemptState.UNKNOWN, ResumeAction.VERIFY_DELIVERY),
            (Scenario.TIMEOUT_AFTER_DELIVERY, AttemptState.RESPONSE_PENDING, ResumeAction.WAIT_FOR_RESPONSE),
            (Scenario.PARTIAL, AttemptState.PARTIAL_RESPONSE, ResumeAction.WAIT_FOR_DECISION),
            (Scenario.INVALID_JSON, AttemptState.INVALID_RESPONSE, ResumeAction.WAIT_FOR_DECISION),
            (Scenario.SESSION_EXPIRED, AttemptState.WAITING_LOGIN, ResumeAction.WAIT_FOR_LOGIN)]
        # Independent databases keep each expectation separate, never overwrite a result.
        for scenario, state, action in expectations:
            with self.subTest(scenario=scenario):
                db = self.path.with_name(scenario.value + ".sqlite3")
                self.store.backup(db)
                with SQLiteStore(db) as branch:
                    branch.ledger.begin_send(self.request, expected_revision=3)
                    result = MockAdapter(scenario=scenario).send(self.request)
                    branch.ledger.record_result(result, expected_revision=4)
                    self.assertEqual(branch.ledger.get_attempt(self.attempt).state, state)
                    self.assertEqual(branch.ledger.resume(self.attempt).action, action)
                    with self.assertRaises(Conflict): branch.ledger.confirm_result(self.attempt, expected_revision=5)

    def test_invalid_json_marked_complete_by_transport_is_not_confirmed(self):
        self.store.ledger.begin_send(self.request, expected_revision=3)
        result = MockAdapter().send(self.request).model_copy(update={"content": '{"answer":broken}'})
        self.store.ledger.record_result(result, expected_revision=4)
        self.store.ledger.validate_response(self.attempt, expected_revision=5)
        self.assertEqual(self.store.ledger.get_attempt(self.attempt).state, AttemptState.INVALID_RESPONSE)
        with self.assertRaises(Conflict): self.store.ledger.confirm_result(self.attempt, expected_revision=6)

    def test_duplicate_json_keys_and_wrong_response_shape_are_rejected(self):
        for content in ['{"answer":"first","answer":"second"}', '{"answer":7}',
                        '{"answer":"ok","decision":"FINISH"}', '{"answer":" "}']:
            with self.subTest(content=content):
                db = self.path.with_name(uuid4().hex + ".sqlite3"); self.store.backup(db)
                with SQLiteStore(db) as branch:
                    branch.ledger.begin_send(self.request, expected_revision=3)
                    result = MockAdapter().send(self.request).model_copy(update={"content": content})
                    branch.ledger.record_result(result, expected_revision=4)
                    branch.ledger.validate_response(self.attempt, expected_revision=5)
                    self.assertEqual(branch.ledger.get_attempt(self.attempt).state, AttemptState.INVALID_RESPONSE)

    def test_invalid_state_transitions_are_rejected(self):
        for state, event in [(AttemptState.PREPARED, "CONFIRM"), (AttemptState.SENT, "CONFIRM"),
                             (AttemptState.CONFIRMED, "SEND"), (AttemptState.UNKNOWN, "SEND")]:
            with self.assertRaises(ValueError): transition(state, event)

    def test_runner_exception_preserves_ambiguity_and_never_automatically_retries(self):
        adapter = MockAdapter()
        with patch.object(adapter, "send", side_effect=TimeoutError("private error not persisted")):
            with self.assertRaises(TimeoutError): DurableRunner(self.store).execute(self.request, adapter, expected_revision=3)
        self.reopen()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt).state, AttemptState.UNKNOWN)
        with self.assertRaises(Conflict): DurableRunner(self.store).execute(self.request, MockAdapter(), expected_revision=self.revision)

    def test_confirmed_result_resume_uses_no_provider_calls(self):
        adapter = MockAdapter()
        DurableRunner(self.store).execute(self.request, adapter, expected_revision=3)
        self.reopen()
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(self.store.ledger.resume(self.attempt).action, ResumeAction.USE_CONFIRMED_RESULT)
        with self.assertRaises(Conflict): DurableRunner(self.store).execute(self.request, adapter, expected_revision=self.revision)
        self.assertEqual(len(adapter.calls), 1)

    def test_decision_gate_cannot_open_for_an_unconfirmed_round(self):
        with self.assertRaises(Conflict):
            self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id, expected_revision=3)

    def test_stale_user_decision_cannot_override_a_new_binding_or_wait_state(self):
        self.confirm()
        self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id, expected_revision=self.revision)
        old_revision = self.revision
        replacement = self.replace_binding()
        decision = UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=old_revision, kind="FINISH")
        before = self.store.export_debate(self.debate.debate_id)
        with self.assertRaises(Conflict): self.store.ledger.record_decision(decision, actor="test-user")
        self.assertEqual(self.store.export_debate(self.debate.debate_id), before)
        self.assertEqual(before["bindings"][0]["connection"]["connection_id"], str(replacement.connection_id))

    def test_finish_waits_for_explicit_judge_and_does_not_complete_debate(self):
        self.confirm()
        self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id, expected_revision=self.revision)
        decision = UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=self.revision, kind="FINISH")
        self.store.ledger.record_decision(decision, actor="test-user")
        exported = self.store.export_debate(self.debate.debate_id)
        self.assertEqual(exported["wait_state"], "WAITING_JUDGE_SELECTION")
        self.assertFalse(exported["debate_completed"])
        with self.assertRaises(Conflict): self.store.ledger.record_decision(decision, actor="test-user")

    def retry_arguments(self):
        observation = DeliveryObservation(identity=self.intent.identity, request_hash=self.intent.request_hash,
            connection_id=self.connection.connection_id, connection_revision=0, delivery=Delivery.NOT_SENT,
            evidence=("UNIT_POLICY_FIXTURE_NOT_LIVE:authoritative negative receipt",))
        capabilities = AdapterCapabilities(mode="API", verification="LIVE_VERIFIED", delivery_probe=True,
            verification_evidence=("UNIT_POLICY_FIXTURE_NOT_LIVE:contract verification",))
        return dict(expected_revision=self.revision, actor="test-user", reason="explicit verified-unsent retry",
                    capabilities=CapabilityBinding(connection=self.connection, connection_revision=0, capabilities=capabilities), observation=observation)

    def test_verified_unsent_retry_has_a_new_attempt_but_preserves_logical_generation_and_input(self):
        self.send_and_record(Scenario.SEND_REJECTED)
        next_id = uuid4()
        self.store.ledger.prepare_retry(self.attempt, next_id, **self.retry_arguments())
        retry = self.store.get_intent(next_id)
        self.assertEqual(retry.identity.logical_operation_id, self.intent.identity.logical_operation_id)
        self.assertEqual(retry.identity.generation_id, self.intent.identity.generation_id)
        self.assertEqual(retry.frozen_input, self.intent.frozen_input)
        self.assertEqual(retry.request_hash, self.intent.request_hash)
        self.assertNotEqual(next_id, self.attempt)
        self.assertEqual(len(self.store.export_debate(self.debate.debate_id)["attempts"]), 2)
        with self.assertRaises(Conflict): self.store.ledger.prepare_retry(self.attempt, uuid4(), **self.retry_arguments())

    def test_retry_denies_missing_reason_unverified_capabilities_and_nonnegative_probe(self):
        self.send_and_record(Scenario.SEND_REJECTED)
        args = self.retry_arguments()
        for change in [{"reason": " "}, {"actor": " "},
                       {"capabilities": args["capabilities"].model_copy(update={"capabilities": AdapterCapabilities(mode="API", delivery_probe=True)})},
                       {"capabilities": args["capabilities"].model_copy(update={"connection_revision": 1})},
                       {"capabilities": args["capabilities"].model_copy(update={"connection": self.connection.model_copy(update={"provider_id": "another-provider"})})},
                       {"observation": args["observation"].model_copy(update={"delivery": Delivery.UNKNOWN})},
                       {"observation": args["observation"].model_copy(update={"evidence": ()})}]:
            with self.assertRaises((Conflict, ValueError)):
                self.store.ledger.prepare_retry(self.attempt, uuid4(), **(args | change))
        self.assertEqual(len(self.store.export_debate(self.debate.debate_id)["attempts"]), 1)

    def test_ambiguous_retry_is_denied_even_if_somebody_supplies_an_unsent_claim(self):
        self.send_and_record(Scenario.TIMEOUT_AFTER_SEND)
        with self.assertRaises(Conflict): self.store.ledger.prepare_retry(self.attempt, uuid4(), **self.retry_arguments())

    def test_retry_after_binding_change_is_denied(self):
        self.send_and_record(Scenario.SEND_REJECTED)
        self.replace_binding()
        with self.assertRaises(Conflict): self.store.ledger.prepare_retry(self.attempt, uuid4(), **self.retry_arguments())

    def test_tampered_result_hash_is_rejected_on_reopen(self):
        self.send_and_record()
        self.store._db.execute("UPDATE transport_results SET result_hash=?", ("0"*64,))
        self.store.close()
        with self.assertRaises(SchemaError): SQLiteStore(self.path)

    def test_no_next_round_without_a_current_continue_decision(self):
        next_round = self.round.model_copy(update={"round_id": uuid4(), "number": 2, "kind": "REVIEW"})
        with self.assertRaises(Conflict): self.store.register_round(next_round, expected_revision=self.revision)
        self.confirm()
        with self.assertRaises(Conflict): self.store.register_round(next_round, expected_revision=self.revision)
        self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id, expected_revision=self.revision)
        decision = UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=self.revision, kind="CONTINUE")
        self.store.ledger.record_decision(decision, actor="test-user")
        self.store.register_round(next_round, expected_revision=self.revision)
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["wait_state"], "ACTIVE")
        with self.assertRaises(Conflict): self.store.prepare_intent(self.intent.model_copy(update={
            "identity": OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()), "expected_revision": self.revision}))

    def test_prepare_and_resume_cannot_authorize_work_after_finish(self):
        self.confirm()
        self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id, expected_revision=self.revision)
        decision = UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=self.revision, kind="FINISH")
        self.store.ledger.record_decision(decision, actor="test-user")
        extra = self.intent.model_copy(update={"identity": OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
                                               "expected_revision": self.revision})
        with self.assertRaises(Conflict): self.store.prepare_intent(extra)

    def test_a_second_dispatch_waits_for_the_first_operation_to_be_resolved(self):
        extra = self.intent.model_copy(update={"identity": OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
                                               "expected_revision": self.revision})
        self.store.prepare_intent(extra)
        self.store.ledger.begin_send(self.request, expected_revision=self.revision)
        request = self.request.model_copy(update={"intent": extra})
        with self.assertRaises(Conflict): self.store.ledger.begin_send(request, expected_revision=self.revision)

    def test_provider_is_called_outside_transaction_and_can_open_a_second_connection(self):
        store, path = self.store, self.path
        class InspectingAdapter(MockAdapter):
            def send(self, request):
                if store._db.in_transaction: raise AssertionError("Transport was called inside transaction")
                with SQLiteStore(path) as other:
                    if other.ledger.get_attempt(request.intent.identity.attempt_id).state != AttemptState.SENT:
                        raise AssertionError("Send-start was not committed")
                return super().send(request)
        DurableRunner(store).execute(self.request, InspectingAdapter(), expected_revision=3)

    def test_stale_unconfirmed_validation_resume_requires_a_decision(self):
        self.send_and_record()
        self.store.ledger.validate_response(self.attempt, expected_revision=self.revision)
        self.replace_binding()
        self.assertEqual(self.store.ledger.resume(self.attempt).action, ResumeAction.WAIT_FOR_DECISION)
        with self.assertRaises(Conflict): self.store.ledger.confirm_result(self.attempt, expected_revision=self.revision)

    def test_retry_can_confirm_one_canonical_response_and_preserves_the_old_unsent_attempt(self):
        self.send_and_record(Scenario.SEND_REJECTED)
        new_id = uuid4(); self.store.ledger.prepare_retry(self.attempt, new_id, **self.retry_arguments())
        retry = self.store.get_intent(new_id)
        request = self.request.model_copy(update={"intent": retry})
        DurableRunner(self.store).execute(request, MockAdapter(), expected_revision=self.revision)
        self.reopen()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt).state, AttemptState.NOT_SENT)
        self.assertEqual(self.store.ledger.canonical_result(self.intent.identity.logical_operation_id).identity.attempt_id, new_id)
        self.assertEqual(len(self.store.export_debate(self.debate.debate_id)["canonical_results"]), 1)

    def test_result_with_known_secret_is_not_persisted(self):
        from consilium.shell.private import PublicBoundaryError
        self.store._forbidden_values = ("test-only-known-secret",)
        self.store.ledger.begin_send(self.request, expected_revision=3)
        result = MockAdapter().send(self.request).model_copy(update={"content": '{"answer":"test-only-known-secret"}'})
        with self.assertRaises(PublicBoundaryError): self.store.ledger.record_result(result, expected_revision=4)
        self.assertEqual(self.revision, 4)
        self.assertEqual(self.store._db.execute("SELECT count(*) FROM transport_results").fetchone()[0], 0)

    def test_current_revision_cannot_reopen_an_old_decision_after_next_round(self):
        self.confirm()
        self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id, expected_revision=self.revision)
        decision = UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=self.revision, kind="CONTINUE")
        self.store.ledger.record_decision(decision, actor="test-user")
        next_round = self.round.model_copy(update={"round_id": uuid4(), "number": 2, "kind": "REVIEW"})
        self.store.register_round(next_round, expected_revision=self.revision)
        with self.assertRaises(Conflict): self.store.ledger.record_decision(decision.model_copy(update={
            "decision_id": uuid4(), "expected_revision": self.revision}), actor="test-user")

    def test_connection_change_invalidates_an_unconsumed_continue_decision(self):
        self.confirm()
        self.store.ledger.wait_for_decision(self.debate.debate_id, self.round.round_id, expected_revision=self.revision)
        self.store.ledger.record_decision(UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=self.revision, kind="CONTINUE"), actor="test-user")
        self.replace_binding()
        next_round = self.round.model_copy(update={"round_id": uuid4(), "number": 2, "kind": "REVIEW"})
        with self.assertRaises(Conflict): self.store.register_round(next_round, expected_revision=self.revision)
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["wait_state"], "WAITING_DECISION")

    def test_resume_does_not_call_another_prepared_attempt_ready_while_send_is_unresolved(self):
        extra = self.intent.model_copy(update={"identity": OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4()),
                                               "expected_revision": self.revision})
        self.store.prepare_intent(extra)
        self.store.ledger.begin_send(self.request, expected_revision=self.revision)
        self.assertEqual(self.store.ledger.resume(extra.identity.attempt_id).action, ResumeAction.WAIT_FOR_DECISION)

    def test_partial_response_does_not_authorize_a_finish_decision(self):
        self.send_and_record(Scenario.PARTIAL)
        decision = UserDecision(decision_id=uuid4(), debate_id=self.debate.debate_id,
            round_id=self.round.round_id, expected_revision=self.revision, kind="FINISH")
        with self.assertRaises(Conflict): self.store.ledger.record_decision(decision, actor="test-user")
        self.assertEqual(self.store.export_debate(self.debate.debate_id)["user_decisions"], [])

    def test_exclusive_new_store_refuses_an_existing_database(self):
        before = self.store.export_debate(self.debate.debate_id)
        with self.assertRaises(FileExistsError): SQLiteStore(self.path, require_new=True)
        self.assertEqual(self.store.export_debate(self.debate.debate_id), before)


class MigrationTests(unittest.TestCase):
    @staticmethod
    def create_populated_v1(path):
        participant = uuid4()
        debate = DebateSpec(debate_id=uuid4(), original_request="  preserved؛ V1\n", participant_ids=(participant,))
        round_spec = RoundSpec(round_id=uuid4(), debate_id=debate.debate_id, number=1, kind="INDEPENDENT", participant_ids=(participant,))
        connection = ConnectionSpec(connection_id=uuid4(), provider_id="mock", model_id="mock-v1", mode="API")
        frozen = FrozenInput(messages=(Message(role="USER", content=debate.original_request),))
        intent = OperationIntent(identity=OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4(), generation_id=uuid4()),
            debate_id=debate.debate_id, round_id=round_spec.round_id, participant_id=participant,
            connection_id=connection.connection_id, expected_revision=2, connection_revision=0,
            frozen_input=frozen, request_hash=frozen.content_hash)
        checksum = "cab17ab34b0eec71991cedb6a945cb9c8743cde08c67891b4a04fe291709d700"
        with closing(sqlite3.connect(path, autocommit=True)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN")
            for sql in V1_STATEMENTS: db.execute(sql)
            db.execute("INSERT INTO schema_migrations VALUES(1,?,?)", (checksum, "historic"))
            db.execute("PRAGMA application_id=" + str(APPLICATION_ID)); db.execute("PRAGMA user_version=1")
            db.execute("INSERT INTO debates VALUES(?,?,0,NULL)", (str(debate.debate_id), debate.model_dump_json()))
            db.execute("INSERT INTO rounds VALUES(?,?,1,?)", (str(round_spec.round_id), str(debate.debate_id), round_spec.model_dump_json()))
            db.execute("INSERT INTO bindings VALUES(?,?,?,0,?)", (str(debate.debate_id), str(participant), str(connection.connection_id), connection.model_dump_json()))
            db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,?)", (str(intent.identity.logical_operation_id), str(debate.debate_id),
                str(round_spec.round_id), str(participant), str(intent.identity.generation_id), intent.request_hash, frozen.canonical_bytes().decode()))
            db.execute("INSERT INTO attempts VALUES(?,?,'PREPARED',?)", (str(intent.identity.attempt_id), str(intent.identity.logical_operation_id), intent.model_dump_json()))
            for revision, kind, payload in [(0,"DEBATE_CREATED",{}), (1,"ROUND_REGISTERED",{}), (2,"CONNECTION_BOUND",{}),
                (3,"OPERATION_PREPARED",{"attempt_id": str(intent.identity.attempt_id), "logical_operation_id": str(intent.identity.logical_operation_id)})]:
                db.execute("INSERT INTO events(debate_id,revision,kind,payload_json,created_at) VALUES(?,?,?,?,?)",
                           (str(debate.debate_id), revision, kind, json.dumps(payload), "historic"))
            db.execute("UPDATE debates SET revision=3,checkpoint_event=4")
            db.execute("COMMIT")
        return debate, intent

    def test_v1_data_and_immutable_migration_hash_survive_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.sqlite3"
            debate, intent = self.create_populated_v1(path)
            old_hash = hashlib.sha256(json.dumps(V1_STATEMENTS, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            self.assertEqual(old_hash, "cab17ab34b0eec71991cedb6a945cb9c8743cde08c67891b4a04fe291709d700")
            with closing(sqlite3.connect(path, autocommit=True)) as db:
                old_events = db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
                old_attempt = db.execute("SELECT * FROM attempts").fetchone()
            with SQLiteStore(path) as store:
                self.assertEqual(store._db.execute("PRAGMA user_version").fetchone()[0], 6)
                self.assertEqual(store._db.execute("SELECT checksum FROM schema_migrations WHERE version=1").fetchone()[0], old_hash)
                self.assertEqual(store._db.execute("SELECT applied_at FROM schema_migrations WHERE version=1").fetchone()[0], "historic")
                self.assertEqual(store.get_debate(debate.debate_id), debate)
                self.assertEqual(store.get_intent(intent.identity.attempt_id), intent)
                self.assertEqual(store.checkpoint(debate.debate_id).revision, 3)
                self.assertEqual([tuple(r) for r in store._db.execute("SELECT * FROM events ORDER BY sequence")], old_events)
                self.assertEqual(tuple(store._db.execute("SELECT attempt_id,logical_operation_id,state,intent_json FROM attempts").fetchone()), old_attempt)
                self.assertEqual(store._db.execute("PRAGMA foreign_key_check").fetchall(), [])
            with SQLiteStore(path) as store:
                self.assertEqual(store.ledger.get_attempt(intent.identity.attempt_id).state, AttemptState.PREPARED)

    def test_failed_v2_upgrade_preserves_populated_v1_data_and_version(self):
        import consilium.shell.storage as storage_module
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.sqlite3"
            self.create_populated_v1(path)
            with closing(sqlite3.connect(path)) as db:
                before = {name: db.execute("SELECT * FROM " + name).fetchall() for name in
                    ["debates","rounds","bindings","operations","attempts","events","schema_migrations"]}
            with patch.object(storage_module, "V2_STATEMENTS", storage_module.V2_STATEMENTS + ("INVALID SQL",)):
                with self.assertRaises(SchemaError): SQLiteStore(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertEqual({name: db.execute("SELECT * FROM " + name).fetchall() for name in before}, before)


class ProcessCrashTests(LedgerTests):
    # Reuse setup/helpers, not inherited test cases, in the loader below.
    def crash_case(self, point, code, state, sends, canonical):
        request_file = self.path.with_name("request.json")
        request_file.write_text(self.request.model_dump_json(), encoding="utf-8")
        remote = self.path.with_name("MOCK_ONLY_remote_receipts.jsonl")
        self.store.close()
        worker = Path(__file__).with_name("dispatch_crash_worker.py")
        proc = subprocess.run([sys.executable, str(worker), str(self.path), str(request_file), str(remote), point],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=20, shell=False)
        self.assertEqual(proc.returncode, code, proc.stderr.decode("utf-8", errors="replace"))
        self.store = SQLiteStore(self.path)
        record = self.store.ledger.get_attempt(self.attempt)
        self.assertEqual(record.state, state)
        self.assertEqual(record.intent, self.intent)
        if state != AttemptState.PREPARED: self.assertEqual(record.request, self.request)
        if record.result is not None: self.assertEqual(record.result.content, '{"answer":"offline mock response"}')
        expected_revision = {95:3,96:4,97:4,98:4,99:4,100:5,101:6,102:6,103:7}[code]
        self.assertEqual(self.store.checkpoint(self.debate.debate_id).revision, expected_revision)
        receipts = remote.read_text(encoding="utf-8").splitlines() if remote.exists() else []
        self.assertEqual(len(receipts), sends)
        if receipts:
            self.assertEqual(json.loads(receipts[0])["request_hash"], self.intent.request_hash)
        self.assertEqual(self.store.ledger.canonical_result(self.intent.identity.logical_operation_id) is not None, canonical)
        export = self.store.export_debate(self.debate.debate_id)
        self.assertEqual(export["checkpoint"]["revision"], export["events"][-1]["revision"])
        self.assertEqual(self.store._db.execute("PRAGMA quick_check").fetchone()[0], "ok")
        # Resume classification is read-only; it cannot send to this simulated remote.
        before = self.store.export_debate(self.debate.debate_id)
        self.store.ledger.resume(self.attempt)
        self.assertEqual(self.store.export_debate(self.debate.debate_id), before)
        self.assertEqual(remote.read_text(encoding="utf-8").splitlines() if remote.exists() else [], receipts)

    def test_process_exit_before_send(self):
        self.crash_case("before_send", 95, AttemptState.PREPARED, 0, False)

    def test_process_exit_after_send_start_before_transport(self):
        self.crash_case("after_send_start", 96, AttemptState.SENT, 0, False)

    def test_process_exit_after_external_mock_send(self):
        self.crash_case("after_external_send", 97, AttemptState.SENT, 1, False)

    def test_process_exit_before_result_persistence(self):
        self.crash_case("before_result", 98, AttemptState.SENT, 1, False)

    def test_process_exit_inside_result_transaction(self):
        self.crash_case("during_result", 99, AttemptState.SENT, 1, False)

    def test_process_exit_after_result_persistence(self):
        self.crash_case("after_result", 100, AttemptState.RESPONSE_RECEIVED, 1, False)

    def test_process_exit_after_validation(self):
        self.crash_case("after_validation", 101, AttemptState.VALIDATED, 1, False)

    def test_process_exit_inside_confirmation_transaction(self):
        self.crash_case("during_confirmation", 102, AttemptState.VALIDATED, 1, False)

    def test_process_exit_after_confirmation(self):
        self.crash_case("after_confirmation", 103, AttemptState.CONFIRMED, 1, True)


def load_tests(loader, standard_tests, pattern):
    # An inherited helper must not inflate evidence by rerunning LedgerTests.
    suite = unittest.TestSuite([loader.loadTestsFromTestCase(LedgerTests), loader.loadTestsFromTestCase(MigrationTests)])
    suite.addTests(ProcessCrashTests(name) for name in ProcessCrashTests.__dict__ if name.startswith("test_"))
    return suite
