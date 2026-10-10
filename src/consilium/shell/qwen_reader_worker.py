"""Contain a configured observation process before executing it; no live grant."""

import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from consilium.shell.windows_job import windows_job


def main(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    ownership = windows_job() if os.name == "nt" else None
    parent_handle = None
    if ownership:
        from ctypes import wintypes as w

        kernel = ownership[0]
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.WaitForSingleObject.restype = w.DWORD
        parent_handle = kernel.OpenProcess(0x00100000, False, config["parent_pid"])
        if not parent_handle:
            raise ctypes.WinError(ctypes.get_last_error())
    task = subprocess.Popen(config["command"], stdin=subprocess.DEVNULL, shell=False)
    while task.poll() is None:
        if parent_handle and ownership[0].WaitForSingleObject(parent_handle, 0) != 0x102:
            return 125
        if os.name != "nt" and os.getppid() != config["parent_pid"]:
            os.killpg(os.getpid(), signal.SIGKILL)
        time.sleep(0.02)
    return task.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
