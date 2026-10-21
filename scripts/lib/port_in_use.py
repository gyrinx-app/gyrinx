#!/usr/bin/env python3
"""Say whether a dev port is already taken.

Exit 0 when something is listening. Exit 1 when the port is free.

A connect to 127.0.0.1 catches a listener there. Binding 0.0.0.0 catches a
listener on another address, which still stops runserver. A sandbox that
refuses that bind is not a listener: EPERM and EACCES leave the port free.
Dev ports are above 1024, so EACCES here is not the privileged-port check.

    scripts/lib/port_in_use.py 8482

Uses the standard library only, so it runs before the worktree venv exists.
"""

import errno
import socket
import sys


def port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return True
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # Probe only. The socket closes immediately and nothing listens.
            probe.bind(("0.0.0.0", port))  # nosec B104
        except OSError as exc:
            return exc.errno == errno.EADDRINUSE
    return False


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: port_in_use.py <port>", file=sys.stderr)
        return 2
    return 0 if port_in_use(int(argv[1])) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
