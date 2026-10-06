"""P03 recorder tests use synthetic observations; never live browser evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError

from consilium.core.browser_probe import (
    BrowserBinding, BrowserContext, BrowserObservation, ProbeTicket, classify_observation,
)
from consilium.core.contracts import (
    AdapterCapabilities, AdapterRequest, ConnectionSpec, DebateSpec, Delivery, Failure,
    FrozenInput, Message, OperationIdentity, OperationIntent, ResponseState, RoundSpec,
)
from consilium.core.operation_states import AttemptState, ResumeAction
from consilium.shell.browser_probe import BrowserProbeRecorder
from consilium.shell.private import PublicBoundaryError
from consilium.shell.storage import Conflict, SQLiteStore

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = hashlib.sha256(b"SYNTHETIC_PROBE_FIXTURE_NOT_A_PROVIDER_RECEIPT").hexdigest()


class BrowserProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.database = self.directory / "probe.sqlite3"
        self.path = self.directory / "ticket.json"
        self.participant = uuid4()
        identity = OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4())
        self.debate = DebateSpec(debate_id=uuid4(), original_request="  پرسش آزمایشی\n[consilium-probe:" + str(identity.attempt_id) + "]",
                                 participant_ids=(self.participant,))
        round_spec = RoundSpec(round_id=uuid4(), debate_id=self.debate.debate_id, number=1,
                               kind="INDEPENDENT", participant_ids=(self.participant,))
        connection = ConnectionSpec(connection_id=uuid4(), provider_id="synthetic-browser",
                                    model_id="synthetic-model", mode="BROWSER", account_binding_id=uuid4())
        self.store = SQLiteStore(self.database)
        self.store.create_debate(self.debate)
        self.store.register_round(round_spec, expected_revision=0)
        self.store.bind_connection(self.debate.debate_id, self.participant, connection,
                                   expected_revision=1, expected_connection_revision=None)
        frozen = FrozenInput(messages=(Message(role="USER", content=self.debate.original_request),))
        intent = OperationIntent(identity=identity,
            debate_id=self.debate.debate_id, round_id=round_spec.round_id, participant_id=self.participant,
            connection_id=connection.connection_id, expected_revision=2, connection_revision=0,
            frozen_input=frozen, request_hash=frozen.content_hash)
        self.store.prepare_intent(intent)
        self.binding = BrowserBinding(connection_id=connection.connection_id, connection_revision=0,
            account_binding_id=connection.account_binding_id, conversation_binding_id=uuid4(), model_id=connection.model_id)
        self.context = BrowserContext(authentication="AUTHENTICATED", account_binding_id=connection.account_binding_id,
            conversation_binding_id=self.binding.conversation_binding_id, model_id=connection.model_id, evidence=(EVIDENCE,))
        self.request = AdapterRequest(intent=intent, connection=connection, timeout_seconds=20.0,
                                      transport_binding_hash=self.binding.content_hash)
        self.ticket = ProbeTicket(request=self.request, binding=self.binding, initial_context=self.context)
        self.user_message, self.assistant_message = uuid4(), uuid4()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    @property
    def revision(self):
        return self.store.checkpoint(self.debate.debate_id).revision

    @property
    def recorder(self):
        return BrowserProbeRecorder(self.store)

    @property
    def attempt_id(self):
        return self.request.intent.identity.attempt_id

    def observation(self, *, state="COMPLETE", correlated=True, **changes):
        values = dict(identity=self.request.intent.identity, request_hash=self.request.intent.request_hash,
            context=self.context, send_action_attempted=True, response_state=state,
            evidence=(EVIDENCE,), elapsed_seconds=5.0)
        if correlated:
            values.update(user_message_ref=self.user_message,
                          observed_prompt_hash=hashlib.sha256(self.debate.original_request.encode("utf-8")).hexdigest())
        if state != "NONE":
            values.update(assistant_message_ref=self.assistant_message, response_to_user_message_ref=self.user_message,
                          content="synthetic response", completion_evidence=(EVIDENCE,) if state == "COMPLETE" else ())
        return BrowserObservation(**{**values, **changes})

    def start(self):
        return self.recorder.start(self.ticket, self.path, expected_revision=self.revision)

    def reopen(self):
        self.store.close()
        self.store = SQLiteStore(self.database)

    def test_complete_requires_positive_completion_evidence(self):
        with self.assertRaises(ValidationError):
            self.observation(completion_evidence=())

    def test_partial_cannot_claim_completion_evidence(self):
        with self.assertRaises(ValidationError):
            self.observation(state="PARTIAL", completion_evidence=(EVIDENCE,))

    def test_response_must_reference_exact_observed_user_message(self):
        with self.assertRaises(ValidationError):
            self.observation(response_to_user_message_ref=uuid4())

    def test_an_assistant_message_cannot_be_the_user_message(self):
        with self.assertRaises(ValidationError):
            self.observation(assistant_message_ref=self.user_message)

    def test_no_response_cannot_contain_hidden_output(self):
        with self.assertRaises(ValidationError):
            self.observation(state="NONE", content="hidden output")

    def test_sign_in_page_is_not_proof_of_expiration(self):
        with self.assertRaises(ValidationError):
            BrowserContext(authentication="EXPIRED", evidence=(EVIDENCE,))
        context = BrowserContext(authentication="SIGNED_OUT", evidence=(EVIDENCE,))
        result = classify_observation(self.ticket, self.observation(state="NONE", correlated=False, context=context))
        self.assertEqual(result.delivery, Delivery.UNKNOWN)
        self.assertNotEqual(result.failure, Failure.SESSION_EXPIRED)

    def test_authentication_needs_all_observed_identity_fields(self):
        with self.assertRaises(ValidationError):
            self.context.model_copy(update={"model_id": None})

    def test_signed_out_context_cannot_start_probe(self):
        with self.assertRaises(ValidationError):
            self.ticket.model_copy(update={"initial_context": BrowserContext(authentication="SIGNED_OUT", evidence=(EVIDENCE,))})
        self.assertEqual(self.store.ledger.get_attempt(self.attempt_id).state, AttemptState.PREPARED)

    def test_probe_rejects_api_mode(self):
        request = self.request.model_copy(update={"connection": self.request.connection.model_copy(update={"mode": "API"})})
        with self.assertRaises(ValidationError):
            self.ticket.model_copy(update={"request": request})

    def test_budget_is_finite_and_never_above_sixty_seconds(self):
        with self.assertRaises(ValidationError):
            self.ticket.model_copy(update={"request": self.request.model_copy(update={"timeout_seconds": 61.0})})
        with self.assertRaises(ValidationError):
            self.observation(elapsed_seconds=float("nan"))
        with self.assertRaises(ValueError):
            classify_observation(self.ticket, self.observation(elapsed_seconds=21.0))

    def test_probe_rejects_unfrozen_transport_binding(self):
        with self.assertRaises(ValidationError):
            self.ticket.model_copy(update={"request": self.request.model_copy(update={"transport_binding_hash": None})})

    def test_old_matching_prompt_without_unique_attempt_marker_cannot_start(self):
        frozen = FrozenInput(messages=(Message(role="USER", content="old identical question"),))
        intent = self.request.intent.model_copy(update={"frozen_input": frozen, "request_hash": frozen.content_hash})
        with self.assertRaises(ValidationError):
            self.ticket.model_copy(update={"request": self.request.model_copy(update={"intent": intent})})

    def test_probe_version_cannot_be_boolean(self):
        with self.assertRaises(ValidationError):
            self.ticket.model_copy(update={"schema_version": True})

    def test_dispatch_commits_before_external_ui_action(self):
        checkpoint = self.start()
        self.assertEqual(checkpoint.revision, 4)
        self.reopen()
        plan = self.recorder.inspect(self.path)
        self.assertEqual(plan.attempt.state, AttemptState.SENT)
        self.assertEqual(plan.action, ResumeAction.VERIFY_DELIVERY)
        self.assertFalse(plan.automatic_send)

    def test_started_attempt_cannot_be_started_twice(self):
        self.start()
        before = self.path.read_bytes()
        with self.assertRaises(Conflict):
            self.start()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(self.revision, 4)

    def test_click_success_without_correlated_prompt_remains_unknown(self):
        self.start()
        plan = self.recorder.record(self.path, self.observation(state="NONE", correlated=False), expected_revision=self.revision)
        self.assertEqual(plan.attempt.state, AttemptState.UNKNOWN)
        self.assertEqual(plan.action, ResumeAction.VERIFY_DELIVERY)
        self.assertFalse(plan.automatic_send)

    def test_missing_click_observation_never_proves_not_sent(self):
        result = classify_observation(self.ticket, self.observation(state="NONE", correlated=False, send_action_attempted=False))
        self.assertEqual(result.delivery, Delivery.UNKNOWN)

    def test_matching_prompt_without_response_is_pending_not_complete(self):
        self.start()
        plan = self.recorder.record(self.path, self.observation(state="NONE"), expected_revision=self.revision)
        self.assertEqual(plan.attempt.state, AttemptState.RESPONSE_PENDING)
        self.assertIsNone(plan.attempt.result.content)

    def test_partial_output_is_durable_and_never_confirmed(self):
        self.start()
        self.recorder.record(self.path, self.observation(state="PARTIAL"), expected_revision=self.revision)
        self.reopen()
        plan = self.recorder.inspect(self.path)
        self.assertEqual(plan.attempt.state, AttemptState.PARTIAL_RESPONSE)
        self.assertEqual(plan.attempt.result.content, "synthetic response")
        self.assertIsNone(self.store.ledger.canonical_result(self.request.intent.identity.logical_operation_id))

    def test_complete_transport_output_does_not_bypass_product_validation(self):
        self.start()
        plan = self.recorder.record(self.path, self.observation(), expected_revision=self.revision)
        self.assertEqual(plan.attempt.state, AttemptState.RESPONSE_RECEIVED)
        self.assertEqual(plan.action, ResumeAction.VALIDATE_STORED_RESPONSE)
        self.assertIsNone(self.store.ledger.canonical_result(self.request.intent.identity.logical_operation_id))

    def test_wrong_prompt_hash_cannot_confirm_delivery(self):
        result = classify_observation(self.ticket, self.observation(observed_prompt_hash="0" * 64))
        self.assertEqual((result.delivery, result.response_state, result.content), (Delivery.UNKNOWN, ResponseState.NONE, None))

    def test_changed_account_conversation_or_model_cannot_confirm(self):
        for name, replacement in [("account_binding_id", uuid4()), ("conversation_binding_id", uuid4()), ("model_id", "another-model")]:
            with self.subTest(field=name):
                result = classify_observation(self.ticket, self.observation(context=self.context.model_copy(update={name: replacement})))
                self.assertEqual(result.delivery, Delivery.UNKNOWN)
                self.assertIsNone(result.content)

    def test_expired_authenticated_session_remains_ambiguous_after_dispatch(self):
        context = BrowserContext(authentication="EXPIRED", evidence=(EVIDENCE,), prior_authenticated_evidence=(EVIDENCE,))
        result = classify_observation(self.ticket, self.observation(state="NONE", correlated=False, context=context))
        self.assertEqual((result.delivery, result.failure), (Delivery.UNKNOWN, Failure.SESSION_EXPIRED))

    def test_another_operation_or_input_is_rejected_without_ledger_change(self):
        self.start()
        for changes in ({"identity": OperationIdentity(logical_operation_id=uuid4(), attempt_id=uuid4())}, {"request_hash": "0" * 64}):
            with self.subTest(fields=tuple(changes)):
                with self.assertRaises(ValueError):
                    self.recorder.record(self.path, self.observation(**changes), expected_revision=self.revision)
                self.assertEqual(self.revision, 4)

    def test_rewritten_ticket_cannot_change_the_durable_conversation_binding(self):
        self.start()
        replacement = self.binding.model_copy(update={"conversation_binding_id": uuid4()})
        context = self.context.model_copy(update={"conversation_binding_id": replacement.conversation_binding_id})
        altered = self.ticket.model_copy(update={"binding": replacement, "initial_context": context,
            "request": self.request.model_copy(update={"transport_binding_hash": replacement.content_hash})})
        self.path.write_text(altered.model_dump_json(), encoding="utf-8")
        with self.assertRaises(Conflict):
            self.recorder.record(self.path, self.observation(context=context), expected_revision=self.revision)
        self.assertEqual(self.revision, 4)

    def test_ambiguous_result_cannot_be_replaced_by_later_claimed_success(self):
        self.start()
        self.recorder.record(self.path, self.observation(state="NONE", correlated=False), expected_revision=self.revision)
        with self.assertRaises(Conflict):
            self.recorder.record(self.path, self.observation(), expected_revision=self.revision)
        self.assertEqual(self.store.ledger.get_attempt(self.attempt_id).state, AttemptState.UNKNOWN)

    def test_identical_result_recording_is_idempotent(self):
        self.start()
        observation = self.observation()
        self.recorder.record(self.path, observation, expected_revision=self.revision)
        previous = self.revision
        self.recorder.record(self.path, observation, expected_revision=previous)
        self.assertEqual(self.revision, previous)

    def test_stale_result_is_quarantined_without_confirming(self):
        self.start()
        with self.assertRaises(Conflict):
            self.recorder.record(self.path, self.observation(), expected_revision=3)
        self.assertEqual(self.store.ledger.get_attempt(self.attempt_id).state, AttemptState.SENT)

    def test_partial_ticket_is_not_silently_repaired(self):
        self.path.write_bytes(b'{"schema_version":')
        with self.assertRaises(ValidationError):
            self.start()
        self.assertEqual(self.store.ledger.get_attempt(self.attempt_id).state, AttemptState.PREPARED)
        self.assertEqual(self.path.read_bytes(), b'{"schema_version":')

    def test_failed_ledger_start_preserves_ticket_but_does_not_dispatch(self):
        with patch.object(self.store.ledger, "begin_send", side_effect=Conflict("synthetic conflict")):
            with self.assertRaises(Conflict):
                self.start()
        self.assertEqual(self.recorder.read_ticket(self.path), self.ticket)
        self.assertEqual(self.store.ledger.get_attempt(self.attempt_id).state, AttemptState.PREPARED)
        self.start()  # Exact PREPARED ticket can resume; SENT can never repeat.

    def test_known_secret_cannot_enter_ticket_or_result(self):
        self.store._forbidden_values = ("synthetic-model",)
        with self.assertRaises(PublicBoundaryError):
            self.start()
        self.assertFalse(self.path.exists())

    def test_observation_schema_rejects_credential_fields(self):
        with self.assertRaises(ValidationError):
            self.observation().model_copy(update={"cookies": "private-data"})
        with self.assertRaises(ValidationError):
            self.observation().model_copy(update={"evidence": ("raw-session-token",)})

    def test_recorder_never_certifies_adapter_capabilities(self):
        self.start()
        self.recorder.record(self.path, self.observation(), expected_revision=self.revision)
        self.assertEqual(AdapterCapabilities(mode="BROWSER").verification, "UNVERIFIED")

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools/run_browser_probe.py"), *args],
            capture_output=True, timeout=10, env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})

    def test_cli_single_step_start_inspect_record_works_without_account_or_ui(self):
        source = self.directory / "input.json"
        source.write_text(self.ticket.model_dump_json(), encoding="utf-8")
        common = ("--database", str(self.database), "--ticket", str(self.path))
        start = self.cli("start", *common, "--input", str(source), "--expected-revision", "3")
        self.assertEqual(start.returncode, 0, start.stderr)
        self.assertEqual(json.loads(start.stdout)["provider_prompt_sent"], "NOT_OBSERVED")
        source.write_text(self.observation().model_dump_json(), encoding="utf-8")
        record = self.cli("record", *common, "--input", str(source), "--expected-revision", "4")
        self.assertEqual(record.returncode, 0, record.stderr)
        inspected = self.cli("inspect", *common)
        self.assertEqual(json.loads(inspected.stdout)["state"], "RESPONSE_RECEIVED")
        self.assertFalse(json.loads(inspected.stdout)["phase_accepted"])

    def test_cli_diagnostics_never_dump_private_invalid_input(self):
        source = self.directory / "invalid.json"
        source.write_text('{"password":"synthetic-sensitive-marker"}', encoding="utf-8")
        proc = self.cli("start", "--database", str(self.database), "--ticket", str(self.path),
                        "--input", str(source), "--expected-revision", "3")
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(b"synthetic-sensitive-marker", proc.stdout + proc.stderr)

    def kill_worker(self, point):
        source, observed = self.directory / "input.json", self.directory / "observation.json"
        source.write_text(self.ticket.model_dump_json(), encoding="utf-8")
        observed.write_text(self.observation().model_dump_json(), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(ROOT / "tests/browser_probe/crash_worker.py"),
            str(self.database), str(source), str(self.path), str(observed), point], capture_output=True, timeout=10,
            env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(proc.returncode, 71, proc.stderr)
        self.reopen()

    def test_process_exit_after_ticket_before_ledger_leaves_prepared(self):
        self.kill_worker("before_ledger")
        self.assertEqual(self.recorder.inspect(self.path).attempt.state, AttemptState.PREPARED)
        self.start()

    def test_process_exit_after_dispatch_never_reinvokes(self):
        self.kill_worker("after_start")
        self.assertEqual(self.recorder.inspect(self.path).action, ResumeAction.VERIFY_DELIVERY)
        with self.assertRaises(Conflict):
            self.start()

    def test_process_exit_after_result_keeps_received_response(self):
        self.kill_worker("after_result")
        plan = self.recorder.inspect(self.path)
        self.assertEqual(plan.attempt.state, AttemptState.RESPONSE_RECEIVED)
        self.assertEqual(plan.attempt.result.content, "synthetic response")
        self.assertFalse(plan.automatic_send)


if __name__ == "__main__":
    unittest.main()
