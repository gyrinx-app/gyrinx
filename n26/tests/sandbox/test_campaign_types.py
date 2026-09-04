"""Campaign types and assets — the library kinds a campaign is founded on.

A campaign type declares the kinds of asset a campaign of it deals in,
offers a catalogue of assets, and — being assignable, as a gang type is
— carries built-ins that every member gang gets. An asset is one thing
of one kind; its income is a figure on the card and its boons ride it
as modifiers. The N26 core type ships with Settlement held one each,
Territory pooled, and Reputation at 0 built in. See
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
    add_asset_kind,
    add_built_in,
    create_asset,
    create_campaign_type,
    create_counter,
    create_pack,
    create_rule,
    ef_adds,
    modifier,
    remove_asset_kind,
    set_assets,
    targets_gang,
)
from n26.library.core_campaign import seed_core_campaign
from n26.library.forms import cross_pack_refusal
from n26.library.models import (
    Asset,
    AssetKind,
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
    """A campaign type with the two kinds the core rules deal in."""
    campaign_type = create_campaign_type("Dominion")
    territory = add_asset_kind(
        campaign_type, "Territory", "pooled", label_plural="Territories"
    )
    settlement = add_asset_kind(campaign_type, "Settlement", "held-one-each")
    return {"type": campaign_type, "territory": territory, "settlement": settlement}


@pytest.fixture
def owned(db):
    """A pack somebody owns, with a campaign type, a kind, an asset and a
    counter of its own — the content a system row must never point at."""
    arbitrator = User.objects.create_user("arbitrator")
    pack = create_pack("Sump Rats", owner=arbitrator)
    campaign_type = create_campaign_type("Sump Rats campaign", pack=pack)
    # No pack named: a kind joins its type's pack on its own.
    kind = add_asset_kind(campaign_type, "Rat hole", "pooled")
    asset = create_asset("The Big Hole", kind, pack=pack)
    counter = create_counter("Meat", pack=pack)
    return {
        "pack": pack,
        "type": campaign_type,
        "kind": kind,
        "asset": asset,
        "counter": counter,
    }


class TestAuthoringACampaignType:
    """The verbs build a type, its kinds and its catalogue, and refuse
    the two mistakes an author can make in words."""

    def test_a_campaign_type_declares_its_asset_kinds_in_order(self, dominion):
        kinds = list(dominion["type"].asset_kinds.all())
        assert [kind.label_singular for kind in kinds] == ["Territory", "Settlement"]
        assert [kind.position for kind in kinds] == [0, 1]
        assert dominion["territory"].plural == "Territories"
        assert dominion["settlement"].plural == "Settlements"
        assert dominion["territory"].is_pooled
        assert not dominion["settlement"].is_pooled

    def test_an_asset_kind_joins_its_types_pack(self, dominion, owned):
        assert owned["kind"].pack == owned["pack"]
        assert dominion["territory"].pack == dominion["type"].pack

    def test_two_kinds_of_one_type_cannot_share_a_label(self, dominion):
        with pytest.raises(ValidationError, match="already has an asset kind"):
            add_asset_kind(dominion["type"], "territory", "pooled")

    def test_an_asset_is_of_one_kind_and_the_type_offers_it(self, dominion):
        ruins = create_asset("Old Ruins", dominion["territory"], income=10)
        set_assets(dominion["type"], [ruins])

        assert ruins.campaign_type == dominion["type"]
        assert list(dominion["type"].assets.all()) == [ruins]
        assert list(ruins.offered_by.all()) == [dominion["type"]]

    def test_a_kind_with_assets_of_it_cannot_be_removed(self, dominion):
        ruins = create_asset("Old Ruins", dominion["territory"])

        with pytest.raises(ValidationError, match="1 asset is of the kind Territory"):
            remove_asset_kind(dominion["territory"])
        assert AssetKind.objects.filter(pk=dominion["territory"].pk).exists()

        ruins.delete()
        remove_asset_kind(dominion["territory"])
        assert not AssetKind.objects.filter(pk=dominion["territory"].pk).exists()

    def test_a_held_one_each_asset_and_a_counter_can_be_built_in(self, dominion):
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
    """What every install ships with: the N26 core type, its two kinds,
    a Settlement, and Reputation at 0 — created once, whatever the
    database already holds."""

    def test_it_creates_the_type_its_kinds_the_settlement_and_reputation(
        self, default_pack
    ):
        lines = list(seed_core_campaign(apps))

        core = CampaignType.objects.get(name="N26 core")
        assert [
            (kind.label_singular, kind.plural, kind.mode)
            for kind in core.asset_kinds.all()
        ] == [
            ("Settlement", "Settlements", "held-one-each"),
            ("Territory", "Territories", "pooled"),
        ]
        settlement = Asset.objects.get(name="Settlement")
        assert settlement.kind.label_singular == "Settlement"
        assert list(core.assets.all()) == [settlement]

        reputation = Counter.objects.get(name="Reputation")
        members = list(core.built_in_members)
        assert [(member.assignable, member.amount) for member in members] == [
            (reputation, 0),
            (settlement, 0),
        ]
        assert core.built_ins.name == "N26 core built-ins"
        assert all(row.pack == default_pack for row in (core, settlement, reputation))
        # One line per row: the counter, the type, two kinds, the asset,
        # its listing in the catalogue, the set, and two members.
        assert len(lines) == 9

    def test_running_it_again_creates_nothing(self, default_pack):
        list(seed_core_campaign(apps))
        before = (
            CampaignType.objects.count(),
            AssetKind.objects.count(),
            Asset.objects.count(),
            Counter.objects.count(),
            DefaultAssignmentSet.objects.count(),
            DefaultAssignment.objects.count(),
        )

        assert list(seed_core_campaign(apps)) == []
        assert (
            CampaignType.objects.count(),
            AssetKind.objects.count(),
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
        core = CampaignType.objects.get(name="N26 core")
        assert core.built_in_members.filter(counter=existing).exists()


class TestTheAuthoringPages:
    """Both kinds have pages in the existing style: a listing, a create
    page, and a page per row. The campaign type's page lists its asset
    kinds and edits each in place."""

    def test_the_menu_offers_both_kinds(self, author, client, default_pack):
        body = client.get("/n26/authoring/").content.decode()
        assert 'href="/n26/authoring/campaign-type/"' in body
        assert 'href="/n26/authoring/asset/"' in body

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

    def test_the_type_page_lists_its_kinds_with_their_forms_and_offers_built_ins(
        self, author, client, dominion
    ):
        body = client.get(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        ).content.decode()

        territory = dominion["territory"]
        assert f'name="part-{territory.pk}-label_singular"' in body
        assert 'value="Territory"' in body
        assert "Territories · pooled · no assets yet" in body
        assert "Comes with" in body
        assert "Modifiers" in body
        assert f"/n26/authoring/asset-kinds/{territory.pk}/remove/" in body

    def test_the_type_page_adds_an_asset_kind(self, author, client, dominion):
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {"label_singular": "Racket", "label_plural": "Rackets", "mode": "pooled"},
        )

        racket = dominion["type"].asset_kinds.get(label_singular="Racket")
        assert response.status_code == 302
        assert racket.position == 2
        assert racket.plural == "Rackets"

    def test_the_type_page_edits_an_asset_kind_in_place(self, author, client, dominion):
        territory = dominion["territory"]
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "edit-part",
                "part": str(territory.pk),
                f"part-{territory.pk}-label_singular": "Turf",
                f"part-{territory.pk}-label_plural": "Turfs",
                f"part-{territory.pk}-mode": "held-one-each",
                f"part-{territory.pk}-position": "5",
            },
        )

        territory.refresh_from_db()
        assert response.status_code == 302
        assert (
            territory.label_singular,
            territory.label_plural,
            territory.mode,
            territory.position,
        ) == ("Turf", "Turfs", "held-one-each", 5)

    def test_renaming_a_kind_onto_its_siblings_label_is_refused_in_words(
        self, author, client, dominion
    ):
        territory = dominion["territory"]
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "edit-part",
                "part": str(territory.pk),
                f"part-{territory.pk}-label_singular": "settlement",
                f"part-{territory.pk}-mode": "pooled",
            },
        )

        territory.refresh_from_db()
        assert response.status_code == 200
        assert "already has an asset kind called" in response.content.decode()
        assert territory.label_singular == "Territory"

    def test_removing_a_kind_is_a_page_that_names_what_stands_in_the_way(
        self, author, client, dominion
    ):
        territory = dominion["territory"]
        ruins = create_asset("Old Ruins", territory)
        remove = f"/n26/authoring/asset-kinds/{territory.pk}/remove/"

        body = client.get(remove).content.decode()
        assert "Old Ruins" in body
        assert "You cannot remove it" in body

        refused = client.post(remove, follow=True)
        assert AssetKind.objects.filter(pk=territory.pk).exists()
        assert "1 asset is of the kind Territory" in refused.content.decode()

        ruins.delete()
        done = client.post(remove)
        assert done.status_code == 302
        assert done.url == f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        assert not AssetKind.objects.filter(pk=territory.pk).exists()

    def test_creating_an_asset_through_its_page(self, author, client, dominion):
        response = client.post(
            "/n26/authoring/asset/new/",
            {
                "name": "Old Ruins",
                "kind": str(dominion["territory"].pk),
                "income": "10",
            },
        )

        ruins = Asset.objects.get(name="Old Ruins")
        assert response.status_code == 302
        assert ruins.kind == dominion["territory"]
        assert ruins.income == 10

        page = client.get(f"/n26/authoring/asset/{ruins.pk}/").content.decode()
        # Filed under its campaign type, which the breadcrumb names.
        assert f"/n26/authoring/campaign-type/{dominion['type'].pk}/" in page

    def test_the_asset_listing_says_kind_and_income(self, author, client, dominion):
        create_asset("Old Ruins", dominion["territory"], income=10)

        body = client.get("/n26/authoring/asset/").content.decode()
        assert "Territory (Dominion)" in body
        assert "income 10cr" in body

    def test_the_type_listing_says_kinds_and_catalogue(self, author, client, dominion):
        set_assets(dominion["type"], [create_asset("Old Ruins", dominion["territory"])])

        body = client.get("/n26/authoring/campaign-type/").content.decode()
        assert "Territories, Settlements" in body
        assert "offers 1 asset" in body


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

    def test_a_system_pack_form_refuses_an_owned_pack_reference(
        self, author, client, default_pack, owned
    ):
        response = client.post(
            "/n26/authoring/asset/new/",
            {"name": "Rat hole asset", "kind": str(owned["kind"].pk)},
        )

        assert response.status_code == 200
        assert not Asset.objects.filter(name="Rat hole asset").exists()
        body = response.content.decode()
        assert "Rat hole (Sump Rats campaign) is in the Sump Rats pack" in body
        assert "which has an owner" in body

    def test_an_owned_pack_form_may_reference_system_content(
        self, author, client, dominion, owned
    ):
        asset = owned["asset"]
        response = client.post(
            f"/n26/authoring/asset/{asset.pk}/",
            {
                "act": "edit",
                "edit-name": asset.name,
                "edit-kind": str(dominion["territory"].pk),
                "edit-income": "0",
            },
        )

        asset.refresh_from_db()
        assert response.status_code == 302
        assert asset.kind == dominion["territory"]
        assert asset.pack == owned["pack"]

    def test_a_system_types_catalogue_refuses_an_owned_asset(
        self, author, client, dominion, owned
    ):
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "edit",
                "edit-name": "Dominion",
                "edit-assets": [str(owned["asset"].pk)],
            },
        )

        assert response.status_code == 200
        assert "which has an owner" in response.content.decode()
        assert not dominion["type"].assets.exists()

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

    def test_an_asset_kind_added_to_an_owned_type_joins_its_pack(
        self, author, client, owned
    ):
        """The kind lands in the type's own pack, so a type in a pack
        somebody owns takes new kinds from the staff page."""
        response = client.post(
            f"/n26/authoring/campaign-type/{owned['type'].pk}/",
            {"label_singular": "Sump", "mode": "pooled"},
        )

        sump = owned["type"].asset_kinds.get(label_singular="Sump")
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
