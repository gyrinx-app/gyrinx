"""C2 of Track C (#1861): fighter stat overrides move to the EAV store.

C1 gave every ContentFighter a real statline, so every fighter now reads the
`ListFighterStatOverride` branch first and only falls back to the legacy
`<stat>_override` columns when no EAV row exists. This migrates those legacy
values across so the fallback has nothing left to serve.

Per (fighter, stat), one of:

- **migrate** — a legacy value with no EAV row: create the row verbatim, clear
  the column. Display-preserving, because the new row is read in the fallback's
  place.
- **drop-redundant** — an EAV row already holds the same value: the column was
  already dead (EAV outranks it), so just clear it. No display change.
- **conflict** — an EAV row holds a *different* value: EAV is what the card
  shows, so it wins and the column is cleared. Reported individually, because
  the discarded value is a real edit somebody made.
- **inert** — the stat is not in the fighter's statline type at all (weapon
  skill on a crew fighter, say). Nothing rendered it; clear and report.
- **unmigratable** — the value is longer than the EAV column allows. Left
  alone and reported rather than truncated.

Values copy verbatim, always. Cards display these strings as-is today —
including dice expressions and player typos — so verbatim is the
display-preserving choice, and this migration is not the place to tidy them.

The record is created RUNNING before any write and enumerates every decision;
each fighter commits in its own transaction, so an interrupted run leaves
completed fighters migrated and the rest for a re-run.
"""

import logging
import traceback
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction

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

MIGRATE = "migrate"
DROP_REDUNDANT = "drop-redundant"
CONFLICT = "conflict"
INERT = "inert"
UNMIGRATABLE = "unmigratable"
NO_STATLINE = "no-statline"

ACTION_LABELS = {
    MIGRATE: "moved to the override store",
    DROP_REDUNDANT: "column cleared, override store already agreed",
    CONFLICT: "column cleared, override store held a different value",
    INERT: "column cleared, stat not in the fighter's statline",
    UNMIGRATABLE: "left alone, value too long for the override store",
    NO_STATLINE: "left alone, template has no statline — the column is the card",
}

# Everything except UNMIGRATABLE and NO_STATLINE clears the legacy column.
CLEARS_COLUMN = {MIGRATE, DROP_REDUNDANT, CONFLICT, INERT}


@dataclass
class Move:
    fighter_id: str
    fighter_name: str
    list_name: str
    owner_id: int | None
    stat: str
    action: str
    legacy_value: str
    eav_value: str | None = None
    # The ContentStatlineTypeStat to attach a new row to, when there is one.
    type_stat_id: str | None = None

    @property
    def writes(self):
        return self.action in CLEARS_COLUMN


@dataclass
class Plan:
    moves: list = field(default_factory=list)

    def by_action(self):
        counts = {}
        for m in self.moves:
            counts[m.action] = counts.get(m.action, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def writable(self):
        return [m for m in self.moves if m.writes]

    @property
    def conflicts(self):
        return [m for m in self.moves if m.action == CONFLICT]


def _legacy_override_filter():
    from django.db.models import Q

    q = Q()
    for stat in STAT_FIELDS:
        q |= Q(**{f"{stat}_override__isnull": False}) & ~Q(**{f"{stat}_override": ""})
    return q


def build_plan():
    """Classify every legacy override value still on a fighter."""
    from n23.core.models.list import ListFighter, ListFighterStatOverride

    max_len = ListFighterStatOverride._meta.get_field("value").max_length

    fighters = (
        ListFighter.objects.filter(_legacy_override_filter())
        .select_related("list", "content_fighter", "content_fighter__custom_statline")
        .prefetch_related(
            "content_fighter__custom_statline__statline_type__stats__stat",
            "stat_overrides__content_stat__stat",
        )
        .order_by("id")
    )

    plan = Plan()
    for fighter in fighters.iterator(chunk_size=200):
        statline = getattr(fighter.content_fighter, "custom_statline", None)
        type_stats = (
            {ts.field_name: ts for ts in statline.statline_type.stats.all()}
            if statline
            else {}
        )
        # Read without an archived filter, unlike the annotated fast path.
        # Deliberate: filtering would hide an archived row and let MIGRATE
        # fire into the unique_together on (list_fighter, content_stat).
        # Nothing in the codebase can archive one of these rows today.
        existing = {o.content_stat.field_name: o for o in fighter.stat_overrides.all()}

        for stat in STAT_FIELDS:
            legacy = getattr(fighter, f"{stat}_override", None)
            if legacy in (None, ""):
                continue

            type_stat = type_stats.get(stat)
            current = existing.get(stat)

            if statline is None:
                # No statline at all: this fighter renders through the LEGACY
                # branch, so the column IS the card. Clearing it would destroy
                # the value and move the stat. Distinct from INERT, which is a
                # stat genuinely absent from an existing statline type.
                action, eav_value = NO_STATLINE, None
            elif type_stat is None:
                action, eav_value = INERT, None
            elif current is not None:
                action = DROP_REDUNDANT if current.value == legacy else CONFLICT
                eav_value = current.value
            elif len(legacy) > max_len:
                action, eav_value = UNMIGRATABLE, None
            else:
                action, eav_value = MIGRATE, None

            plan.moves.append(
                Move(
                    fighter_id=str(fighter.id),
                    fighter_name=fighter.name,
                    list_name=fighter.list.name,
                    # The fighter's own owner, matching every other creator of
                    # these rows (clone, copy_attributes_to, the stats view).
                    owner_id=fighter.owner_id,
                    stat=stat,
                    action=action,
                    legacy_value=legacy,
                    eav_value=eav_value,
                    type_stat_id=str(type_stat.id) if type_stat else None,
                )
            )
    return plan


def apply_plan(plan):
    """Write the plan. Returns (applied, skipped).

    One transaction per fighter: an interrupted run leaves whole fighters
    done, never half-migrated.

    Columns are cleared with a queryset UPDATE carrying the planned value in
    its WHERE, never ``fighter.save()``. That does two jobs at once. It is
    the compare-and-set — a zero rowcount means the owner edited that stat
    since planning, so their edit stands and the pair is reported. And it
    avoids the post_save receivers, which would bump every affected gang's
    modified timestamp (reordering 1,500 owners' gang lists) and materialise
    child fighter defaults — a stats migration must not spawn fighters. The
    sibling stat-advancement cleanup documents the same rule.
    """
    from n23.core.models.list import ListFighter, ListFighterStatOverride

    by_fighter = {}
    for move in plan.writable:
        by_fighter.setdefault(move.fighter_id, []).append(move)

    applied, skipped = [], []
    for fighter_id, moves in by_fighter.items():
        try:
            with transaction.atomic():
                done = []
                for move in moves:
                    field_name = f"{move.stat}_override"
                    cleared = ListFighter.objects.filter(
                        pk=fighter_id, **{field_name: move.legacy_value}
                    ).update(**{field_name: None})
                    if not cleared:
                        skipped.append(move)
                        continue
                    if move.action == MIGRATE:
                        ListFighterStatOverride.objects.create(
                            list_fighter_id=fighter_id,
                            content_stat_id=move.type_stat_id,
                            value=move.legacy_value,
                            owner_id=move.owner_id,
                        )
                    done.append(move)
                applied.extend(done)
        except IntegrityError:
            # A row for this (fighter, stat) appeared concurrently — the
            # owner's stats form deletes and recreates rows without touching
            # the column. Roll this fighter back and carry on; one racing
            # owner must not abort the remaining fifteen hundred.
            logger.warning(
                "Stat-override migration skipped fighter %s: override row "
                "created concurrently",
                fighter_id,
            )
            skipped.extend(moves)
        except Exception:
            logger.exception("Stat-override migration failed for %s", fighter_id)
            raise
    if skipped:
        logger.warning(
            "Stat-override migration skipped %d pair(s) changed mid-run: %s",
            len(skipped),
            ", ".join(f"{m.fighter_id}:{m.stat}" for m in skipped[:20]),
        )
    return applied, skipped


def run(*, triggered_by=None):
    """Plan, apply, and record. Returns (record, applied, skipped)."""
    from n23.core.models import Backfill

    record = Backfill.objects.create(
        operation=Backfill.Operation.MIGRATE_STAT_OVERRIDES,
        triggered_by=triggered_by,
        status=Backfill.Status.RUNNING,
    )
    applied, skipped = [], []
    try:
        plan = build_plan()
        applied, skipped = apply_plan(plan)
    except Exception as e:
        record.status = Backfill.Status.FAILED
        record.error = f"{e}\n\n{traceback.format_exc()}"
        # Whatever committed before the failure is named here: per-fighter
        # transactions mean a mid-run abort leaves real work behind, and a
        # record saying only "failed" would hide it.
        record.summary = {
            "applied_before_failure": len(applied),
            "note": "partial run; re-running is safe and re-plans from current state",
        }
        record.save(update_fields=["status", "error", "summary", "modified"])
        raise

    record.summary = {
        "applied": len(applied),
        "skipped_edited_mid_run": len(skipped),
        "by_action": plan.by_action(),
        # Conflicts discard a real edit, so each is named individually.
        "conflicts": [
            {
                "fighter_id": m.fighter_id,
                "fighter": m.fighter_name,
                "list": m.list_name,
                "stat": m.stat,
                "discarded_column_value": m.legacy_value,
                "kept_override_value": m.eav_value,
            }
            for m in plan.conflicts
        ],
        "unmigratable": [
            {
                "fighter_id": m.fighter_id,
                "fighter": m.fighter_name,
                "stat": m.stat,
                "value": m.legacy_value,
            }
            for m in plan.moves
            if m.action == UNMIGRATABLE
        ],
    }
    record.status = Backfill.Status.DONE
    record.save(update_fields=["summary", "status", "modified"])
    return record, applied, skipped
