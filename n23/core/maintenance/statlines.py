"""C1 of Track C (#1861): every ContentFighter gets a real statline.

Two operations, run in order from the maintenance admin:

1. **Normalise stat formats** — fix the suffix-less values (`4` for `4+`,
   `5` for `5"`) on the legacy stat columns of templates that have no
   statline yet, so the statlines are materialised from clean values. This
   is a *visible* cosmetic correction on the affected fighters' cards,
   approved as such. Only two shapes are touched: a bare integer on a
   target-roll stat gains its ``+``, and on a distance stat gains its ``"``.
   Everything else — including dice expressions like ``D6+1"``, which are
   legitimate content — is left exactly as it is.

2. **Materialise statlines** — create a ``ContentStatline`` on the 12-stat
   "Fighter" type for every ContentFighter that lacks one, copying the
   column values verbatim.

Display preservation is the bar, and it dictates two non-obvious choices:

- **Every template goes on the "Fighter" type**, whatever its category. The
  legacy branch renders all 12 columns for everyone; a category-appropriate
  type (Crew's 5 stats, say) would change the card.
- **Every stat gets a row, with ``-`` for blank columns.** The Python
  renderer shows ``-`` for a missing row, but the annotated fast path
  (``sq_content_fighter_statline``) aggregates only the rows that exist, so
  a missing row would drop the column from the card entirely. A ``-`` row
  renders identically through the legacy branch (``value or "-"``), the
  Python EAV branch, and the fast path. This also means Stash templates get
  statlines of dashes — which leaves C3/C4 with zero legacy-branch users.

Writes here bypass simple-history (queryset ``update`` / bulk creates); the
Backfill record enumerates every change and is the audit trail.
"""

import logging
import re
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

FIGHTER_STATLINE_TYPE = "Fighter"

_BARE_INT = re.compile(r"^\d+$")


@dataclass
class FormatFix:
    cf_id: str
    cf_type: str
    house: str
    stat: str
    old: str
    new: str


@dataclass
class StatlineEntry:
    cf_id: str
    cf_type: str
    house: str
    # field_name -> value to write (always all 12, blanks already dashed)
    values: dict = field(default_factory=dict)
    # how many of the 12 came from blank columns
    blank_count: int = 0


def _stat_flags():
    from n23.content.models.statline import ContentStat

    return {
        s["field_name"]: s
        for s in ContentStat.objects.filter(field_name__in=STAT_FIELDS).values(
            "field_name", "is_target", "is_inches"
        )
    }


def _statline_less_fighters():
    """Templates with no statline yet — including pack-owned ones.

    ``all_content`` bypasses the pack-excluding default manager: pack
    fighters also fall back to the legacy branch today, and C4 drops the
    columns for everyone.
    """
    from n23.content.models import ContentFighter

    return (
        ContentFighter.objects.all_content()
        .filter(custom_statline__isnull=True)
        .select_related("house")
        .order_by("type")
    )


def build_format_plan():
    """Every suffix-less value on a statline-less template, with its fix."""
    flags = _stat_flags()
    fixes = []
    for cf in _statline_less_fighters():
        for stat in STAT_FIELDS:
            value = (getattr(cf, stat) or "").strip()
            if not _BARE_INT.fullmatch(value):
                continue
            f = flags.get(stat)
            if not f:
                continue
            if f["is_target"]:
                suffix = "+"
            elif f["is_inches"]:
                suffix = '"'
            else:
                continue  # plain-number stats are already correct
            fixes.append(
                FormatFix(
                    cf_id=str(cf.id),
                    cf_type=cf.type,
                    house=cf.house.name if cf.house else "",
                    stat=stat,
                    old=getattr(cf, stat),
                    new=value + suffix,
                )
            )
    return fixes


def apply_format_plan(fixes):
    """Write the fixes. Returns (applied, skipped).

    Compare-and-set on the value read at planning time: content admins can
    edit templates at any moment, and a plan built against an old value must
    not overwrite a newer one. Stale fixes are skipped and reported.
    """
    from n23.content.models import ContentFighter

    applied, skipped = [], []
    for fix in fixes:
        written = (
            ContentFighter.objects.all_content()
            .filter(pk=fix.cf_id, **{fix.stat: fix.old})
            .update(**{fix.stat: fix.new})
        )
        (applied if written else skipped).append(fix)
    if skipped:
        logger.warning(
            "Stat-format normalise skipped %d value(s) edited mid-run: %s",
            len(skipped),
            ", ".join(f"{f.cf_type}.{f.stat}" for f in skipped),
        )
    return applied, skipped


def build_statline_plan():
    """One entry per template that needs a statline."""
    entries = []
    for cf in _statline_less_fighters():
        values = {}
        blanks = 0
        for stat in STAT_FIELDS:
            value = (getattr(cf, stat) or "").strip()
            if not value:
                value = "-"
                blanks += 1
            values[stat] = value
        entries.append(
            StatlineEntry(
                cf_id=str(cf.id),
                cf_type=cf.type,
                house=cf.house.name if cf.house else "",
                values=values,
                blank_count=blanks,
            )
        )
    return entries


def fighter_statline_type():
    """The 12-stat "Fighter" type, with its per-stat rows keyed by field name.

    Raises with a pointed message if absent: content.0156 guarantees it in
    every migrated database, but tests run with --nomigrations and a fresh
    environment missing it should fail loudly, not materialise nothing.
    """
    from n23.content.models.statline import ContentStatlineType

    statline_type = (
        ContentStatlineType.objects.filter(name=FIGHTER_STATLINE_TYPE)
        .prefetch_related("stats__stat")
        .first()
    )
    if statline_type is None:
        raise RuntimeError(
            f"No '{FIGHTER_STATLINE_TYPE}' ContentStatlineType — content.0156 "
            "seeds it; this database has not been migrated."
        )
    by_field = {ts.field_name: ts for ts in statline_type.stats.all()}
    missing = [s for s in STAT_FIELDS if s not in by_field]
    if missing:
        raise RuntimeError(
            f"'{FIGHTER_STATLINE_TYPE}' statline type is missing stats: {missing}"
        )
    return statline_type, by_field


def apply_statline_plan(entries):
    """Create the statlines. Returns (created, skipped).

    Each template's statline and its 12 rows commit atomically. A statline
    appearing concurrently (pack editor, admin) trips the OneToOne
    constraint and the template is skipped — never half-written, never
    overwritten.
    """
    from n23.content.models.statline import ContentStatline, ContentStatlineStat

    statline_type, by_field = fighter_statline_type()

    created, skipped = [], []
    for entry in entries:
        try:
            with transaction.atomic():
                statline = ContentStatline.objects.create(
                    content_fighter_id=entry.cf_id, statline_type=statline_type
                )
                ContentStatlineStat.objects.bulk_create(
                    ContentStatlineStat(
                        statline=statline,
                        statline_type_stat=by_field[stat],
                        value=value,
                    )
                    for stat, value in entry.values.items()
                )
        except IntegrityError:
            skipped.append(entry)
            continue
        created.append(entry)
    if skipped:
        logger.warning(
            "Statline materialise skipped %d template(s) that gained a "
            "statline mid-run: %s",
            len(skipped),
            ", ".join(e.cf_type for e in skipped),
        )
    return created, skipped


def _record(operation, triggered_by, summary):
    from n23.core.models import Backfill

    return Backfill.objects.create(
        operation=operation,
        triggered_by=triggered_by,
        status=Backfill.Status.DONE,
        summary=summary,
    )


def run_normalise(*, triggered_by=None):
    from n23.core.models import Backfill

    fixes = build_format_plan()
    applied, skipped = apply_format_plan(fixes)
    record = _record(
        Backfill.Operation.NORMALISE_STAT_FORMATS,
        triggered_by,
        {
            "applied": len(applied),
            "skipped_edited_mid_run": len(skipped),
            "changes": [
                {"type": f.cf_type, "stat": f.stat, "old": f.old, "new": f.new}
                for f in applied
            ],
        },
    )
    return record, applied, skipped


def run_materialise(*, triggered_by=None):
    from n23.core.models import Backfill

    entries = build_statline_plan()
    created, skipped = apply_statline_plan(entries)
    record = _record(
        Backfill.Operation.MATERIALISE_STATLINES,
        triggered_by,
        {
            "created": len(created),
            "skipped_gained_statline_mid_run": len(skipped),
            "all_blank_templates": sum(1 for e in created if e.blank_count == 12),
            "templates": [
                {"type": e.cf_type, "house": e.house, "blank_stats": e.blank_count}
                for e in created
            ],
        },
    )
    return record, created, skipped
