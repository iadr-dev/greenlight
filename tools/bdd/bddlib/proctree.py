"""Run a command, and on a timeout stop it together with everything it started, without waiting for its pipes.

``subprocess.run(timeout=...)`` kills only the process it started. A build tool is rarely that process: ``gradlew.bat``
is a ``cmd.exe`` that starts a Java process, which starts daemons. The Java process inherits the output pipes, so it
holds them after ``cmd.exe`` is gone. On POSIX the call then returns (but leaves the tree running); on Windows
``subprocess.run`` reads the pipes again with no limit and blocks until the last holder exits, which can be never.

Here the command starts in its own process group (POSIX) or job object (Windows), a timeout ends all of it, and the
output is read by threads that are waited for only a bounded time. A command that has finished normally is not
stopped: a build daemon it left running is meant to live on.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

GRACE = 5.0           # seconds to collect the output of a command that has ended or been stopped

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _PROCESS_SET_QUOTA, _PROCESS_TERMINATE = 0x0100, 0x0001
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


@dataclass
class Completed:
    returncode: int
    stdout: str
    stderr: str


class TimedOut(Exception):
    """The command ran longer than its limit and was stopped; ``stdout`` and ``stderr`` hold what it had written."""

    def __init__(self, timeout: float, stdout: str, stderr: str):
        super().__init__(f"timed out after {timeout} s")
        self.timeout, self.stdout, self.stderr = timeout, stdout, stderr


class Tree:
    """The command's process and all it starts: a job object on Windows, a process group elsewhere."""

    def __init__(self, pid: int):
        self.pid = pid
        self.job = None
        if os.name != "nt":
            return
        job = _kernel32.CreateJobObjectW(None, None)
        process = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        # a process started between its creation and this call has escaped the job; the window is a few microseconds
        if job and process and _kernel32.AssignProcessToJobObject(job, process):
            self.job = job
        elif job:
            _kernel32.CloseHandle(job)
        if process:
            _kernel32.CloseHandle(process)

    def kill(self) -> None:
        if os.name != "nt":
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass             # nothing of the group is left
        elif self.job:
            _kernel32.TerminateJobObject(self.job, 1)
        else:                    # the process could not be put in a job (taskkill ends a tree by its parent links)
            subprocess.run(["taskkill", "/PID", str(self.pid), "/T", "/F"], capture_output=True, check=False)

    def close(self) -> None:
        """Release the job object. Closing it does not end the processes in it."""
        if self.job:
            _kernel32.CloseHandle(self.job)
            self.job = None


class Reader(threading.Thread):
    """Collects what one pipe delivers. A daemon thread: one that cannot finish is abandoned, not waited for."""

    def __init__(self, stream):
        super().__init__(daemon=True)
        self.stream, self.chunks = stream, []
        self.start()

    def run(self) -> None:
        try:
            while chunk := self.stream.read(65536):
                self.chunks.append(chunk)
        except (OSError, ValueError):
            pass
        finally:
            self.stream.close()              # a reader abandoned on a held pipe closes it when the holder ends

    def text(self) -> str:
        return b"".join(self.chunks).decode("utf-8", errors="replace").replace("\r\n", "\n")


def run(argv: list[str], *, cwd: Path | str | None = None, env: dict[str, str] | None = None,
        timeout: float, grace: float = GRACE) -> Completed:
    """Run ``argv`` with an empty standard input and return its status and output. Raises ``TimedOut`` after ``timeout``
    seconds, having stopped the command and everything it started. Waits at most ``grace`` seconds for the output of a
    command that has ended: a process it left behind that still holds a pipe does not delay the result."""
    flags = {"start_new_session": True} if os.name != "nt" else {}
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, bufsize=0, **flags)
    tree = Tree(process.pid)
    out, err = Reader(process.stdout), Reader(process.stderr)
    timed_out = False
    try:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            tree.kill()
            process.wait()
        deadline = time.monotonic() + grace
        for reader in (out, err):
            reader.join(max(0.0, deadline - time.monotonic()))
    except BaseException:
        tree.kill()              # an interrupt must not leave the tree running either
        raise
    finally:
        tree.close()
    if timed_out:
        raise TimedOut(timeout, out.text(), err.text())
    return Completed(process.returncode, out.text(), err.text())
