"""Read-only correlation of a durable page journal and operation ledger."""

from uuid import UUID

from consilium.core.browser_probe import BrowserBinding
from consilium.shell.browser_watch_journal import digest, encoded


class BrowserLedgerView:
    def __init__(self, journal):
        self.journal = journal

    def resume(self, ledger, *, attempt_id: UUID, expected_revision: int):
        """Read both committed stores; never dispatch or promote synthetic text.

        The ledger read transaction pins connection/round/revision while the
        journal is replayed. This is a point-in-time view, not a send permit.
        """
        from consilium.core.operation_states import AttemptState, ResumeAction
        from consilium.shell.storage import Conflict, _revision

        _revision(expected_revision)
        if encoded(self.journal.spec) != self.journal.spec_json:
            raise ValueError("JOURNAL_SPEC_CHANGED")
        with ledger.store._transaction(write=False):
            record = ledger.get_attempt(attempt_id)
            ledger._current(record, expected_revision)
            request = record.request
            binding = BrowserBinding.model_validate_json(
                encoded(self.journal.spec["binding"])
            )
            if (
                request is None
                or request.connection.mode != "BROWSER"
                or record.intent.identity.attempt_id
                != UUID(self.journal.spec["operation_id"])
                or record.intent.request_hash != self.journal.spec["request_hash"]
                or request.connection.connection_id != binding.connection_id
                or record.intent.connection_revision != binding.connection_revision
                or request.connection.account_binding_id != binding.account_binding_id
                or request.connection.model_id != binding.model_id
                or request.transport_binding_hash != binding.content_hash
                or len(record.intent.frozen_input.messages) != 1
                or record.intent.frozen_input.messages[0].role != "USER"
                or digest(record.intent.frozen_input.messages[0].content)
                != self.journal.spec["prompt_hash"]
            ):
                raise Conflict("JOURNAL_DOES_NOT_MATCH_STARTED_BROWSER_OPERATION")
            observation = self.journal.resume()
            plan = ledger.resume(attempt_id)
            outstanding = record.state in {
                AttemptState.SENT,
                AttemptState.UNKNOWN,
            } and plan.action in {
                ResumeAction.VERIFY_DELIVERY,
                ResumeAction.WAIT_FOR_RESPONSE,
            }
            return {
                **observation,
                "attempt_id": str(attempt_id),
                "ledger_revision": expected_revision,
                "ledger_state": record.state.value,
                "next_action": (
                    "OBSERVE_ONLY_NO_RESEND"
                    if outstanding and not observation["stopped"]
                    else "STOP_REQUIRES_RECONCILIATION"
                ),
                "scope": "OFFLINE_CORRELATION_NOT_LIVE_RESULT_ADMISSION",
                "result_admitted": False,
                "may_dispatch": False,
                "may_confirm_product_response": False,
            }
