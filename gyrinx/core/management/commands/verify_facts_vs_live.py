"""Read-only drift harness: compare each List's persisted facts to a live recompute.

Stage 0 of #1860 (finish the facts/cost-cache migration). Before any of the
legacy cost regimes can be deleted we must *prove* the persisted facts cache
(``rating_current`` / ``stash_current`` / ``credits_current``) agrees with a
clean live ``cost_int()`` recompute, list-wide. This command does exactly that
and NOTHING else — it computes, compares, and reports. It never writes.

For every non-archived ``List`` (optionally filtered by id or owner) it:

  * reads the PERSISTED facts — the stored ``rating_current`` /
    ``stash_current`` / ``credits_current`` fields. These are exactly what
    ``List.facts()`` serves on a clean list and what the UI displays; they are
    the values the migration intends to trust. (We read the raw stored fields,
    not ``facts_from_db(update=False)``: the latter lazily *re-derives* the
    List aggregate from the child fighter caches, so a List-level cache drift
    would be silently re-derived away and never reported. The stored fields are
    the thing we must prove correct.) and
  * computes a fresh LIVE recompute by summing ``cost_int()`` over a brand-new
    set of model instances (``@cached_property`` survives ``refresh_from_db``,
    so we must fetch fresh instances to get a genuinely uncached recompute —
    see the project memory note on this).

It then compares the two at the rating / stash / credits levels and reports
every list where they disagree, with both values and the delta. Because the
live side recomputes the whole assignment -> fighter -> list subtree, drift at
*any* level surfaces here. The exit code is non-zero if any mismatch is found,
so it is CI/scriptable.

This mirrors the computation approach of the ``recompute_cost_caches`` admin
action (``gyrinx/core/admin/list.py``) — which rebuilds assignment -> fighter
-> list from ``cost_int()`` ignoring dirty flags — but performs ZERO writes.

Intended to be run read-only, including via ``manage prodshell``-style
read-only access against production.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError

from gyrinx.core.models.list import List


@dataclass
class Triple:
    """A (rating, stash, credits) triple of cost values."""

    rating: int
    stash: int
    credits: int

    @property
    def wealth(self) -> int:
        return self.rating + self.stash + self.credits


@dataclass
class ListComparison:
    """The persisted-vs-live comparison for a single list."""

    list_id: str
    list_name: str
    owner: str
    dirty: bool
    persisted: Triple
    live: Triple

    @property
    def rating_delta(self) -> int:
        return self.persisted.rating - self.live.rating

    @property
    def stash_delta(self) -> int:
        return self.persisted.stash - self.live.stash

    @property
    def credits_delta(self) -> int:
        return self.persisted.credits - self.live.credits

    @property
    def has_mismatch(self) -> bool:
        return bool(self.rating_delta or self.stash_delta or self.credits_delta)


def _live_recompute(list_id) -> Triple:
    """Compute a clean live recompute for a list from FRESH instances.

    ``@cached_property`` (cost_int caches, stash_fighter, fighters_cached, …)
    survives ``refresh_from_db``, so to get a genuinely uncached recompute we
    must load brand-new instances rather than reuse the ones we read the
    persisted facts from. Mirrors ``List.cost_int()``'s decomposition
    (rating = non-stash fighters, stash = stash fighter, credits = stored
    credits) but reads each level explicitly so we never call
    ``check_wealth_sync`` / emit telemetry as a side effect.
    """
    fresh = List.objects.get(pk=list_id)

    rating = sum(
        f.cost_int() for f in fresh.fighters() if not f.content_fighter.is_stash
    )
    stash = fresh.stash_fighter.cost_int() if fresh.stash_fighter else 0
    credits = fresh.credits_current

    return Triple(rating=rating, stash=stash, credits=credits)


def _persisted_facts(lst: List) -> Triple:
    """Read the raw STORED facts fields (no recompute, no write).

    These are the values ``List.facts()`` serves on a clean list and the UI
    displays. We deliberately read the stored fields rather than calling
    ``facts_from_db(update=False)``: the latter re-derives the List aggregate
    from the child fighter caches, which would mask a List-level drift. The
    stored values are exactly what the migration wants to trust, so they are
    what we compare against the live recompute.
    """
    return Triple(
        rating=lst.rating_current,
        stash=lst.stash_current,
        credits=lst.credits_current,
    )


def compare_list(lst: List) -> ListComparison:
    """Build the persisted-vs-live comparison for one list (read-only)."""
    return ListComparison(
        list_id=str(lst.pk),
        list_name=lst.name,
        owner=getattr(lst.owner, "username", "<none>"),
        dirty=lst.dirty,
        persisted=_persisted_facts(lst),
        live=_live_recompute(lst.pk),
    )


class Command(BaseCommand):
    help = (
        "Read-only drift harness (#1860 Stage 0): for every non-archived List, "
        "compare the stored facts (rating_current / stash_current / "
        "credits_current) to a fresh live cost_int() recompute and report any "
        "list where they disagree at the rating / stash / credits level. Writes "
        "NOTHING. Exits non-zero if any mismatch is found so it is CI/scriptable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--list-id",
            type=str,
            default=None,
            help="Restrict to a single list by id.",
        )
        parser.add_argument(
            "--owner",
            type=str,
            default=None,
            help="Restrict to lists owned by this username.",
        )
        parser.add_argument(
            "--include-archived",
            action="store_true",
            help="Also check archived lists (default: non-archived only).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print the summary line, not per-mismatch detail.",
        )

    def _select_lists(self, options):
        qs = List.objects.all()
        if not options.get("include_archived"):
            qs = qs.filter(archived=False)
        if options.get("list_id"):
            qs = qs.filter(pk=options["list_id"])
        if options.get("owner"):
            qs = qs.filter(owner__username=options["owner"])
        return qs.select_related("owner", "content_house").order_by("name")

    def _report_mismatch(self, comparison: ListComparison):
        self.stdout.write(
            self.style.ERROR(
                f"MISMATCH: {comparison.list_name!r} (id={comparison.list_id}, "
                f"owner={comparison.owner}, dirty={comparison.dirty})"
            )
        )
        levels = [
            (
                "rating",
                comparison.persisted.rating,
                comparison.live.rating,
                comparison.rating_delta,
            ),
            (
                "stash",
                comparison.persisted.stash,
                comparison.live.stash,
                comparison.stash_delta,
            ),
            (
                "credits",
                comparison.persisted.credits,
                comparison.live.credits,
                comparison.credits_delta,
            ),
        ]
        for name, persisted, live, delta in levels:
            if delta:
                self.stdout.write(
                    f"    {name:8s}: persisted={persisted} live={live} delta={delta:+d}"
                )

    def handle(self, *args, **options):
        quiet = options.get("quiet", False)
        lists = self._select_lists(options)

        if options.get("list_id") and not lists.exists():
            raise CommandError(f"No list found with id={options['list_id']}")

        checked = 0
        mismatches = 0

        for lst in lists.iterator():
            comparison = compare_list(lst)
            checked += 1
            if comparison.has_mismatch:
                mismatches += 1
                if not quiet:
                    self._report_mismatch(comparison)

        summary = f"Checked {checked} list(s); {mismatches} mismatch(es)."
        if mismatches:
            self.stdout.write(self.style.ERROR(summary))
            # Non-zero exit so the harness is CI/scriptable.
            raise CommandError(
                f"{mismatches} list(s) drifted: persisted facts disagree with "
                "live cost_int() recompute."
            )

        self.stdout.write(self.style.SUCCESS(summary))
