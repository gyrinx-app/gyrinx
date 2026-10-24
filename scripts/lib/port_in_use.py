#!/usr/bin/env python3
"""Say whether a dev port is already taken.

Exit 0 when something is listening. Exit 1 when the port is free.

A connect to 127.0.0.1 catches a listener there. /proc/net/tcp catches a
listener on another IPv4 address, which still stops runserver. Binding
127.0.0.1 catches a wildcard socket that has not called listen yet: that
socket is missing from the table, and it still occupies the port. The probe
never binds every interface.

A sandbox that refuses the loopback bind is not a listener: EPERM and
EACCES leave the port free. Dev ports are above 1024, so EACCES here is
not the privileged-port check.

    scripts/lib/port_in_use.py 8482

Uses the standard library only, so it runs before the worktree venv exists.
"""

import errno
import socket
import sys

_LISTEN = "0A"


def _ipv4_listener(port: int) -> bool:
    """True when /proc/net/tcp shows an IPv4 listener on this port.

    Missing or unreadable tables mean unknown, so the caller falls through
    to the loopback bind. A bound socket that has not called listen does
    not appear here.
    """
    hexport = f"{port:04X}"
    try:
        with open("/proc/net/tcp", encoding="ascii", errors="replace") as handle:
            next(handle, None)
            for line in handle:
                fields = line.split()
                if len(fields) < 4 or fields[3] != _LISTEN:
                    continue
                if fields[1].rsplit(":", 1)[-1].upper() == hexport:
                    return True
    except OSError:
        return False
    return False


def port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return True
    if _ipv4_listener(port):
        return True
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
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
