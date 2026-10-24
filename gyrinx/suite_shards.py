"""Deterministic module assignments shared by pytest and its evidence verifier."""

import hashlib

# The five largest modules on shard one move together to shard zero. Whole-file
# placement preserves module fixtures. Calibrated against main runs on 2026-10-24:
# https://github.com/gyrinx-app/gyrinx/actions/runs/40081834137
# The other two samples were 40081697973 and 40081308747.
_TWO_SHARD_MOVES = frozenset(
    {
        "n23/core/tests/test_crew.py",
        "n26/tests/sandbox/test_advancement_action_flows.py",
        "n26/tests/sandbox/test_fighter_progression_setup.py",
        "n26/tests/sandbox/test_power_advancements.py",
        "n26/tests/test_views_post_battle.py",
    }
)


def module_shard(nodeid: str, count: int) -> int:
    """Keep every case in a module together, including unmeasured new modules."""
    module = nodeid.split("::", 1)[0]
    if count == 2 and module in _TWO_SHARD_MOVES:
        return 0
    return int.from_bytes(hashlib.sha256(module.encode()).digest(), "big") % count
