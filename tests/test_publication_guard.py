from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from publication_guard import Blocked, PublicationGuard


class PublicationGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "guard.sqlite3"
        self.guard = PublicationGuard(self.path)
        self.plan = dict(kind="GIT_OBJECT", resource="mehrangtr/Consilium/git-object",
                         expected_sha="a"*40, request_sha256="b"*64, source_digest="c"*64)
        self.operation_id = self.guard.prepare(self.plan)["id"]

    def tearDown(self):
        self.guard.close()
        self.temp.cleanup()

    def test_pending_intent_survives_restart_and_blocks_duplicate(self):
        attempt = self.guard.begin(self.operation_id)
        self.guard.close(); self.guard = PublicationGuard(self.path)
        with self.assertRaises(Blocked): self.guard.begin(self.operation_id)
        self.assertEqual(self.guard.pending()[0]["nonce"], attempt["nonce"])

    def test_timeout_is_unknown_until_read_reconciliation(self):
        a = self.guard.begin(self.operation_id)
        self.guard.unknown(self.operation_id, a["nonce"])
        with self.assertRaises(Blocked): self.guard.begin(self.operation_id)
        self.assertEqual(self.guard.reconcile(self.operation_id, a["nonce"], observed_sha="a"*40)["state"], "VERIFIED_COMPLETE")
        with self.assertRaises(Blocked): self.guard.begin(self.operation_id)

    def test_only_one_immutable_retry_and_old_attempt_cannot_finish_it(self):
        first = self.guard.begin(self.operation_id)
        self.guard.unknown(self.operation_id, first["nonce"])
        self.guard.reconcile(self.operation_id, first["nonce"], observed_sha=None)
        second = self.guard.begin(self.operation_id)
        with self.assertRaises(Blocked): self.guard.reconcile(self.operation_id, first["nonce"], observed_sha="a"*40)
        self.guard.unknown(self.operation_id, second["nonce"])
        self.guard.reconcile(self.operation_id, second["nonce"], observed_sha=None)
        with self.assertRaises(Blocked): self.guard.begin(self.operation_id)

    def test_mutable_ref_never_retries_after_missing_or_old_read(self):
        for observed in (None, "d"*40):
            with self.subTest(observed=observed):
                plan = dict(self.plan, kind="REF_UPDATE", resource="repo/ref/" + str(observed))
                action = self.guard.prepare(plan)["id"]; a = self.guard.begin(action)
                self.guard.unknown(action, a["nonce"])
                self.assertEqual(self.guard.reconcile(action, a["nonce"], observed_sha=observed)["state"], "BLOCKED")
                with self.assertRaises(Blocked): self.guard.begin(action)

    def test_exact_ref_read_resolves_without_repeating_write(self):
        action = self.guard.prepare(dict(self.plan, kind="REF_UPDATE"))["id"]
        a = self.guard.begin(action); self.guard.unknown(action, a["nonce"])
        self.assertEqual(self.guard.reconcile(action, a["nonce"], observed_sha="a"*40)["state"], "VERIFIED_COMPLETE")

    def test_new_plan_cannot_bypass_unknown_mutation_on_same_resource(self):
        action = self.guard.prepare(dict(self.plan, kind="REF_UPDATE"))["id"]
        a = self.guard.begin(action); self.guard.unknown(action, a["nonce"])
        different = self.guard.prepare(dict(self.plan, kind="REF_UPDATE", expected_sha="d"*40))["id"]
        with self.assertRaises(Blocked): self.guard.begin(different)

    def test_mismatched_result_blocks_and_never_becomes_success(self):
        a = self.guard.begin(self.operation_id)
        self.assertEqual(self.guard.reconcile(self.operation_id, a["nonce"], observed_sha="d"*40)["state"], "BLOCKED")
        with self.assertRaises(Blocked): self.guard.begin(self.operation_id)

    def test_late_ref_can_be_reverified_read_only_after_blocking_old_ref(self):
        action = self.guard.prepare(dict(self.plan, kind="REF_UPDATE"))["id"]
        a = self.guard.begin(action); self.guard.unknown(action,a["nonce"])
        self.guard.reconcile(action,a["nonce"],observed_sha="d"*40)
        with self.assertRaises(Blocked): self.guard.begin(action)
        self.assertEqual(self.guard.reconcile(action,a["nonce"],observed_sha="a"*40)["state"],"VERIFIED_COMPLETE")
        self.assertEqual(self.guard.inspect(action)["attempts"],1)

    def test_modified_stored_plan_is_not_a_valid_permit(self):
        self.guard.db.execute("UPDATE operations SET plan=?", ('{}',)); self.guard.db.commit()
        with self.assertRaises(Blocked): self.guard.begin(self.operation_id)

    def test_two_connections_cannot_obtain_same_permit(self):
        self.guard.begin(self.operation_id)
        with closing(PublicationGuard(self.path)) as other:
            with self.assertRaises(Blocked): other.begin(self.operation_id)

    def test_repreparing_same_plan_keeps_completed_checkpoint(self):
        a = self.guard.begin(self.operation_id); self.guard.reconcile(self.operation_id, a["nonce"], observed_sha="a"*40)
        self.assertEqual(self.guard.prepare(self.plan)["state"], "VERIFIED_COMPLETE")
        self.assertEqual(self.guard.pending(), [])

    def test_payload_and_credentials_are_not_accepted_in_public_plan(self):
        for update in ({"payload": "private"}, {"resource": "https://user:password@host/path"}):
            with self.subTest(update=update), self.assertRaises(Blocked): self.guard.prepare(dict(self.plan, **update))

    def test_long_or_invalid_wait_and_unknown_error_text_are_rejected(self):
        for value in (0, 61, True, 1.5):
            with self.subTest(value=value), self.assertRaises(Blocked): self.guard.begin(self.operation_id, wait_seconds=value)
        a = self.guard.begin(self.operation_id)
        with self.assertRaises(Blocked): self.guard.unknown(self.operation_id, a["nonce"], reason="private provider output")
