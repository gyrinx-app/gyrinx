"""Finish moving stat advancements onto the mod system (#2070).

Migration ``core.0196`` converted the fighter/stat pairs whose stored override
provably matched what the mod system would compute, and deliberately left the
rest alone. This handles those leftovers, and tells the affected players.

Every decision is made from what the fighter's card actually shows — the base
from ``content_fighter_statline`` with ``AdvancementStatMod`` chained over it —
never from a re-derivation of what the legacy code would have written. Those two
disagree, which is the bug 0196 shipped with and had to be fixed for.

The situations, keyed on (fighter, stat), where L counts live legacy
advancements and M counts live mod-system ones:

1. L>0, override holds a number no advancement produces — someone typed it.
   Back-compute the override so the advancements restore today's value.
2. L>0, override is advancement output written in the old format ("5" for a
   distance that should read '5"'). Clear it; the value is unchanged.
3. L>0, no override at all — the advancement is inert and shows nothing,
   despite being charged for. Flip it so it starts applying.
4. The fighter reads its stats from ``ListFighterStatOverride`` instead, or the
   stat is absent from its statline. Left for the work that reconciles the two
   stores.
5. L=0, override numerically equals what the advancements already produce, so
   the improvement lands twice. Clear it.
6. L=0, override matches a partial count — same duplication, partially applied.
   Clear it.
7. L=0, override is a genuine manual edit alongside working advancements.
   Legitimate; left alone.
8. The stat value cannot be parsed. Left for manual repair.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

STAT_FIELDS = [
    "movement",
    "weapon_skill",
    "ballistic_skill",
    "strength",
    "toughness",
    "wounds",
    "initiative",
    "attacks",
    "leadership",
    "cool",
    "willpower",
    "intelligence",
]

# What each situation means for the player, and so whether it earns a message.
GAIN = "gain"
LOSS = "loss"
INVISIBLE = "invisible"

SITUATION_LABELS = {
    1: "manual edit — override back-computed",
    2: "advancement output in the old format — override cleared",
    3: "advancement was inert — now applies",
    4: "stats read from the other override store — left alone",
    5: "duplicate improvement (format-disguised) — override cleared",
    6: "duplicate improvement (partial count) — override cleared",
    7: "manual edit alongside working advancements — left alone",
    8: "stat value cannot be parsed — left alone",
}

ACTED_ON = {1, 2, 3, 5, 6}
NOTIFIED = {3: GAIN, 5: LOSS, 6: LOSS}


@dataclass
class Change:
    """One (fighter, stat) pair and what should happen to it."""

    fighter_id: str
    fighter_name: str
    list_id: str
    list_name: str
    owner_id: Optional[int]
    stat: str
    situation: int
    override_before: Optional[str]
    override_after: Optional[str]
    flip_advancements: bool
    displayed_before: Optional[str] = None
    displayed_after: Optional[str] = None

    @property
    def acted_on(self):
        return self.situation in ACTED_ON

    @property
    def visible_to_player(self):
        return (
            self.situation in NOTIFIED
            and self.displayed_before != self.displayed_after
            and self.displayed_after is not None
        )

    @property
    def direction(self):
        return NOTIFIED.get(self.situation, INVISIBLE)


@dataclass
class Plan:
    changes: list = field(default_factory=list)

    def by_situation(self):
        counts = {}
        for change in self.changes:
            counts[change.situation] = counts.get(change.situation, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def acted_on(self):
        return [c for c in self.changes if c.acted_on]

    @property
    def visible(self):
        return [c for c in self.changes if c.visible_to_player]


def numeric(value):
    """The number inside a stat value, ignoring a trailing ``"`` or ``+``."""
    if value is None:
        return None
    match = re.fullmatch(r'\s*([+-]?\d+)\s*[+"]?\s*', str(value))
    return int(match.group(1)) if match else None


def _mod(stat, mode):
    from gyrinx.core.models.list.advancement import AdvancementStatMod

    mod = AdvancementStatMod(stat)
    mod.mode = mode
    return mod


def step(stat, value, count, mod_ctx, mode="improve"):
    """Apply ``count`` advancement steps to ``value``, or None if it cannot be.

    Stats are free text and production holds values no arithmetic works on, so
    a failure here means "cannot be reasoned about" rather than an error.
    """
    if value is None or count < 1:
        return value
    mod = _mod(stat, mode)
    result = value
    try:
        for _ in range(count):
            result = mod.apply(result, mod_ctx)
    except (ValueError, TypeError):
        return None
    return result


def build_plan():
    """Work out what should happen to every outstanding (fighter, stat) pair."""
    from gyrinx.content.models.statline import ContentStat
    from gyrinx.core.models.list import ListFighter, ListFighterStatOverride
    from gyrinx.core.models.list.advancement import ListFighterAdvancement
    from gyrinx.core.models.util import ModContext

    grouped = {}
    rows = ListFighterAdvancement.objects.filter(
        advancement_type="stat", archived=False
    ).values_list("fighter_id", "stat_increased", "uses_mod_system")
    for fighter_id, stat, uses_mod_system in rows:
        if stat:
            counts = grouped.setdefault((fighter_id, stat), [0, 0])
            counts[1 if uses_mod_system else 0] += 1

    shadowed = {
        (fighter_id, field_name)
        for fighter_id, field_name in ListFighterStatOverride.objects.values_list(
            "list_fighter_id", "content_stat__stat__field_name"
        )
    }

    mod_ctx = ModContext(
        all_stats={
            stat["field_name"]: stat for stat in ContentStat.objects.all().values()
        }
    )

    plan = Plan()
    # with_related_data is essential here, not a nicety: classifying a pair
    # reads the fighter's fully resolved statline, which pulls in equipment,
    # injuries and mods. Without the prefetch this is N+1 over every affected
    # fighter and takes long enough to be unusable.
    fighters = (
        ListFighter.objects.filter(id__in={fighter_id for fighter_id, _ in grouped})
        .with_related_data()
        .select_related("list__owner")
    )

    # chunk_size is required once the queryset prefetches, and keeps the
    # working set bounded over the couple of thousand fighters involved.
    for fighter in fighters.iterator(chunk_size=200):
        base_by_stat = {
            entry["field_name"]: entry["value"]
            for entry in fighter.content_fighter_statline
        }
        displayed_by_stat = {
            entry.field_name: entry.value for entry in fighter.statline
        }

        for stat in STAT_FIELDS:
            counts = grouped.get((fighter.id, stat))
            if counts is None:
                continue
            change = _classify(
                fighter=fighter,
                stat=stat,
                legacy_count=counts[0],
                mod_count=counts[1],
                base=base_by_stat.get(stat),
                displayed=displayed_by_stat.get(stat),
                shadowed=(fighter.id, stat) in shadowed,
                mod_ctx=mod_ctx,
            )
            if change is not None:
                plan.changes.append(change)

    return plan


def _classify(
    *, fighter, stat, legacy_count, mod_count, base, displayed, shadowed, mod_ctx
):
    def make(situation, override_after=None, flip=False, displayed_after=None):
        return Change(
            fighter_id=str(fighter.id),
            fighter_name=fighter.name,
            list_id=str(fighter.list_id),
            list_name=fighter.list.name,
            owner_id=fighter.list.owner_id,
            stat=stat,
            situation=situation,
            override_before=override,
            override_after=override_after,
            flip_advancements=flip,
            displayed_before=displayed,
            displayed_after=(displayed if displayed_after is None else displayed_after),
        )

    override = getattr(fighter, f"{stat}_override", None)

    if shadowed or base is None:
        return make(4)

    expected = step(stat, base, legacy_count or mod_count, mod_ctx)
    if expected is None:
        return make(8)

    if legacy_count:
        if override in (None, ""):
            # The advancement writes nothing and shows nothing. Flipping it
            # makes it start applying, so the stat gains a step per advancement.
            after = step(stat, displayed, legacy_count, mod_ctx)
            if after is None:
                return make(8)
            return make(3, override_after=None, flip=True, displayed_after=after)

        if override == expected:
            # 0196 should have taken this; nothing left to do.
            return None

        if numeric(override) is not None and numeric(override) == numeric(expected):
            # Same number, older formatting. Clearing it leaves the value alone.
            return make(2, override_after=None, flip=True)

        # A person typed this. Store it one step worse so the advancements
        # restore exactly what is on the card today.
        back = step(stat, override, legacy_count, mod_ctx, mode="worsen")
        if back is None:
            return make(8)
        # Round-trip: improving the back-computed value must give the original
        # back, or the card would move.
        if step(stat, back, legacy_count, mod_ctx) != override:
            return make(8)
        return make(1, override_after=back, flip=True)

    if override in (None, ""):
        return None

    if numeric(override) is not None and numeric(override) == numeric(expected):
        # The override duplicates what the advancements already apply.
        after = step(stat, displayed, mod_count, mod_ctx, mode="worsen")
        if after is None:
            return make(8)
        return make(5, override_after=None, displayed_after=after)

    for count in range(1, mod_count):
        partial = step(stat, base, count, mod_ctx)
        if partial is not None and numeric(override) == numeric(partial):
            after = step(stat, displayed, count, mod_ctx, mode="worsen")
            if after is None:
                return make(8)
            return make(6, override_after=None, displayed_after=after)

    return make(7)


def apply_plan(plan):
    """Write the plan's changes. Returns how many pairs were acted on."""
    from gyrinx.core.models.list import ListFighter
    from gyrinx.core.models.list.advancement import ListFighterAdvancement

    by_fighter = {}
    for change in plan.acted_on:
        by_fighter.setdefault(change.fighter_id, []).append(change)

    for fighter_id, changes in by_fighter.items():
        overrides = {
            f"{c.stat}_override": c.override_after
            for c in changes
            if c.override_before != c.override_after
        }
        if overrides:
            # An UPDATE rather than save(): saving a fighter fires receivers
            # that materialise child fighters and bump the gang's modified
            # timestamp, reordering every affected player's gang list.
            ListFighter.objects.filter(pk=fighter_id).update(**overrides)

        for change in changes:
            if change.flip_advancements:
                ListFighterAdvancement.objects.filter(
                    fighter_id=fighter_id,
                    stat_increased=change.stat,
                    advancement_type="stat",
                    archived=False,
                    uses_mod_system=False,
                ).update(uses_mod_system=True)

    return len(plan.acted_on)


STAT_NAMES = {
    "movement": "Movement",
    "weapon_skill": "Weapon Skill",
    "ballistic_skill": "Ballistic Skill",
    "strength": "Strength",
    "toughness": "Toughness",
    "wounds": "Wounds",
    "initiative": "Initiative",
    "attacks": "Attacks",
    "leadership": "Leadership",
    "cool": "Cool",
    "willpower": "Willpower",
    "intelligence": "Intelligence",
}


def _lines(changes):
    """Render one bullet per change, grouped under the gang it belongs to."""
    by_list = {}
    for change in changes:
        by_list.setdefault(change.list_name, []).append(change)

    out = []
    for list_name in sorted(by_list):
        out.append(f"<p><strong>{list_name}</strong></p><ul>")
        for change in sorted(
            by_list[list_name], key=lambda c: (c.fighter_name, c.stat)
        ):
            stat_name = STAT_NAMES.get(change.stat, change.stat)
            out.append(
                f"<li>{change.fighter_name} — {stat_name} "
                f"<strong>{change.displayed_before} → {change.displayed_after}</strong></li>"
            )
        out.append("</ul>")
    return "".join(out)


def build_messages(plan):
    """One message per owner, covering every gang of theirs that changed.

    Losses are listed before gains: the bad news is what someone needs to see,
    and burying it under good news reads as spin.
    """
    by_owner = {}
    for change in plan.visible:
        if change.owner_id is not None:
            by_owner.setdefault(change.owner_id, []).append(change)

    messages = []
    for owner_id, changes in by_owner.items():
        losses = [c for c in changes if c.direction == LOSS]
        gains = [c for c in changes if c.direction == GAIN]

        body = []
        if losses and gains:
            subject = "We've corrected some fighter stats"
            body.append(
                "<p>We found two problems with how characteristic advancements "
                "were being applied to your fighters, and have fixed both.</p>"
            )
            body.append(
                "<p><strong>These stats were too high</strong> — an advancement "
                "was being counted twice:</p>"
            )
            body.append(_lines(losses))
            body.append(
                "<p><strong>These advancements weren't being applied at all</strong> "
                "— they now show the improvement you paid for:</p>"
            )
            body.append(_lines(gains))
            body.append(
                "<p>Your gangs' ratings and credits haven't changed. Where an "
                "advancement wasn't being applied, you were still being charged "
                "for it; only the stat was missing.</p>"
            )
        elif losses:
            subject = "We've corrected some fighter stats that were too high"
            body.append(
                "<p>Some of your fighters had a characteristic advancement counted "
                "twice, so a stat showed one step better than it should have. "
                "We've corrected it.</p>"
            )
            body.append(_lines(losses))
            body.append("<p>Your gang's rating and credits haven't changed.</p>")
        else:
            subject = "We've fixed some advancements that weren't being applied"
            body.append(
                "<p>Some characteristic advancements you'd bought weren't being "
                "applied to your fighters' stats. We've fixed that, so they now "
                "show the improvement you paid for.</p>"
            )
            body.append(_lines(gains))
            body.append(
                "<p>Your gang's rating and credits haven't changed. You were "
                "always being charged for these advancements; only the stat "
                "was missing.</p>"
            )

        body.append(
            "<p>If anything looks wrong, you can change a fighter's stats "
            "yourself from their edit page.</p>"
        )
        messages.append((owner_id, subject, "".join(body)))

    return messages


def send_messages(messages):
    """Deliver the messages. Returns how many were created."""
    from django.contrib.auth import get_user_model

    from gyrinx.core.models.notification import NotificationType, notify

    User = get_user_model()
    users = User.objects.in_bulk([owner_id for owner_id, _, _ in messages])

    sent = 0
    for owner_id, subject, content in messages:
        recipient = users.get(owner_id)
        if recipient is None:
            logger.warning("No user %r for stat cleanup message; skipping", owner_id)
            continue
        if notify(
            recipient=recipient,
            subject=subject,
            content=content,
            notification_type=NotificationType.SYSTEM,
        ):
            sent += 1
    return sent
