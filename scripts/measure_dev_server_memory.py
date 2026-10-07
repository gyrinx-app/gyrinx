#!/usr/bin/env python
"""Measure how much memory a dev server holds after serving the same pages again and again.

Starts this worktree's ``manage runserver`` with ``settings_dev`` on a free
port, logs in as an agent user, requests each URL once per round, and reads the
server's memory after every request. On macOS that is the physical footprint,
the figure Activity Monitor shows, which counts compressed memory. Elsewhere it
is the resident size.

The debug toolbar keeps the last 25 requests, so run at least 7 rounds of 4
pages to see where memory settles. The guard in gyrinx/devserver/guard.py is
turned off for the run, so it does not restart the server it is measuring.

    .venv/bin/python scripts/measure_dev_server_memory.py --rounds 8 \\
        /n26/gangs/<id>/ /n26/fighters/<id>/edit/

Prints one JSON line: memory after start-up, after the first round and at the
end, the peak, and the median request time.
"""

import argparse
import http.cookiejar
import json
import os
import re
import signal
import socket
import statistics
import subprocess  # nosec B404 — starts runserver and footprint with fixed arguments
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def memory_mb(pid):
    if sys.platform == "darwin":
        out = subprocess.run(  # nosec B607 — fixed argv; footprint resolved from PATH
            ["footprint", "-p", str(pid)], capture_output=True, text=True
        ).stdout
        match = re.search(r"phys_footprint:\s+([\d.]+)\s+(KB|MB|GB)", out)
        if not match:
            return float("nan")
        scale = {"KB": 1 / 1024, "MB": 1, "GB": 1024}[match.group(2)]
        return float(match.group(1)) * scale
    with open(f"/proc/{pid}/status") as status:
        for line in status:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return float("nan")


def wait_until_up(base):
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base + "/robots.txt", timeout=2)  # nosec B310 — local http URL
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(0.5)
    raise SystemExit("The dev server did not start within two minutes.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "urls", nargs="+", help="paths to request, such as /n26/gangs/<id>/"
    )
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument(
        "--user", default="agent-memory", help="agent user to log in as"
    )
    parser.add_argument(
        "--log", default=os.devnull, help="file for the server's output"
    )
    args = parser.parse_args()

    port = free_port()
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "gyrinx.settings_dev",
        "DJANGO_PORT": str(port),
        "GYRINX_DEV_MEMORY_LIMIT_MB": "0",
        "GYRINX_DEV_IDLE_MINUTES": "0",
    }
    manage = Path(sys.executable).parent / "manage"
    with open(args.log, "w") as log:
        server = subprocess.Popen(
            [str(manage), "runserver", "--noreload", f"127.0.0.1:{port}"],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        base = f"http://127.0.0.1:{port}"
        wait_until_up(base)
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        opener.open(f"{base}/_debug/login/?user={args.user}&next=/", timeout=60).read()

        start_mb = memory_mb(server.pid)
        samples, times = [], []
        for round_number in range(1, args.rounds + 1):
            for url in args.urls:
                started = time.perf_counter()
                try:
                    with opener.open(base + url, timeout=300) as response:
                        size, status = len(response.read()), response.status
                except urllib.error.HTTPError as error:
                    size, status = len(error.read()), error.code
                times.append(time.perf_counter() - started)
                samples.append(memory_mb(server.pid))
                if round_number == 1:
                    print(
                        f"  {status} {size:>9,} B {times[-1] * 1000:6.0f} ms "
                        f"{samples[-1]:8.0f} MB  {url}",
                        file=sys.stderr,
                    )
            print(
                f"  round {round_number}: {samples[-1]:.0f} MB after "
                f"{len(samples)} requests",
                file=sys.stderr,
            )
        print(
            json.dumps(
                {
                    "requests": len(samples),
                    "start_mb": round(start_mb),
                    "after_first_round_mb": round(samples[len(args.urls) - 1]),
                    "final_mb": round(samples[-1]),
                    "peak_mb": round(max(samples)),
                    "median_ms": round(statistics.median(times) * 1000),
                }
            )
        )
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)


if __name__ == "__main__":
    main()
