"""A sibling worktree can hash to the same dev port.

Not marked core: that suite is capped and was already full. CI still runs
this file when a pull request changes it, and the full suite runs it on
every push.
"""

import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKTREE_SH = REPO_ROOT / "scripts" / "lib" / "worktree.sh"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def sys_executable() -> str:
    return sys.executable


class _RunserverProcess:
    """A listener whose command line contains runserver."""

    def __init__(self, port: int, cwd: Path):
        self.port = port
        self.cwd = cwd
        self.proc: subprocess.Popen | None = None

    def __enter__(self):
        # The filename is part of the command line, which is how dev.sh
        # recognises this worktree's runserver.
        script = self.cwd / "runserver"
        script.write_text(
            textwrap.dedent(
                """\
                import socket
                import sys

                # Accept and close, like a real server. A listener that
                # never accepts fills its queue, and macOS then refuses
                # the probe that asks whether the port is in use.
                port = int(sys.argv[1])
                sock = socket.socket()
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
                sock.listen(16)
                sock.settimeout(60)
                while True:
                    try:
                        conn, _ = sock.accept()
                    except TimeoutError:
                        break
                    conn.close()
                """
            )
        )
        self.proc = subprocess.Popen(
            [sys_executable(), str(script), str(self.port)],
            cwd=self.cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            with socket.socket() as probe:
                probe.settimeout(0.1)
                if probe.connect_ex(("127.0.0.1", self.port)) == 0:
                    return self
            if self.proc.poll() is not None:
                error = self.proc.stderr.read() if self.proc.stderr else ""
                raise RuntimeError(f"listener exited {self.proc.returncode}: {error}")
            time.sleep(0.05)
        raise RuntimeError(f"listener did not bind {self.port}")

    def __exit__(self, *_args):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def test_worktree_port_prefers_logs_dev_port(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "dev-port").write_text("9648\n")
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1" && worktree_port "$2"',
            "test",
            str(WORKTREE_SH),
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "9648"


def test_invalid_dev_port_file_is_ignored(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "dev-port").write_text("nope\n")
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1" && _worktree_saved_port "$2"',
            "test",
            str(WORKTREE_SH),
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_port_is_listening_sees_a_bound_socket():
    port = _free_port()
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        listening = subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source "$1" && port_is_listening "$2"',
                "test",
                str(WORKTREE_SH),
                str(port),
            ],
            text=True,
            capture_output=True,
        )
    assert listening.returncode == 0, listening.stderr
    closed = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1" && port_is_listening "$2"',
            "test",
            str(WORKTREE_SH),
            str(port),
        ],
        text=True,
        capture_output=True,
    )
    assert closed.returncode == 1


def test_next_free_dev_port_skips_a_listener():
    port = _free_port()
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        result = subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source "$1" && next_free_dev_port "$2"',
                "test",
                str(WORKTREE_SH),
                str(port - 1),
            ],
            text=True,
            capture_output=True,
        )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) != port


def test_choose_dev_port_records_a_free_port_when_a_sibling_has_it(tmp_path):
    worktree = tmp_path / "ours"
    sibling = tmp_path / "sibling"
    worktree.mkdir()
    sibling.mkdir()
    port = _free_port()
    with _RunserverProcess(port, sibling):
        result = subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source "$1" && choose_dev_port "$2" "$3"',
                "test",
                str(WORKTREE_SH),
                str(worktree),
                str(port),
            ],
            text=True,
            capture_output=True,
        )
    assert result.returncode == 0, result.stderr
    chosen = int(result.stdout.strip())
    assert chosen != port
    assert (worktree / "logs" / "dev-port").read_text().strip() == str(chosen)
    assert "already in use by another process" in result.stderr
    assert "logs/dev-port" in result.stderr


def test_choose_dev_port_leaves_this_worktree_server_alone(tmp_path):
    port = _free_port()
    with _RunserverProcess(port, tmp_path):
        result = subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source "$1" && choose_dev_port "$2" "$3"',
                "test",
                str(WORKTREE_SH),
                str(tmp_path),
                str(port),
            ],
            text=True,
            capture_output=True,
        )
    assert result.returncode == 10, result.stderr
    assert result.stdout.strip() == str(port)
    assert not (tmp_path / "logs" / "dev-port").exists()
    assert "already serving" in result.stderr


def test_choose_dev_port_returns_a_free_preferred_port(tmp_path):
    port = _free_port()
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1" && choose_dev_port "$2" "$3"',
            "test",
            str(WORKTREE_SH),
            str(tmp_path),
            str(port),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(port)
    assert not (tmp_path / "logs" / "dev-port").exists()


def test_a_sibling_whose_name_starts_with_ours_is_not_ours(tmp_path):
    """`gang-fix` must not read as `gang`'s own server."""
    worktree = tmp_path / "gang"
    sibling = tmp_path / "gang-fix"
    worktree.mkdir()
    sibling.mkdir()
    port = _free_port()
    with _RunserverProcess(port, sibling):
        result = subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source "$1" && choose_dev_port "$2" "$3"',
                "test",
                str(WORKTREE_SH),
                str(worktree),
                str(port),
            ],
            text=True,
            capture_output=True,
        )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) != port


def test_a_port_bound_on_the_wildcard_address_counts_as_in_use():
    """runserver binds 0.0.0.0, so a port it cannot bind is not free,
    even when nothing answers on 127.0.0.1."""
    port = _free_port()
    with socket.socket() as holder:
        holder.bind(("0.0.0.0", port))
        result = subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source "$1" && port_is_listening "$2"',
                "test",
                str(WORKTREE_SH),
                str(port),
            ],
            text=True,
            capture_output=True,
        )
    assert result.returncode == 0, result.stderr
