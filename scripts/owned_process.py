"""Linux subreaper for one command; native sessions remain in its owned tree."""
import ctypes
import errno
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def process(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(fields[1]), int(fields[19]), fields[0]  # PPID, start ticks, state
    except (OSError, IndexError, ValueError):
        return None


def descendants(owner):
    rows = {}
    with os.scandir("/proc") as entries:
        for entry in entries:
            if entry.name.isdecimal():
                value = process(int(entry.name))
                if value:
                    rows[int(entry.name)] = value
    owned = {owner}
    while True:
        added = {pid for pid, value in rows.items() if value[0] in owned} - owned
        if not added:
            return {pid: rows[pid] for pid in owned - {owner}}
        owned.update(added)


def signal_owned(owner, pid, identity, signum):
    fd = None
    try:
        if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
            try:
                fd = os.pidfd_open(pid)
            except OSError as error:
                if error.errno not in (errno.ENOSYS, errno.EINVAL, errno.EPERM):
                    raise
        current = process(pid)
        if current is None or current[1] != identity[1]:
            return False
        cursor, seen = pid, set()
        while cursor != owner:
            value = process(cursor)
            if value is None or cursor in seen or cursor <= 1:
                return False
            seen.add(cursor)
            cursor = value[0]
        if fd is not None:
            signal.pidfd_send_signal(fd, signum)
        else:
            current = process(pid)
            if current is None or current[1] != identity[1]:
                return False
            os.kill(pid, signum)
        return True
    except ProcessLookupError:
        pass
    finally:
        if fd is not None:
            os.close(fd)


def main():
    if sys.platform != "linux" or len(sys.argv) < 5 or sys.argv[1] != "--receipt" or sys.argv[3] != "--":
        raise SystemExit("Usage (Linux): owned_process.py --receipt FILE -- COMMAND [ARG...]")
    receipt, owner = Path(sys.argv[2]), os.getpid()

    def record(cleanup, code, remaining=""):
        temporary = receipt.with_name(receipt.name + ".tmp")
        temporary.write_text(f"cleanup={cleanup}\nsubreaper_pid={owner}\nexit_code={code}\nremaining={remaining}\n")
        os.replace(temporary, receipt)

    record("pending", "")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, ctypes.c_ulong(1), ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_ulong(0)) != 0:
        print(f"owned_process: PR_SET_CHILD_SUBREAPER errno={ctypes.get_errno()}", file=sys.stderr)
        record("unknown", 125)
        return 125
    stopping = [0]
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda sig, frame: stopping.__setitem__(0, stopping[0] or sig))
    child, code = None, 125

    def reap():
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return True  # Kernel ECHILD proves no remaining owned descendant.
            if pid == 0:
                return False
            if child is not None and pid == child.pid:
                child.returncode = os.waitstatus_to_exitcode(status)

    try:
        child = subprocess.Popen(sys.argv[4:])
        while child.returncode is None and not stopping[0]:
            reap()
            if child.returncode is None:
                time.sleep(0.05)
        code = child.returncode if child.returncode is not None else 128 + stopping[0]
        if code < 0:
            code = 128 - code
    except BaseException as error:
        print(f"owned_process: {type(error).__name__}: {error}", file=sys.stderr)
    finally:
        term_until, sent = time.monotonic() + 15.0, set()
        while True:
            if reap():
                code = 128 + stopping[0] if stopping[0] else code
                record("confirmed", code)
                return code
            now = time.monotonic()
            if now >= term_until + 5.0:
                remaining = " ".join(f"{pid}:{value[1]}" for pid, value in descendants(owner).items())
                record("unknown", 125, remaining)
                return 125
            signum = signal.SIGTERM if now < term_until else signal.SIGKILL
            for pid, identity in descendants(owner).items():
                key = (pid, identity[1], signum)
                if identity[2] != "Z" and key not in sent:
                    try:
                        if signal_owned(owner, pid, identity, signum):
                            sent.add(key)
                    except OSError:
                        pass  # Retry; final ECHILD, never signal delivery, proves cleanup.
            time.sleep(0.05)


if __name__ == "__main__":
    sys.exit(main())
