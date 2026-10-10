"""P08 durable MOCK-gated wire integration, error replay and full council flow."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "council"))
import test_council as council_fixtures
from test_api_codec import envelope, raw

from consilium.adapters.api_offline import ApiFixture, OfflineApiAdapter
from consilium.core.contracts import Delivery, Failure, ResponseState
from consilium.core.operation_states import AttemptState
from consilium.shell.storage import Conflict


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.case = council_fixtures.CouncilCase()
        self.case.setUp()

    def tearDown(self):
        self.case.tearDown()

    def send(self, provider, fixture, request=None):
        c = self.case
        request = request or c.prepare()
        adapter = OfflineApiAdapter(provider, "fixture-model", fixture)
        result = c.council.execute_offline_api(
            request, adapter, expected_revision=c.revision
        )
        return request, adapter, result

    def test_each_codec_passes_typed_durable_confirmation_and_mock_provenance(self):
        c = self.case
        for provider, pid in zip(("google", "qwen"), c.pid):
            request = c.prepare(pid)
            text = json.dumps({"schema_version": 1, "answer": "پاسخ fixture"})
            _, adapter, plan = self.send(
                provider,
                ApiFixture(chunks=(raw(envelope(provider, text=text)),)),
                request,
            )
            self.assertEqual(plan.attempt.state, AttemptState.CONFIRMED)
            source = c.store.artifacts.get(
                request.intent.identity.logical_operation_id
            ).sources[0]
            self.assertEqual(source.provenance, "MOCK")
            self.assertEqual(source.item.provenance, "MOCK")
            self.assertEqual(len(adapter.calls), 1)
            self.assertEqual(adapter.capabilities.verification, "DECLARED_MOCK")
            self.assertFalse(adapter.capabilities.idempotency)
            self.assertFalse(adapter.capabilities.delivery_probe)
            before = plan.attempt.result
            c.reopen()
            self.assertEqual(
                c.store.ledger.get_attempt(request.intent.identity.attempt_id).result,
                before,
            )
            self.assertTrue(any(x.startswith("API_METADATA:") for x in before.evidence))

    def test_http_errors_never_claim_not_sent_or_repeat(self):
        for status, failure in (
            (401, Failure.SESSION_EXPIRED),
            (403, Failure.SESSION_EXPIRED),
            (429, Failure.QUOTA),
            (500, Failure.SEND_REJECTED),
        ):
            if status != 401:
                self.tearDown()
                self.setUp()
            request, adapter, plan = self.send(
                "qwen", ApiFixture(status=status, chunks=(b"private error secret",))
            )
            self.assertEqual(plan.attempt.result.delivery, Delivery.UNKNOWN)
            self.assertEqual(plan.attempt.result.failure, failure)
            self.assertNotIn("secret", plan.attempt.result.model_dump_json())
            with self.assertRaises(Conflict):
                self.case.council.execute_offline_api(
                    request,
                    OfflineApiAdapter(
                        "qwen", "fixture-model", ApiFixture(status=status)
                    ),
                    expected_revision=self.case.revision,
                )
            self.assertEqual(len(adapter.calls), 1)
            self.case.reopen()
            self.assertFalse(
                self.case.council.recover(self.case.debate.debate_id)["automatic_send"]
            )

    def test_partial_stream_survives_restart_without_publication_or_resend(self):
        text = json.dumps({"schema_version": 1, "answer": "incomplete"})
        chunk = (
            b"data: "
            + raw(
                {
                    "id": "q-1",
                    "choices": [{"delta": {"content": text}, "finish_reason": None}],
                }
            )
            + b"\n\n"
        )
        request, _, plan = self.send(
            "qwen", ApiFixture(chunks=(chunk,), streaming=True, interrupted=True)
        )
        self.assertEqual(plan.attempt.result.response_state, ResponseState.PARTIAL)
        self.assertIsNone(
            self.case.store.artifacts.get(request.intent.identity.logical_operation_id)
        )
        self.case.reopen()
        plan = self.case.store.ledger.resume(request.intent.identity.attempt_id)
        self.assertEqual(plan.attempt.result.content, text)
        self.assertNotEqual(plan.attempt.state, AttemptState.CONFIRMED)

    def test_malformed_envelope_and_invalid_typed_response_do_not_publish(self):
        request, _, plan = self.send("google", ApiFixture(chunks=(b"{secret",)))
        self.assertEqual(plan.attempt.result.response_state, ResponseState.NONE)
        self.assertNotEqual(plan.attempt.state, AttemptState.CONFIRMED)
        self.assertIsNone(
            self.case.store.artifacts.get(request.intent.identity.logical_operation_id)
        )
        self.tearDown()
        self.setUp()
        request, _, plan = self.send(
            "google",
            ApiFixture(chunks=(raw(envelope("google", text="not typed JSON")),)),
        )
        self.assertNotEqual(plan.attempt.state, AttemptState.CONFIRMED)
        self.assertIsNone(
            self.case.store.artifacts.get(request.intent.identity.logical_operation_id)
        )

    def test_driver_rejects_live_binding_subclass_and_repeated_attempt(self):
        request = self.case.prepare()
        adapter = OfflineApiAdapter("qwen", "fixture-model", ApiFixture(status=429))
        live = request.model_copy(
            update={
                "connection": request.connection.model_copy(
                    update={"provider_id": "qwen", "model_id": "real"}
                )
            }
        )
        with self.assertRaises(ValueError):
            adapter.send(live)
        self.assertEqual(adapter.calls, ())

        class Fake(OfflineApiAdapter):
            pass

        with self.assertRaises(Conflict):
            self.case.council.execute_offline_api(
                request,
                Fake("qwen", "fixture-model", ApiFixture(status=429)),
                expected_revision=self.case.revision,
            )
        adapter.send(request)
        with self.assertRaises(ValueError):
            adapter.send(request)
        changed = request.model_copy(update={"timeout_seconds": 3.0})
        with self.assertRaises(ValueError):
            adapter.probe(changed)

    def test_full_two_codec_council_preserves_dissent_and_recovers_final(self):
        c = self.case
        count = 0

        def submit(pid, text=None):
            nonlocal count
            request = c.prepare(pid)
            contract = c.store.artifacts.get_contract(request.intent)
            output = (
                c.review_content(contract.targets)
                if c.round.kind == "REVIEW"
                else json.dumps(
                    {
                        "schema_version": 1,
                        "answer": text
                        or (
                            "MAJORITY"
                            if pid == c.pid[0]
                            else "MINORITY_DISSENT: missing evidence"
                        ),
                    }
                )
            )
            provider = "google" if pid == c.pid[0] else "qwen"
            self.send(
                provider,
                ApiFixture(chunks=(raw(envelope(provider, text=output)),)),
                request,
            )
            count += 1

        for pid in c.round.participant_ids:
            submit(pid)
        c.council.seal_round(debate_id=c.debate.debate_id, expected_revision=c.revision)
        c.decide("CONTINUE")
        c.start("REVIEW")
        for pid in c.round.participant_ids:
            submit(pid)
        c.council.seal_round(debate_id=c.debate.debate_id, expected_revision=c.revision)
        c.decide("FINISH")
        selected = c.select()
        submit(selected.participant_id, c.judge_output())
        result = c.council.finalize(
            debate_id=c.debate.debate_id, expected_revision=c.revision
        )
        self.assertTrue(result.preserved_objections)
        self.assertEqual(count, 5)
        before = c.store.export_debate(c.debate.debate_id)
        c.reopen()
        self.assertEqual(before, c.store.export_debate(c.debate.debate_id))
        self.assertEqual(
            c.council.recover(c.debate.debate_id)["next_action"], "USE_FINAL"
        )
        self.assertFalse(c.council.recover(c.debate.debate_id)["automatic_send"])

    def test_preflight_rejection_does_not_advance_ledger_or_call_driver(self):
        request = self.case.prepare()
        before = self.case.revision
        adapter = OfflineApiAdapter("google", "bad/model", ApiFixture())
        with self.assertRaises(ValueError):
            self.case.council.execute_offline_api(
                request, adapter, expected_revision=before
            )
        self.assertEqual(self.case.revision, before)
        self.assertEqual(adapter.calls, ())
        self.assertEqual(
            self.case.store.ledger.get_attempt(
                request.intent.identity.attempt_id
            ).state,
            AttemptState.PREPARED,
        )

    def test_invalid_fixture_configuration_rejected_without_keys_or_network(self):
        for changes in (
            {"status": True},
            {"elapsed_seconds": float("nan")},
            {"chunks": (b"x" * 1048577,)},
            {"streaming": 1},
            {"chunks": (bytearray(b"x"),)},
        ):
            with self.assertRaises(ValueError):
                ApiFixture(**changes)

    def test_real_exit_after_api_result_preserves_partial_and_prevents_resend(self):
        import os
        import subprocess

        c = self.case
        request = c.prepare()
        record = Path(c.temp.name) / "request.json"
        record.write_text(request.model_dump_json())
        env = dict(
            os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src")
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("api_crash_worker.py")),
                str(c.path),
                str(record),
            ],
            env=env,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(proc.returncode, 79, proc.stderr.decode())
        c.reopen()
        plan = c.store.ledger.resume(request.intent.identity.attempt_id)
        self.assertEqual(plan.attempt.result.response_state, ResponseState.PARTIAL)
        self.assertIsNone(
            c.store.artifacts.get(request.intent.identity.logical_operation_id)
        )
        self.assertFalse(c.council.recover(c.debate.debate_id)["automatic_send"])
        with self.assertRaises(Conflict):
            c.council.execute_offline_api(
                request,
                OfflineApiAdapter("qwen", "fixture-model", ApiFixture(status=429)),
                expected_revision=c.revision,
            )
