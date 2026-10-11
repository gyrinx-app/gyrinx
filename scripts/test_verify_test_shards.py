"""Full-suite certification rejects partial, repeated and failed execution.

The tiny subprocess projects exercise real serial/xdist hooks without Django,
database setup, or this repository's pytest configuration.
"""

import argparse
import json
import os
import shutil
import subprocess  # nosec B404 - Fixed argv lists; no shell or command text.
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gyrinx.pytest_suite_shards import ShardState, SuiteShardPlugin, module_shard
from scripts.verify_test_shards import InvalidManifest, main, verify_manifests

pytestmark = pytest.mark.core
REVISION = "a" * 40


def _case_reports(nodeid, status="passed"):
    setup = {"nodeid": nodeid, "when": "setup", "outcome": "passed"}
    teardown = {"nodeid": nodeid, "when": "teardown", "outcome": "passed"}
    if status == "setup-skipped":
        setup["outcome"] = "skipped"
        return [setup, teardown]
    call = {"nodeid": nodeid, "when": "call", "outcome": "passed"}
    if status in ("skipped", "xfailed"):
        call["outcome"] = "skipped"
    if status in ("xfailed", "xpassed"):
        call["wasxfail"] = "expected failure"
    return [setup, call, teardown]


def _recount(manifest):
    reports = manifest["reports"]
    manifest["counts"] = {
        "finished": len(manifest["finished"]),
        "reports": len(reports),
        "phases": dict(sorted(Counter(r["when"] for r in reports).items())),
        "outcomes": dict(sorted(Counter(r["outcome"] for r in reports).items())),
    }


def _manifests():
    collected = sorted(f"test_{i}.py::test_case" for i in range(12))
    statuses = dict(
        zip(collected, ("setup-skipped", "skipped", "xfailed", "xpassed"), strict=False)
    )
    manifests = []
    for index in range(2):
        selected = [n for n in collected if module_shard(n, 2) == index]
        manifest = {
            "format_version": 1,
            "revision": REVISION,
            "run_id": "123",
            "run_attempt": "2",
            "shard_count": 2,
            "shard_index": index,
            "started_at": 100.0 + index,
            "finished_at": 120.0 + index * 10,
            "collected": collected[:],
            "selected": selected,
            "reports": [
                r for n in selected for r in _case_reports(n, statuses.get(n, "passed"))
            ],
            "finished": selected[:],
            "collection_complete": True,
            "session_complete": True,
            "exit_status": 0,
            "errors": [],
            "workers": [{"id": "gw0", "exit_status": 0}],
        }
        _recount(manifest)
        manifests.append(manifest)
    return manifests


def test_complete_union_includes_skips_xfails_and_aggregate_elapsed():
    result = verify_manifests(_manifests(), REVISION, run_id="123", run_attempt="2")
    assert result["executed"] == result["collected"] == 12
    assert result["statuses"] == {"passed": 8, "skipped": 2, "xfailed": 1, "xpassed": 1}
    assert result["elapsed_seconds"] == 30.0
    assert len(result["coverage_sha256"]) == 64
    assert verify_manifests(list(reversed(_manifests())), REVISION) == result


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda m: m.pop(), "missing shards"),
        (lambda m: m.append(deepcopy(m[0])), "duplicate shard"),
        (lambda m: m[1].update(revision="b" * 40), "revision mismatch"),
        (lambda m: m[1].update(shard_count=3), "shard counts differ"),
        (lambda m: m[1].update(shard_index=2), "invalid shard index"),
        (lambda m: m[1].update(exit_status=1), "exit status"),
        (lambda m: m[1].update(session_complete=False), "incomplete"),
        (lambda m: m[1].update(collection_complete=False), "incomplete"),
        (lambda m: m[1]["collected"].pop(), "collections differ"),
        (lambda m: m[1]["collected"].append(m[1]["collected"][-1]), "unique"),
        (lambda m: m[1]["selected"].pop(), "module assignment"),
        (
            lambda m: m[1].update(selected=sorted(m[1]["selected"] + m[0]["selected"])),
            "module assignment",
        ),
        (lambda m: m[1]["finished"].pop(), "finish exactly once"),
        (lambda m: m[1]["finished"].append(m[1]["finished"][-1]), "unique"),
        (
            lambda m: m[1]["reports"].append(deepcopy(m[1]["reports"][0])),
            "duplicate case",
        ),
        (lambda m: m[1]["reports"].pop(), "setup/teardown"),
        (lambda m: m[1]["reports"][0].update(outcome="failed"), "reported failure"),
        (lambda m: m[1]["counts"].update(finished=99), "counts differ"),
        (lambda m: m[1]["workers"][0].update(exit_status=2), "worker failed"),
        (lambda m: m[1].update(started_at=float("nan")), "timestamps"),
    ],
)
def test_invalid_execution_cannot_certify_full_suite(change, message):
    manifests = _manifests()
    change(manifests)
    with pytest.raises(InvalidManifest, match=message):
        verify_manifests(manifests, REVISION)


@pytest.mark.parametrize(
    "run_id, attempt, message",
    [
        ("124", "2", "run ID mismatch"),
        ("123", "1", "attempt mismatch"),
        ("123", None, "supplied together"),
    ],
)
def test_artifact_from_another_run_or_attempt_is_rejected(run_id, attempt, message):
    with pytest.raises(InvalidManifest, match=message):
        verify_manifests(_manifests(), REVISION, run_id=run_id, run_attempt=attempt)


def test_cli_missing_artifact_fails_cleanly(tmp_path, capsys):
    assert main(["--revision", REVISION, str(tmp_path / "missing.json")]) == 1
    assert "Shard verification failed" in capsys.readouterr().err


def test_worker_collection_disagreement_and_lost_reports_fail_closed(tmp_path):
    manifest = _manifests()[0]
    state = ShardState(2, 0, tmp_path / "manifest.json", REVISION)
    state.expected_workers = {"gw0", "gw1"}
    payload = {
        "revision": REVISION,
        "collected": manifest["collected"],
        "selected": manifest["selected"],
        "collection_complete": True,
        "exit_status": 0,
        "errors": [],
        "reports": manifest["reports"],
        "finished": manifest["finished"],
    }
    state.workers = {"gw0": payload, "gw1": deepcopy(payload)}
    state.workers["gw1"]["collected"] = payload["collected"][:-1]
    plugin = SuiteShardPlugin(SimpleNamespace(), state)
    plugin._merge_workers()
    assert "worker gw1 collection differs" in state.errors
    assert "controller and worker execution reports differ" in state.errors


def test_crashed_worker_metadata_is_not_replaced_by_a_restart(tmp_path):
    state = ShardState(2, 0, tmp_path / "manifest.json", REVISION)
    plugin = SuiteShardPlugin(SimpleNamespace(), state)
    node = SimpleNamespace(gateway=SimpleNamespace(id="gw0"))
    plugin.pytest_testnodedown(node, "process exited")
    assert any("worker gw0 failed" in error for error in state.errors)
    assert any("no shard metadata" in error for error in state.errors)


@pytest.fixture
def shard_project(tmp_path):
    git = shutil.which("git")
    if git is None:
        pytest.fail("isolated sharding projects require the git executable")
    project = tmp_path / "suite"
    project.mkdir()
    (project / "pytest.ini").write_text("[pytest]\n")
    # Both shards have modules; one module has multiple cases to prove co-location.
    for index in range(6):
        (project / f"test_{index}.py").write_text(
            "import pytest\n"
            "def test_pass(): pass\n"
            "@pytest.mark.skip(reason='skip')\n"
            "def test_skip(): pass\n"
            "@pytest.mark.xfail(reason='expected')\n"
            "def test_xfail(): assert False\n"
        )
    subprocess.run([git, "init", "-q", str(project)], check=True)
    subprocess.run([git, "add", "."], cwd=project, check=True)
    subprocess.run(
        [
            git,
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=Shard test",
            "-c",
            "user.email=shard-test@example.invalid",
            "commit",
            "-qm",
            "test: isolated sharding project",
        ],
        cwd=project,
        check=True,
    )
    revision = subprocess.run(
        [git, "rev-parse", "HEAD"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["GITHUB_RUN_ID"] = "123"
    env["GITHUB_RUN_ATTEMPT"] = "2"
    return project, revision, env


def _run_project(project, env, *args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "xdist",
            "-p",
            "gyrinx.pytest_suite_shards",
            *args,
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("workers", [0, 2])
def test_real_serial_and_xdist_shards_certify_identical_full_collection(
    shard_project, workers
):
    project, revision, env = shard_project
    manifests = []
    for index in range(2):
        path = project / f"shard-{index}.json"
        result = _run_project(
            project,
            env,
            "-n",
            str(workers),
            "--dist",
            "worksteal",
            "--suite-shard-count",
            "2",
            "--suite-shard-index",
            str(index),
            "--suite-shard-manifest",
            str(path),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        manifest = json.loads(path.read_text())
        assert len(manifest["workers"]) == workers
        manifests.append(manifest)
    verified = verify_manifests(manifests, revision, run_id="123", run_attempt="2")
    assert verified["executed"] == 18
    assert verified["statuses"] == {"passed": 6, "skipped": 6, "xfailed": 6}


@pytest.mark.parametrize(
    "selector",
    [
        ["-k", "pass"],
        ["-m", "skip"],
        ["test_0.py"],
        ["--ignore", "test_0.py"],
        ["--deselect", "test_0.py::test_pass"],
        ["--lf"],
        ["--collect-only"],
    ],
)
def test_full_claim_refuses_narrowing_selectors(shard_project, selector):
    project, _, env = shard_project
    path = project / "manifest.json"
    result = _run_project(
        project,
        env,
        "-n",
        "0",
        "--suite-shard-count",
        "2",
        "--suite-shard-index",
        "0",
        "--suite-shard-manifest",
        str(path),
        *selector,
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR
    assert "suite sharding" in result.stderr
    assert not path.exists()


def test_unexpected_plugin_deselection_does_not_certify_a_partial_collection(
    shard_project,
):
    project, _, env = shard_project
    (project / "conftest.py").write_text(
        "def pytest_collection_modifyitems(items):\n    items.pop()\n"
    )
    path = project / "manifest.json"
    result = _run_project(
        project,
        env,
        "-n",
        "0",
        "--suite-shard-count",
        "2",
        "--suite-shard-index",
        "0",
        "--suite-shard-manifest",
        str(path),
    )
    assert result.returncode != 0
    if path.exists():
        assert not json.loads(path.read_text())["session_complete"]


def test_no_shard_flags_preserve_normal_filtered_execution(shard_project):
    project, _, env = shard_project
    result = _run_project(project, env, "-n", "0", "-k", "pass", "test_0.py", "-q")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed, 2 deselected" in result.stdout


def _workflow_jobs():
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/test.yaml"
    return yaml.safe_load(workflow.read_text())["jobs"]


def _named_step(job, name):
    return next(step for step in job["steps"] if step.get("name") == name)


def _trace_workflow_step(step, directory, **overrides):
    """Execute the actual shell body with recorders instead of app commands."""
    directory.mkdir(parents=True, exist_ok=True)
    binaries = directory / "bin"
    binaries.mkdir(exist_ok=True)
    activate = directory / ".venv/bin/activate"
    activate.parent.mkdir(parents=True, exist_ok=True)
    activate.write_text("")
    recorder = (
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "command = Path(sys.argv[0]).name\n"
        "with Path(os.environ['COMMAND_TRACE']).open('a') as output:\n"
        "    output.write(json.dumps({'command': command, 'args': sys.argv[1:]}) + '\\n')\n"
        "if command == 'git':\n"
        "    if sys.argv[1:] != ['rev-parse', 'HEAD']: raise SystemExit(3)\n"
        "    print(os.environ['ACTUAL_GIT_REVISION'])\n"
    )
    for name in ("python", "pytest", "git"):
        executable = binaries / name
        executable.write_text(recorder)
        executable.chmod(0o755)
    trace = directory / "trace.jsonl"
    trace.unlink(missing_ok=True)
    env = {
        **os.environ,
        "PATH": str(binaries) + os.pathsep + os.environ.get("PATH", ""),
        "COMMAND_TRACE": str(trace),
        "GITHUB_SHA": REVISION,
        "ACTUAL_GIT_REVISION": REVISION,
        **overrides,
    }
    bash = shutil.which("bash")
    assert bash is not None, "workflow shell regression requires bash"
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    commands = [json.loads(line) for line in trace.read_text().splitlines()]
    return result, commands


def test_ci_always_executes_both_full_shards_for_every_changed_scope(tmp_path):
    jobs = _workflow_jobs()
    # Accept only unfiltered pytest arguments: a partial core/path fallback must
    # fail even when it invokes the measurement helper rather than plain pytest.
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", action="store_true")
    parser.add_argument("-n", type=int, required=True)
    parser.add_argument("-p", required=True)
    parser.add_argument("--suite-shard-count", type=int, required=True)
    parser.add_argument("--suite-shard-index", type=int, required=True)
    parser.add_argument("--suite-shard-manifest", required=True)
    for index, job_name, run_name, upload_name in (
        (0, "test", "Run full-suite shard zero", "Upload required shard evidence"),
        (1, "test-full", "Run full-suite shard one", "Upload companion shard evidence"),
    ):
        job = jobs[job_name]
        step = _named_step(job, run_name)
        assert step.get("if") is None
        assert "${{" not in step["run"]
        assert _named_step(job, upload_name).get("if") == "always()"
        for scope_index, scope in enumerate(("", ".", "n26/core/test_example.py")):
            directory = tmp_path / f"shard-{index}-scope-{scope_index}"
            (directory / "logs").mkdir(parents=True)
            (directory / "logs/changed-test-paths.txt").write_text(scope + "\n")
            result, commands = _trace_workflow_step(
                step, directory, GYRINX_CHANGED_TEST_PATHS=scope
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert len(commands) == 1 and commands[0]["command"] == "python"
            argv = commands[0]["args"]
            assert argv[0] == "scripts/measure_test_performance.py"
            separator = argv.index("--")
            options = parser.parse_args(argv[separator + 1 :])
            assert (
                options.n,
                options.suite_shard_count,
                options.suite_shard_index,
            ) == (4, 2, index)
            assert options.p == "gyrinx.pytest_suite_shards"
            assert options.suite_shard_manifest == "logs/full-suite-shard.json"
    fan_in = _named_step(
        jobs["test"], "Verify both shards completed the full suite exactly once"
    )
    assert fan_in.get("if") in (None, "success()")
    assert (
        fan_in["env"]["EXPECTED_HEAD_SHA"]
        == "${{ github.event.pull_request.head.sha || github.sha }}"
    )


def test_ci_preserves_smoke_skip_and_verifies_actual_checkout_revision(tmp_path):
    for name, job in _workflow_jobs().items():
        if name not in ("test", "test-full"):
            continue
        # A manual PR run cannot make the required check pass by skipping it.
        assert (
            job["if"]
            == "github.event_name != 'workflow_dispatch' || github.ref != 'refs/heads/main'"
        )
        checkout = next(
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        assert "ref" not in checkout.get("with", {})
        step = _named_step(job, "Verify the checked-out revision")
        assert step.get("if") is None
        for matches, actual in ((True, REVISION), (False, "b" * 40)):
            result, commands = _trace_workflow_step(
                step, tmp_path / f"{name}-{matches}", ACTUAL_GIT_REVISION=actual
            )
            assert (result.returncode == 0) is matches
            assert commands == [{"command": "git", "args": ["rev-parse", "HEAD"]}]
