"""Actual process exits around an offline simulated external send; never live."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from consilium.adapters.mock import MockAdapter
from consilium.core.contracts import AdapterRequest
from consilium.shell.storage import SQLiteStore


def main():
    database, request_path, remote_path, point = sys.argv[1:]
    request = AdapterRequest.model_validate_json(Path(request_path).read_bytes())
    with SQLiteStore(Path(database)) as store:
        if point == "before_send": os._exit(95)
        checkpoint = store.ledger.begin_send(request, expected_revision=3)
        if point == "after_send_start": os._exit(96)
        result = MockAdapter().send(request)
        # A separate fsynced journal simulates a transport outside the local transaction.
        with open(remote_path, "xb") as receipt:
            receipt.write((json.dumps({"provenance": "MOCK_ONLY", "attempt_id": str(request.intent.identity.attempt_id),
                "request_hash": request.intent.request_hash}) + "\n").encode("utf-8"))
            receipt.flush(); os.fsync(receipt.fileno())
        if point == "after_external_send": os._exit(97)
        if point == "before_result": os._exit(98)
        if point == "during_result":
            store._db.create_function("crash_now", 0, lambda: os._exit(99))
            store._db.execute("CREATE TEMP TRIGGER crash_result AFTER INSERT ON transport_results BEGIN SELECT crash_now(); END")
        checkpoint = store.ledger.record_result(result, expected_revision=checkpoint.revision)
        if point == "after_result": os._exit(100)
        checkpoint = store.ledger.validate_response(request.intent.identity.attempt_id, expected_revision=checkpoint.revision)
        if point == "after_validation": os._exit(101)
        if point == "during_confirmation":
            store._db.create_function("crash_now", 0, lambda: os._exit(102))
            store._db.execute("CREATE TEMP TRIGGER crash_confirm AFTER INSERT ON canonical_results BEGIN SELECT crash_now(); END")
        store.ledger.confirm_result(request.intent.identity.attempt_id, expected_revision=checkpoint.revision)
        if point == "after_confirmation": os._exit(103)
    raise RuntimeError("Unknown test kill point")


if __name__ == "__main__": main()
