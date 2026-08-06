"""Slugs identifying this edition's data repairs.

These are written into ``Backfill.operation`` and are the registry keys the
maintenance console labels records by, so they are effectively permanent: a slug
that changes orphans every historical record that carries it.

Retired operations keep their member here and their registration in
``n23/core/admin/maintenance.py`` — without a view, so they get no page, but old
records still render a name rather than a bare slug.
"""

from django.db import models

__all__ = ["Operation"]


class Operation(models.TextChoices):
    MIGRATE_PERSISTENT_STASH = (
        "migrate_persistent_stash",
        "Migrate persistent stash items (#1825)",
    )
    RECONCILE_LISTS = (
        "reconcile_lists",
        "Reconcile list cost caches (#1826 Phase 8)",
    )
    BACKFILL_PINS = (
        "backfill_pins",
        "Backfill acquisition receipts (#1826 Phase 8)",
    )
    # Retired: run once in production on 2026-08-04 and its code removed
    # with #1861 Track C3. The member stays so the historical records keep
    # rendering a name rather than a bare slug; re-running it now would
    # switch on advancements that C2 deliberately left shadowed.
    FIX_STAT_ADVANCEMENTS = (
        "fix_stat_advancements",
        "Finish the stat-advancement cleanup (#2070, retired)",
    )
    # Both retired: run once in production on 2026-08-04, and their code
    # removed once every fighter type was guaranteed a statline at save
    # time — which left them with nothing to find. The members stay so the
    # historical records keep rendering names.
    NORMALISE_STAT_FORMATS = (
        "normalise_stat_formats",
        "Normalise legacy stat-column formats (#1861 Track C1, retired)",
    )
    MATERIALISE_STATLINES = (
        "materialise_statlines",
        "Materialise statlines for legacy templates (#1861 Track C1, retired)",
    )
    # Retired: run once in production on 2026-08-05, and its code removed
    # with #1861 Track C4, which dropped the columns it read. The member
    # stays so the historical record keeps rendering a name.
    MIGRATE_STAT_OVERRIDES = (
        "migrate_stat_overrides",
        "Migrate fighter stat overrides to the override store "
        "(#1861 Track C2, retired)",
    )


#: Operations with no trigger page left — registered for their labels only.
RETIRED = (
    Operation.FIX_STAT_ADVANCEMENTS,
    Operation.NORMALISE_STAT_FORMATS,
    Operation.MATERIALISE_STATLINES,
    Operation.MIGRATE_STAT_OVERRIDES,
)
