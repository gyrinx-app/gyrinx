"""The dev server guard restarts a bloated server and stops one nobody is using."""

import pytest
from django.apps import apps
from django.conf import settings

from gyrinx.devserver.guard import (
    DRAIN_SECONDS,
    RESTART,
    STOP,
    Guard,
    Owner,
    agent_name,
    exit_plan,
    find_owner,
    memory_mb,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_guard(
    *, used=100, limit=500, idle_minutes=60, owner=None, alive=True, served=True
):
    clock = Clock()
    state = {"used": used, "alive": alive}
    guard = Guard(
        memory_limit_mb=limit,
        idle_minutes=idle_minutes,
        owner=owner,
        clock=clock,
        memory=lambda: state["used"],
        alive=lambda pid: state["alive"],
    )
    if served:
        guard.request_started()
        guard.request_finished()
    return guard, clock, state


AGENT = Owner(pid=4242, name="Claude Code")


def test_a_server_within_its_limit_keeps_running():
    guard, clock, _ = make_guard()
    clock.advance(10 * 3600)
    assert guard.check() is None


def test_a_server_over_its_limit_restarts():
    guard, _, _ = make_guard(used=600)
    code, reason = guard.check()
    assert code == RESTART
    assert "600 MB" in reason


def test_a_server_over_its_limit_lets_requests_finish_first():
    guard, clock, _ = make_guard(used=600)
    guard.request_started()
    assert guard.check() is None
    guard.request_finished()
    assert guard.check()[0] == RESTART


def test_a_server_over_its_limit_restarts_if_requests_never_finish():
    guard, clock, _ = make_guard(used=600)
    guard.request_started()
    assert guard.check() is None
    clock.advance(DRAIN_SECONDS)
    assert guard.check()[0] == RESTART


def test_dropping_back_under_the_limit_resets_the_wait():
    guard, clock, state = make_guard(used=600)
    guard.request_started()
    guard.check()
    state["used"] = 100
    clock.advance(DRAIN_SECONDS)
    assert guard.check() is None
    state["used"] = 600
    assert guard.check() is None


def test_a_limit_of_zero_turns_the_memory_check_off():
    guard, _, _ = make_guard(used=10_000, limit=0)
    assert guard.check() is None


def test_a_negative_limit_turns_the_memory_check_off():
    guard, _, _ = make_guard(used=10_000, limit=-1)
    assert guard.check() is None


def test_a_server_that_has_served_nothing_is_not_restarted():
    """A limit below a fresh server's size would otherwise restart it forever."""
    guard, _, _ = make_guard(used=600, served=False)
    assert guard.check() is None
    guard.request_started()
    guard.request_finished()
    assert guard.check()[0] == RESTART


def test_a_server_stops_when_its_agent_session_ends():
    guard, _, state = make_guard(owner=AGENT)
    assert guard.check() is None
    state["alive"] = False
    code, reason = guard.check()
    assert code == STOP
    assert "Claude Code" in reason and "4242" in reason


def test_an_agents_idle_server_stops():
    guard, clock, _ = make_guard(owner=AGENT, idle_minutes=60)
    clock.advance(59 * 60)
    assert guard.check() is None
    clock.advance(60)
    code, reason = guard.check()
    assert code == STOP
    assert "60 minutes" in reason


def test_a_request_keeps_an_agents_server_running():
    guard, clock, _ = make_guard(owner=AGENT, idle_minutes=60)
    clock.advance(59 * 60)
    guard.request_started()
    clock.advance(10 * 60)
    assert guard.check() is None  # Still serving that request.
    guard.request_finished()
    clock.advance(59 * 60)
    assert guard.check() is None


def test_a_server_nobody_owns_is_never_stopped_for_being_idle():
    guard, clock, _ = make_guard(owner=None, idle_minutes=60)
    clock.advance(24 * 3600)
    assert guard.check() is None


def test_an_idle_limit_of_zero_turns_the_idle_check_off():
    guard, clock, _ = make_guard(owner=AGENT, idle_minutes=0)
    clock.advance(24 * 3600)
    assert guard.check() is None


def test_claude_code_names_its_own_process():
    owner = find_owner({"CLAUDE_PID": "1234"}, alive=lambda pid: True)
    assert owner == Owner(1234, "Claude Code")


def test_a_claude_pid_whose_process_has_gone_is_ignored(monkeypatch):
    """A terminal can inherit CLAUDE_PID from a session that has since ended."""
    fake_ps(monkeypatch, {500: " 1 /bin/zsh"})
    owner = find_owner({"CLAUDE_PID": "1234"}, parent_pid=500, alive=lambda pid: False)
    assert owner is None


class PsResult:
    def __init__(self, stdout):
        self.stdout = stdout


def fake_ps(monkeypatch, table):
    """Answer ``ps -o ppid=,comm= -p PID`` from ``table`` of pid to output."""

    def run(argv, **kwargs):
        return PsResult(table.get(int(argv[-1]), ""))

    monkeypatch.setattr("gyrinx.devserver.guard.subprocess.run", run)


def test_an_agent_is_found_among_the_ancestors(monkeypatch):
    fake_ps(
        monkeypatch,
        {
            500: "  400 /opt/homebrew/bin/python",
            400: "  300 /bin/bash",
            300: "    1 /usr/local/lib/node_modules/@openai/codex/bin/codex",
        },
    )
    assert find_owner({}, parent_pid=500) == Owner(300, "Codex")


def test_a_process_title_names_the_agent(monkeypatch):
    fake_ps(monkeypatch, {500: "  400 /bin/zsh", 400: "  1 claude bg-spare --x"})
    assert find_owner({}, parent_pid=500) == Owner(400, "Claude Code")


def test_an_ancestor_walk_without_an_agent_finds_nothing(monkeypatch):
    fake_ps(monkeypatch, {500: "  400 /bin/zsh", 400: "  1 /usr/bin/login"})
    assert find_owner({}, parent_pid=500) is None


def test_an_ancestor_walk_stops_where_ps_has_no_answer(monkeypatch):
    fake_ps(monkeypatch, {})
    assert find_owner({}, parent_pid=500) is None


def test_an_agent_is_recognised_by_its_command():
    assert agent_name("claude") == "Claude Code"
    assert agent_name("claude bg-spare --bg-spare /tmp/x.sock") == "Claude Code"
    assert agent_name("/usr/local/lib/node_modules/@openai/codex/bin/codex") == "Codex"
    assert agent_name("/bin/zsh") is None
    assert agent_name("-zsh") is None


def test_an_ancestor_walk_stops_at_launchd():
    assert find_owner({}, parent_pid=1) is None


def test_memory_is_readable_here():
    used = memory_mb()
    assert used is not None
    assert 10 < used < 100_000


def test_the_guard_is_off_under_pytest():
    assert settings.DEV_SERVER_GUARD is False


@pytest.fixture
def started(monkeypatch):
    """Record the guard starting instead of starting it."""
    calls = []
    monkeypatch.setattr(
        "gyrinx.devserver.guard.start", lambda **kwargs: calls.append(kwargs)
    )
    return calls


def run_ready(monkeypatch, settings, *, guard_on, run_main, argv):
    settings.DEV_SERVER_GUARD = guard_on
    if run_main:
        monkeypatch.setenv("RUN_MAIN", "true")
    else:
        monkeypatch.delenv("RUN_MAIN", raising=False)
    monkeypatch.setattr("sys.argv", argv)
    apps.get_app_config("gyrinx_devserver").ready()


def test_the_guard_starts_in_the_process_that_serves(monkeypatch, settings, started):
    run_ready(
        monkeypatch,
        settings,
        guard_on=True,
        run_main=True,
        argv=["manage", "runserver"],
    )
    assert started == [
        {
            "memory_limit_mb": settings.DEV_SERVER_MEMORY_LIMIT_MB,
            "idle_minutes": settings.DEV_SERVER_IDLE_MINUTES,
        }
    ]


def test_the_guard_starts_without_the_autoreloader(monkeypatch, settings, started):
    argv = ["manage", "runserver", "--noreload"]
    run_ready(monkeypatch, settings, guard_on=True, run_main=False, argv=argv)
    assert len(started) == 1


def test_the_guard_skips_the_autoreloaders_parent(monkeypatch, settings, started):
    argv = ["manage", "runserver"]
    run_ready(monkeypatch, settings, guard_on=True, run_main=False, argv=argv)
    assert started == []


def test_the_guard_stays_off_unless_settings_turn_it_on(monkeypatch, settings, started):
    argv = ["manage", "runserver"]
    run_ready(monkeypatch, settings, guard_on=False, run_main=True, argv=argv)
    assert started == []


def test_a_server_over_its_limit_restarts_under_the_autoreloader():
    code, message = exit_plan(RESTART, "it is using 3,000 MB", under_autoreloader=True)
    assert code == RESTART
    assert message == "Restarting the dev server: it is using 3,000 MB."


def test_a_server_over_its_limit_stops_without_the_autoreloader():
    """With --noreload nothing would start the server again after exit code 3."""
    code, message = exit_plan(RESTART, "it is using 3,000 MB", under_autoreloader=False)
    assert code == STOP
    assert message.startswith("Stopping the dev server: it is using 3,000 MB.")
    assert "Without the autoreloader" in message


def test_a_stop_ends_the_autoreloader_too():
    code, message = exit_plan(STOP, "it has had no requests", under_autoreloader=True)
    assert code == STOP
    assert message.endswith("Run ./scripts/dev.sh to start it again.")
