"""One bounded, owned observation process; commands never certify live origin."""

import base64
import binascii
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from consilium.adapters.qwen_page_reader import (
    MAX_CAPTURE_BYTES,
    _require_bounded_depth,
    _unique_object,
)
from consilium.core.browser_probe import BrowserContext
from consilium.shell.qwen_capture_ingest import QwenCaptureRead

MAX_READER_BYTES = 3 * 1048576


def decode_reader_output(raw):
    invalid = False
    try:
        if type(raw) is not bytes or not raw or len(raw) > MAX_READER_BYTES:
            raise ValueError("size")
        _require_bounded_depth(raw)
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "before", "raw_capture_base64", "after"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or type(value["raw_capture_base64"]) is not str
        ):
            raise ValueError("schema")
        capture = base64.b64decode(value["raw_capture_base64"], validate=True)
        if (
            not capture or len(capture) > MAX_CAPTURE_BYTES
            or base64.b64encode(capture).decode("ascii") != value["raw_capture_base64"]
        ):
            raise ValueError("capture")
        before = BrowserContext.model_validate_json(json.dumps(value["before"], allow_nan=False))
        after = BrowserContext.model_validate_json(json.dumps(value["after"], allow_nan=False))
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        invalid = True
    if invalid:
        raise ValueError("QWEN_READER_OUTPUT_INVALID")
    return QwenCaptureRead(before, capture, after)


def _stop_owned(worker, deadline):
    if os.name == "nt":
        if worker.poll() is None:
            worker.kill()  # Worker exit closes its sole job handle.
    else:
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    worker.wait(timeout=max(0.001, deadline - time.monotonic()))


class QwenProcessReader:
    """Execute a configured read-only command once with no shell or retries.

    The operator must supply an observation-only command. This does not sandbox
    arbitrary command behavior or certify account/model/site observations.
    The worker owns only newly spawned descendants, never an attached browser.
    Execution budget is 0 < seconds <= 60, plus at most five seconds for cleanup.
    stderr is discarded; bounded stdout is private and validated before return.
    """

    def __init__(self, command: tuple[str, ...], *, timeout_seconds=30.0):
        if (
            type(command) is not tuple or not command
            or any(type(arg) is not str or not arg or "\0" in arg for arg in command)
            or type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 60
        ):
            raise ValueError("QWEN_READER_CONFIGURATION_INVALID")
        self.command = command
        self.timeout_seconds = float(timeout_seconds)

    def __call__(self):
        output = bytearray()
        overflow, stream_failed = threading.Event(), threading.Event()
        failure = None
        with tempfile.TemporaryDirectory(prefix="consilium-read-") as directory:
            config = Path(directory) / "command.json"
            config.write_text(json.dumps({"command": self.command, "parent_pid": os.getpid()}))
            start = time.monotonic()
            environment = dict(os.environ)
            package_root = str(Path(__file__).resolve().parents[2])
            environment["PYTHONPATH"] = package_root + (
                os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
            )
            try:
                worker = subprocess.Popen(
                    [sys.executable, "-m", "consilium.shell.qwen_reader_worker", str(config)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    shell=False, start_new_session=os.name != "nt",
                    env=environment,
                )
            except OSError:
                failure = "QWEN_READER_START_FAILED"
            if failure:
                raise ValueError(failure)

            def drain():
                try:
                    while chunk := worker.stdout.read(65536):
                        if len(output) + len(chunk) > MAX_READER_BYTES:
                            overflow.set()
                            return
                        output.extend(chunk)
                except OSError:
                    stream_failed.set()

            thread = threading.Thread(target=drain, daemon=True)
            thread.start()
            try:
                while worker.poll() is None:
                    if overflow.is_set():
                        failure = "QWEN_READER_OUTPUT_OVERSIZED"
                        break
                    remaining = self.timeout_seconds - (time.monotonic() - start)
                    if remaining <= 0:
                        failure = "QWEN_READER_TIMEOUT"
                        break
                    try:
                        worker.wait(timeout=min(0.02, remaining))
                    except subprocess.TimeoutExpired:
                        pass
                if time.monotonic() - start >= self.timeout_seconds and failure is None:
                    failure = "QWEN_READER_TIMEOUT"
                if failure is None and worker.returncode != 0:
                    failure = "QWEN_READER_PROCESS_FAILED"
            finally:
                cleanup_deadline = time.monotonic() + 5
                try:
                    _stop_owned(worker, cleanup_deadline)
                except (OSError, subprocess.TimeoutExpired):
                    failure = "QWEN_READER_CLEANUP_FAILED"
                thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))
                if not thread.is_alive():
                    worker.stdout.close()
            if thread.is_alive() or stream_failed.is_set():
                failure = "QWEN_READER_STREAM_FAILED"
            elif overflow.is_set():
                failure = "QWEN_READER_OUTPUT_OVERSIZED"
        if failure:
            raise ValueError(failure)
        return decode_reader_output(bytes(output))
