"""Measure pytest without changing its test selection or worker count."""

import argparse
import hashlib
import json
import os
import platform
import resource
import shutil
import subprocess  # nosec B404 - Fixed argv lists; no shell or command text.
import sys
import time
from pathlib import Path

from defusedxml import ElementTree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, default=Path("logs/test-performance"))
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.label or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for c in args.label
    ):
        parser.error(
            "--label must contain only letters, digits, hyphens or underscores"
        )
    pytest_args = args.pytest_args
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]

    args.output.mkdir(parents=True, exist_ok=True)
    report = args.output / f"{args.label}.xml"
    # Do not mistake a previous successful run for the current result if
    # pytest exits before it can write its report.
    report.unlink(missing_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--durations=50",
        *pytest_args,
        f"--junitxml={report}",
    ]
    git = shutil.which("git")
    if git is None:
        parser.error("git is required to record the measured revision")
    revision = subprocess.check_output([git, "rev-parse", "HEAD"], text=True).strip()
    diff = subprocess.check_output([git, "diff", "HEAD"])
    digest = hashlib.sha256(diff)
    untracked = subprocess.check_output(
        [git, "ls-files", "--others", "--exclude-standard", "-z"]
    ).split(b"\0")
    for path in sorted(path for path in untracked if path):
        digest.update(path + b"\0")
        digest.update(Path(os.fsdecode(path)).read_bytes())
        digest.update(b"\0")
    started = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = subprocess.run(command, check=False)
    elapsed = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    measured = {
        "label": args.label,
        "revision": revision,
        "working_tree_sha256": digest.hexdigest(),
        "command": command,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "wall_seconds": elapsed,
        "user_cpu_seconds": after.ru_utime - before.ru_utime,
        "system_cpu_seconds": after.ru_stime - before.ru_stime,
        "exit_code": result.returncode,
    }
    if report.exists():
        suites = ElementTree.parse(report).getroot().iter("testsuite")
        counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
        for suite in suites:
            for key in counts:
                counts[key] += int(suite.get(key, "0"))
        measured.update(counts)
    output = args.output / f"{args.label}.json"
    output.write_text(json.dumps(measured, indent=2) + "\n")
    print(f"\nMeasurement saved to {output}", flush=True)
    print(json.dumps(measured, sort_keys=True), flush=True)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
