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
`n23.core.cost.pinning.pin_assignment(...)` after the rows exist (then
record it as PINNED), or it is genuinely one of the exception kinds — argue
that in review, then record it with the right label.

This is a source-level heuristic: aliased imports, getattr dispatch, or
string-built model access can slip past it. That is acceptable — it exists
to catch the ordinary way new code gets written, not adversarial evasion.

Labels:
- PINNED    calls pin_assignment (or is a sub-step of a caller that does)
- COPIES    clone(): receipts are copied verbatim, not re-resolved
- ANCHORED  zero-anchored gear (default-kit, linked-child): resolution
            anchors outrank any pin, nothing to record
- ADMIN     staff write surface; bypasses delta propagation by design, the
            remediation is the recompute action (permanent exception)
- CONTENT   same field names on ContentFighterDefaultAssignment (a content
            model) — not a core assignment at all

The death transfer (kill.py) was labelled KILL until Phase 9. It now clones
each transferred item with its receipt (COPIES, in assignment.py) and calls
pin_assignment on any UNPINNED straggler first, so it no longer constructs
assignments or writes M2Ms directly — it matches no creation pattern and is
tracked purely by its pin_assignment call in PIN_CALL_COUNTS.
"""

import re
from pathlib import Path

import n23

# Scan the platform tree as well as the edition's. Restricting this to n23/
# would leave assignment creation sites under gyrinx/ unpoliced — gyrinx/
# maintenance/admin.py already imports ListFighterEquipmentAssignment — and it
# would fail silently, because a root with no matches simply contributes
# nothing. Keys are repo-root-relative so n23/core/… and a future n26/core/…
# can never collide.
REPO_ROOT = Path(n23.__file__).parent.parent
SCAN_ROOTS = (REPO_ROOT / "gyrinx", REPO_ROOT / "n23")

PATTERNS = {
    "instantiate": re.compile(r"(?<!\w)(?<!class )ListFighterEquipmentAssignment\("),
    "manager-create": re.compile(
        r"ListFighterEquipmentAssignment\.objects\."
        r"(create|get_or_create|update_or_create|bulk_create)"
    ),
    "reverse-create": re.compile(
        r"listfighterequipmentassignment_set\."
        r"(create|get_or_create|update_or_create|bulk_create)"
    ),
    "through-create": re.compile(
        r"ListFighterEquipmentAssignment(Profile|Accessory|Upgrade)\.objects\."
        r"(create|get_or_create|update_or_create|bulk_create)"
    ),
    "m2m-write": re.compile(
        r"(weapon_profiles_field|weapon_accessories_field|upgrades_field)\.(add|set)\("
    ),
}

# PINNED files must actually contain the calls their label claims: deleting
# a pin_assignment(...) line must fail here, not silently unpin a path.
PIN_CALL_COUNTS = {
    "n23/core/cost/pinning.py": 2,  # module docstring + the def itself
    "n23/core/handlers/equipment/purchase.py": 4,  # equipment/accessory/profile/upgrades
    "n23/core/handlers/fighter/kill.py": 1,  # defensive pin before clone-to-stash
    "n23/core/handlers/fighter/vehicle.py": 1,
    "n23/core/models/list/advancement.py": 1,
    "n23/core/models/list/fighter.py": 1,  # assign()
}

# (path, pattern) -> (count, label)
INVENTORY = {
    # Main purchase view: form creates, handle_equipment_purchase pins.
    ("n23/core/views/fighter/equipment.py", "instantiate"): (1, "PINNED"),
    # Component purchase handlers: each add/set is followed by pin_assignment.
    ("n23/core/handlers/equipment/purchase.py", "m2m-write"): (3, "PINNED"),
    # Vehicle purchase: creates then pins.
    ("n23/core/handlers/fighter/vehicle.py", "manager-create"): (1, "PINNED"),
    # Equipment advancement: creates + sets upgrades, then pins.
    ("n23/core/models/list/advancement.py", "manager-create"): (1, "PINNED"),
    ("n23/core/models/list/advancement.py", "m2m-write"): (1, "PINNED"),
    # ListFighter.assign(): instantiates + adds components, pins at the end.
    # (The m2m writes are assign()'s own adds; assign_profile is its
    # sub-step. The create_with_facts is default-kit materialisation.)
    ("n23/core/models/list/fighter.py", "instantiate"): (1, "PINNED"),
    ("n23/core/models/list/fighter.py", "m2m-write"): (1, "PINNED"),
    ("n23/core/models/list/fighter.py", "manager-create"): (1, "ANCHORED"),
    # clone(): one create + three through-row copies, receipts carried over.
    # The fourth m2m write is assign_profile (a sub-step of assign()).
    ("n23/core/models/list/assignment.py", "manager-create"): (1, "COPIES"),
    ("n23/core/models/list/assignment.py", "m2m-write"): (4, "COPIES"),
    # Linked-child creation (post-save signal): structurally free.
    ("n23/core/models/list/signal_handlers.py", "manager-create"): (1, "ANCHORED"),
    # Death transfer (kill.py): as of Phase 9 it clones each item (COPIES,
    # above) and pins any straggler first (PIN_CALL_COUNTS), so it matches no
    # creation pattern here.
    # Content-side models sharing the M2M field names.
    ("n23/content/models/fighter.py", "m2m-write"): (2, "CONTENT"),
    ("n23/core/views/pack.py", "m2m-write"): (1, "CONTENT"),
}
# The admin write surface (core/admin/list.py) creates assignments and
# through rows via ModelAdmin/inline forms, which none of the source-level
# patterns above match — its ADMIN exception is enforced by policy (the
# recompute action is the remediation), not by this scan.


def _scan(extra_files=None):
    """Scan non-test source for creation shapes. ``extra_files`` lets the
    guard's own negative test inject a synthetic bypassing call site."""
    sources = {
        path.relative_to(REPO_ROOT).as_posix(): path.read_text()
        for root in SCAN_ROOTS
        for path in sorted(root.rglob("*.py"))
    }
    sources.update(extra_files or {})
    found = {}
    for rel, text in sources.items():
        if (
            "/tests/" in f"/{rel}"
            or "/migrations/" in f"/{rel}"
            or rel.endswith("conftest.py")
        ):
            continue
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
        "New acquisition paths must call n23.core.cost.pinning."
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


def test_pinned_files_still_call_the_choke_point():
    """A PINNED label is a claim: the file wires pin_assignment. Deleting
    the call must fail here, not silently unpin an acquisition path."""
    for rel, expected in PIN_CALL_COUNTS.items():
        actual = (REPO_ROOT / rel).read_text().count("pin_assignment(")
        assert actual == expected, (
            f"{rel}: expected {expected} pin_assignment references, found "
            f"{actual}. If a call site moved or was removed, re-verify the "
            "pinning story for every creation site in that file, then "
            "update PIN_CALL_COUNTS."
        )


def test_guard_detects_synthetic_bypass():
    """The DoD negative case: a new creation site the inventory doesn't
    know about must be flagged."""
    found = _scan(
        extra_files={
            "n23/core/rogue.py": (
                "def rogue(fighter, equipment):\n"
                "    return ListFighterEquipmentAssignment.objects.create(\n"
                "        list_fighter=fighter, content_equipment=equipment\n"
                "    )\n"
            )
        }
    )
    assert found.get(("n23/core/rogue.py", "manager-create")) == 1

    # The wider creation shapes are matched too.
    for snippet, pattern in [
        ("ListFighterEquipmentAssignment.objects.get_or_create(", "manager-create"),
        ("fighter.listfighterequipmentassignment_set.create(", "reverse-create"),
        (
            "ListFighterEquipmentAssignmentProfile.objects.bulk_create(",
            "through-create",
        ),
    ]:
        assert PATTERNS[pattern].search(snippet), (pattern, snippet)
