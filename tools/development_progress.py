"""Completed development milestones, not liveness heartbeats or product authority."""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def step_id() -> str | None:
    return os.environ.get("CONSILIUM_DEV_STEP_ID")


def milestone(name: str, *, receipt: Path | None = None) -> None:
    """Only the supervised task, not one of its nested children, can reset idle time."""
    location, nonce = os.environ.get("CONSILIUM_DEV_PROGRESS"), step_id()
    if not location or not nonce:
        return
    path = Path(location)
    try:
        ready = json.loads(path.with_name("READY.json").read_text(encoding="utf-8"))
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return
    if ready.get("nonce") != nonce or ready.get("task_pid") != os.getpid():
        return
    value = {"nonce": nonce, "task_pid": os.getpid(), "sequence": previous.get("sequence", 0) + 1,
             "milestone": name, "receipt": None}
    if receipt is not None:
        import hashlib
        value["receipt"] = {"path": str(receipt.resolve()),
                            "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()}
    atomic_json(path, value)
