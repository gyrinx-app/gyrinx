"""An asset table is given to every gang without an author's step.

A table of one Holding asset type — the core rulebook's Territory
Selection Table — is something every gang in a campaign of that type
may roll on, and the way a campaign type gives anything to every gang
that joins is its built-ins. So creating a table under a campaign type's
asset type builds it into that type's built-in set, and deleting or
archiving the table takes it out again, exactly as a possession is given
(``n26.library.possessions``). The member is an ordinary
``DefaultAssignment`` naming the table, so joining and catch-up
propagation need nothing new, and the table draws no line anywhere.

Which campaign type gives a table follows the table's pack, by the rule
possessions follow: a table in its asset type's own pack is given by
that asset type's campaign type; a table an arbitrator writes into a
campaign's own pack under a shared asset type is given by that
campaign's additions type, so one campaign's table never reaches every
campaign founded on the shared type.

``authoring.create_asset_table`` applies the rule to live models and
files the propagation pass. ``give_back`` puts an unarchived table back.
``build_in_missing`` applies the rule to whatever is already there,
written against the model classes it is handed so the seed and a data
migration can run it on historical ones.
"""

from django.apps import apps as live_models
from django.db import transaction
from django.db.models import Max

from n26.library.possessions import _built_ins_of, giver_of


@transaction.atomic
def give_back(table):
    """Give an unarchived table again, the mirror of the archive that
    stopped it: gangs joining from here on are given it, and the gangs
    that joined while it was archived catch up.

    The archived membership is revived rather than replaced, for the
    reason a possession's is: every copy already on a gang names that
    membership as its provenance, and a fresh one would have the
    catch-up pass hand those gangs a second copy. Where the membership
    was deleted instead — nothing had come from it — a new one is added
    through the authoring verb, which files the pass itself. Does
    nothing where the table is already given.
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
    giver = giver_of(table, live_models)
    if giver is not None:
        add_built_in(giver, table, pack=table.pack)


def build_in_missing(apps, campaign_type=None):
    """Build every table into its giver's built-ins where no live member
    names it, and return the members made.

    Idempotent: a table already given is left alone, so this can run over
    a database that has some of it. Archived tables are skipped — an
    archived table is one taken out on purpose. ``campaign_type``
    narrows to the tables of one type's asset types, for the seed.

    Members are written directly rather than through the authoring verb,
    because the classes handed in may be historical ones; the caller
    files whatever propagation the sets that changed are owed.
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
    # One instance per giver for the whole pass, so the first table to
    # found a type's set is the only one that does.
    givers = {}
    for table in tables.order_by("name"):
        giver = giver_of(table, apps)
        if giver is None:
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
