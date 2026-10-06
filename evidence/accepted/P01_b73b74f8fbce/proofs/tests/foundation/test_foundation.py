"""Independent negative and behavioral tests for the P01 foundation."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from pydantic import ValidationError

from consilium.core.contracts import (
    AdapterCapabilities, AdapterRequest, Answer, ConnectionSpec, Critique,
    DebateSpec, Delivery, DeliveryObservation, Failure, FrozenInput,
    GenerationParameters, Message, OperationIdentity, OperationIntent,
    Participant, PeerPoint, ResponseState, RoundSpec, TransportResult, UserDecision,
)
from consilium.ports.adapter import Adapter
from consilium.adapters.mock import MockAdapter, Scenario
from consilium.shell.private import PrivateBindings, PublicBoundaryError, ensure_public_payload


def identity():
    return OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4())


def request(mode="API", *, prompt="سؤال آزمایشی", timeout=2.0, frozen=None, ids=None):
    connection = ConnectionSpec(connection_id=uuid4(), provider_id="mock", model_id="mock-v1", mode=mode)
    frozen = frozen or FrozenInput(messages=(Message(role="USER", content=prompt),))
    intent = OperationIntent(identity=ids or identity(), debate_id=uuid4(), round_id=uuid4(),
                             participant_id=uuid4(), connection_id=connection.connection_id,
                             expected_revision=0, connection_revision=0, frozen_input=frozen,
                             request_hash=frozen.content_hash)
    return AdapterRequest(intent=intent, connection=connection, timeout_seconds=timeout)


class ContractTests(unittest.TestCase):
    def test_operation_identity_is_not_content_hash(self):
        frozen = FrozenInput(messages=(Message(role="USER", content="same input"),))
        first, second = request(frozen=frozen), request(frozen=frozen)
        self.assertEqual(first.intent.request_hash, second.intent.request_hash)
        self.assertNotEqual(first.intent.identity.logical_operation_id, second.intent.identity.logical_operation_id)

    def test_retry_preserves_logical_identity_and_changes_attempt(self):
        first = identity()
        retry = OperationIdentity(logical_operation_id=first.logical_operation_id,
                                  attempt_id=uuid4(), generation_id=first.generation_id)
        self.assertEqual(first.logical_operation_id, retry.logical_operation_id)
        self.assertNotEqual(first.attempt_id, retry.attempt_id)

    def test_generation_identity_is_independent(self):
        value = OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4(), generation_id=uuid4())
        self.assertEqual(len({value.logical_operation_id, value.attempt_id, value.generation_id}), 3)

    def test_reused_identity_fields_are_rejected(self):
        value = uuid4()
        with self.assertRaises(ValidationError):
            OperationIdentity(logical_operation_id=value, attempt_id=value)

    def test_nil_identity_is_rejected(self):
        with self.assertRaises(ValidationError):
            OperationIdentity(logical_operation_id=UUID(int=0), attempt_id=uuid4())

    def test_frozen_input_cannot_be_mutated(self):
        frozen = request().intent.frozen_input
        with self.assertRaises(ValidationError):
            frozen.messages = ()
        with self.assertRaises(ValidationError):
            frozen.messages[0].content = "replacement"

    def test_model_copy_does_not_bypass_validation(self):
        with self.assertRaises(ValidationError):
            request().intent.model_copy(update={"expected_revision": -1})

    def test_hash_changes_when_generation_parameters_change(self):
        left = FrozenInput(messages=(Message(role="USER", content="hello"),))
        right = FrozenInput(messages=left.messages, parameters=GenerationParameters(max_output_tokens=100))
        self.assertNotEqual(left.content_hash, right.content_hash)

    def test_hash_preserves_exact_prompt_bytes(self):
        self.assertNotEqual(request(prompt="hello").intent.request_hash,
                            request(prompt="hello ").intent.request_hash)

    def test_hash_is_reproducible_after_json_round_trip(self):
        original = request(prompt="سلام؛ English")
        restored = AdapterRequest.model_validate_json(original.model_dump_json())
        self.assertEqual(original, restored)
        self.assertEqual(original.intent.frozen_input.content_hash, restored.intent.frozen_input.content_hash)

    def test_schema_version_cannot_be_boolean(self):
        with self.assertRaises(ValidationError):
            FrozenInput(schema_version=True, messages=(Message(role="USER", content="hello"),))

    def test_mismatched_request_hash_is_rejected(self):
        value = request().intent.model_dump(mode="python")
        value["request_hash"] = "0" * 64
        with self.assertRaises(ValidationError):
            OperationIntent.model_validate(value)

    def test_unrelated_connection_cannot_receive_intent(self):
        original = request()
        other = ConnectionSpec(connection_id=uuid4(), provider_id="mock", model_id="mock-v1", mode="API")
        with self.assertRaises(ValidationError):
            AdapterRequest(intent=original.intent, connection=other, timeout_seconds=2.0)

    def test_strings_and_booleans_are_not_revision_numbers(self):
        for bad in ("0", True, -1):
            with self.assertRaises(ValidationError):
                request().intent.model_copy(update={"expected_revision": bad})

    def test_empty_messages_are_rejected(self):
        with self.assertRaises(ValidationError):
            FrozenInput(messages=())

    def test_blank_prompt_is_rejected_without_echoing_input(self):
        with self.assertRaises(ValidationError):
            Message(role="USER", content=" \n ")

    def test_non_finite_generation_parameter_is_rejected(self):
        for bad in (float("nan"), float("inf"), -1.0, 3.0):
            with self.assertRaises(ValidationError):
                GenerationParameters(temperature=bad)

    def test_duplicate_debate_participants_are_rejected(self):
        p = uuid4()
        with self.assertRaises(ValidationError):
            DebateSpec(debate_id=uuid4(), original_request="question", participant_ids=(p, p))

    def test_blind_review_is_default(self):
        debate = DebateSpec(debate_id=uuid4(), original_request="question", participant_ids=(uuid4(),))
        self.assertEqual(debate.review_visibility, "BLIND")

    def test_targeted_round_requires_target(self):
        with self.assertRaises(ValidationError):
            RoundSpec(round_id=uuid4(), debate_id=uuid4(), number=2, kind="TARGETED", participant_ids=(uuid4(),))

    def test_custom_decision_requires_instruction(self):
        with self.assertRaises(ValidationError):
            UserDecision(decision_id=uuid4(), debate_id=uuid4(), round_id=uuid4(), expected_revision=1, kind="CUSTOM")

    def test_non_custom_decision_cannot_smuggle_instruction(self):
        with self.assertRaises(ValidationError):
            UserDecision(decision_id=uuid4(), debate_id=uuid4(), round_id=uuid4(), expected_revision=1,
                         kind="FINISH", instruction="choose a different judge")

    def test_critique_requires_reason_and_real_numeric_score(self):
        data = dict(critique_id=uuid4(), debate_id=uuid4(), round_id=uuid4(), reviewer_id=uuid4(),
                    target_answer_id=uuid4(), points=(PeerPoint(verdict="REJECT", reference="claim-1", reason="unsupported"),),
                    score=6, scoring_reason="two claims ungrounded", rubric_version="test-v1")
        self.assertEqual(Critique(**data).score, 6)
        for bad in (True, "6", 0, 11):
            with self.assertRaises(ValidationError):
                Critique(**{**data, "score": bad})
        with self.assertRaises(ValidationError):
            PeerPoint(verdict="REJECT", reference="claim-1", reason=" ")

    def test_manual_answer_records_actual_prompt_and_round_visibility(self):
        answer = Answer(answer_id=uuid4(), debate_id=uuid4(), round_id=uuid4(), participant_id=uuid4(),
                        content="manual text", provenance="MANUAL", used_prompt="actual prompt", round_seen=False)
        self.assertFalse(answer.round_seen)
        self.assertEqual(answer.used_prompt, "actual prompt")
        with self.assertRaises(ValidationError):
            Answer(answer_id=uuid4(), debate_id=uuid4(), round_id=uuid4(), participant_id=uuid4(),
                   content="text", provenance="MANUAL")

    def test_complete_result_cannot_claim_unknown_delivery(self):
        req = request()
        with self.assertRaises(ValidationError):
            TransportResult(identity=req.intent.identity, request_hash=req.intent.request_hash,
                            connection_id=req.connection.connection_id, connection_revision=0,
                            delivery=Delivery.UNKNOWN, response_state=ResponseState.COMPLETE, content="answer")

    def test_empty_complete_response_is_rejected(self):
        req = request()
        with self.assertRaises(ValidationError):
            TransportResult(identity=req.intent.identity, request_hash=req.intent.request_hash,
                            connection_id=req.connection.connection_id, connection_revision=0,
                            delivery=Delivery.CONFIRMED, response_state=ResponseState.COMPLETE, content=" ")

    def test_invalid_response_failure_requires_an_invalid_received_response(self):
        req = request()
        with self.assertRaises(ValidationError):
            TransportResult(identity=req.intent.identity, request_hash=req.intent.request_hash,
                            connection_id=req.connection.connection_id, connection_revision=0,
                            delivery=Delivery.CONFIRMED, response_state=ResponseState.NONE,
                            failure=Failure.INVALID_RESPONSE)

    def test_capabilities_cannot_silently_claim_live_verification(self):
        with self.assertRaises(ValidationError):
            AdapterCapabilities(mode="BROWSER", verification="LIVE_VERIFIED", delivery_probe=True)

    def test_schema_generation_for_all_contracts(self):
        for model in (Participant, ConnectionSpec, DebateSpec, RoundSpec, Answer, PeerPoint, Critique,
                      UserDecision, OperationIdentity, Message, GenerationParameters, FrozenInput, OperationIntent, AdapterCapabilities,
                      AdapterRequest, TransportResult, DeliveryObservation):
            schema = model.model_json_schema()
            self.assertEqual(schema["additionalProperties"], False)


class AdapterTests(unittest.TestCase):
    def test_mock_satisfies_the_adapter_protocol(self):
        self.assertIsInstance(MockAdapter(), Adapter)

    def test_mock_does_not_advertise_unimplemented_operations(self):
        for mode in ("API", "BROWSER"):
            capabilities = MockAdapter(mode=mode).capabilities
            self.assertFalse(capabilities.continuation)
            self.assertFalse(capabilities.streaming)

    def test_api_success_binds_result_to_request(self):
        req, adapter = request(), MockAdapter()
        result = adapter.send(req)
        self.assertEqual(result.identity, req.intent.identity)
        self.assertEqual(result.request_hash, req.intent.request_hash)
        self.assertEqual(result.connection_id, req.connection.connection_id)
        self.assertEqual(result.delivery, Delivery.CONFIRMED)
        self.assertEqual(result.response_state, ResponseState.COMPLETE)

    def test_browser_success_has_browser_capabilities(self):
        adapter = MockAdapter(mode="BROWSER")
        self.assertEqual(adapter.send(request("BROWSER")).response_state, ResponseState.COMPLETE)
        self.assertTrue(adapter.capabilities.delivery_probe)
        self.assertFalse(adapter.capabilities.idempotency)
        self.assertEqual(adapter.capabilities.verification, "DECLARED_MOCK")

    def test_wrong_transport_mode_is_rejected_before_recording_send(self):
        adapter = MockAdapter(mode="BROWSER")
        with self.assertRaises(ValueError):
            adapter.send(request("API"))
        self.assertEqual(adapter.calls, ())

    def test_timeout_before_send_is_provably_not_sent(self):
        result = MockAdapter(scenario=Scenario.TIMEOUT_BEFORE_SEND).send(request())
        self.assertEqual(result.delivery, Delivery.NOT_SENT)
        self.assertEqual(result.failure, Failure.TIMEOUT)

    def test_timeout_after_send_stays_unknown(self):
        result = MockAdapter(scenario=Scenario.TIMEOUT_AFTER_SEND).send(request())
        self.assertEqual(result.delivery, Delivery.UNKNOWN)
        self.assertEqual(result.response_state, ResponseState.NONE)
        self.assertIsNone(result.content)

    def test_timeout_after_delivery_preserves_confirmed_delivery(self):
        result = MockAdapter(scenario=Scenario.TIMEOUT_AFTER_DELIVERY).send(request())
        self.assertEqual(result.delivery, Delivery.CONFIRMED)
        self.assertEqual(result.response_state, ResponseState.NONE)
        self.assertEqual(result.failure, Failure.TIMEOUT)

    def test_partial_response_does_not_become_complete(self):
        result = MockAdapter(scenario=Scenario.PARTIAL).send(request())
        self.assertEqual(result.delivery, Delivery.CONFIRMED)
        self.assertEqual(result.response_state, ResponseState.PARTIAL)
        self.assertEqual(result.failure, Failure.TIMEOUT)

    def test_invalid_json_is_a_received_but_invalid_response(self):
        result = MockAdapter(scenario=Scenario.INVALID_JSON).send(request())
        self.assertEqual(result.delivery, Delivery.CONFIRMED)
        self.assertEqual(result.response_state, ResponseState.INVALID)
        self.assertEqual(result.failure, Failure.INVALID_RESPONSE)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(result.content)

    def test_expired_session_does_not_send(self):
        result = MockAdapter(scenario=Scenario.SESSION_EXPIRED).send(request())
        self.assertEqual(result.delivery, Delivery.NOT_SENT)
        self.assertEqual(result.failure, Failure.SESSION_EXPIRED)

    def test_quota_rejection_does_not_send(self):
        result = MockAdapter(scenario=Scenario.QUOTA).send(request())
        self.assertEqual(result.delivery, Delivery.NOT_SENT)
        self.assertEqual(result.failure, Failure.QUOTA)

    def test_delayed_response_uses_virtual_time(self):
        req = request(timeout=5.0)
        result = MockAdapter(scenario=Scenario.DELAYED, latency_seconds=3.0).send(req)
        self.assertEqual(result.response_state, ResponseState.COMPLETE)
        self.assertEqual(result.elapsed_seconds, 3.0)

    def test_delayed_response_past_deadline_is_pending(self):
        result = MockAdapter(scenario=Scenario.DELAYED, latency_seconds=3.0).send(request(timeout=2.0))
        self.assertEqual(result.response_state, ResponseState.NONE)
        self.assertEqual(result.delivery, Delivery.CONFIRMED)
        self.assertEqual(result.elapsed_seconds, 2.0)

    def test_unknown_observation_does_not_trigger_retry(self):
        adapter, req = MockAdapter(scenario=Scenario.TIMEOUT_AFTER_SEND), request()
        adapter.send(req)
        self.assertEqual(adapter.probe(req).delivery, Delivery.UNKNOWN)
        self.assertEqual(len(adapter.calls), 1)

    def test_unseen_attempt_cannot_be_proved_not_sent(self):
        self.assertEqual(MockAdapter().probe(request()).delivery, Delivery.UNKNOWN)

    def test_probe_cannot_rebind_a_recorded_attempt_to_a_new_connection(self):
        adapter, original = MockAdapter(), request()
        adapter.send(original)
        other_connection = original.connection.model_copy(update={"connection_id": uuid4()})
        other_intent = original.intent.model_copy(update={"connection_id": other_connection.connection_id})
        forged = AdapterRequest(intent=other_intent, connection=other_connection, timeout_seconds=2.0)
        with self.assertRaises(ValueError):
            adapter.probe(forged)

    def test_probe_cannot_rebind_a_recorded_attempt_to_new_input(self):
        adapter, original = MockAdapter(), request()
        adapter.send(original)
        frozen = FrozenInput(messages=(Message(role="USER", content="different prompt"),))
        changed = original.intent.model_copy(update={"frozen_input": frozen, "request_hash": frozen.content_hash})
        forged = AdapterRequest(intent=changed, connection=original.connection, timeout_seconds=2.0)
        with self.assertRaises(ValueError):
            adapter.probe(forged)

    def test_probe_keeps_frozen_request_hash(self):
        adapter, req = MockAdapter(), request()
        adapter.send(req)
        self.assertEqual(adapter.probe(req).request_hash, req.intent.request_hash)

    def test_same_attempt_cannot_be_sent_twice(self):
        adapter, req = MockAdapter(), request()
        adapter.send(req)
        with self.assertRaises(ValueError):
            adapter.send(req)
        self.assertEqual(len(adapter.calls), 1)

    def test_all_scenarios_execute_without_network(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
             patch("time.sleep", side_effect=AssertionError("real sleep forbidden")):
            for scenario in Scenario:
                MockAdapter(scenario=scenario).send(request())


class PrivateBoundaryTests(unittest.TestCase):
    def test_credentials_are_not_fields_in_public_connection(self):
        data = request().connection.model_dump(mode="python")
        marker = "fake-sensitive-value-for-negative-test"
        for name in ("api_key", "password", "cookies", "profile_path"):
            with self.assertRaises(ValidationError) as caught:
                ConnectionSpec.model_validate({**data, name: marker})
            self.assertNotIn(marker, str(caught.exception))

    def test_environment_secret_is_not_in_repr_or_public_spec(self):
        marker = "fake-sensitive-value-for-test"
        binding = PrivateBindings(environment={"CONSILIUM_TEST_CREDENTIAL": marker})
        secret = binding.read_environment_secret("CONSILIUM_TEST_CREDENTIAL")
        self.assertNotIn(marker, repr(secret))
        self.assertNotIn(marker, str(secret))
        self.assertEqual(secret.reveal_for_transport(), marker)
        self.assertNotIn(marker, request().connection.model_dump_json())

    def test_private_profile_must_be_outside_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            binding = PrivateBindings(environment={})
            with self.assertRaises(ValueError):
                binding.profile_path(source, source / "profiles", uuid4())
            path = binding.profile_path(source, Path(temp) / "private", uuid4())
            self.assertFalse(path.is_relative_to(source))
            self.assertFalse(path.exists())

    def test_existing_profile_cannot_resolve_back_into_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source, private = Path(temp) / "source", Path(temp) / "private"
            profile_id = uuid4()
            resolve = Path.resolve
            def resolved(path, *args, **kwargs):
                if path.name == "profile-" + str(profile_id):
                    return resolve(source)
                return resolve(path, *args, **kwargs)
            with patch.object(Path, "resolve", resolved):
                with self.assertRaises(ValueError):
                    PrivateBindings(environment={}).profile_path(source, private, profile_id)

    def test_public_boundary_rejects_multiline_known_secret(self):
        marker = "fake-sensitive\nmultiline-value"
        with self.assertRaises(PublicBoundaryError):
            ensure_public_payload({"content": marker}, (marker,))

    def test_public_boundary_rejects_known_secret_without_echo(self):
        marker = "fake-sensitive-test-marker"
        with self.assertRaises(PublicBoundaryError) as caught:
            ensure_public_payload({"nested": ["prefix " + marker]}, (marker,))
        self.assertNotIn(marker, str(caught.exception))

    def test_public_boundary_rejects_secret_field_even_with_short_value(self):
        with self.assertRaises(PublicBoundaryError):
            ensure_public_payload({"metadata": {"api_key": "abc"}}, ())

    def test_private_field_aliases_cannot_escape_the_public_boundary(self):
        for name in ("profilePath", "sessionToken", "privateKey", "API Key", "access-token"):
            with self.subTest(field=name), self.assertRaises(PublicBoundaryError):
                ensure_public_payload({"metadata": {name: "short synthetic marker"}}, ())

    def test_public_boundary_accepts_nonsecret_report(self):
        ensure_public_payload({"answer": "متن آزمون", "attempt_id": str(uuid4())}, ("private-marker",))

    def test_pure_core_does_not_import_transport_or_storage(self):
        import ast
        root = Path(__file__).resolve().parents[2]
        forbidden = {"sqlite3", "socket", "requests", "httpx", "urllib", "subprocess", "os"}
        for path in (root / "src/consilium/core").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.extend(x.name for x in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
            self.assertFalse(forbidden.intersection(x.split('.')[0] for x in names))
            self.assertFalse(any("adapters" in n or "shell" in n for n in names))


if __name__ == "__main__":
    unittest.main()
