"""The acquisition-pinning CI guard (#1826 Phase 7, §4.6).

Every way an equipment assignment (or one of its component through-rows) can
come into existence must either write acquisition receipts via the
`pin_assignment` choke point, copy them (clone), or be a named exception.
A missed path fails SILENTLY in production — it just keeps minting
receipt-less gear that reprices on movement — so this guard turns "someone
added an acquisition path and forgot to pin" into a CI failure.

It scans non-test source for the three creation shapes (direct
instantiation, manager create, component M2M writes) and compares the
result against the labelled inventory below. If you land here because this
test failed: either your new call site must call
`gyrinx.core.cost.pinning.pin_assignment(...)` after the rows exist (then
record it as PINNED), or it is genuinely one of the exception kinds — argue
that in review, then record it with the right label.

Labels:
- PINNED    calls pin_assignment (or is a sub-step of a caller that does)
- COPIES    clone(): receipts are copied verbatim, not re-resolved
- ANCHORED  zero-anchored gear (default-kit, linked-child): resolution
            anchors outrank any pin, nothing to record
- KILL      the death transfer — becomes the clone-with-pins path in
            Phase 9, unpinned until then (deliberate, tracked by the P2
            xfail cells in test_balance_sheet.py)
- ADMIN     staff write surface; bypasses delta propagation by design, the
            remediation is the recompute action (permanent exception)
- CONTENT   same field names on ContentFighterDefaultAssignment (a content
            model) — not a core assignment at all
"""

import re
from pathlib import Path

import gyrinx

PATTERNS = {
    "instantiate": re.compile(r"(?<!\w)(?<!class )ListFighterEquipmentAssignment\("),
    "manager-create": re.compile(r"ListFighterEquipmentAssignment\.objects\.create"),
    "m2m-write": re.compile(
        r"(weapon_profiles_field|weapon_accessories_field|upgrades_field)\.(add|set)\("
    ),
}

# (path, pattern) -> (count, label)
INVENTORY = {
    # Main purchase view: form creates, handle_equipment_purchase pins.
    ("core/views/fighter/equipment.py", "instantiate"): (1, "PINNED"),
    # Component purchase handlers: each add/set is followed by pin_assignment.
    ("core/handlers/equipment/purchase.py", "m2m-write"): (3, "PINNED"),
    # Vehicle purchase: creates then pins.
    ("core/handlers/fighter/vehicle.py", "manager-create"): (1, "PINNED"),
    # Equipment advancement: creates + sets upgrades, then pins.
    ("core/models/list/advancement.py", "manager-create"): (1, "PINNED"),
    ("core/models/list/advancement.py", "m2m-write"): (1, "PINNED"),
    # ListFighter.assign(): instantiates + adds components, pins at the end.
    # (The m2m writes are assign()'s own adds; assign_profile is its
    # sub-step. The create_with_facts is default-kit materialisation.)
    ("core/models/list/fighter.py", "instantiate"): (1, "PINNED"),
    ("core/models/list/fighter.py", "m2m-write"): (1, "PINNED"),
    ("core/models/list/fighter.py", "manager-create"): (1, "ANCHORED"),
    # clone(): one create + three through-row copies, receipts carried over.
    # The fourth m2m write is assign_profile (a sub-step of assign()).
    ("core/models/list/assignment.py", "manager-create"): (1, "COPIES"),
    ("core/models/list/assignment.py", "m2m-write"): (4, "COPIES"),
    # Linked-child creation (post-save signal): structurally free.
    ("core/models/list/signal_handlers.py", "manager-create"): (1, "ANCHORED"),
    # Death transfer: unpinned until Phase 9 converts it to clone-with-pins.
    ("core/handlers/fighter/kill.py", "instantiate"): (1, "KILL"),
    ("core/handlers/fighter/kill.py", "m2m-write"): (3, "KILL"),
    # Content-side models sharing the M2M field names.
    ("content/models/fighter.py", "m2m-write"): (2, "CONTENT"),
    ("core/views/pack.py", "m2m-write"): (1, "CONTENT"),
}
# The admin write surface (core/admin/list.py) creates assignments and
# through rows via ModelAdmin/inline forms, which none of the source-level
# patterns above match — its ADMIN exception is enforced by policy (the
# recompute action is the remediation), not by this scan.


def _scan():
    root = Path(gyrinx.__file__).parent
    found = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if (
            "/tests/" in f"/{rel}"
            or "/migrations/" in f"/{rel}"
            or rel.endswith("conftest.py")
        ):
            continue
        text = path.read_text()
        for name, rx in PATTERNS.items():
            n = len(rx.findall(text))
            if n:
                found[(rel, name)] = n
    return found


def test_every_assignment_creation_site_is_accounted_for():
    found = _scan()
    expected = {key: count for key, (count, _label) in INVENTORY.items()}

    new_sites = {k: v for k, v in found.items() if k not in expected}
    assert not new_sites, (
        f"Unrecorded assignment-creation site(s): {new_sites}. "
        "New acquisition paths must call gyrinx.core.cost.pinning."
        "pin_assignment(...) after the rows exist — then add the site to "
        "INVENTORY in this test with the PINNED label (see the module "
        "docstring for the exception kinds)."
    )

    gone_or_moved = {k: v for k, v in expected.items() if found.get(k) != v}
    assert not gone_or_moved, (
        f"Inventory drift (site moved, removed, or count changed): "
        f"{ {k: (expected[k], found.get(k)) for k in gone_or_moved} }. "
        "Re-verify the pinning story for each affected site, then update "
        "INVENTORY."
    )
