"""The dev server guard restarts a bloated server and stops one nobody is using."""

from django.conf import settings

from gyrinx.devserver.guard import (
    DRAIN_SECONDS,
    RESTART,
    STOP,
    Guard,
    Owner,
    agent_name,
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


def make_guard(*, used=100, limit=500, idle_minutes=60, owner=None, alive=True):
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
    assert find_owner({"CLAUDE_PID": "1234"}) == Owner(1234, "Claude Code")


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
