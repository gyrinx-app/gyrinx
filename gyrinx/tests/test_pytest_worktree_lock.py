"""A second pytest in one worktree shares test database names.

yew (4 Oct) and wren (27 Sep) on #lessons: a focused suite beside a full
suite died during schema creation. The root conftest holds
``logs/pytest.lock`` and the second process exits.

Not marked core: that suite is capped. CI still runs this file when a
pull request changes it, and the full suite runs it on every push.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from gyrinx import pytest_worktree_lock
from gyrinx.pytest_worktree_lock import (
    WorktreePytestLock,
    busy_message,
    is_xdist_worker,
)

ROOT = Path(__file__).resolve().parents[2]


def test_the_holder_records_its_pid(tmp_path):
    lock = WorktreePytestLock(tmp_path)
    assert lock.acquire() is None
    try:
        assert lock.path.read_text().strip() == str(os.getpid())
    finally:
        lock.release()


def test_a_second_lock_names_the_holder_and_the_shared_databases(tmp_path):
    holder = WorktreePytestLock(tmp_path)
    assert holder.acquire() is None
    try:
        message = WorktreePytestLock(tmp_path).acquire()
    finally:
        holder.release()

    assert message == busy_message(os.getpid())
    assert f"pid {os.getpid()}" in message
    assert "test_<DB>_gwN" in message
    assert "Wait for it to finish" in message


def test_a_lock_with_no_pid_still_says_to_wait(tmp_path):
    holder = WorktreePytestLock(tmp_path)
    assert holder.acquire() is None
    try:
        holder.path.write_text("")
        message = WorktreePytestLock(tmp_path).acquire()
    finally:
        holder.release()

    assert message == busy_message(None)
    assert "pid" not in message


def test_release_lets_the_next_acquire_succeed(tmp_path):
    first = WorktreePytestLock(tmp_path)
    assert first.acquire() is None
    first.release()

    second = WorktreePytestLock(tmp_path)
    assert second.acquire() is None
    try:
        assert second.path.read_text().strip() == str(os.getpid())
    finally:
        second.release()


def test_a_dead_process_does_not_keep_the_lock(tmp_path):
    code = textwrap.dedent(
        """\
        import os
        import sys

        sys.path.insert(0, sys.argv[1])
        from gyrinx.pytest_worktree_lock import WorktreePytestLock

        message = WorktreePytestLock(sys.argv[2]).acquire()
        if message:
            print(message)
            raise SystemExit(2)
        os._exit(0)
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(ROOT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    lock = WorktreePytestLock(tmp_path)
    assert lock.acquire() is None
    lock.release()


def test_an_xdist_worker_does_not_take_its_own_lock():
    class Config:
        workerinput = {"workerid": "gw0"}

    assert is_xdist_worker(Config()) is True


def test_the_controller_takes_the_lock():
    class Config:
        pass

    assert is_xdist_worker(Config()) is False


def _config(root, *, worker=False):
    class Config:
        def __init__(self):
            self.rootpath = root
            self.stash = pytest.Stash()
            if worker:
                self.workerinput = {"workerid": "gw0"}

    return Config()


def test_configure_exits_when_this_worktree_lock_is_held(tmp_path):
    holder = WorktreePytestLock(tmp_path)
    assert holder.acquire() is None
    try:
        with pytest.raises(pytest.exit.Exception) as raised:
            pytest_worktree_lock.pytest_configure(_config(tmp_path))
    finally:
        holder.release()

    assert raised.value.returncode == 2
    assert raised.value.msg == busy_message(os.getpid())


def test_configure_locks_and_unconfigure_releases(tmp_path):
    config = _config(tmp_path)
    pytest_worktree_lock.pytest_configure(config)
    try:
        assert WorktreePytestLock(tmp_path).acquire() == busy_message(os.getpid())
    finally:
        pytest_worktree_lock.pytest_unconfigure(config)

    released = WorktreePytestLock(tmp_path)
    assert released.acquire() is None
    released.release()


def test_configure_on_a_worker_leaves_the_controllers_lock_alone(tmp_path):
    holder = WorktreePytestLock(tmp_path)
    assert holder.acquire() is None
    try:
        config = _config(tmp_path, worker=True)
        pytest_worktree_lock.pytest_configure(config)
        pytest_worktree_lock.pytest_unconfigure(config)
        assert WorktreePytestLock(tmp_path).acquire() == busy_message(os.getpid())
    finally:
        holder.release()
