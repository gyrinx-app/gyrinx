"""Staged content, as players and authors meet it.

An author writes a new gang type, a fighter, a weapon, a skill and a pick,
and stages each. A player meets none of them anywhere they add to a gang:
the create-gang cards, the hire screen, the equipment lists and the
Trading Post, the skills screen, the pick screen. The author meets every
one of them exactly where the player would once it is live, and so does a
player the staged-content flag is open to. What a gang already holds is
drawn for everyone, staged or not. Putting everything live is one act, and
an import can hold back what it makes. (n26/library/staged.py, and
design/collections.md on hiding content from some viewers.)
"""

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import Assignment, Gang, Miniature
from n26.core.render import build_choice_offer, render_gang
from n26.core.views.choose import _find_slot, link_slots
from n26.flags import STAGED_CONTENT
from n26.library.authoring import put_everything_live, stage
from n26.library.models import Category, Collection, CollectionEntry, Profile, Weapon
from n26.tests.sandbox.actions import (
    add_picklist_member,
    assign,
    create_category,
    create_collection,
    create_default_set,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_skill,
    create_slot,
    create_slot_type,
    create_trading_post,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    places,
    section_of,
    targets_model,
)

pytestmark = pytest.mark.django_db


def key_of(thing):
    return f"{thing._meta.label_lower}:{thing.pk}"


# --- The people ---------------------------------------------------------------


@pytest.fixture
def player(db):
    return User.objects.create_user("player")


@pytest.fixture
def author(db):
    return User.objects.create_user("author", is_staff=True)


@pytest.fixture
def tester(db):
    """A player the staged-content flag has been opened to."""
    group = Group.objects.create(name="N26 Staged content")
    FeatureFlag.objects.create(
        slug=STAGED_CONTENT,
        name="Staged content",
        availability=Availability.ALLOWLIST,
        group=group,
    )
    user = User.objects.create_user("tester")
    user.groups.add(group)
    return user


# --- The content, live and staged side by side --------------------------------


@pytest.fixture
def staged_type(default_pack):
    return stage(create_gang_type("Ash Wastes Nomads", starting_credits=1000))


@pytest.fixture
def gear(default_pack):
    """A knife and a spear on the house list, a lasgun and a plasma caliver
    at the Trading Post — one of each pair staged."""
    knife = create_wargear("Knife", price=10)
    spear = stage(create_wargear("Spear", price=15))
    lasgun = create_weapon("Lasgun", price=15, trade_point_price=5)
    caliver = stage(create_weapon("Plasma caliver", price=90, trade_point_price=8))
    return {"knife": knife, "spear": spear, "lasgun": lasgun, "caliver": caliver}


@pytest.fixture
def house_list(gear):
    return create_collection("House List", entries=[gear["knife"], gear["spear"]])


@pytest.fixture
def trading_post(gear):
    from n26.library.models import Wargear

    return create_trading_post(contains=[Weapon, Wargear])


@pytest.fixture
def skills(default_pack):
    """Two Combat skills in the skills collection, Parry staged."""
    combat = create_category("Skills", "Combat", 0)
    berserker = create_skill("Berserker", category=combat)
    parry = stage(create_skill("Parry", category=combat))
    collection = create_collection("Skills", entries=[berserker, parry])
    primary = section_of(collection, "Primary", 0)
    section_of(collection, "Other", 1, is_default=True)
    return {
        "combat": combat,
        "berserker": berserker,
        "parry": parry,
        "primary": primary,
    }


@pytest.fixture
def profiles(gang_type, person_type, make_statline, skills, house_list):
    """The gang's Ganger, live, and a Nomad Runner nobody has put live.

    Every gang of the type founds with the house list, and a Ganger's
    grid places Combat under Primary — so the skills screen has
    something to list.
    """
    gang_type.built_ins = create_default_set("Escher kit", members=[house_list])
    gang_type.save()
    ganger = create_profile("Ganger", person_type, gang_type, price=55)
    make_statline(ganger, movement=5, weapon_skill=4, toughness=3)
    modifier(
        "Ganger: Combat is Primary",
        targets_model(),
        places(skills["combat"], skills["primary"]),
        carried_by=ganger,
    )
    runner = stage(create_profile("Nomad Runner", person_type, gang_type, price=60))
    make_statline(runner, movement=6, weapon_skill=4, toughness=3)
    return {"ganger": ganger, "runner": runner}


@pytest.fixture
def legacy(default_pack):
    """A Gang Legacy slot: Cawdor and a staged Van Saar on its picklist."""
    slot_type = create_slot_type("Gang Legacy", plural_name="Gang Legacies")
    cawdor = create_pickable("Cawdor", slot_type)
    van_saar = stage(create_pickable("Van Saar", slot_type))
    picklist = create_picklist("House Legacies", slot_type)
    add_picklist_member(picklist, cawdor)
    add_picklist_member(picklist, van_saar)
    slot = create_slot("Gang Legacy", slot_type, picklist=picklist)
    return {"slot": slot, "cawdor": cawdor, "van_saar": van_saar}


def a_gang_for(owner, gang_type, profiles, legacy):
    """A gang with one Ganger and the legacy question open."""
    gang = found_gang(f"{owner.username}'s gang", gang_type, owner=owner, budget=1000)
    fighter = hire(gang, profiles["ganger"], "Vex")
    assign(legacy["slot"], gang=gang)
    return gang, fighter


@pytest.fixture
def players_gang(player, gang_type, profiles, legacy, trading_post):
    return a_gang_for(player, gang_type, profiles, legacy)


@pytest.fixture
def authors_gang(author, gang_type, profiles, legacy, trading_post):
    return a_gang_for(author, gang_type, profiles, legacy)


@pytest.fixture
def testers_gang(tester, gang_type, profiles, legacy, trading_post):
    return a_gang_for(tester, gang_type, profiles, legacy)


def founding_post(gang_type):
    return {
        "name": "Rust in Peace",
        "gang_type": str(gang_type.pk),
        "starting_credits": "",
        "colour": "",
    }


def hire_url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def equip_url(fighter, list_param):
    return f"{reverse('n26-equip', args=[fighter.pk])}?list={list_param}"


def legacy_offer(gang, include_staged):
    """What the pick screen would list for the gang's open legacy slot."""
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    line = next(line for line in sheet.choices if line.kind_label == "Gang Legacy")
    found = _find_slot(gang, line.key)
    offer = build_choice_offer(
        found.slot, found.computed, include_staged=include_staged
    )
    return line.href, {
        option.name for group in offer.groups for option in group.options
    }


# --- Creating a gang ----------------------------------------------------------


class TestCreatingAGang:
    """A staged gang type is not on the cards for a player, and the id is
    refused if typed; an author and a flagged player are offered it."""

    def test_a_player_is_not_offered_it_and_cannot_found_on_it(
        self, client, player, gang_type, staged_type
    ):
        client.force_login(player)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert "Escher" in body
        assert "Ash Wastes Nomads" not in body

        response = client.post(reverse("n26-create-gang"), founding_post(staged_type))

        assert response.status_code == 200
        assert "not a gang type you can found" in response.content.decode()
        assert not Gang.objects.filter(name="Rust in Peace").exists()

    def test_an_author_is_offered_it_and_founds_on_it(
        self, client, author, gang_type, staged_type
    ):
        client.force_login(author)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert "Ash Wastes Nomads" in body

        response = client.post(reverse("n26-create-gang"), founding_post(staged_type))

        assert response.status_code == 302
        assert Gang.objects.get(name="Rust in Peace").gang_type == staged_type

    def test_a_player_the_flag_is_open_to_is_offered_it(
        self, client, tester, gang_type, staged_type
    ):
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert "Ash Wastes Nomads" in body

    def test_open_to_everyone_the_flag_offers_it_to_every_player(
        self, client, player, gang_type, staged_type
    ):
        """A rehearsal of the release, with a way back."""
        FeatureFlag.objects.create(
            slug=STAGED_CONTENT,
            name="Staged content",
            availability=Availability.EVERYONE,
        )
        client.force_login(player)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert "Ash Wastes Nomads" in body


# --- Hiring -------------------------------------------------------------------


class TestHiring:
    def test_a_player_is_not_offered_the_staged_fighter_on_any_scope(
        self, client, player, players_gang
    ):
        gang, _ = players_gang
        client.force_login(player)
        for scope in ("", "?list=all", "?list=supplementary"):
            body = client.get(f"{hire_url(gang)}{scope}").content.decode()
            assert "Nomad Runner" not in body, scope
        assert "Ganger" in client.get(hire_url(gang)).content.decode()

    def test_a_player_cannot_hire_it_by_typing_its_id(
        self, client, player, players_gang, profiles
    ):
        gang, _ = players_gang
        client.force_login(player)
        runner = profiles["runner"]
        assert (
            client.get(f"{hire_url(gang)}?hire={runner.pk}").context["dialog"] is None
        )

        response = client.post(
            hire_url(gang), {"profile": str(runner.pk), "name": "Sand"}
        )

        assert response.status_code == 200
        assert not Miniature.objects.filter(membership__profile=runner).exists()
        # The card behind the row is not drawn for them either.
        assert (
            client.get(reverse("n26-hire-card", args=[gang.pk, runner.pk])).status_code
            == 404
        )

    def test_an_author_is_offered_it_and_hires_it(
        self, client, author, authors_gang, profiles
    ):
        gang, _ = authors_gang
        client.force_login(author)
        runner = profiles["runner"]
        assert "Nomad Runner" in client.get(hire_url(gang)).content.decode()

        response = client.post(
            hire_url(gang), {"profile": str(runner.pk), "name": "Sand"}
        )

        assert response.status_code == 302
        assert Miniature.objects.filter(
            membership__profile=runner, name="Sand"
        ).exists()

    def test_a_collection_offering_a_staged_fighter_offers_it_to_authors_only(
        self, client, player, author, players_gang, authors_gang, profiles
    ):
        mercs = create_collection(
            "Mercenaries", entries=[(profiles["runner"], {"price_override": 30})]
        )
        for gang, _ in (players_gang, authors_gang):
            assign(mercs, gang=gang)

        client.force_login(player)
        assert (
            "Mercenaries" not in client.get(hire_url(players_gang[0])).content.decode()
        )
        client.force_login(author)
        body = client.get(hire_url(authors_gang[0])).content.decode()
        assert "Mercenaries" in body
        assert "Nomad Runner" in body


# --- Equipping ----------------------------------------------------------------


class TestEquipping:
    def test_a_player_does_not_see_staged_gear_on_any_list(
        self, client, player, players_gang, house_list, trading_post
    ):
        gang, fighter = players_gang
        client.force_login(player)
        on_house = client.get(equip_url(fighter, house_list.pk)).content.decode()
        assert "Knife" in on_house
        assert "Spear" not in on_house
        at_post = client.get(equip_url(fighter, trading_post.pk)).content.decode()
        assert "Lasgun" in at_post
        assert "Plasma caliver" not in at_post
        everything = client.get(equip_url(fighter, "all")).content.decode()
        assert "Lasgun" in everything
        assert "Plasma caliver" not in everything
        assert "Spear" not in everything

    def test_a_player_cannot_buy_it_by_typing_its_key(
        self, client, player, players_gang, house_list, gear
    ):
        gang, fighter = players_gang
        client.force_login(player)
        client.post(equip_url(fighter, house_list.pk), {"thing": key_of(gear["spear"])})
        assert not Assignment.objects.filter(wargear=gear["spear"]).exists()

    def test_an_author_sees_it_everywhere_and_buys_it(
        self, client, author, authors_gang, house_list, trading_post, gear
    ):
        gang, fighter = authors_gang
        client.force_login(author)
        assert "Spear" in client.get(equip_url(fighter, house_list.pk)).content.decode()
        assert (
            "Plasma caliver"
            in client.get(equip_url(fighter, trading_post.pk)).content.decode()
        )
        assert (
            "Plasma caliver" in client.get(equip_url(fighter, "all")).content.decode()
        )

        client.post(equip_url(fighter, house_list.pk), {"thing": key_of(gear["spear"])})

        assert Assignment.objects.filter(wargear=gear["spear"], miniature_root=fighter)

    def test_what_a_gang_already_holds_is_drawn_for_everyone(
        self, client, authors_gang, gear
    ):
        """The gate is where things are chosen, never where they are drawn:
        a stranger reading the author's roster sees the staged gun on it."""
        gang, fighter = authors_gang
        give_weapon(fighter, gear["caliver"], paid=90)

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Plasma caliver" in body


# --- Skills -------------------------------------------------------------------


class TestSkills:
    def test_a_player_is_not_offered_the_staged_skill(
        self, client, player, players_gang, skills
    ):
        gang, fighter = players_gang
        client.force_login(player)
        url = reverse("n26-skills", args=[fighter.pk])
        body = client.get(url).content.decode()
        assert "Berserker" in body
        assert "Parry" not in body

        client.post(url, {"thing": key_of(skills["parry"])})

        assert not Assignment.objects.filter(skill=skills["parry"]).exists()

    def test_an_author_is_offered_it_and_selects_it(
        self, client, author, authors_gang, skills
    ):
        gang, fighter = authors_gang
        client.force_login(author)
        url = reverse("n26-skills", args=[fighter.pk])
        assert "Parry" in client.get(url).content.decode()

        client.post(url, {"thing": key_of(skills["parry"])})

        assert Assignment.objects.filter(
            skill=skills["parry"], miniature_root=fighter
        ).exists()


# --- Choosing -----------------------------------------------------------------


class TestChoosing:
    def test_a_staged_pick_is_offered_to_authors_only(self, players_gang, authors_gang):
        _, theirs = legacy_offer(players_gang[0], include_staged=False)
        assert theirs == {"Cawdor"}
        _, ours = legacy_offer(authors_gang[0], include_staged=True)
        assert ours == {"Cawdor", "Van Saar"}

    def test_a_staged_line_on_the_picklist_is_held_back_too(
        self, players_gang, authors_gang, legacy
    ):
        """A picklist line and the pickable it names are staged apart: a
        live pickable a staged line offers is off the list for a player,
        exactly as a staged entry is off its collection."""
        from n26.library.models import PicklistMember

        stage(PicklistMember.objects.get(pickable=legacy["cawdor"]))

        _, theirs = legacy_offer(players_gang[0], include_staged=False)
        assert theirs == set()
        _, ours = legacy_offer(authors_gang[0], include_staged=True)
        assert ours == {"Cawdor", "Van Saar"}

    def test_the_pick_screen_reads_the_same_way(
        self, client, player, author, players_gang, authors_gang
    ):
        href, _ = legacy_offer(players_gang[0], include_staged=False)
        client.force_login(player)
        body = client.get(href).content.decode()
        assert "Cawdor" in body
        assert "Van Saar" not in body

        href, _ = legacy_offer(authors_gang[0], include_staged=True)
        client.force_login(author)
        assert "Van Saar" in client.get(href).content.decode()


# --- The edit boxes, the accessory dialog, ammo lines ------------------------------


class TestTheModelsEditPage:
    """The Special rules box offers every rule the library has — every live
    one. A staged rule is on it for authors alone, and a save naming it
    from a player assigns nothing."""

    @pytest.fixture
    def rules(self, default_pack):
        from n26.tests.sandbox.actions import create_rule

        return {
            "live": create_rule("Group Activation"),
            "staged": stage(create_rule("Gang Fighter")),
        }

    def test_a_player_is_not_offered_the_staged_rule(
        self, client, player, players_gang, rules
    ):
        gang, fighter = players_gang
        client.force_login(player)
        url = reverse("n26-edit-fighter", args=[fighter.pk])
        body = client.get(url).content.decode()
        assert "Group Activation" in body
        assert "Gang Fighter" not in body

        client.post(url, {"act": "rules", "rules": [key_of(rules["staged"])]})

        assert not Assignment.objects.filter(rule=rules["staged"]).exists()

    def test_an_author_is_offered_it_and_ticks_it(
        self, client, author, authors_gang, rules
    ):
        gang, fighter = authors_gang
        client.force_login(author)
        url = reverse("n26-edit-fighter", args=[fighter.pk])
        assert "Gang Fighter" in client.get(url).content.decode()

        client.post(url, {"act": "rules", "rules": [key_of(rules["staged"])]})

        assert Assignment.objects.filter(
            rule=rules["staged"], miniature_root=fighter
        ).exists()


class TestTheAccessoryDialog:
    """What may be bolted onto a gun is offered from a dialog on the equip
    screen and checked again on the click."""

    @pytest.fixture
    def sights(self, default_pack):
        from n26.tests.sandbox.actions import create_weapon_accessory

        return {
            "live": create_weapon_accessory("Telescopic sight", price=25),
            "staged": stage(create_weapon_accessory("Infra-sight", price=30)),
        }

    def armed(self, gang_and_fighter, gear):
        gang, fighter = gang_and_fighter
        return give_weapon(fighter, gear["lasgun"], paid=15)

    def test_a_player_is_not_offered_the_staged_sight(
        self, client, player, players_gang, gear, sights
    ):
        gun = self.armed(players_gang, gear)
        client.force_login(player)
        body = client.get(equip_url(players_gang[1], "all")).content.decode()
        assert "Telescopic sight" in body
        assert "Infra-sight" not in body

        client.post(
            reverse("n26-accessorise", args=[gun.pk]),
            {"accessory": str(sights["staged"].pk)},
        )

        assert not Assignment.objects.filter(weapon_accessory=sights["staged"]).exists()

    def test_an_author_is_offered_it_and_fits_it(
        self, client, author, authors_gang, gear, sights
    ):
        gun = self.armed(authors_gang, gear)
        client.force_login(author)
        assert (
            "Infra-sight"
            in client.get(equip_url(authors_gang[1], "all")).content.decode()
        )

        client.post(
            reverse("n26-accessorise", args=[gun.pk]),
            {"accessory": str(sights["staged"].pk)},
        )

        assert Assignment.objects.filter(weapon_accessory=sights["staged"]).exists()


class TestAmmoLines:
    """A gun's paid rounds are listed under it at the Trading Post; a staged
    round is under it for authors alone."""

    @pytest.fixture
    def hotshot(self, gear):
        from n26.library.authoring import add_weapon_profile

        return stage(
            add_weapon_profile(
                gear["lasgun"], name="Hotshot", price=5, trade_point_price=2
            )
        )

    def test_a_player_does_not_see_the_staged_round(
        self, client, player, players_gang, trading_post, hotshot
    ):
        client.force_login(player)
        body = client.get(equip_url(players_gang[1], trading_post.pk)).content.decode()
        assert "Lasgun" in body
        assert "Hotshot" not in body

    def test_an_author_does(self, client, author, authors_gang, trading_post, hotshot):
        client.force_login(author)
        body = client.get(equip_url(authors_gang[1], trading_post.pk)).content.decode()
        assert "Hotshot" in body


# --- Campaigns ----------------------------------------------------------------


class TestCampaigns:
    """The types a campaign is set up on, and the assets one hands out, are
    offered on the same terms as everything else."""

    @pytest.fixture
    def campaigns_open(self, db):
        from n26.flags import CAMPAIGNS

        FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )

    @pytest.fixture
    def types(self, default_pack, campaigns_open):
        from n26.library.authoring import create_campaign_type

        return {
            "live": create_campaign_type("Territory campaign"),
            "staged": stage(create_campaign_type("Dominion")),
        }

    def founding(self, campaign_type):
        return {
            "name": "Dust Falls",
            "budget": "1000",
            "summary": "",
            "campaign_type": str(campaign_type.pk),
        }

    def test_a_player_is_not_offered_the_staged_type(self, client, player, types):
        from n26.core.models import Campaign

        client.force_login(player)
        body = client.get(reverse("n26-create-campaign")).content.decode()
        assert "Territory campaign" in body
        assert "Dominion" not in body

        response = client.post(
            reverse("n26-create-campaign"), self.founding(types["staged"])
        )

        assert response.status_code == 200
        assert not Campaign.objects.filter(name="Dust Falls").exists()

    def test_an_author_is_offered_it_and_founds_on_it(self, client, author, types):
        from n26.core.models import Campaign

        client.force_login(author)
        assert "Dominion" in client.get(reverse("n26-create-campaign")).content.decode()

        response = client.post(
            reverse("n26-create-campaign"), self.founding(types["staged"])
        )

        assert response.status_code == 302
        assert Campaign.objects.get(name="Dust Falls").campaign_type == types["staged"]

    @pytest.fixture
    def territories(self, types):
        from n26.library.authoring import add_asset_type, create_asset

        territory = add_asset_type(types["live"], "Territory", "pooled")
        return {
            "type": territory,
            "live": create_asset("Old Ruins", territory),
            "staged": stage(create_asset("Sump Hole", territory)),
        }

    def test_a_staged_asset_is_offered_to_authors_only(
        self, client, player, author, types, territories
    ):
        from n26.core.models import CampaignAsset
        from n26.tests.sandbox.actions import found_campaign

        theirs = found_campaign("Dust Falls", types["live"], owner=player, budget=1000)
        ours = found_campaign(
            "Dust Falls Too", types["live"], owner=author, budget=1000
        )

        client.force_login(player)
        url = reverse("n26-campaign-add-asset", args=[theirs.pk])
        body = client.get(url).content.decode()
        assert "Old Ruins" in body
        assert "Sump Hole" not in body
        client.post(url, {"asset": str(territories["staged"].pk), "name": ""})
        assert not CampaignAsset.objects.filter(asset=territories["staged"]).exists()

        client.force_login(author)
        url = reverse("n26-campaign-add-asset", args=[ours.pk])
        assert "Sump Hole" in client.get(url).content.decode()
        client.post(url, {"asset": str(territories["staged"].pk), "name": ""})
        assert CampaignAsset.objects.filter(
            asset=territories["staged"], campaign=ours
        ).exists()


# --- Rolling ------------------------------------------------------------------


class TestRollingOnATable:
    """A roll lands only on lines the reader may see: a player's roll onto
    a staged result reads as no result, not as a name they were never
    offered."""

    @pytest.fixture
    def injuries(self, default_pack):
        from n26.library.models import Picklist, Slot
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["lasting-effect-tables"].create()
        table = Picklist.objects.get(name="Lasting Injury Table")
        out_cold = next(
            member.pickable
            for member in table.members.select_related("pickable")
            if member.pickable.name == "Out Cold"
        )
        stage(out_cold)
        return {"table": table, "slot": Slot.objects.get(name="Lasting Injury")}

    def roll_page(self, client, gang, fighter, injuries):
        """Enter a 24 at the fighter's injury table and open the page on it."""
        from n26.core.card import build_card, build_modifier_index
        from n26.core.effects import compute
        from n26.core.models import LedgerEvent

        assign(injuries["slot"], miniature=fighter)
        card = build_card(fighter)
        computed = compute(
            card, build_modifier_index([n.assignable for n in card.all_nodes()])
        )
        slot = next(
            line
            for line in computed.choices
            if line.slot is not None and line.slot.picklist_id == injuries["table"].pk
        )
        key = f"{fighter.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"
        address = reverse("n26-choose", args=[gang.pk, key])
        client.post(address, {"act": "enter", "rolled": "24"})
        event = LedgerEvent.objects.filter(kind=LedgerEvent.Kind.ROLLED).latest(
            "created"
        )
        return client.get(f"{address}?roll={event.pk}").content.decode()

    def test_a_players_roll_onto_a_staged_result_names_nothing(
        self, client, player, players_gang, injuries
    ):
        gang, fighter = players_gang
        client.force_login(player)
        page = self.roll_page(client, gang, fighter, injuries)
        assert "Out Cold" not in page
        assert "This table has no result for 24." in page

    def test_an_authors_roll_lands_on_it(self, client, author, authors_gang, injuries):
        gang, fighter = authors_gang
        client.force_login(author)
        page = self.roll_page(client, gang, fighter, injuries)
        assert "Landed on" in page
        assert "Out Cold" in page


# --- Releasing ----------------------------------------------------------------


class TestPuttingEverythingLive:
    def test_one_act_and_a_player_meets_all_of_it(
        self, client, player, players_gang, staged_type, house_list, gear, skills
    ):
        gang, fighter = players_gang
        client.force_login(player)

        released = put_everything_live()

        assert released == 6  # the type, the runner, spear, caliver, Parry, Van Saar
        assert (
            "Ash Wastes Nomads"
            in client.get(reverse("n26-create-gang")).content.decode()
        )
        assert "Nomad Runner" in client.get(hire_url(gang)).content.decode()
        assert "Spear" in client.get(equip_url(fighter, house_list.pk)).content.decode()
        assert (
            "Parry"
            in client.get(reverse("n26-skills", args=[fighter.pk])).content.decode()
        )
        _, offered = legacy_offer(gang, include_staged=False)
        assert offered == {"Cawdor", "Van Saar"}


# --- Importing ----------------------------------------------------------------


class TestAnImportCanHoldBackWhatItMakes:
    @pytest.fixture
    def sheets(self, default_pack):
        from n26.library.ingest import read_csv
        from n26.library.standard_content import STANDARD_CONTENT
        from n26.tests.sandbox.test_ingest import (
            EQUIPMENT_CSV,
            EQUIPMENT_LISTS_CSV,
            PROFILES_CSV,
            WEAPON_PROFILES_CSV,
        )

        for item in STANDARD_CONTENT.values():
            item.create()
        return {
            "equipment": read_csv(EQUIPMENT_CSV),
            "weapon_profiles": read_csv(WEAPON_PROFILES_CSV),
            "equipment_lists": read_csv(EQUIPMENT_LISTS_CSV),
            "profiles": read_csv(PROFILES_CSV),
        }

    def test_what_it_creates_is_staged_and_what_it_reaches_through_is_not(self, sheets):
        from n26.library.ingest import perform, plan_ingest

        result = perform(plan_ingest(pack=None, **sheets), staged=True)

        assert result.staged is True
        assert Profile.objects.exists() and not Profile.objects.live().exists()
        assert Weapon.objects.exists() and not Weapon.objects.live().exists()
        # The lines that offer the gear are held back with it.
        assert CollectionEntry.objects.exists()
        assert not CollectionEntry.objects.live().exists()
        # Reached only through the fighters and the gear: nothing to hold back.
        assert Collection.objects.exists()
        assert not Collection.objects.filter(staged=True).exists()
        assert not Category.objects.filter(staged=True).exists()

    def test_a_second_import_changes_nothing_and_stages_nothing(self, sheets):
        from n26.library.ingest import perform, plan_ingest

        perform(plan_ingest(pack=None, **sheets))
        assert not Profile.objects.filter(staged=True).exists()

        result = perform(plan_ingest(pack=None, **sheets), staged=True)

        assert result.created == {}
        assert not Profile.objects.filter(staged=True).exists()

    def test_by_default_an_import_makes_live_rows(self, sheets):
        from n26.library.ingest import perform, plan_ingest

        perform(plan_ingest(pack=None, **sheets))

        assert Profile.objects.exists()
        assert not Profile.objects.filter(staged=True).exists()
