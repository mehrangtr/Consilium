"""Deliberate process exits around the recorder; all observations are synthetic."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from consilium.core.browser_probe import BrowserObservation, ProbeTicket
from consilium.shell.browser_probe import BrowserProbeRecorder
from consilium.shell.storage import SQLiteStore

database, source, destination, observation, point = sys.argv[1:]
store = SQLiteStore(Path(database))
probe = BrowserProbeRecorder(store)
ticket = ProbeTicket.model_validate_json(Path(source).read_bytes())
if point == "before_ledger":
    with patch.object(store.ledger, "begin_send", side_effect=lambda *args, **kwargs: os._exit(71)):
        probe.start(ticket, Path(destination), current_context=ticket.initial_context, expected_revision=3)
# This worker uses a synthetic context fixture, never a live browser observation.
probe.start(ticket, Path(destination), current_context=ticket.initial_context, expected_revision=3)
if point == "after_result":
    probe.record(Path(destination), BrowserObservation.model_validate_json(Path(observation).read_bytes()), expected_revision=4)
os._exit(71)
