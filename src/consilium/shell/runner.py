"""Serial P02 runner; no provider call inside a database transaction."""
from consilium.core.contracts import AdapterRequest, AdapterCapabilities, TransportResult
from consilium.core.operation_states import AttemptState
from consilium.ports.adapter import Adapter
from consilium.shell.storage import Conflict, SQLiteStore


class DurableRunner:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def execute(self, request: AdapterRequest, adapter: Adapter, *, expected_revision: int):
        capabilities = AdapterCapabilities.model_validate(adapter.capabilities.model_dump(mode="python"))
        if capabilities.mode != request.connection.mode:
            raise ValueError("Adapter and bound transport mode differ")
        checkpoint = self.store.ledger.begin_send(request, expected_revision=expected_revision)
        try:
            result = adapter.send(request)
            result = TransportResult.model_validate(result.model_dump(mode="python"))
        except Exception:
            try:
                self.store.ledger.mark_interrupted(request.intent.identity.attempt_id, expected_revision=checkpoint.revision)
            except Conflict:
                pass  # SENT remains ambiguous if another writer moved the revision.
            raise
        checkpoint = self.store.ledger.record_result(result, expected_revision=checkpoint.revision)
        if self.store.ledger.get_attempt(request.intent.identity.attempt_id).state == AttemptState.RESPONSE_RECEIVED:
            checkpoint = self.store.ledger.validate_response(request.intent.identity.attempt_id, expected_revision=checkpoint.revision)
            if self.store.ledger.get_attempt(request.intent.identity.attempt_id).state == AttemptState.VALIDATED:
                self.store.ledger.confirm_result(request.intent.identity.attempt_id, expected_revision=checkpoint.revision)
        return self.store.ledger.resume(request.intent.identity.attempt_id)
