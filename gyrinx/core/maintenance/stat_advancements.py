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

import contextlib
import logging
import re

from django.db import transaction
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
    9: "already handled by an earlier run — left alone",
    10: "re-resolution disagreed with the proposal — left alone",
}

# What re-resolving the fighter's card must show for a proposal to be accepted.
# Situation 1 exists to leave the card untouched. Situation 2 normalises how the
# value is written ("6" becomes the 6" the mod system renders), so the number
# must hold even though the string changes. Situations 3, 5 and 6 exist to
# correct the card, so they must actually move it.
EXPECT_UNCHANGED = {1}
EXPECT_SAME_NUMBER = {2}
EXPECT_CHANGED = {3, 5, 6}

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
    archived: bool = False

    @property
    def acted_on(self):
        return self.situation in ACTED_ON

    @property
    def visible_to_player(self):
        """Whether this earns the owner a message.

        Archived gangs are still repaired — the data should be right if they
        are ever restored — but nobody wants to hear about a gang they put
        away months ago.
        """
        return (
            self.situation in NOTIFIED
            and not self.archived
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


def rendered(fighter, stat):
    """The value the fighter's card shows for this stat, resolved fresh.

    Drops the cached properties first — the caller mutates the fighter in
    memory, and a stale cache would report the value from before the change.
    """
    for prop in ("_mods", "_mod_pairs", "statline"):
        fighter.__dict__.pop(prop, None)
    for entry in fighter.statline:
        if entry.field_name == stat:
            return entry.value
    return None


@contextlib.contextmanager
def applied_in_memory(fighter, stat, override_after, flip):
    """Apply a proposal to the in-memory fighter, then put it back.

    Nothing is saved. This exists so a proposal can be judged by what the card
    actually renders rather than by arithmetic predicting it — every bug in
    this work came from predicting.
    """
    field = f"{stat}_override"
    original = getattr(fighter, field)
    flipped = []

    setattr(fighter, field, override_after)
    if flip:
        for adv in fighter.advancements.all():
            if (
                adv.advancement_type == "stat"
                and adv.stat_increased == stat
                and not adv.archived
                and not adv.uses_mod_system
            ):
                adv.uses_mod_system = True
                flipped.append(adv)
    try:
        yield
    finally:
        setattr(fighter, field, original)
        for adv in flipped:
            adv.uses_mod_system = False
        for prop in ("_mods", "_mod_pairs", "statline"):
            fighter.__dict__.pop(prop, None)


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


def previously_handled():
    """(fighter, stat) keys that a completed earlier run already decided.

    Without this the operation is not idempotent, and destructively so. A
    manual edit is stored one step lower so its advancement restores it — but
    that stored value is exactly what the advancement produces from the base,
    which is also the signature of a duplicated improvement. A second run
    therefore reads its own repair as the bug and undoes it, discarding the
    player's edit. The record of what was done is the only thing that tells
    the two apart.
    """
    from gyrinx.core.models import Backfill

    handled = set()
    # Every status except CANCELLED. A run that died partway still changed
    # data, and its record is the only thing that stops the next run reading
    # those repairs as the bug they resemble. Filtering to DONE would leave
    # exactly the interrupted case unprotected.
    summaries = (
        Backfill.objects.filter(operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS)
        .exclude(status=Backfill.Status.CANCELLED)
        .values_list("summary", flat=True)
    )
    for summary in summaries:
        handled.update((summary or {}).get("acted_pairs") or [])
    return handled


def build_plan(skip_pairs=None):
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

    skip_pairs = previously_handled() if skip_pairs is None else skip_pairs

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
            if f"{fighter.id}:{stat}" in skip_pairs:
                plan.changes.append(
                    Change(
                        fighter_id=str(fighter.id),
                        fighter_name=fighter.name,
                        list_id=str(fighter.list_id),
                        list_name=fighter.list.name,
                        owner_id=fighter.list.owner_id,
                        stat=stat,
                        situation=9,
                        override_before=getattr(fighter, f"{stat}_override", None),
                        override_after=getattr(fighter, f"{stat}_override", None),
                        flip_advancements=False,
                        displayed_before=displayed_by_stat.get(stat),
                        displayed_after=displayed_by_stat.get(stat),
                    )
                )
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
                plan.changes.append(_verify(fighter, change))

    return plan


def _verify(fighter, change):
    """Judge a proposal by re-resolving the card, not by arithmetic.

    Applies it in memory and reads the stat back. Situations that exist to
    leave the card alone must not move it; those that exist to correct it must.
    A proposal failing its own expectation is downgraded and left alone — which
    is how a value swallowed by a "set" from equipment, or an odd base format,
    gets caught without having to be anticipated.

    The recorded before/after are the real rendered values, so the messages
    sent to players describe what actually happened.
    """
    if not change.acted_on:
        return change

    before = rendered(fighter, change.stat)
    with applied_in_memory(
        fighter, change.stat, change.override_after, change.flip_advancements
    ):
        after = rendered(fighter, change.stat)

    change.displayed_before = before
    change.displayed_after = after

    unchanged = before == after
    same_number = numeric(before) is not None and numeric(before) == numeric(after)
    if (
        (change.situation in EXPECT_UNCHANGED and not unchanged)
        or (change.situation in EXPECT_SAME_NUMBER and not same_number)
        or (change.situation in EXPECT_CHANGED and unchanged)
    ):
        change.situation = 10
        change.override_after = change.override_before
        change.flip_advancements = False
        change.displayed_after = before
    return change


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


@dataclass
class ApplyResult:
    """What a run did, recorded on the Backfill row."""

    changed: int = 0
    visible: int = 0
    messages_sent: int = 0
    # What was asked for, so a summary reading "sent 0" can be told apart from
    # "there was nothing to send".
    notify_requested: bool = False
    messages_expected: int = 0
    skipped: int = 0
    by_situation: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)
    # Every pair acted on, so a later run can tell its own repairs apart from
    # the bug they resemble. Not just the visible ones.
    acted_pairs: list = field(default_factory=list)
    backfill: object = None

    def as_dict(self):
        return {
            "changed": self.changed,
            "visible": self.visible,
            "messages_sent": self.messages_sent,
            "notify_requested": self.notify_requested,
            "messages_expected": self.messages_expected,
            "skipped_changed_by_someone_else": self.skipped,
            "by_situation": {str(k): v for k, v in self.by_situation.items()},
            "changes": self.changes,
            "acted_pairs": self.acted_pairs,
        }


def apply_plan(plan):
    """Write the plan's changes. Returns (applied, skipped).

    Each write is conditional on the value the plan was built against still
    being there. Building the plan walks every affected fighter, which takes
    long enough that a player can edit a stat in the meantime — and writing
    blind would overwrite that edit with a decision made about the old value.
    Losing a player's edit is the exact harm this operation exists to undo, so
    a stale pair is skipped and reported rather than forced through.
    """
    from gyrinx.core.models.list import ListFighter
    from gyrinx.core.models.list.advancement import ListFighterAdvancement

    applied = []
    skipped = []

    for change in plan.acted_on:
        field = f"{change.stat}_override"
        # Compare-and-set, unconditionally — including where the value is not
        # changing at all. Situation 3 only flips the advancement and leaves
        # the field alone, but the decision was still made against the field
        # being empty; if someone typed a value meanwhile, switching the
        # advancement on regardless would move their card. A no-op UPDATE
        # still reports a matched row, so the check works either way, and it
        # takes a row lock that holds until the flip below.
        #
        # An UPDATE rather than save(), because saving fires receivers that
        # materialise child fighters and bump the gang's modified timestamp,
        # reordering the owner's gang list.
        written = ListFighter.objects.filter(
            pk=change.fighter_id, **{field: change.override_before}
        ).update(**{field: change.override_after})
        if not written:
            skipped.append(change)
            continue

        if change.flip_advancements:
            flipped = ListFighterAdvancement.objects.filter(
                fighter_id=change.fighter_id,
                stat_increased=change.stat,
                advancement_type="stat",
                archived=False,
                uses_mod_system=False,
            ).update(uses_mod_system=True)
            if not flipped:
                # The advancement was archived between planning and now, so
                # the conversion did not happen. Put the field back: leaving
                # it written without the advancement to justify it would move
                # the fighter's stat. Mirror of the stale-value case above.
                ListFighter.objects.filter(pk=change.fighter_id).update(
                    **{field: change.override_before}
                )
                skipped.append(change)
                continue

        applied.append(change)

    if skipped:
        logger.warning(
            "Stat cleanup skipped %d pair(s) changed by someone else mid-run: %s",
            len(skipped),
            ", ".join(f"{c.fighter_id}:{c.stat}" for c in skipped),
        )
    return applied, skipped


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
    """Render one bullet per change, grouped under the gang it belongs to.

    Gang and fighter names are user input. The notification template runs the
    content through a sanitiser, but this builds HTML by concatenation, so
    escape here too rather than depending on one filter at the far end.
    """

    from django.utils.html import escape

    by_list = {}
    for change in changes:
        by_list.setdefault(change.list_name, []).append(change)

    out = []
    for list_name in sorted(by_list):
        out.append(f"<p><strong>{escape(list_name)}</strong></p><ul>")
        for change in sorted(
            by_list[list_name], key=lambda c: (c.fighter_name, c.stat)
        ):
            stat_name = STAT_NAMES.get(change.stat, change.stat)
            out.append(
                f"<li>{escape(change.fighter_name)} — {escape(stat_name)} "
                f"<strong>{escape(change.displayed_before)} → "
                f"{escape(change.displayed_after)}</strong></li>"
            )
        out.append("</ul>")
    return "".join(out)


def build_messages(plan):
    """One message per owner, for everything visible in the plan."""
    return build_messages_for(plan.visible)


def build_messages_for(changes):
    """One message per owner, covering every gang of theirs that changed.

    Losses are listed before gains: the bad news is what someone needs to see,
    and burying it under good news reads as spin.
    """
    by_owner = {}
    for change in changes:
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


def run(*, notify=True, triggered_by=None):
    """Plan, apply, tell the affected players, and record what was done.

    The Backfill record is written here rather than by the caller because a
    later run reads it to recognise its own repairs. Leaving that to the
    caller would mean a missed write silently makes the next run destructive.

    ``triggered_by`` is accepted for symmetry with the other maintenance
    operations; the messages are deliberately system-sent rather than
    attributed to the operator.
    """
    from gyrinx.core.models import Backfill

    plan = build_plan()

    result = ApplyResult(
        changed=len(plan.acted_on),
        visible=len(plan.visible),
        messages_sent=0,
        by_situation=plan.by_situation(),
        acted_pairs=[f"{c.fighter_id}:{c.stat}" for c in plan.acted_on],
        changes=[
            {
                "list": c.list_name,
                "fighter": c.fighter_name,
                "stat": c.stat,
                "situation": c.situation,
                "before": c.displayed_before,
                "after": c.displayed_after,
                "direction": c.direction,
            }
            for c in plan.visible
        ],
    )

    # The record is created and committed on its own, BEFORE the data changes,
    # naming every pair about to be touched. Two things depend on it being
    # visible to other connections rather than buried inside the write
    # transaction: the guard that stops a second run starting, and the memory
    # that stops a later run undoing these repairs. If the process dies during
    # the write, the data rolls back and this record remains, so those pairs
    # are skipped next time — conservative, and never destructive.
    record = Backfill.objects.create(
        operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS,
        triggered_by=triggered_by,
        status=Backfill.Status.RUNNING,
        summary=result.as_dict(),
    )

    with transaction.atomic():
        applied, skipped = apply_plan(plan)

        result.changed = len(applied)
        result.skipped = len(skipped)
        result.acted_pairs = [f"{c.fighter_id}:{c.stat}" for c in applied]

        # INVARIANT: nothing may write to record.summary after this block
        # exits. The delivery runs from on_commit — always after the commit,
        # whatever order it was registered in — and writes the message count.
        # Any later write here would clobber it, which is how the count came
        # to read zero once already.
        record.summary = result.as_dict()
        record.status = Backfill.Status.DONE
        record.save(update_fields=["summary", "status", "modified"])

        if notify:
            # Only once the data is committed: nobody should be told about a
            # change that rolled back. Keyed on (fighter, stat) rather than by
            # identity — Change is mutable and compared by value.
            stale = {(c.fighter_id, c.stat) for c in skipped}
            delivered = [c for c in plan.visible if (c.fighter_id, c.stat) not in stale]
            outgoing = build_messages_for(delivered)

            # Recorded before the send so that "0 sent" can be read afterwards.
            # Without it a delivery that crashed looks exactly like having had
            # nothing to send, and a re-run cannot tell the difference either:
            # these pairs are already recorded as handled, so it finds nothing
            # visible and sends nothing.
            result.notify_requested = True
            result.messages_expected = len(outgoing)
            record.summary = result.as_dict()
            record.save(update_fields=["summary", "modified"])

            transaction.on_commit(lambda: _deliver(record, outgoing))

    record.refresh_from_db()
    result.messages_sent = (record.summary or {}).get("messages_sent", 0)
    result.backfill = record
    return result


def _deliver(record, messages):
    """Send the messages and note how many landed on the record.

    Written in a finally so a crash partway records what did go out. Without
    it a failed delivery is indistinguishable from having had nothing to send,
    and a re-run cannot recover: the pairs are already recorded as handled, so
    it finds nothing visible and sends nothing. The list needed for a manual
    send is in summary["changes"].
    """
    record.refresh_from_db()
    sent = 0
    try:
        sent = send_messages(messages)
    finally:
        record.summary = {**(record.summary or {}), "messages_sent": sent}
        record.save(update_fields=["summary", "modified"])
    return sent
