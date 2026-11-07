"""Hold one exclusive pytest-controller lock per worktree.

Separate invocations share test_<DB>_gwN database names and would collide
during schema creation. Xdist workers use the controller's lock; the
kernel releases it when the controller exits.

Load this as a pytest plugin rather than from root conftest.py: editing
that conftest selects the whole suite for the required CI job.
"""

import errno
import fcntl
import os
from pathlib import Path

import pytest


def is_xdist_worker(config) -> bool:
    """Workers share the controller's test databases on purpose."""
    return getattr(config, "workerinput", None) is not None


_LOCK = pytest.StashKey()


def pytest_configure(config):
    """Hold the worktree lock for this session, or exit if it is taken."""
    if is_xdist_worker(config):
        return
    lock = WorktreePytestLock(config.rootpath)
    message = lock.acquire()
    if message:
        pytest.exit(message, returncode=2)
    config.stash[_LOCK] = lock


def pytest_unconfigure(config):
    """Drop the worktree lock when this process is finished."""
    lock = config.stash.get(_LOCK, None)
    if lock is not None:
        lock.release()


class WorktreePytestLock:
    """Exclusive lock at ``logs/pytest.lock`` for this checkout."""

    def __init__(self, rootpath):
        self.path = Path(rootpath) / "logs" / "pytest.lock"
        self._fd: int | None = None

    def acquire(self) -> str | None:
        """Take the lock. Return an error message when another pytest holds it."""
        if self._fd is not None:
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            message = busy_message(_read_pid(fd))
            os.close(fd)
            return message
        except OSError as exc:
            os.close(fd)
            if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            return busy_message(None)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd
        return None

    def release(self) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def busy_message(pid: int | None) -> str:
    who = f"pytest (pid {pid})" if pid else "another pytest"
    return (
        f"{who} is already using this worktree's test databases "
        "(test_<DB> and test_<DB>_gwN). Wait for it to finish, then run one suite."
    )


def _read_pid(fd: int) -> int | None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 32).decode(errors="replace").strip()
    except OSError:
        return None
    if raw.isdigit():
        return int(raw)
    return None
