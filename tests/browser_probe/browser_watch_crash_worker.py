"""Exit inside the actual journal's commit boundary, never contact a browser."""

import json
import os
import sqlite3
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from consilium.core.browser_probe import BrowserBinding
from consilium.core.browser_watch import PageSnapshot
from consilium.shell.browser_watch_journal import BrowserWatchJournal


def main():
    database, config, stage = sys.argv[1:]
    value = json.loads(Path(config).read_text())
    journal = BrowserWatchJournal(
        Path(database),
        operation_id=UUID(value["operation_id"]),
        request_hash=value["request_hash"],
        binding=BrowserBinding.model_validate_json(json.dumps(value["binding"])),
        baseline=PageSnapshot.model_validate_json(json.dumps(value["baseline"])),
        prompt_hash=value["prompt_hash"],
    )
    original = sqlite3.connect

    class CrashConnection:
        def __init__(self, *args, **kwargs):
            self.db = original(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.db, name)

        def commit(self):
            if stage == "before":
                os._exit(73)
            self.db.commit()
            os._exit(74)

    sqlite3.connect = CrashConnection
    if "raw_capture_utf8" in value:
        journal.append_qwen_capture(
            value["raw_capture_utf8"].encode("utf-8"),
            event_id=UUID(value["event_id"]),
            expected_revision=0,
        )
    else:
        journal.append(
            PageSnapshot.model_validate_json(json.dumps(value["snapshot"])),
            event_id=UUID(value["event_id"]),
            expected_revision=0,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
