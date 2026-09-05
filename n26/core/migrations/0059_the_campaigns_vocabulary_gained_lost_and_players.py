"""A campaign's asset is gained and lost; the people at its table are players.

Two new ledger kinds, GAINED and LOST, record a campaign's asset coming to a
gang or leaving it. Until now those events were written as GRANTED and
TOOK_AWAY, the kinds that also record an assignment arriving or an owner's
removal; a holding is neither, and reading the two apart by whether an
assignment stands behind the record is what this ends. Every holding event
already written — one about a campaign asset, or about no assignment at
all, since nothing else is ever written that way — is moved onto the new
kinds, so the reader needs only them.

Three campaign event kinds take the words a reader meets: an asset type
added, an asset removed, a player removed. Their stored values move with
them. The campaign asset's reverse names lose "pool" and "tokens", its
index is renamed, and the help text on it and on a player says what each
is in the words the pages use. No column changes shape.
"""

import django.db.models.deletion
from django.db import migrations, models

#: (old value, new value) for every stored value that moves.
LEDGER_KINDS = (("granted", "gained"), ("took_away", "lost"))
CAMPAIGN_KINDS = (
    ("kind_added", "asset_type_added"),
    ("asset_dropped", "asset_removed"),
    ("participant_removed", "player_removed"),
)


def _holding_events(LedgerEvent, kinds):
    """The records of a campaign's asset coming or going: about a campaign
    asset that still stands, or about no assignment and no model at all,
    which only such a record ever is."""
    return LedgerEvent.objects.filter(kind__in=kinds).filter(
        models.Q(campaign_asset__isnull=False)
        | models.Q(assignment__isnull=True, miniature__isnull=True)
    )


def forwards(apps, schema_editor):
    LedgerEvent = apps.get_model("n26", "LedgerEvent")
    CampaignEvent = apps.get_model("n26", "CampaignEvent")
    for old, new in LEDGER_KINDS:
        _holding_events(LedgerEvent, [old]).update(kind=new)
    for old, new in CAMPAIGN_KINDS:
        CampaignEvent.objects.filter(kind=old).update(kind=new)


def backwards(apps, schema_editor):
    LedgerEvent = apps.get_model("n26", "LedgerEvent")
    CampaignEvent = apps.get_model("n26", "CampaignEvent")
    for old, new in LEDGER_KINDS:
        LedgerEvent.objects.filter(kind=new).update(kind=old)
    for old, new in CAMPAIGN_KINDS:
        CampaignEvent.objects.filter(kind=new).update(kind=old)


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0084_asset_kind_becomes_asset_type_with_an_ownership"),
        ("n26", "0058_the_arbitrators_additions_are_campaign_events"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="campaignasset",
            options={
                "ordering": [
                    "asset__asset_type__position",
                    "asset__name",
                    "name",
                    "created",
                ],
                "verbose_name": "campaign asset",
                "verbose_name_plural": "campaign assets",
            },
        ),
        migrations.AlterModelOptions(
            name="campaignparticipant",
            options={
                "ordering": ["created"],
                "verbose_name": "player",
                "verbose_name_plural": "players",
            },
        ),
        migrations.RenameIndex(
            model_name="campaignasset",
            new_name="campaign_asset_holder_idx",
            old_name="campaign_asset_pool_idx",
        ),
        migrations.AlterField(
            model_name="campaignasset",
            name="asset",
            field=models.ForeignKey(
                help_text="Which asset in the library this is.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaign_assets",
                to="library.asset",
            ),
        ),
        migrations.AlterField(
            model_name="campaignasset",
            name="campaign",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="campaign_assets",
                to="n26.campaign",
            ),
        ),
        migrations.AlterField(
            model_name="campaignasset",
            name="holder",
            field=models.ForeignKey(
                blank=True,
                help_text="The gang holding this asset. Blank when nobody holds it.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="held",
                to="n26.campaignmembership",
            ),
        ),
        migrations.AlterField(
            model_name="campaignasset",
            name="name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="A name for this asset in this campaign. Leave blank to use the asset's own name.",
                max_length=200,
            ),
        ),
        migrations.AlterField(
            model_name="campaignevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("created", "Set up"),
                    ("renamed", "Renamed"),
                    ("budget_set", "Budget set"),
                    ("summary_edited", "Summary edited"),
                    ("archived", "Archived"),
                    ("battle_recorded", "Battle recorded"),
                    ("battle_removed", "Battle removed"),
                    ("invited", "Invited a player"),
                    ("invite_accepted", "Invitation accepted"),
                    ("invite_declined", "Invitation declined"),
                    ("player_removed", "Player removed"),
                    ("asset_added", "Asset added"),
                    ("asset_removed", "Asset removed"),
                    ("asset_type_added", "Asset type added"),
                    ("asset_created", "Asset created"),
                    ("counter_added", "Counter added"),
                    ("label_added", "Label added"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="campaignmembership",
            name="additions_carrier",
            field=models.OneToOneField(
                blank=True,
                help_text="The gang's assignment of the campaign's own campaign type. What the arbitrator adds to this campaign is caused by it.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="additions_carrier_of",
                to="n26.assignment",
            ),
        ),
        migrations.AlterField(
            model_name="ledgerevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("purchased", "Purchased"),
                    ("added", "Added"),
                    ("granted", "Granted"),
                    ("caught_up", "Caught up"),
                    ("moved", "Moved"),
                    ("tallied", "Tallied"),
                    ("amended", "Amended"),
                    ("repriced", "Repriced"),
                    ("removed", "Removed"),
                    ("refunded", "Refunded"),
                    ("sold", "Sold"),
                    ("took_away", "Took away"),
                    ("renamed", "Renamed"),
                    ("noted", "Notes edited"),
                    ("lore_edited", "Lore edited"),
                    ("image_set", "Picture set"),
                    ("image_cleared", "Picture removed"),
                    ("stat_set", "Characteristic set"),
                    ("stat_cleared", "Characteristic cleared"),
                    ("budget_set", "Budget set"),
                    ("trade_points_set", "Trade Points set"),
                    ("visited_post", "Visited the trading post"),
                    ("action_opened", "Action started"),
                    ("action_closed", "Action completed"),
                    ("joined_campaign", "Joined a campaign"),
                    ("left_campaign", "Left a campaign"),
                    ("rolled", "Rolled"),
                    ("gained", "Gained"),
                    ("lost", "Lost"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
