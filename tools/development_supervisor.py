"""Five-minute idle guard for predefined offline development commands only."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import qualityctl as q
from development_progress import atomic_json

ROOT = Path(__file__).resolve().parents[1]
IDLE_SECONDS = 300
HARD_SECONDS = 900


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    replay_safe: bool = False


def presets(name: str) -> tuple[Step, ...]:
    scripts = {"check": ("tools/check.py",), "native": ("tools/record_target_checks.py",),
               "phase": ("tools/run_current_phase.py", "--report-blocked")}
    selected = ("check", "phase") if name == "local" else (name,)
    return tuple(Step(key, (sys.executable, *scripts[key]), replay_safe=True) for key in selected)


def timeout_reason(start: float, last: float, now: float, idle: float = IDLE_SECONDS,
                   hard: float = HARD_SECONDS) -> str | None:
    if now - last >= idle:
        return "IDLE_TIMEOUT"
    if now - start >= hard:
        return "HARD_TIMEOUT"
    return None


def stop_tree(worker: subprocess.Popen) -> None:
    if os.name == "nt":
        if worker.poll() is None:
            worker.kill()  # Closing the worker's sole job handle kills its descendants.
    else:
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    worker.wait(timeout=5)


def read_progress(path: Path, nonce: str, task_pid: int | None, sequence: int,
                  seen: set[str]) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (task_pid is None or value["nonce"] != nonce or value["task_pid"] != task_pid
                or type(value["sequence"]) is not int or value["sequence"] <= sequence
                or not isinstance(value["milestone"], str) or not value["milestone"]
                or value["milestone"] in seen):
            return None
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return None


def reconcile(root: Path, progress: dict | None, nonce: str, source: str) -> dict:
    """Reopen the fresh receipt and every declared artifact; stale PASS is insufficient."""
    try:
        q.require(progress is not None and progress.get("receipt") is not None, "No completed receipt")
        ref = progress["receipt"]
        path = Path(ref["path"]).resolve()
        q.require(path.is_relative_to((root / "evidence").resolve()), "Receipt outside project evidence")
        raw = path.read_bytes()
        q.require(q.digest(raw) == ref["sha256"], "Receipt changed")
        receipt = json.loads(raw)
        q.require(receipt.get("development_step_id") == nonce, "Receipt belongs to another execution")
        q.require(receipt["status"] == "PASS", "Receipt did not pass")
        q.require(receipt["source_digest_before"] == receipt["source_digest_after"] == source
                  == q.source_digest(root), "Source changed")
        for reference in receipt.get("artifacts", {}).values():
            q.artifact(root, reference)
        for check in receipt.get("checks", []):
            q.require(check["status"] == "PASS", "A subcheck failed")
            for reference in check.get("artifacts", {}).values():
                q.artifact(root, reference)
            if "log" in check:
                q.artifact(root, {"path": check["log"], "sha256": check["log_sha256"]})
            if "junit" in check:
                junit = q.artifact(root, {"path": check["junit"], "sha256": check["junit_sha256"]})
                q.require(q.junit_counts(junit) == check["counts"], "Configured JUnit differs")
        if receipt.get("scope") == "NATIVE_TARGET_OFFLINE_EXECUTION":
            from check_target_matrix import inspect_matrix
            rows = inspect_matrix(root)["targets"]
            target = receipt["host"]["system"]
            q.require(any(r["target"] == target and r["status"] == "PASS"
                          and r["evidence"]["sha256"] == ref["sha256"] for r in rows),
                      "Native report graph did not verify")
        return {"status": "VERIFIED_COMPLETE", "receipt": path.relative_to(root).as_posix(),
                "sha256": ref["sha256"]}
    except (q.Blocked, OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "INCOMPLETE", "reason": str(exc)}


def retain_receipt(root: Path, directory: Path, progress: dict | None, nonce: str) -> dict:
    """Preserve failed as well as successful results before mutable reports change."""
    retained, errors = [], []
    try:
        q.require(progress is not None and progress.get("receipt"), "No receipt to preserve")
        ref = progress["receipt"]
        path = Path(ref["path"]).resolve()
        q.require(path.is_relative_to((root / "evidence").resolve()), "Receipt outside evidence")
        raw = path.read_bytes()
        q.require(q.digest(raw) == ref["sha256"], "Receipt changed before preservation")
        receipt = json.loads(raw)
        q.require(receipt.get("development_step_id") == nonce, "Cannot preserve an older receipt as current")
        refs = [dict(path=path.relative_to(root).as_posix(), sha256=ref["sha256"])]
        refs += list(receipt.get("artifacts", {}).values())
        for check in receipt.get("checks", []):
            if "log" in check:
                refs.append({"path": check["log"], "sha256": check["log_sha256"]})
            if "junit" in check:
                refs.append({"path": check["junit"], "sha256": check["junit_sha256"]})
        for reference in refs:
            try:
                original = q.artifact(root, reference)
                q.require(original.is_relative_to(root / "evidence"), "Proof outside evidence")
                saved = directory / "proofs" / original.relative_to(root)
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(original.read_bytes())
                retained.append({"original_path": reference["path"], "path": saved.relative_to(root).as_posix(),
                                 "sha256": reference["sha256"]})
            except (q.Blocked, OSError, KeyError, TypeError) as exc:
                errors.append(str(exc))
    except (q.Blocked, OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"artifacts": retained, "errors": errors}


def supervise(root: Path, steps: tuple[Step, ...], *, idle_seconds: float = IDLE_SECONDS,
              hard_seconds: float = HARD_SECONDS, retry_limit: int = 1,
              clock=time.monotonic) -> Path:
    if idle_seconds <= 0 or hard_seconds < idle_seconds or retry_limit not in (0, 1):
        raise ValueError("Invalid development guard limits")
    run = root / "evidence/development-supervisor" / uuid.uuid4().hex
    run.mkdir(parents=True)
    state_path = run / "STATE.json"
    state = {"schema_version": 1, "scope": "OWNED_OFFLINE_DEVELOPMENT_NOT_CHAT_SESSION_CONTROL",
             "status": "RUNNING", "idle_seconds": idle_seconds, "hard_seconds": hard_seconds,
             "phase_advanced": False, "source_digest": q.source_digest(root), "steps": [],
             "remaining_steps": [s.name for s in steps], "next_action": "RECONCILE_CURRENT_STEP_BEFORE_ADVANCING"}
    atomic_json(state_path, state)
    for step in steps:
        succeeded = False
        for attempt in range(retry_limit + 1):
            nonce = uuid.uuid4().hex
            directory = run / (step.name + "_" + str(attempt + 1))
            directory.mkdir()
            progress_path = directory / "PROGRESS.json"
            config_path = directory / "COMMAND.json"
            atomic_json(config_path, {"command": step.command, "root": str(root), "nonce": nonce,
                                      "supervisor_pid": os.getpid()})
            environment = dict(os.environ, CONSILIUM_DEV_STEP_ID=nonce,
                               CONSILIUM_DEV_PROGRESS=str(progress_path))
            row = {"step": step.name, "attempt": attempt + 1, "nonce": nonce, "status": "RUNNING",
                   "log": (directory / "OUTPUT.log").relative_to(root).as_posix()}
            state["steps"].append(row)
            atomic_json(state_path, state)
            with (directory / "OUTPUT.log").open("wb") as log:
                worker = subprocess.Popen([sys.executable, str(Path(__file__).with_name("development_worker.py")),
                                           str(config_path)], cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, shell=False,
                                           start_new_session=os.name != "nt")
                row["worker_pid"] = worker.pid
                atomic_json(state_path, state)
                start = last = clock()
                latest, task_pid, sequence, seen, stop_reason = None, None, 0, set(), None
                try:
                    while worker.poll() is None:
                        try:
                            ready = json.loads((directory / "READY.json").read_text(encoding="utf-8"))
                            if ready["nonce"] == nonce and type(ready["task_pid"]) is int:
                                task_pid = ready["task_pid"]
                        except (OSError, ValueError, KeyError, TypeError):
                            pass
                        progress = read_progress(progress_path, nonce, task_pid, sequence, seen)
                        if progress is not None:
                            latest, sequence = progress, progress["sequence"]
                            seen.add(progress["milestone"])
                            last = clock()
                            row["last_completed_milestone"] = progress["milestone"]
                            atomic_json(state_path, state)
                        now = clock()
                        stop_reason = timeout_reason(start, last, now, idle_seconds, hard_seconds)
                        if stop_reason:
                            break
                        time.sleep(min(0.05, idle_seconds / 5))
                finally:
                    stop_tree(worker)
                # The command can finish between polls; read its final atomic checkpoint once more.
                try:
                    task_pid = json.loads((directory / "READY.json").read_text(encoding="utf-8"))["task_pid"]
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                final = read_progress(progress_path, nonce, task_pid, sequence, seen)
                if final is not None:
                    latest = final
                proof = reconcile(root, latest, nonce, state["source_digest"])
                row["retained_proof"] = retain_receipt(root, directory, latest, nonce)
                if proof["status"] == "VERIFIED_COMPLETE" and row["retained_proof"]["errors"]:
                    proof = {"status": "INCOMPLETE", "reason": "Completed proof could not be preserved"}
                row.update(status="RECOVERED_COMPLETE" if stop_reason and proof["status"] == "VERIFIED_COMPLETE"
                           else "COMPLETE" if proof["status"] == "VERIFIED_COMPLETE" and worker.returncode == 0
                           else "INCOMPLETE", stop_reason=stop_reason, returncode=worker.returncode,
                           reconciliation=proof)
                if row["status"] in {"COMPLETE", "RECOVERED_COMPLETE"}:
                    succeeded = True
                atomic_json(state_path, state)
            if succeeded or not stop_reason or not step.replay_safe or q.source_digest(root) != state["source_digest"]:
                break
        if not succeeded:
            state.update(status="BLOCKED", next_action="REPAIR_OR_VERIFY_" + step.name)
            atomic_json(state_path, state)
            return state_path
        state["remaining_steps"].pop(0)
        atomic_json(state_path, state)
    state.update(status="PASS", next_action="REVIEW_CURRENT_PHASE_EXIT_CRITERIA_NOT_AUTOMATIC_ACCEPTANCE")
    atomic_json(state_path, state)
    return state_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("check", "native", "phase", "local"))
    args = parser.parse_args()
    path = supervise(ROOT, presets(args.task))
    report = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps({"status": report["status"], "state": str(path), "remaining": report["remaining_steps"]}))
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
