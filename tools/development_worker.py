"""Own a development subprocess tree before starting any real command."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from development_progress import atomic_json


def windows_job():
    """Keep the sole non-inheritable job handle in this worker until it exits."""
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", w.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                    ("active", w.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", w.DWORD), ("scheduling", w.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway flags.
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    return kernel, job


def main(config_path: Path) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    ownership = windows_job() if os.name == "nt" else None
    parent_handle = None
    if ownership:
        from ctypes import wintypes as w
        kernel = ownership[0]
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.WaitForSingleObject.restype = w.DWORD
        parent_handle = kernel.OpenProcess(0x00100000, False, config["supervisor_pid"])
        if not parent_handle:
            raise ctypes.WinError(ctypes.get_last_error())
    # On Windows assignment to the job precedes spawning the task; failure is closed.
    task = subprocess.Popen(config["command"], cwd=config["root"], stdin=subprocess.DEVNULL,
                            shell=False)
    atomic_json(config_path.with_name("READY.json"), {"nonce": config["nonce"], "task_pid": task.pid,
                                                     "containment": "WINDOWS_JOB" if ownership else "POSIX_SESSION"})
    while task.poll() is None:
        if parent_handle and ownership[0].WaitForSingleObject(parent_handle, 0) != 0x102:
            return 125  # Worker exit closes its job and stops descendants.
        if os.name != "nt" and os.getppid() != config["supervisor_pid"]:
            # A dead supervisor must not leave its ordinary project children running.
            import signal
            os.killpg(os.getpid(), signal.SIGKILL)
        time.sleep(0.05)
    return task.returncode


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
