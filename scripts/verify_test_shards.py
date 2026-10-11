"""Verify full-suite execution evidence from all shards (standard library only)."""

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


class InvalidManifest(ValueError):
    """A manifest cannot prove one successful, complete execution."""


def _require(condition, message):
    if not condition:
        raise InvalidManifest(message)


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _ids(value, label):
    _require(isinstance(value, list), f"{label} must be a list")
    _require(all(isinstance(v, str) and v for v in value), f"invalid {label}")
    _require(value == sorted(set(value)), f"{label} must be sorted and unique")
    return set(value)


def module_shard(nodeid, count):
    module = nodeid.split("::", 1)[0]
    return int.from_bytes(hashlib.sha256(module.encode()).digest(), "big") % count


def _validate_execution(manifest, selected):
    finished = _ids(manifest.get("finished"), "finished IDs")
    _require(finished == selected, "selected cases did not each finish exactly once")
    reports = manifest.get("reports")
    _require(isinstance(reports, list), "reports must be a list")
    by_case = defaultdict(dict)
    for report in reports:
        _require(isinstance(report, dict), "invalid execution report")
        nodeid = report.get("nodeid")
        when = report.get("when")
        outcome = report.get("outcome")
        _require(
            isinstance(nodeid, str) and nodeid in selected,
            "report belongs to an unselected case",
        )
        _require(
            isinstance(when, str) and when in ("setup", "call", "teardown"),
            "invalid report phase",
        )
        _require(
            isinstance(outcome, str) and outcome in ("passed", "skipped", "failed"),
            "invalid report outcome",
        )
        _require(when not in by_case[nodeid], "duplicate case execution/report phase")
        _require(
            "wasxfail" not in report or isinstance(report["wasxfail"], str),
            "invalid xfail reason",
        )
        _require(outcome != "failed", "a case reported failure")
        by_case[nodeid][when] = report
    statuses = Counter()
    for nodeid in selected:
        phases = by_case[nodeid]
        _require(
            "setup" in phases and "teardown" in phases, "missing setup/teardown report"
        )
        setup = phases["setup"]
        _require(phases["teardown"]["outcome"] == "passed", "unsuccessful teardown")
        if setup["outcome"] == "passed":
            _require("call" in phases, "missing call report after successful setup")
            result = phases["call"]
        else:
            _require("call" not in phases, "call report after skipped setup")
            result = setup
        if "wasxfail" in result:
            status = "xfailed" if result["outcome"] == "skipped" else "xpassed"
        else:
            status = result["outcome"]
        statuses[status] += 1
    counts = {
        "finished": len(finished),
        "reports": len(reports),
        "phases": dict(sorted(Counter(r["when"] for r in reports).items())),
        "outcomes": dict(sorted(Counter(r["outcome"] for r in reports).items())),
    }
    _require(manifest.get("counts") == counts, "execution counts differ from reports")
    return statuses


def verify_manifests(manifests, revision, *, run_id=None, run_attempt=None):
    """Return verified counts, coverage digest and the aggregate UTC time span."""
    _require(bool(manifests), "no shard manifests supplied")
    _require(
        (run_id is None) == (run_attempt is None),
        "run ID and attempt must be supplied together",
    )
    reference = None
    shard_count = None
    seen_indices = set()
    all_selected = set()
    statuses = Counter()
    starts = []
    ends = []
    for manifest in manifests:
        _require(isinstance(manifest, dict), "manifest must be an object")
        _require(
            _integer(manifest.get("format_version"))
            and manifest["format_version"] == 1,
            "unsupported manifest format",
        )
        _require(manifest.get("revision") == revision, "revision mismatch")
        if run_id is not None:
            _require(manifest.get("run_id") == str(run_id), "workflow run ID mismatch")
            _require(
                manifest.get("run_attempt") == str(run_attempt),
                "workflow run attempt mismatch",
            )
        count = manifest.get("shard_count")
        index = manifest.get("shard_index")
        _require(_integer(count) and count > 0, "invalid shard count")
        _require(_integer(index) and 0 <= index < count, "invalid shard index")
        if shard_count is None:
            shard_count = count
        _require(count == shard_count, "shard counts differ")
        _require(index not in seen_indices, "duplicate shard index")
        seen_indices.add(index)
        _require(
            _integer(manifest.get("exit_status")) and manifest["exit_status"] == 0,
            "nonzero or missing pytest exit status",
        )
        _require(
            manifest.get("collection_complete") is True
            and manifest.get("session_complete") is True,
            "incomplete collection/session",
        )
        _require(manifest.get("errors") == [], "manifest records session errors")
        collected = _ids(manifest.get("collected"), "collected IDs")
        _require(bool(collected), "empty full collection")
        selected = _ids(manifest.get("selected"), "selected IDs")
        if reference is None:
            reference = collected
        _require(collected == reference, "full collections differ")
        expected = {
            nodeid for nodeid in collected if module_shard(nodeid, count) == index
        }
        _require(
            selected == expected,
            "selection differs from deterministic module assignment",
        )
        _require(not all_selected & selected, "shard selections overlap")
        all_selected.update(selected)
        statuses.update(_validate_execution(manifest, selected))
        workers = manifest.get("workers")
        _require(isinstance(workers, list), "missing worker completion evidence")
        worker_ids = set()
        for worker in workers:
            _require(
                isinstance(worker, dict) and isinstance(worker.get("id"), str),
                "invalid worker evidence",
            )
            _require(worker["id"] not in worker_ids, "duplicate worker completion")
            worker_ids.add(worker["id"])
            _require(
                _integer(worker.get("exit_status")) and worker["exit_status"] == 0,
                "worker failed",
            )
        start, end = manifest.get("started_at"), manifest.get("finished_at")
        _require(
            all(
                isinstance(v, (float, int))
                and not isinstance(v, bool)
                and math.isfinite(v)
                for v in (start, end)
            ),
            "invalid session timestamps",
        )
        _require(0 < start <= end, "session timestamps out of order")
        starts.append(start)
        ends.append(end)
    _require(seen_indices == set(range(shard_count)), "missing shards")
    _require(all_selected == reference, "full collection has execution gaps")
    digest = hashlib.sha256("\n".join(sorted(reference)).encode()).hexdigest()
    return {
        "revision": revision,
        "shards": shard_count,
        "collected": len(reference),
        "executed": len(all_selected),
        "statuses": dict(sorted(statuses.items())),
        "coverage_sha256": digest,
        "started_at": min(starts),
        "finished_at": max(ends),
        "elapsed_seconds": max(ends) - min(starts),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--run-attempt")
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        manifests = [json.loads(path.read_text()) for path in args.manifests]
        result = verify_manifests(
            manifests, args.revision, run_id=args.run_id, run_attempt=args.run_attempt
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Shard verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
