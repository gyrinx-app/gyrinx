"""Thin CLI wrapper around the persistent-stash data repair service.

Production triggers this from the admin maintenance page; the CLI is for local
testing and debugging. See ``gyrinx.core.maintenance.persistent_stash`` for the
actual logic, and the admin view at ``/admin/maintenance/persistent-stash/``.
"""

from django.core.management.base import BaseCommand

from gyrinx.core.maintenance.persistent_stash import (
    SKIP_REASONS,
    apply,
    find_candidates,
)


class Command(BaseCommand):
    help = (
        "Move persistent-category gear off stash fighters back to the dying "
        "fighter that originally carried it. Only acts on items provably from "
        "a kill via the ListAction ledger. Dry-run by default; pass --apply "
        "to commit. Use the admin maintenance page in prod."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually move items and append audit ListAction entries.",
        )
        parser.add_argument(
            "--list-id",
            type=str,
            default=None,
            help="Restrict to a single list (useful for local testing).",
        )
        parser.add_argument(
            "--verbose-skips",
            action="store_true",
            help="Print one line per skipped item with the reason.",
        )

    def handle(self, *args, **options):
        do_apply = options.get("apply", False)
        list_id = options.get("list_id")
        verbose_skips = options.get("verbose_skips", False)
        mode = "APPLY" if do_apply else "DRY RUN"

        self.stdout.write(self.style.NOTICE(f"[{mode}] migrate_persistent_stash_items"))

        candidates = find_candidates(list_id=list_id)
        skips = {r: 0 for r in SKIP_REASONS}
        for c in candidates:
            if c.decision == "move":
                self.stdout.write(
                    f"  {'MOVE' if do_apply else 'WOULD MOVE'}: "
                    f"{c.equipment_name!r} → {c.dying_fighter_name!r} "
                    f"(list {c.list_name!r}, assign {c.assignment_id})"
                )
            else:
                skips[c.decision] += 1
                if verbose_skips:
                    self.stdout.write(
                        f"  SKIP[{c.decision}]: {c.equipment_name!r} "
                        f"on list {c.list_id} — {c.detail}"
                    )

        if do_apply:
            result = apply(list_id=list_id)
            moved = result.moved
            affected = result.affected_lists
        else:
            moved = sum(1 for c in candidates if c.decision == "move")
            affected = len({c.list_id for c in candidates if c.decision == "move"})

        self.stdout.write(self.style.NOTICE(f"\nSUMMARY [{mode}]"))
        self.stdout.write(f"  scanned                : {len(candidates)}")
        self.stdout.write(f"  {'moved' if do_apply else 'would-move'}: {moved}")
        self.stdout.write(f"  affected lists         : {affected}")
        for k in SKIP_REASONS:
            self.stdout.write(f"  skip:{k:13s}     : {skips[k]}")
