"""Distribute asset tables through campaign-type built-in sets.

Tables in an asset type's pack use its campaign type as giver.
Campaign-specific tables use that campaign's additions type, preventing
shared types from distributing them to unrelated campaigns.

Skip tables granted by modifiers, such as House-specific journal tables.
Archiving removes future distribution; restoring revives the same membership
to preserve provenance. ``build_in_missing`` accepts historical model classes
and returns created memberships for the caller to propagate.
"""

from django.apps import apps as live_models
from django.core.exceptions import FieldError
from django.db import transaction
from django.db.models import Max

from n26.library.possessions import _built_ins_of, giver_of


def is_granted(table, apps):
    """Detect modifier-granted tables, including historical states without table grants."""
    try:
        AddsAssignable = apps.get_model("library", "AddsAssignable")
        return AddsAssignable.objects.filter(asset_table=table).exists()
    except LookupError, FieldError:
        return False


@transaction.atomic
def give_back(table):
    """Restore an unarchived table's built-in membership when eligible.

    Revive the archived membership to preserve provenance and avoid duplicate
    catch-up grants. Create a new member when no archived one remains.
    """
    from n26.core.propagation import file_propagation_task
    from n26.library.authoring import add_built_in
    from n26.library.models import DefaultAssignment

    members = DefaultAssignment.objects.filter(asset_table=table)
    if members.filter(archived=False).exists():
        return
    revived = list(members.filter(archived=True))
    for member in revived:
        member.unarchive()
        file_propagation_task(member.default_set)
    if revived:
        return
    if is_granted(table, live_models):
        return
    giver = giver_of(table, live_models)
    if giver is not None:
        add_built_in(giver, table, pack=table.pack)


def build_in_missing(apps, campaign_type=None):
    """Return missing built-in table memberships created directly from the supplied models.

    Skip archived tables, modifier-granted tables and existing live memberships.
    Optionally limit to one campaign type. The caller schedules propagation.
    """
    AssetTable = apps.get_model("library", "AssetTable")
    DefaultAssignment = apps.get_model("library", "DefaultAssignment")
    DefaultAssignmentSet = apps.get_model("library", "DefaultAssignmentSet")

    tables = AssetTable.objects.filter(archived=False).select_related(
        "asset_type__campaign_type"
    )
    if campaign_type is not None:
        tables = tables.filter(asset_type__campaign_type=campaign_type)

    made = []
    # Reuse each campaign type instance so subsequent tables see its new built-in set.
    givers = {}
    for table in tables.order_by("name"):
        giver = giver_of(table, apps)
        if giver is None or is_granted(table, apps):
            continue
        giver = givers.setdefault(giver.pk, giver)
        built_ins = _built_ins_of(giver, DefaultAssignmentSet)
        if built_ins.members.filter(asset_table=table, archived=False).exists():
            continue
        last = built_ins.members.aggregate(last=Max("position"))["last"]
        made.append(
            DefaultAssignment.objects.create(
                pack_id=table.pack_id,
                default_set=built_ins,
                asset_table=table,
                position=0 if last is None else last + 1,
            )
        )
    return made
