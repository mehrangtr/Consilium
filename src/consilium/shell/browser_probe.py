"""Single-step P03 recording: immutable ticket, then ledger, then external UI work.

There are no browser calls, polling loops, authentication or automatic retries here.
"""
from __future__ import annotations

import os
from pathlib import Path

from consilium.core.browser_probe import BrowserObservation, ProbeTicket, classify_observation
from consilium.core.operation_states import AttemptState
from consilium.shell.storage import Conflict, SQLiteStore


class BrowserProbeRecorder:
    def __init__(self, store: SQLiteStore):
        self.store = store

    @staticmethod
    def read_ticket(path: Path) -> ProbeTicket:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Probe ticket must be a regular local file")
        return ProbeTicket.model_validate_json(path.read_bytes())

    def start(self, ticket: ProbeTicket, path: Path, *, expected_revision: int):
        ticket = ProbeTicket.model_validate(ticket.model_dump(mode="python"))
        payload = self.store._public(ticket.model_dump(mode="json")).encode("utf-8")
        if path.is_symlink():
            raise ValueError("Probe ticket must not be a symlink")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if self.read_ticket(path) != ticket:
                raise Conflict("An existing probe ticket cannot be replaced")
        else:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name == "posix":
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        # A crash between ticket and ledger is conservative: no external action yet.
        # The ledger is the single-use dispatch gate, including concurrent callers.
        return self.store.ledger.begin_send(ticket.request, expected_revision=expected_revision)

    def record(self, path: Path, observation: BrowserObservation, *, expected_revision: int):
        ticket = self.read_ticket(path)
        attempt = self.store.ledger.get_attempt(ticket.request.intent.identity.attempt_id)
        if attempt.request != ticket.request:
            raise Conflict("Ticket does not match the durable dispatch request")
        result = classify_observation(ticket, observation)
        self.store.ledger.record_result(result, expected_revision=expected_revision)
        # Transport completion is not schema validation or product confirmation.
        return self.store.ledger.resume(ticket.request.intent.identity.attempt_id)

    def inspect(self, path: Path):
        ticket = self.read_ticket(path)
        plan = self.store.ledger.resume(ticket.request.intent.identity.attempt_id)
        if (plan.attempt.intent != ticket.request.intent
                or plan.attempt.state != AttemptState.PREPARED and plan.attempt.request != ticket.request):
            raise Conflict("Ticket differs from durable operation state")
        return plan
