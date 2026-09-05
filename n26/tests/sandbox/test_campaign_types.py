"""Campaign types and assets — the library kinds a campaign is founded on.

A campaign type declares the asset types a campaign of it deals in,
lists under each asset type the assets of it, and — being assignable, as
a gang type is — carries built-ins that every member gang gets. An asset
is one entry in that list: it belongs to one asset type, and so to one
campaign type, and is authored on the campaign type's page under its
asset type; its income is a figure on the card and its boons ride it as
modifiers. The Territory campaign type ships with Settlement as a
possession, Territory as a holding, and Reputation at 0 built in. See
design/campaign-assets.md.

The same note settles one rule about packs: content in a pack nobody
owns may never point at content in a pack somebody does. The library's
models do not check it; the authoring forms do, once, for every pick.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    create_asset,
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

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def dominion(default_pack):
    """A campaign type with the two asset types the core rules deal in."""
    campaign_type = create_campaign_type("Dominion")
    territory = add_asset_type(
        campaign_type, "Territory", "pooled", label_plural="Territories"
    )
    settlement = add_asset_type(campaign_type, "Settlement", "held-one-each")
    return {"type": campaign_type, "territory": territory, "settlement": settlement}


@pytest.fixture
def owned(db):
    """A pack somebody owns, with a campaign type, an asset type, an asset and a
    counter of its own — the content a system row must never point at."""
    arbitrator = User.objects.create_user("arbitrator")
    pack = create_pack("Sump Rats", owner=arbitrator)
    campaign_type = create_campaign_type("Sump Rats campaign", pack=pack)
    # No pack named: an asset type joins its type's pack on its own, and
    # an asset its asset type's.
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
    """The verbs build a type, its asset types and the assets under them, and
    refuse the mistakes an author can make in words."""

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
        """The asset type is the whole of how an asset belongs to a campaign
        type: the type's list of assets is read through its asset types,
        and there is no second list to add the asset to."""
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

    def test_a_possession_and_a_counter_can_be_built_in(self, dominion):
        settlement = create_asset("Settlement", dominion["settlement"])
        reputation = create_counter("Reputation")

        add_built_in(dominion["type"], reputation, amount=0)
        add_built_in(dominion["type"], settlement)

        members = list(dominion["type"].built_in_members)
        assert [member.assignable for member in members] == [reputation, settlement]
        assert members[0].amount == 0

    def test_a_gang_can_be_assigned_a_campaign_type_and_an_asset(
        self, dominion, gang_type, owner
    ):
        """The wiring every assignable needs: a column on the gang's
        assignments for each new kind, so joining a campaign and
        holding a Settlement can both be ordinary assignments."""
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
    """What every install ships with: the Territory campaign type, its two asset types,
    a Settlement, and Reputation at 0 — created once, whatever the
    database already holds."""

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
            (reputation, 0),
            (settlement, 0),
            (income, 0),
        ]
        assert core.built_ins.name == "Territory campaign built-ins"
        assert all(row.pack == default_pack for row in (core, settlement, reputation))
        # One line per row: two counters, the type, two asset types, the
        # asset, the set, and three members.
        assert len(lines) == 10

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
        """Names are unique per pack without regard to case, so a counter
        already there as "reputation" is the one the type builds in —
        creating another would be refused by the database."""
        existing = create_counter("reputation")

        list(seed_core_campaign(apps))

        assert Counter.objects.filter(name__iexact="reputation").count() == 1
        core = CampaignType.objects.get(name="Territory campaign")
        assert core.built_in_members.filter(counter=existing).exists()

    def test_it_gives_the_type_its_words_for_arbitrators_and_authors(
        self, default_pack
    ):
        """The description is what the set-up screen's card draws; the
        author help is what the authoring pages draw. Both are ours, about
        the core rulebook's campaign, and never the book's own words."""
        list(seed_core_campaign(apps))

        core = CampaignType.objects.get(name="Territory campaign")
        assert core.description == DESCRIPTION
        assert core.library_author_help == LIBRARY_AUTHOR_HELP
        assert "fight for control of Territory" in core.description
        assert "Occupation, Downtime and Takeover" in core.description


class TestRenamingTheCoreType:
    """The type every install has was first created under a working name.
    Renaming it moves the standing row across, built-ins set and all, so a
    campaign founded on it keeps its type; a database that has already
    been through this is left as it stands."""

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
        """Only a blank text is filled in: an author who has already
        written the type's description keeps it across every run."""
        theirs = create_campaign_type("Territory campaign", description="Ours.")

        rename_core_campaign(apps)

        theirs.refresh_from_db()
        assert theirs.description == "Ours."
        assert theirs.library_author_help == LIBRARY_AUTHOR_HELP

    def test_the_built_ins_set_follows_a_type_already_renamed(self, default_pack):
        """A type renamed by hand keeps a set under the former name; the
        set is renamed on its own."""
        renamed = create_campaign_type("Territory campaign")
        renamed.built_ins = DefaultAssignmentSet.objects.create(name=FORMER_BUILT_INS)
        renamed.save()

        rename_core_campaign(apps)

        renamed.built_ins.refresh_from_db()
        assert renamed.built_ins.name == "Territory campaign built-ins"

    def test_nothing_is_renamed_while_both_names_stand(self, default_pack):
        """Two types cannot share the name, and which of the two is the
        real one is a question for a person rather than a migration."""
        create_campaign_type("Territory campaign")
        former = create_campaign_type(FORMER_NAME)

        rename_core_campaign(apps)

        former.refresh_from_db()
        assert former.name == FORMER_NAME

    def test_a_database_with_no_system_pack_is_left_alone(self, db):
        assert rename_core_campaign(apps) == []


class TestTheAuthoringPages:
    """A campaign type has pages in the existing style: a listing, a
    create page, and a page per row. The type's page lists its asset types
    and edits each in place, and under each asset type lists the assets of it
    and adds one more. An asset has no menu entry, listing or create page
    of its own: it is one entry in the type's list, made on the type's
    page, and keeps a page of its own for its modifiers."""

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
        assert "Territories · holding" in body
        assert "No Territories yet." in body
        assert f'name="add-asset-{territory.pk}-name"' in body
        assert f'name="add-asset-{territory.pk}-income"' in body
        assert "Add Territory" in body
        assert "Comes with" in body
        assert "Modifiers" in body
        assert f"/n26/authoring/asset-types/{territory.pk}/remove/" in body

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
        """The block an author types in settles the asset type, so a post
        naming an asset type of another campaign type is a mistyped
        address, not a choice."""
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
        """The assets under each asset type and their modifier counts are
        loaded with the asset types, so a type with a dozen assets draws for the same
        number of queries as one with a single asset."""
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
        # The first visit pays for caches the process keeps warm afterwards;
        # only the second and third are compared.
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
        # The trail runs through the type: Content library, Campaign
        # types, Dominion, Old Ruins — there is no asset listing to name.
        assert 'href="/n26/authoring/campaign-type/"' in page
        assert f'href="/n26/authoring/campaign-type/{dominion["type"].pk}/"' in page
        assert 'href="/n26/authoring/asset/"' not in page
        # The asset type was settled where the asset was made, so the edit form
        # does not offer it; the rest of the fields are here.
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


class TestSystemContentNeverReferencesOwnedContent:
    """A row in a pack nobody owns may not point at a row in a pack
    somebody does; the other way round is fine. Stated once, in the
    forms, and read by every pick they take."""

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
        """An asset's only reference is its asset type, and the type's page
        offers only the type's own asset types — so an asset added there can
        never point into a pack somebody owns, and lands in the type's."""
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
        """The asset type lands in the type's own pack, so a type in a pack
        somebody owns takes new asset types from the staff page."""
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
        """A built-in set is written into the default pack whatever its
        carrier, so a member there would be system content pointing at
        the owned type that carries it."""
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
        """Conditions are part of a modifier the composer writes into the
        default pack, so the rows they name are held to the same rule."""
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
