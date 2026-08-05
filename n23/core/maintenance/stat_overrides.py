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

from django.db import transaction

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

ACTION_LABELS = {
    MIGRATE: "moved to the override store",
    DROP_REDUNDANT: "column cleared, override store already agreed",
    CONFLICT: "column cleared, override store held a different value",
    INERT: "column cleared, stat not in the fighter's statline",
    UNMIGRATABLE: "left alone, value too long for the override store",
}

# Everything except UNMIGRATABLE clears the legacy column.
CLEARS_COLUMN = {MIGRATE, DROP_REDUNDANT, CONFLICT, INERT}


@dataclass
class Move:
    fighter_id: str
    fighter_name: str
    list_id: str
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
        # C1 gave everyone a statline; a fighter without one would fall back to
        # the legacy branch, where migrating would hide the value entirely.
        type_stats = (
            {ts.field_name: ts for ts in statline.statline_type.stats.all()}
            if statline
            else {}
        )
        existing = {o.content_stat.field_name: o for o in fighter.stat_overrides.all()}

        for stat in STAT_FIELDS:
            legacy = getattr(fighter, f"{stat}_override", None)
            if legacy in (None, ""):
                continue

            type_stat = type_stats.get(stat)
            current = existing.get(stat)

            if type_stat is None:
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
                    list_id=str(fighter.list_id),
                    list_name=fighter.list.name,
                    owner_id=fighter.list.owner_id,
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
    done, never a half-migrated statline. Each column clear is
    compare-and-set on the value the plan was built from, so an owner
    editing their stats mid-run keeps their edit and the pair is reported.
    """
    from n23.core.models.list import ListFighter, ListFighterStatOverride

    by_fighter = {}
    for move in plan.writable:
        by_fighter.setdefault(move.fighter_id, []).append(move)

    applied, skipped = [], []
    for fighter_id, moves in by_fighter.items():
        try:
            with transaction.atomic():
                # of=("self",) because the default queryset joins nullable
                # relations, and Postgres refuses FOR UPDATE on the nullable
                # side of an outer join. Only the fighter row needs locking.
                fighter = ListFighter.objects.select_for_update(of=("self",)).get(
                    pk=fighter_id
                )
                done = []
                for move in moves:
                    field_name = f"{move.stat}_override"
                    if getattr(fighter, field_name, None) != move.legacy_value:
                        # The owner edited this stat since planning.
                        skipped.append(move)
                        continue
                    if move.action == MIGRATE:
                        ListFighterStatOverride.objects.create(
                            list_fighter_id=fighter_id,
                            content_stat_id=move.type_stat_id,
                            value=move.legacy_value,
                            owner_id=move.owner_id,
                        )
                    setattr(fighter, field_name, None)
                    done.append(move)
                if done:
                    fighter.save(update_fields=[f"{m.stat}_override" for m in done])
                applied.extend(done)
        except Exception:
            logger.exception("Stat-override migration failed for %s", fighter_id)
            raise
    if skipped:
        logger.warning(
            "Stat-override migration skipped %d pair(s) edited mid-run: %s",
            len(skipped),
            ", ".join(f"{m.fighter_id}:{m.stat}" for m in skipped),
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
    try:
        plan = build_plan()
        applied, skipped = apply_plan(plan)
    except Exception as e:
        record.status = Backfill.Status.FAILED
        record.error = f"{e}\n\n{traceback.format_exc()}"
        record.save(update_fields=["status", "error", "modified"])
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
