"""Test-only kill points; no fabricated crash receipt or provider delivery."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from consilium.core.contracts import OperationIntent
from consilium.shell.storage import SQLiteStore


def main():
    database, intent_path, point = sys.argv[1:]
    intent = OperationIntent.model_validate_json(Path(intent_path).read_bytes())
    with SQLiteStore(Path(database)) as store:
        if point == "before_intent":
            os._exit(91)
        if point == "during_intent":
            store._db.create_function("crash_now", 0, lambda: os._exit(92))
            store._db.execute("""CREATE TEMP TRIGGER crash_before_intent_event
                BEFORE INSERT ON events WHEN NEW.kind='OPERATION_PREPARED'
                BEGIN SELECT crash_now(); END""")
        store.prepare_intent(intent)
        if point == "after_intent":
            os._exit(93)
    raise RuntimeError("Unknown test kill point")


if __name__ == "__main__":
    main()
