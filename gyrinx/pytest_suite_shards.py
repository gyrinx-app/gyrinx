"""Opt-in, module-stable partitioning of an unfiltered full pytest collection.

Each invocation collects the whole suite. Only its assigned modules execute.
Workers send collection and execution evidence through xdist's workeroutput;
only the controller writes the manifest. There is no persistent read cache.
"""

import hashlib
import json
import os
import shutil
import subprocess  # nosec B404 - Fixed argv lists; no shell or command text.
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest

FORMAT_VERSION = 1
_WORKER_KEY = "suite_shards"


def module_shard(nodeid: str, count: int) -> int:
    """Assign every case in a file to the same shard, independent of ordering."""
    module = nodeid.split("::", 1)[0]
    return int.from_bytes(hashlib.sha256(module.encode()).digest(), "big") % count


def pytest_addoption(parser):
    group = parser.getgroup("suite sharding")
    group.addoption("--suite-shard-count", type=int, default=None)
    group.addoption("--suite-shard-index", type=int, default=None)
    group.addoption("--suite-shard-manifest", default=None)


def _options(config):
    count = config.getoption("suite_shard_count")
    index = config.getoption("suite_shard_index")
    manifest = config.getoption("suite_shard_manifest")
    if count is index is manifest is None:
        return None
    if count is None or index is None or manifest is None:
        raise pytest.UsageError("suite sharding requires count, index and manifest")
    if count < 1 or not 0 <= index < count:
        raise pytest.UsageError("suite shard index must be in [0, count), count >= 1")
    for option in (
        "markexpr",
        "keyword",
        "ignore",
        "ignore_glob",
        "deselect",
        "lf",
        "collectonly",
        "pyargs",
    ):
        if config.getoption(option, default=None):
            raise pytest.UsageError(
                f"suite sharding requires unfiltered full collection: {option}"
            )
    # config.args contains the default root when no positional paths were given.
    if len(config.args) != 1 or "::" in str(config.args[0]):
        raise pytest.UsageError("suite sharding accepts only the full repository root")
    path = Path(config.args[0])
    if not path.is_absolute():
        path = config.invocation_params.dir / path
    if path.resolve() != config.rootpath.resolve():
        raise pytest.UsageError("suite sharding accepts only the full repository root")
    return count, index, Path(manifest)


def pytest_configure(config):
    options = _options(config)
    if options is None:
        return
    count, index, path = options
    workerinput = getattr(config, "workerinput", None)
    if workerinput is not None:
        revision = workerinput[_WORKER_KEY + "_revision"]
    else:
        git = shutil.which("git")
        if git is None:
            raise pytest.UsageError("suite sharding requires the git executable")
        try:
            revision = subprocess.run(
                [git, "rev-parse", "HEAD"],
                cwd=config.rootpath,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise pytest.UsageError("suite sharding requires a git revision") from exc
    if not path.is_absolute():
        path = config.invocation_params.dir / path
    config.pluginmanager.register(
        SuiteShardPlugin(config, ShardState(count, index, path, revision)),
        "suite-shard-session",
    )


@dataclass
class ShardState:
    count: int
    index: int
    path: Path
    revision: str
    collected: list[str] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)
    reports: list[dict] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    collection_complete: bool = False
    started_at: float = 0.0
    expected_workers: set[str] = field(default_factory=set)
    workers: dict[str, dict] = field(default_factory=dict)


def _report_key(report):
    return json.dumps(report, sort_keys=True)


def _counts(reports, finished):
    return {
        "finished": len(finished),
        "reports": len(reports),
        "phases": dict(sorted(Counter(r["when"] for r in reports).items())),
        "outcomes": dict(sorted(Counter(r["outcome"] for r in reports).items())),
    }


class SuiteShardPlugin:
    def __init__(self, config, state):
        self.config = config
        self.state = state

    def pytest_sessionstart(self, session):
        self.state.started_at = time.time()

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, session, config, items):
        original_items = {id(item) for item in items}
        result = yield
        if {id(item) for item in items} != original_items:
            self.state.errors.append("another plugin altered the full collection")
            raise pytest.UsageError(
                "suite sharding cannot certify another plugin's deselection"
            )
        nodeids = [item.nodeid for item in items]
        self.state.collected = sorted(nodeids)
        if len(set(nodeids)) != len(nodeids):
            self.state.errors.append("duplicate collected node IDs")
            raise pytest.UsageError("suite sharding requires unique collected node IDs")
        selected = []
        deselected = []
        for item in items:
            target = (
                selected
                if module_shard(item.nodeid, self.state.count) == self.state.index
                else deselected
            )
            target.append(item)
        self.state.selected = sorted(item.nodeid for item in selected)
        items[:] = selected
        if deselected:
            config.hook.pytest_deselected(items=deselected)
        return result

    def pytest_collection_finish(self, session):
        self.state.collection_complete = True

    def pytest_collectreport(self, report):
        if report.failed:
            self.state.errors.append(f"collection failed: {report.nodeid}")

    def pytest_runtest_logreport(self, report):
        record = {
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
        }
        if hasattr(report, "wasxfail"):
            record["wasxfail"] = str(report.wasxfail)
        self.state.reports.append(record)

    def pytest_runtest_logfinish(self, nodeid, location):
        self.state.finished.append(nodeid)

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node):
        node.workerinput[_WORKER_KEY + "_revision"] = self.state.revision
        self.state.expected_workers.add(node.gateway.id)

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error):
        worker_id = node.gateway.id
        if error is not None:
            self.state.errors.append(f"worker {worker_id} failed: {error}")
        # xdist sets workeroutput only after a normal workerfinished event.
        payload = getattr(node, "workeroutput", {}).get(_WORKER_KEY)
        if payload is None:
            self.state.errors.append(f"worker {worker_id} supplied no shard metadata")
            return
        if worker_id in self.state.workers:
            self.state.errors.append(f"duplicate completion of worker {worker_id}")
        self.state.workers[worker_id] = payload

    def _merge_workers(self):
        state = self.state
        if set(state.workers) != state.expected_workers:
            state.errors.append("not all started workers completed")
        reference = None
        worker_reports = []
        worker_finished = []
        for worker_id, payload in sorted(state.workers.items()):
            if payload["revision"] != state.revision:
                state.errors.append(f"worker {worker_id} revision differs")
            if payload["exit_status"] != 0 or not payload["collection_complete"]:
                state.errors.append(f"worker {worker_id} session incomplete or failed")
            state.errors.extend(payload["errors"])
            collection = (payload["collected"], payload["selected"])
            if reference is None:
                reference = collection
            elif collection != reference:
                state.errors.append(f"worker {worker_id} collection differs")
            worker_reports.extend(payload["reports"])
            worker_finished.extend(payload["finished"])
        if reference is not None:
            state.collected, state.selected = reference
            state.collection_complete = all(
                p["collection_complete"] for p in state.workers.values()
            )
        if Counter(map(_report_key, worker_reports)) != Counter(
            map(_report_key, state.reports)
        ) or Counter(worker_finished) != Counter(state.finished):
            state.errors.append("controller and worker execution reports differ")

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        state = self.state
        if getattr(self.config, "workerinput", None) is not None:
            self.config.workeroutput[_WORKER_KEY] = {
                "revision": state.revision,
                "collected": state.collected,
                "selected": state.selected,
                "reports": state.reports,
                "finished": state.finished,
                "errors": state.errors,
                "collection_complete": state.collection_complete,
                "exit_status": int(exitstatus),
            }
            return
        if state.expected_workers:
            self._merge_workers()
        if not state.collection_complete:
            state.errors.append("full collection did not complete")
        if Counter(state.finished) != Counter(state.selected):
            state.errors.append("selected cases did not each finish exactly once")
        if state.errors and int(session.exitstatus) == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
        manifest = {
            "format_version": FORMAT_VERSION,
            "revision": state.revision,
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "shard_count": state.count,
            "shard_index": state.index,
            # UTC Unix seconds, including collection and test setup/teardown.
            "started_at": state.started_at,
            "finished_at": time.time(),
            "collected": state.collected,
            "selected": state.selected,
            "reports": sorted(state.reports, key=_report_key),
            "finished": sorted(state.finished),
            "counts": _counts(state.reports, state.finished),
            "collection_complete": state.collection_complete,
            "session_complete": not state.errors,
            "exit_status": int(session.exitstatus),
            "errors": state.errors,
            "workers": [
                {"id": worker_id, "exit_status": payload["exit_status"]}
                for worker_id, payload in sorted(state.workers.items())
            ],
        }
        state.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=state.path.parent, prefix=state.path.name + ".", delete=False
        ) as output:
            temporary = Path(output.name)
            try:
                json.dump(manifest, output, sort_keys=True)
                output.write("\n")
                output.close()
                os.replace(temporary, state.path)
            finally:
                temporary.unlink(missing_ok=True)
