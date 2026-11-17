"""Acquire the provisioning shell's inherited fd 9 on macOS and Linux.

The parent shell keeps this file description open after this helper exits.
Never unlock or unlink it here: ownership lasts until the provisioning subshell
and its children close their descriptors.
"""

import fcntl
import sys
import time


def acquire(label: str, timeout: float = 120) -> int:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return 0
        except BlockingIOError:
            if time.monotonic() >= deadline:
                print(f"[gyrinx] Timed out waiting for the {label}.", file=sys.stderr)
                return 1
            time.sleep(0.1)
        except OSError as exc:
            print(f"[gyrinx] Could not acquire the {label}: {exc}.", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(acquire(sys.argv[1]))
