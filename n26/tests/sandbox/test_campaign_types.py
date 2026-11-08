"""Campaign types declare asset types and built-ins received by member gangs.

Each asset belongs to one asset type. Possession assets become built-ins;
Holding assets remain campaign holdings. The shipped Territory campaign
includes Settlement, Territory and the Reputation and Income counters.
Asset modifiers supply computed benefits. See design/campaign-assets.md.

Authoring forms reject references from unowned packs to owned packs.
The model layer does not enforce this cross-pack restriction.
"""

import re
from html import escape, unescape

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from n26.core.render import render_campaign
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    create_asset,
    create_asset_table,
    create_campaign_type,
    create_counter,
    create_pack,
    create_rule,
    ef_adds,
    modifier,
    remove_asset_type,
    targets_gang,
)
from n26.library.core_campaign import (
    DESCRIPTION,
    FORMER_BUILT_INS,
    FORMER_NAME,
    LIBRARY_AUTHOR_HELP,
    rename_core_campaign,
    seed_core_campaign,
)
from n26.library.forms import cross_pack_refusal
from n26.library.models import (
    Asset,
    AssetType,
    CampaignType,
    Counter,
    DefaultAssignment,
    DefaultAssignmentSet,
)
from n26.tests.sandbox.actions import (
    add_asset,
    create_campaign_asset,
    create_campaign_table,
    found_campaign,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def dominion(default_pack):
    """Create a campaign type with Holding territories and Possession settlements."""
    campaign_type = create_campaign_type("Dominion")
    territory = add_asset_type(
        campaign_type, "Territory", "pooled", label_plural="Territories"
    )
    settlement = add_asset_type(campaign_type, "Settlement", "held-one-each")
    return {"type": campaign_type, "territory": territory, "settlement": settlement}


@pytest.fixture
def owned(db):
    """Create owned campaign content used to test cross-pack reference restrictions."""
    arbitrator = User.objects.create_user("arbitrator")
    pack = create_pack("Sump Rats", owner=arbitrator)
    campaign_type = create_campaign_type("Sump Rats campaign", pack=pack)
    # Asset types inherit the campaign type's pack; assets inherit their asset type's pack.
    kind = add_asset_type(campaign_type, "Rat hole", "pooled")
    asset = create_asset("The Big Hole", kind)
    counter = create_counter("Meat", pack=pack)
    return {
        "pack": pack,
        "type": campaign_type,
        "kind": kind,
        "asset": asset,
        "counter": counter,
    }


class TestAuthoringACampaignType:
    """Create campaign types, asset types and assets through authoring verbs with readable validation errors."""

    def test_a_campaign_type_declares_its_asset_types_in_order(self, dominion):
        kinds = list(dominion["type"].asset_types.all())
        assert [kind.label_singular for kind in kinds] == ["Territory", "Settlement"]
        assert [kind.position for kind in kinds] == [0, 1]
        assert dominion["territory"].plural == "Territories"
        assert dominion["settlement"].plural == "Settlements"
        assert dominion["territory"].is_holding
        assert not dominion["settlement"].is_holding

    def test_an_asset_type_joins_its_campaign_types_pack(self, dominion, owned):
        assert owned["kind"].pack == owned["pack"]
        assert dominion["territory"].pack == dominion["type"].pack

    def test_an_asset_joins_its_asset_types_pack(self, dominion, owned):
        assert owned["asset"].pack == owned["pack"]
        ruins = create_asset("Old Ruins", dominion["territory"])
        assert ruins.pack == dominion["type"].pack

    def test_an_asset_needs_a_name(self, dominion):
        with pytest.raises(ValidationError, match="An asset needs a name"):
            create_asset("  ", dominion["territory"])

    def test_two_asset_types_of_one_campaign_type_cannot_share_a_label(self, dominion):
        with pytest.raises(ValidationError, match="already has an asset type"):
            add_asset_type(dominion["type"], "territory", "pooled")

    def test_an_asset_is_of_one_asset_type_and_so_in_its_campaign_types_list(
        self, dominion
    ):
        """Derive campaign-type membership through the asset type without a second membership list."""
        ruins = create_asset("Old Ruins", dominion["territory"], income=10)
        settlement = create_asset("Settlement", dominion["settlement"])

        assert ruins.campaign_type == dominion["type"]
        assert list(dominion["type"].assets) == [ruins, settlement]
        assert list(dominion["type"].holding_assets()) == [ruins]

    def test_another_types_assets_are_not_in_the_list(self, dominion):
        other = create_campaign_type("Law & Misrule")
        create_asset("Turf", add_asset_type(other, "Turf", "pooled"))

        assert not dominion["type"].assets.exists()

    def test_an_asset_type_with_assets_of_it_cannot_be_removed(self, dominion):
        ruins = create_asset("Old Ruins", dominion["territory"])

        with pytest.raises(
            ValidationError, match="1 asset is of the asset type Territory"
        ):
            remove_asset_type(dominion["territory"])
        assert AssetType.objects.filter(pk=dominion["territory"].pk).exists()

        ruins.delete()
        remove_asset_type(dominion["territory"])
        assert not AssetType.objects.filter(pk=dominion["territory"].pk).exists()

    def test_a_possession_is_built_in_as_it_is_created_and_a_counter_by_hand(
        self, dominion, default_pack
    ):
        settlement = create_asset("Settlement", dominion["settlement"])
        reputation = create_counter("Reputation")
        add_built_in(dominion["type"], reputation, amount=0)

        members = list(dominion["type"].built_in_members)
        assert [member.assignable for member in members] == [settlement, reputation]
        assert members[0].pack == default_pack
        assert members[1].amount == 0
        assert dominion["type"].built_ins.name == "Dominion built-ins"

    def test_a_holding_is_never_built_in(self, dominion):
        create_asset("Old Ruins", dominion["territory"])
        assert dominion["type"].built_ins is None

    def test_every_possession_asset_type_gives_its_assets(self, dominion):
        """Build in assets from every Possession asset type, regardless of its label."""
        hideout = add_asset_type(dominion["type"], "Hideout", "held-one-each")
        settlement = create_asset("Settlement", dominion["settlement"])
        bolthole = create_asset("Bolthole", hideout)

        members = list(dominion["type"].built_in_members)
        assert [member.assignable for member in members] == [settlement, bolthole]

    def test_deleting_or_archiving_a_possession_takes_it_out(self, dominion):
        from n26.library.authoring import delete_content

        hideout = add_asset_type(dominion["type"], "Hideout", "held-one-each")
        settlement = create_asset("Settlement", dominion["settlement"])
        bolthole = create_asset("Bolthole", hideout)

        delete_content(bolthole)
        assert not Asset.objects.filter(pk=bolthole.pk).exists()
        assert [m.assignable for m in dominion["type"].built_in_members] == [settlement]

        settlement.archive()
        # Delete an unused built-in member when its asset is archived; retain the set.
        assert list(dominion["type"].built_in_members) == []
        assert not DefaultAssignment.objects.filter(asset=settlement).exists()
        assert dominion["type"].built_ins is not None

    def test_unarchiving_a_possession_gives_it_again(self, dominion):
        """Recreate the unused built-in member deleted by archiving the possession asset."""
        settlement = create_asset("Settlement", dominion["settlement"])
        settlement.archive()
        assert list(dominion["type"].built_in_members) == []

        settlement.unarchive()

        assert [m.assignable for m in dominion["type"].built_in_members] == [settlement]
        assert DefaultAssignment.objects.filter(asset=settlement).count() == 1

    def test_unarchiving_a_holding_gives_nothing(self, dominion):
        """Unarchiving a Holding asset must not create a built-in member."""
        from n26.library.authoring import add_asset_type

        cache = add_asset_type(dominion["type"], "Cache", "pooled")
        loot = create_asset("Loot", cache)
        loot.archive()
        loot.unarchive()

        assert not DefaultAssignment.objects.filter(asset=loot).exists()

    def test_a_possession_is_given_by_a_type_in_its_own_pack(self, dominion, owned):
        """Build a campaign-specific possession into its own giver rather than the shared campaign type."""
        with pytest.raises(ValueError, match="own pack"):
            create_asset("Sump Home", dominion["settlement"], pack=owned["pack"])
        assert not Asset.objects.filter(name="Sump Home").exists()

        home = create_asset(
            "Sump Home",
            dominion["settlement"],
            pack=owned["pack"],
            given_by=owned["type"],
        )
        assert [m.assignable for m in owned["type"].built_in_members] == [home]
        assert owned["type"].built_ins.pack == owned["pack"]
        assert dominion["type"].built_ins is None

    def test_the_rule_can_be_run_over_what_already_stands(
        self, dominion, owned, default_pack
    ):
        """Repair missing possession members idempotently, using campaign additions for campaign-owned assets."""
        from n26.core.models import Campaign
        from n26.library.possessions import build_in_missing
        from n26.tests.sandbox.actions import found_campaign

        settlement = Asset.objects.create(
            pack=default_pack, name="Settlement", asset_type=dominion["settlement"]
        )
        given = create_asset(
            "Bolthole", add_asset_type(dominion["type"], "Hideout", "held-one-each")
        )
        stray = Asset.objects.create(
            pack=owned["pack"], name="Stray", asset_type=dominion["settlement"]
        )
        campaign = found_campaign(
            "Dust Falls", dominion["type"], owner=User.objects.create_user("arb")
        )
        theirs = Asset.objects.create(
            pack=campaign.pack, name="Sump Home", asset_type=dominion["settlement"]
        )

        made = build_in_missing(apps)

        assert sorted(member.asset.name for member in made) == [
            "Settlement",
            "Sump Home",
        ]
        assert [m.assignable for m in dominion["type"].built_in_members] == [
            given,
            settlement,
        ]
        # Refresh the caller's instance after the repair created its built-in set.
        campaign.additions.refresh_from_db()
        assert [m.assignable for m in campaign.additions.built_in_members] == [theirs]
        # An owned pack without a campaign has no additions type to receive this possession.
        assert not DefaultAssignment.objects.filter(asset=stray).exists()
        assert Campaign.objects.count() == 1
        assert build_in_missing(apps) == []

    def test_the_pass_founds_one_set_for_a_type_with_several_possessions(
        self, dominion, default_pack
    ):
        """Create one shared built-in set when repairing several possessions belonging to the same campaign type."""
        from n26.library.possessions import build_in_missing

        hideout = add_asset_type(dominion["type"], "Hideout", "held-one-each")
        first = Asset.objects.create(
            pack=default_pack, name="Settlement", asset_type=dominion["settlement"]
        )
        second = Asset.objects.create(
            pack=default_pack, name="Bolthole", asset_type=hideout
        )

        made = build_in_missing(apps)

        dominion["type"].refresh_from_db()
        assert {member.default_set_id for member in made} == {
            dominion["type"].built_ins_id
        }
        assert DefaultAssignmentSet.objects.count() == 1
        assert [m.assignable for m in dominion["type"].built_in_members] == [
            second,
            first,
        ]
        assert build_in_missing(apps) == []

    def test_archiving_through_the_admin_takes_a_possession_out(
        self, dominion, default_pack
    ):
        """Apply possession membership updates when the admin saves an archived asset."""
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from n26.library.admin import AssetAdmin

        settlement = create_asset("Settlement", dominion["settlement"])
        assert dominion["type"].built_in_members.count() == 1

        settlement.archived = True
        AssetAdmin(Asset, AdminSite()).save_model(
            RequestFactory().post("/"), settlement, form=None, change=True
        )

        settlement.refresh_from_db()
        assert settlement.archived
        assert list(dominion["type"].built_in_members) == []

    def test_unarchiving_through_the_admin_gives_a_possession_back(
        self, dominion, default_pack
    ):
        """Restore the possession member when the admin clears the asset's archived flag."""
        from types import SimpleNamespace

        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from n26.library.admin import AssetAdmin

        settlement = create_asset("Settlement", dominion["settlement"])
        settlement.archive()
        assert list(dominion["type"].built_in_members) == []

        settlement.archived = False
        AssetAdmin(Asset, AdminSite()).save_model(
            RequestFactory().post("/"),
            settlement,
            form=SimpleNamespace(changed_data=["archived"]),
            change=True,
        )

        settlement.refresh_from_db()
        assert not settlement.archived
        assert [m.assignable for m in dominion["type"].built_in_members] == [settlement]

    def test_a_gang_can_be_assigned_a_campaign_type_and_an_asset(
        self, dominion, gang_type, owner
    ):
        """Wire campaign types and possession assets into the assignment model."""
        from n26.core.models import Assignment, Gang

        gang = Gang.objects.create(
            name="The Sump Dogs", gang_type=gang_type, owner=owner
        )
        settlement = create_asset("Settlement", dominion["settlement"])

        joined = Assignment.objects.create(gang=gang, campaign_type=dominion["type"])
        held = Assignment.objects.create(gang=gang, asset=settlement, caused_by=joined)

        assert joined.assignable == dominion["type"]
        assert held.assignable == settlement
        assert list(dominion["type"].assignments.all()) == [joined]


class TestTheCoreCampaignType:
    """Seed the Territory campaign and its assets and counters idempotently."""

    def test_it_creates_the_type_its_asset_types_the_settlement_and_reputation(
        self, default_pack
    ):
        lines = list(seed_core_campaign(apps))

        core = CampaignType.objects.get(name="Territory campaign")
        assert [
            (t.label_singular, t.plural, t.ownership) for t in core.asset_types.all()
        ] == [
            ("Settlement", "Settlements", "held-one-each"),
            ("Territory", "Territories", "pooled"),
        ]
        settlement = Asset.objects.get(name="Settlement")
        assert settlement.asset_type.label_singular == "Settlement"
        assert list(core.assets) == [settlement]

        reputation = Counter.objects.get(name="Reputation")
        income = Counter.objects.get(name="Income")
        members = list(core.built_in_members)
        assert [(member.assignable, member.amount) for member in members] == [
            (reputation, 1),
            (settlement, 0),
            (income, 0),
        ]
        assert core.built_ins.name == "Territory campaign built-ins"
        assert all(row.pack == default_pack for row in (core, settlement, reputation))
        assert len(lines) == 13

    def test_running_it_again_creates_nothing(self, default_pack):
        list(seed_core_campaign(apps))
        before = (
            CampaignType.objects.count(),
            AssetType.objects.count(),
            Asset.objects.count(),
            Counter.objects.count(),
            DefaultAssignmentSet.objects.count(),
            DefaultAssignment.objects.count(),
        )

        assert list(seed_core_campaign(apps)) == []
        assert (
            CampaignType.objects.count(),
            AssetType.objects.count(),
            Asset.objects.count(),
            Counter.objects.count(),
            DefaultAssignmentSet.objects.count(),
            DefaultAssignment.objects.count(),
        ) == before

    def test_it_takes_an_existing_reputation_counter_whatever_its_case(
        self, default_pack
    ):
        """Reuse an existing Reputation counter because names are unique per pack without regard to case."""
        existing = create_counter("reputation")

        list(seed_core_campaign(apps))

        assert Counter.objects.filter(name__iexact="reputation").count() == 1
        core = CampaignType.objects.get(name="Territory campaign")
        assert core.built_in_members.filter(counter=existing).exists()

    def test_it_gives_the_type_its_words_for_arbitrators_and_authors(
        self, default_pack
    ):
        """Populate the campaign description and author help from their shared definitions."""
        list(seed_core_campaign(apps))

        core = CampaignType.objects.get(name="Territory campaign")
        assert core.description == DESCRIPTION
        assert core.library_author_help == LIBRARY_AUTHOR_HELP
        assert "fight for control of Territory" in core.description
        assert "Occupation, Downtime and Takeover" in core.description


class TestRenamingTheCoreType:
    """Rename the former core campaign type and built-in set without replacing their rows.

    Preserve existing author descriptions and leave an already migrated database unchanged.
    """

    def test_a_type_under_the_former_name_is_renamed_with_its_built_ins(
        self, default_pack
    ):
        former = create_campaign_type(FORMER_NAME)
        former.built_ins = DefaultAssignmentSet.objects.create(name=FORMER_BUILT_INS)
        former.save()

        lines = rename_core_campaign(apps)

        former.refresh_from_db()
        assert former.name == "Territory campaign"
        assert former.built_ins.name == "Territory campaign built-ins"
        assert former.description == DESCRIPTION
        assert former.library_author_help == LIBRARY_AUTHOR_HELP
        assert len(lines) == 3
        assert rename_core_campaign(apps) == []

    def test_a_type_already_renamed_keeps_an_authors_own_words(self, default_pack):
        """Fill blank text fields without overwriting the author's existing description."""
        theirs = create_campaign_type("Territory campaign", description="Ours.")

        rename_core_campaign(apps)

        theirs.refresh_from_db()
        assert theirs.description == "Ours."
        assert theirs.library_author_help == LIBRARY_AUTHOR_HELP

    def test_the_built_ins_set_follows_a_type_already_renamed(self, default_pack):
        """Rename a built-in set still using the former name even if its campaign type was already renamed."""
        renamed = create_campaign_type("Territory campaign")
        renamed.built_ins = DefaultAssignmentSet.objects.create(name=FORMER_BUILT_INS)
        renamed.save()

        rename_core_campaign(apps)

        renamed.built_ins.refresh_from_db()
        assert renamed.built_ins.name == "Territory campaign built-ins"

    def test_nothing_is_renamed_while_both_names_stand(self, default_pack):
        """Leave both rows unchanged when the target name already belongs to another campaign type."""
        create_campaign_type("Territory campaign")
        former = create_campaign_type(FORMER_NAME)

        rename_core_campaign(apps)

        former.refresh_from_db()
        assert former.name == FORMER_NAME

    def test_a_database_with_no_system_pack_is_left_alone(self, db):
        assert rename_core_campaign(apps) == []


class TestTheAuthoringPages:
    """Manage asset types and their assets from the campaign-type page.

    Assets have individual modifier pages but no independent listing or create page.
    """

    def test_the_menu_offers_campaign_types_and_not_assets(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/").content.decode()
        assert 'href="/n26/authoring/campaign-type/"' in body
        assert 'href="/n26/authoring/asset/"' not in body
        assert client.get("/n26/authoring/asset/").status_code == 404
        assert client.get("/n26/authoring/asset/new/").status_code == 404

    def test_creating_a_campaign_type_through_its_page(
        self, author, client, default_pack
    ):
        response = client.post(
            "/n26/authoring/campaign-type/new/", {"name": "Law & Misrule"}
        )

        made = CampaignType.objects.get(name="Law & Misrule")
        assert response.status_code == 302
        assert response.url == f"/n26/authoring/campaign-type/{made.pk}/"
        assert made.pack == default_pack

    def test_the_type_page_lists_its_asset_types_with_their_forms_and_offers_built_ins(
        self, author, client, dominion
    ):
        body = client.get(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        ).content.decode()

        territory = dominion["territory"]
        assert f'name="part-{territory.pk}-label_singular"' in body
        assert 'value="Territory"' in body
        assert "Territories · transferable" in body
        assert "No Territories yet." in body
        assert f'name="add-asset-{territory.pk}-name"' in body
        assert f'name="add-asset-{territory.pk}-income"' in body
        assert "Add Territory" in body
        assert "Every gang that joins gets" in body
        assert "Comes with" not in body
        assert "Modifiers" in body
        assert f"/n26/authoring/asset-types/{territory.pk}/remove/" in body

    def test_the_type_page_says_what_every_gang_gets_and_offers_no_asset(
        self, author, client, dominion
    ):
        """List campaign built-ins with a picker excluding assets, whose possession membership is managed automatically."""
        settlement = create_asset("Settlement", dominion["settlement"])
        add_built_in(dominion["type"], create_counter("Reputation"), amount=0)
        page = f"/n26/authoring/campaign-type/{dominion['type'].pk}/"

        body = client.get(page).content.decode()

        assert "Every gang that joins gets" in body
        assert "Given to every gang when it joins a campaign of this type." in body
        assert "Add something every gang gets" in body
        assert "Add a built-in" not in body
        assert "from the Settlement asset type · delete the asset to remove it" in body
        assert "counter · opening value 0" not in body
        assert "counter" in body
        (given,) = dominion["type"].built_in_members.filter(asset=settlement)
        (counted,) = dominion["type"].built_in_members.filter(counter__isnull=False)
        assert f"/n26/authoring/built-ins/{counted.pk}/remove/" in body
        assert f"/n26/authoring/built-ins/{given.pk}/remove/" not in body
        assert 'value="asset"' not in body
        assert 'value="counter"' in body

    def test_the_type_page_offers_counter_rule_and_slot_and_opens_on_counter(
        self, author, client, dominion
    ):
        """Offer gang-compatible counter, rule and slot built-ins and reject an unsupported kind submitted directly."""

        from n26.library.authoring import create_weapon

        page = f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        body = client.get(page).content.decode()

        assert re.search(r'value="counter"\s+selected', body)
        # The Kind select's own options come first after its id; the
        # per-kind pickers follow.
        options = re.findall(
            r'<option\s+value="(\w+)"', body.split("id_thing_kind")[-1]
        )
        assert options[:3] == ["counter", "rule", "slot"]
        for kind in ("weapon", "wargear", "skill", "collection", "hidden", "subtype"):
            assert f'value="{kind}"' not in body
            assert f'name="thing_{kind}"' not in body

        weapon = create_weapon("Stub gun")
        response = client.post(
            page,
            {
                "act": "built_in",
                "thing_kind": "weapon",
                "thing_weapon": str(weapon.pk),
                "amount": "0",
            },
        )
        assert response.status_code == 200
        assert dominion["type"].built_ins is None

    def test_creating_a_possession_on_the_type_page_lists_it_among_what_every_gang_gets(
        self, author, client, dominion
    ):
        settlement = dominion["settlement"]
        page = f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        response = client.post(
            page,
            {
                "act": "add-asset",
                "part": str(settlement.pk),
                f"add-asset-{settlement.pk}-name": "Settlement",
            },
        )
        assert response.status_code == 302

        made = Asset.objects.get(name="Settlement")
        # Refresh the caller's instance after the page created its built-in set.
        dominion["type"].refresh_from_db()
        assert [m.assignable for m in dominion["type"].built_in_members] == [made]
        body = client.get(page).content.decode()
        assert "from the Settlement asset type" in body

    def test_an_asset_member_cannot_be_taken_off_at_its_address(
        self, author, client, dominion
    ):
        settlement = create_asset("Settlement", dominion["settlement"])
        (member,) = dominion["type"].built_in_members.all()
        remove = f"/n26/authoring/built-ins/{member.pk}/remove/"
        page = f"/n26/authoring/campaign-type/{dominion['type'].pk}/"

        asked = client.get(remove)
        assert asked.status_code == 302
        assert asked.url == page
        refused = client.post(remove, follow=True)
        assert "Delete the asset to remove it." in refused.content.decode()
        assert list(dominion["type"].built_in_members) == [member]
        assert not member.archived
        assert Asset.objects.filter(pk=settlement.pk).exists()

    def test_deleting_a_possession_on_its_page_takes_it_out_of_what_every_gang_gets(
        self, author, client, dominion
    ):
        settlement = create_asset("Settlement", dominion["settlement"])

        response = client.post(f"/n26/authoring/asset/{settlement.pk}/delete/")

        assert response.status_code == 302
        assert not Asset.objects.filter(pk=settlement.pk).exists()
        assert list(dominion["type"].built_in_members) == []

    def test_the_type_page_adds_an_asset_type(self, author, client, dominion):
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "label_singular": "Racket",
                "label_plural": "Rackets",
                "ownership": "pooled",
            },
        )

        racket = dominion["type"].asset_types.get(label_singular="Racket")
        assert response.status_code == 302
        assert racket.position == 2
        assert racket.plural == "Rackets"

    def test_the_type_page_edits_an_asset_type_in_place(self, author, client, dominion):
        territory = dominion["territory"]
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "edit-part",
                "part": str(territory.pk),
                f"part-{territory.pk}-label_singular": "Turf",
                f"part-{territory.pk}-label_plural": "Turfs",
                f"part-{territory.pk}-ownership": "held-one-each",
                f"part-{territory.pk}-position": "5",
            },
        )

        territory.refresh_from_db()
        assert response.status_code == 302
        assert (
            territory.label_singular,
            territory.label_plural,
            territory.ownership,
            territory.position,
        ) == ("Turf", "Turfs", "held-one-each", 5)

    def test_renaming_an_asset_type_onto_its_siblings_label_is_refused_in_words(
        self, author, client, dominion
    ):
        territory = dominion["territory"]
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "edit-part",
                "part": str(territory.pk),
                f"part-{territory.pk}-label_singular": "settlement",
                f"part-{territory.pk}-ownership": "pooled",
            },
        )

        territory.refresh_from_db()
        assert response.status_code == 200
        assert "already has an asset type called" in response.content.decode()
        assert territory.label_singular == "Territory"

    def test_removing_an_asset_type_is_a_page_that_names_what_stands_in_the_way(
        self, author, client, dominion
    ):
        territory = dominion["territory"]
        ruins = create_asset("Old Ruins", territory)
        remove = f"/n26/authoring/asset-types/{territory.pk}/remove/"

        body = client.get(remove).content.decode()
        assert "Old Ruins" in body
        assert "You cannot remove it" in body

        refused = client.post(remove, follow=True)
        assert AssetType.objects.filter(pk=territory.pk).exists()
        assert "1 asset is of the asset type Territory" in refused.content.decode()

        ruins.delete()
        done = client.post(remove)
        assert done.status_code == 302
        assert done.url == f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        assert not AssetType.objects.filter(pk=territory.pk).exists()

    def test_the_type_page_adds_an_asset_under_an_asset_type(
        self, author, client, dominion, default_pack
    ):
        territory = dominion["territory"]
        page = f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        response = client.post(
            page,
            {
                "act": "add-asset",
                "part": str(territory.pk),
                f"add-asset-{territory.pk}-name": "Old Ruins",
                f"add-asset-{territory.pk}-income": "10",
            },
        )

        ruins = Asset.objects.get(name="Old Ruins")
        assert response.status_code == 302
        assert response.url == page
        assert ruins.asset_type == territory
        assert ruins.income == 10
        assert ruins.pack == default_pack

        body = client.get(page, follow=True).content.decode()
        assert "Added Old Ruins under Territory." in body
        assert f'href="/n26/authoring/asset/{ruins.pk}/"' in body
        assert "income 10cr · no other modifiers" in body

    def test_an_asset_is_added_under_an_asset_type_of_this_campaign_type_only(
        self, author, client, dominion, owned
    ):
        """Return 404 when the submitted asset-type key belongs to another campaign type."""
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "add-asset",
                "part": str(owned["kind"].pk),
                f"add-asset-{owned['kind'].pk}-name": "Stray",
            },
        )

        assert response.status_code == 404
        assert not Asset.objects.filter(name="Stray").exists()

    def test_adding_a_second_asset_of_one_name_is_refused_in_words(
        self, author, client, dominion
    ):
        territory = dominion["territory"]
        create_asset("Old Ruins", territory)
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "add-asset",
                "part": str(territory.pk),
                f"add-asset-{territory.pk}-name": "old ruins",
            },
        )

        assert response.status_code == 200
        assert "An asset named “old ruins” already exists" in response.content.decode()
        assert Asset.objects.filter(name__iexact="old ruins").count() == 1

    def test_the_type_page_costs_the_same_however_many_assets_it_lists(
        self, author, client, dominion
    ):
        """Prefetch assets and modifier counts so adding assets adds no page queries."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        page = f"/n26/authoring/campaign-type/{dominion['type'].pk}/"

        def asset_with_a_boon(name):
            asset = create_asset(name, dominion["territory"])
            modifier(
                f"{name} rule",
                targets_gang(),
                ef_adds(create_rule(f"{name} rule")),
                attach_to=asset,
            )

        asset_with_a_boon("Old Ruins")
        # Warm process caches before comparing query counts.
        client.get(page)
        with CaptureQueriesContext(connection) as one:
            client.get(page)

        for name in ("Collapsed Dome", "Sludge Sea", "Wastes", "Rogue Doc"):
            asset_with_a_boon(name)
        with CaptureQueriesContext(connection) as many:
            client.get(page)

        assert len(many) == len(one)

    def test_an_assets_own_page_is_reached_from_the_type_and_fixes_its_asset_type(
        self, author, client, dominion
    ):
        ruins = create_asset("Old Ruins", dominion["territory"], income=10)

        page = client.get(f"/n26/authoring/asset/{ruins.pk}/").content.decode()
        # Link the breadcrumb through the campaign type because assets have no listing page.
        assert 'href="/n26/authoring/campaign-type/"' in page
        assert f'href="/n26/authoring/campaign-type/{dominion["type"].pk}/"' in page
        assert 'href="/n26/authoring/asset/"' not in page
        # Keep the asset type fixed after creation while allowing the remaining fields to change.
        assert 'name="edit-name"' in page
        assert 'name="edit-income"' in page
        assert 'name="edit-asset_type"' not in page
        assert "Modifiers" in page

        response = client.post(
            f"/n26/authoring/asset/{ruins.pk}/",
            {"act": "edit", "edit-name": "Older Ruins", "edit-income": "20"},
        )
        ruins.refresh_from_db()
        assert response.status_code == 302
        assert (ruins.name, ruins.income, ruins.asset_type) == (
            "Older Ruins",
            20,
            dominion["territory"],
        )

    def test_deleting_an_asset_returns_to_its_types_page(
        self, author, client, dominion
    ):
        ruins = create_asset("Old Ruins", dominion["territory"])

        response = client.post(f"/n26/authoring/asset/{ruins.pk}/delete/")

        assert response.status_code == 302
        assert response.url == f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        assert not Asset.objects.filter(pk=ruins.pk).exists()

    def test_the_type_listing_says_asset_types_and_counts_assets(
        self, author, client, dominion
    ):
        create_asset("Old Ruins", dominion["territory"])

        body = client.get("/n26/authoring/campaign-type/").content.decode()
        assert "Territories, Settlements" in body
        assert "1 asset" in body

    def test_a_campaigns_own_assets_stay_off_the_type_pages(
        self, author, client, dominion
    ):
        """Exclude campaign-owned assets and tables from shared library pages while retaining them in the campaign."""
        create_asset("Old Ruins", dominion["territory"])
        create_asset_table("Core Territories", dominion["territory"], dice="d6")
        arbitrator = User.objects.create_user("arbitrator")
        campaign = found_campaign("Dust Falls", dominion["type"], owner=arbitrator)
        hole = create_campaign_asset(campaign, dominion["territory"], "Sump Hole")
        home = create_campaign_asset(campaign, dominion["settlement"], "Sump Home")
        table = create_campaign_table(
            campaign, dominion["territory"], "House table", dice="d6"
        )

        body = client.get(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        ).content.decode()
        assert "Old Ruins" in body
        assert "Core Territories" in body
        assert "Sump Hole" not in body
        assert "Sump Home" not in body
        assert "House table" not in body

        listing = client.get("/n26/authoring/campaign-type/").content.decode()
        assert "1 asset" in listing
        assert "Sump Hole" not in listing
        assert "Sump Home" not in listing

        assert hole.pack == campaign.pack
        assert home.pack == campaign.pack
        assert table.pack == campaign.pack
        given = {member.assignable for member in campaign.additions.built_in_members}
        assert home in given
        assert table in given
        add_asset(campaign, hole)
        names = [
            entry.name
            for block in render_campaign(campaign).assets
            for entry in block.entries
        ]
        assert "Sump Hole" in names


def as_a_browser_would_post(body):
    """Extract edit-form values, including textarea content, as a browser would submit them.

    Discard the initial textarea newline, which HTML parsing ignores. This helper
    does not normalise remaining lone newlines to CRLF as browser submission does.
    """
    form = body[body.index('name="act" value="edit"') :]
    form = form[: form.index("</form>")]
    posting = {"act": "edit"}
    for name, value in re.findall(
        r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', form
    ):
        posting.setdefault(name, unescape(value))
    for name, held in re.findall(
        r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', form, re.S
    ):
        posting[name] = unescape(held[1:] if held.startswith("\n") else held)
    return posting


class TestTheDescriptionSurvivesBeingSaved:
    """Render textarea values without adding whitespace that would accumulate across saves."""

    @pytest.fixture
    def described(self, default_pack):
        return create_campaign_type(
            "Dominion",
            description="Gangs fight for turf.\n\nEach turf gives a boon.",
        )

    def test_the_box_holds_the_description_flush_against_its_tags(
        self, author, client, described
    ):
        body = client.get(
            f"/n26/authoring/campaign-type/{described.pk}/"
        ).content.decode()

        assert f">{escape(described.description)}</textarea>" in body

    def test_saving_twice_without_touching_it_stores_the_same_words(
        self, author, client, described
    ):
        page = f"/n26/authoring/campaign-type/{described.pk}/"
        words = described.description

        for _ in range(2):
            posting = as_a_browser_would_post(client.get(page).content.decode())
            assert posting["edit-description"] == words
            assert client.post(page, posting).status_code == 302
            described.refresh_from_db()
            assert described.description == words

    def test_a_description_stored_with_whitespace_round_it_is_trimmed(
        self, author, client, described
    ):
        padded = "    Gangs fight for turf.\n        "
        CampaignType.objects.filter(pk=described.pk).update(description=padded)
        page = f"/n26/authoring/campaign-type/{described.pk}/"

        posting = as_a_browser_would_post(client.get(page).content.decode())
        # Render only stored whitespace so saving trims the author's padding.
        assert posting["edit-description"] == padded
        client.post(page, posting)

        described.refresh_from_db()
        assert described.description == "Gangs fight for turf."


class TestSystemContentNeverReferencesOwnedContent:
    """Reject form references from unowned packs to owned packs; permit references in the opposite direction."""

    def test_the_rule_reads_off_owners_not_names(self, default_pack, owned):
        unowned = create_pack("Another book")
        system_rule = create_rule("Cult of Personality")
        other_rule = create_rule("Nerves of Steel", pack=unowned)

        assert cross_pack_refusal(default_pack, other_rule) is None
        assert cross_pack_refusal(owned["pack"], system_rule) is None
        assert cross_pack_refusal(owned["pack"], owned["asset"]) is None
        assert "has an owner" in cross_pack_refusal(default_pack, owned["asset"])

    def test_an_asset_added_on_a_system_type_is_system_content(
        self, author, client, dominion, default_pack
    ):
        """Create the asset in the campaign type's pack using one of that type's own asset types."""
        territory = dominion["territory"]
        client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "add-asset",
                "part": str(territory.pk),
                f"add-asset-{territory.pk}-name": "Old Ruins",
            },
        )

        ruins = Asset.objects.get(name="Old Ruins")
        assert ruins.pack == default_pack
        assert ruins.asset_type.pack == default_pack

    def test_an_asset_added_on_an_owned_type_joins_its_pack(
        self, author, client, owned
    ):
        kind = owned["kind"]
        response = client.post(
            f"/n26/authoring/campaign-type/{owned['type'].pk}/",
            {
                "act": "add-asset",
                "part": str(kind.pk),
                f"add-asset-{kind.pk}-name": "The Small Hole",
                f"add-asset-{kind.pk}-income": "5",
            },
        )

        made = Asset.objects.get(name="The Small Hole")
        assert response.status_code == 302
        assert made.asset_type == kind
        assert made.pack == owned["pack"]

    def test_attaching_an_owned_modifier_to_a_system_asset_is_refused(
        self, author, client, dominion, owned
    ):
        ruins = create_asset("Old Ruins", dominion["territory"])
        rule = create_rule("Rat pack", pack=owned["pack"])
        owned_modifier = modifier(
            "Rat pack rule", targets_gang(), ef_adds(rule), pack=owned["pack"]
        )

        response = client.post(
            f"/n26/authoring/asset/{ruins.pk}/",
            {"act": "attach", "modifier": str(owned_modifier.pk)},
            follow=True,
        )

        assert "which has an owner" in response.content.decode()
        assert not ruins.modifiers.exists()

    def test_an_owned_asset_may_carry_a_system_modifier(self, author, client, owned):
        system_modifier = modifier(
            "Salvage rule", targets_gang(), ef_adds(create_rule("Salvage"))
        )

        response = client.post(
            f"/n26/authoring/asset/{owned['asset'].pk}/",
            {"act": "attach", "modifier": str(system_modifier.pk)},
        )

        assert response.status_code == 302
        assert list(owned["asset"].modifiers.all()) == [system_modifier]

    def test_a_system_types_built_ins_refuse_an_owned_counter(
        self, author, client, dominion, owned
    ):
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "built_in",
                "thing_kind": "counter",
                "thing_counter": str(owned["counter"].pk),
                "amount": "0",
            },
        )

        assert response.status_code == 200
        assert "which has an owner" in response.content.decode()
        assert not dominion["type"].built_in_members.exists()

    def test_an_asset_type_added_to_an_owned_type_joins_its_pack(
        self, author, client, owned
    ):
        """Create an owned campaign type's asset types in the same pack through the staff page."""
        response = client.post(
            f"/n26/authoring/campaign-type/{owned['type'].pk}/",
            {"label_singular": "Sump", "ownership": "pooled"},
        )

        sump = owned["type"].asset_types.get(label_singular="Sump")
        assert response.status_code == 302
        assert sump.pack == owned["pack"]

    def test_a_built_in_on_an_owned_type_is_refused_because_the_set_is_system(
        self, author, client, owned
    ):
        """Reject a member whose default-pack built-in set would refer to its owned carrier."""
        reputation = create_counter("Reputation")
        response = client.post(
            f"/n26/authoring/campaign-type/{owned['type'].pk}/",
            {
                "act": "built_in",
                "thing_kind": "counter",
                "thing_counter": str(reputation.pk),
                "amount": "0",
            },
        )

        assert response.status_code == 200
        assert "which has an owner" in response.content.decode()
        assert not owned["type"].built_in_members.exists()

    def test_a_condition_on_a_system_modifier_refuses_an_owned_subtype(
        self, default_pack, owned
    ):
        """Reject an owned subtype referenced by a condition authored into the default pack."""
        from n26.library.authoring import create_subtype
        from n26.library.forms import condition_chip_form

        rat = create_subtype("Rat", pack=owned["pack"])
        chip = condition_chip_form(("has_subtypes",))(
            {"kind": "has_subtypes", "subtypes": [str(rat.pk)]}
        )

        assert not chip.is_valid()
        assert any("which has an owner" in error for error in chip.errors["subtypes"])

    def test_attaching_an_owned_modifier_to_system_content_is_refused(
        self, author, client, dominion, owned
    ):
        rule = create_rule("Rat pack", pack=owned["pack"])
        owned_modifier = modifier(
            "Rat pack rule", targets_gang(), ef_adds(rule), pack=owned["pack"]
        )

        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {"act": "attach", "modifier": str(owned_modifier.pk)},
            follow=True,
        )

        assert "which has an owner" in response.content.decode()
        assert not dominion["type"].modifiers.exists()
