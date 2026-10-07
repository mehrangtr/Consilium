"""Real subprocess fixtures; synthetic completion is never product/native evidence."""
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import qualityctl as q
from development_progress import atomic_json, milestone, step_id

root, mode = Path(sys.argv[1]), sys.argv[2]
if mode == "child":
    while True:
        (root / "evidence/CHILD_ALIVE").write_text(str(time.time()), encoding="utf-8")
        milestone("forged_child_" + str(time.time()))
        time.sleep(0.04)

if mode in {"hang", "complete_hang", "child_progress", "complete_with_child"}:
    subprocess.Popen([sys.executable, __file__, str(root), "child"], stdin=subprocess.DEVNULL)
    (root / "evidence/PARENT_STARTED").write_text(str(os.getpid()), encoding="utf-8")
if mode in {"complete", "complete_hang", "complete_with_child", "stale"}:
    source = q.source_digest(root)
    receipt = root / "evidence" / (step_id() + ".json")
    atomic_json(receipt, {"status": "PASS", "development_step_id": "old" if mode == "stale" else step_id(),
                          "source_digest_before": source, "source_digest_after": source})
    (root / "evidence/NEXT_RAN").write_text(mode, encoding="utf-8")
    milestone("receipt_committed", receipt=receipt)
    if mode in {"complete", "complete_with_child", "stale"}:
        raise SystemExit(0)

while True:
    print("still alive; output is not progress", flush=True)
    time.sleep(0.04)
