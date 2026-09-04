"""Taking something away: bundles, innate rows, and what money protects.

*Takes something away* promises an author that it "cancels something
granted or innate" and "never un-buys what was paid for". This suite is
that sentence, told as the situations it was written for:

* **The bundle.** A house hangs its gang rules off one hidden carrier, and
  a corruption cancels the carrier. Everything the carrier was giving goes
  with it, on the gang's card and on every fighter's, and comes back the
  moment the corruption does.
* **Two givers.** A rule two things give survives losing one of them, and
  the row names the one still standing.
* **Innate.** A fighter's built-in kit is a row nobody paid for, so a
  removal reaches it: the line goes and the row stays exactly where it is,
  which is why the equipment screen stops offering to sell it.
* **What money protects.** A purchase is never taken away by reading a
  card, and neither is free kit with a purchase hanging off it — an
  accessory somebody bought must not be left holding nothing.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.owned import owned_things
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card, render_gang
from n26.tests.sandbox.actions import (
    assign,
    attach,
    create_affiliation,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_rule,
    create_subtype,
    create_wargear,
    create_weapon,
    create_weapon_accessory,
    ef_adds,
    ef_removes,
    found_gang,
    give_weapon,
    has_subtypes,
    hire,
    modifier,
    remove,
    targets_every_model,
    targets_gang,
    targets_model,
)

pytestmark = [pytest.mark.django_db, pytest.mark.core]


HOUSE_RULES = ("Matriarchy", "Quicksilver")


@pytest.fixture
def house(default_pack, fighter_type):
    """A house whose gang rules all hang off one hidden carrier.

    The charter is a built-in of the gang type, so founding writes it as a
    row; the rules themselves are *given* by the charter rather than built
    in beside it. One thing to name, and the whole set answers to it — on
    the gang's own card and, through the broadcast, on every fighter's.
    """
    rules = {name: create_rule(name) for name in HOUSE_RULES}
    charter = create_hidden("Escher gang rules")
    for name, rule in rules.items():
        # Aimed at the gang, the rule is the gang's: it prints on the
        # gang's sheet, and whatever it does reaches every fighter from
        # there. Aimed at the model as well, it is each fighter's own and
        # prints on their card too — which is what this suite reads, so
        # both aims are written.
        modifier(
            f"Escher: the gang has {name}",
            targets_gang(),
            ef_adds(rule),
            carried_by=charter,
        )
        modifier(
            f"Escher: fighters have {name}",
            targets_every_model(),
            ef_adds(rule),
            carried_by=charter,
        )
    gang_type = create_gang_type("Escher", starting_credits=1000)
    gang_type.built_ins = create_default_set("Escher founding", members=[charter])
    gang_type.save()
    return gang_type, charter, rules


@pytest.fixture
def ganger(house, fighter_type):
    gang_type, _, _ = house
    return create_profile("Escher Ganger", fighter_type, gang_type, price=55)


@pytest.fixture
def gang(house, ganger):
    gang_type, _, _ = house
    player = User.objects.create_user("player")
    founded = found_gang("The Bad Girls", gang_type, owner=player)
    hire(founded, ganger, "Yolanda", paid=55)
    return founded


@pytest.fixture
def corruption(house):
    """The affiliation that cancels the house's rules.

    Two modifiers because the charter stands on two cards: the gang's, and
    the copy of that row every fighter's card carries. Cancelled on the
    gang, the gang stops holding what the charter gave — so nothing of it
    reaches anyone. Cancelled on the model as well, the fighter's own copy
    goes too, and with it the rules the charter handed them directly.
    """
    _, charter, _ = house
    corrupted = create_affiliation("Chaos Corrupted")
    modifier(
        "Corrupted: the gang loses its rules",
        targets_gang(),
        ef_removes(charter),
        carried_by=corrupted,
    )
    modifier(
        "Corrupted: fighters lose the gang's rules",
        targets_every_model(),
        ef_removes(charter),
        carried_by=corrupted,
    )
    return corrupted


def owned_names(miniature):
    """What the equipment screen would put a Sell button beside.

    The page computes the card and reads its owned rows off it, so this
    does the same: the rows are the listing's own joining key.
    """
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    compute(card, index)
    return sorted(
        thing.name
        for things in owned_things(card, "/n26/equip").values()
        for thing in things
    )


def card_for(miniature):
    """One model's card, computed the way every screen computes it."""
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def member(gang, name="Yolanda"):
    from n26.core.models import Miniature

    return Miniature.objects.get(membership__gang=gang, name=name)


def plan_for(gang, miniature=None):
    """Every step one card ran, in order — the gang's own, or a model's."""
    from n26.core.effects import compute_gang

    if miniature is not None:
        card = build_card(miniature)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        return compute(card, index).plan
    gang_card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in gang_card.all_nodes()])
    return compute_gang(gang_card, index).plan


class TestTheAuthoringSurface:
    """What an author can name in a *takes something away*."""

    def test_a_removal_can_name_a_hidden_carrier(self, default_pack):
        """A bundle needs something to hang off, and a hidden item is what
        draws no row — so it is what the picker has to offer."""
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        charter = create_hidden("Escher gang rules")
        form = generate_form(specs()["ef_removes"])(
            {"thing_kind": "hidden", "thing_hidden": str(charter.pk)}
        )

        assert form.is_valid(), form.errors
        assert str(form.compile()) == "removes Escher gang rules"


class TestABundleOfGangRules:
    """A hidden carrier gives the house rules; one removal takes them all."""

    def test_the_gang_and_its_fighters_hold_the_house_rules(self, gang):
        sheet = render_gang(gang)
        assert [line.name for line in sheet.rules] == list(HOUSE_RULES)
        assert [line.name for line in sheet.models[0].rules] == list(HOUSE_RULES)

    def test_the_corruption_takes_the_whole_bundle_away(self, gang, corruption):
        assign(corruption, gang=gang)

        sheet = render_gang(gang)
        assert sheet.rules == []
        assert sheet.models[0].rules == []

    def test_the_charter_is_still_a_row_in_the_database(self, gang, corruption, house):
        _, charter, _ = house
        assign(corruption, gang=gang)
        render_gang(gang)

        assert Assignment.objects.filter(
            gang=gang, hidden=charter, archived=False
        ).exists()

    def test_dropping_the_corruption_brings_the_rules_back(self, gang, corruption):
        assigned = assign(corruption, gang=gang)
        assert render_gang(gang).rules == []

        remove(assigned)

        assert [line.name for line in render_gang(gang).rules] == list(HOUSE_RULES)

    def test_a_grant_the_carrier_makes_in_a_later_round_never_stands(
        self, gang, house, corruption
    ):
        """A cancelled carrier's own modifiers may not have run yet: a
        narrowed one waits for a later round, when nothing about the
        rounds knows the carrier has gone. What it grants is undone."""
        _, charter, _ = house
        sisterhood = create_rule("Sisterhood")
        rank = create_subtype("Ganger")
        modifier(
            "Escher: gangers have Sisterhood",
            targets_every_model(has_subtypes(rank)),
            ef_adds(sisterhood),
            carried_by=charter,
        )
        assign(rank, miniature=member(gang))
        assert "Sisterhood" in [line.name for line in card_for(member(gang)).rules]

        assign(corruption, gang=gang)

        assert card_for(member(gang)).rules == []
        late = [
            step
            for step in plan_for(gang, member(gang))
            if step.granted == ("Sisterhood",)
        ]
        assert [(step.ran_in, step.outcome) for step in late] == [(1, "retracted")]

    def test_the_chain_goes_further_than_one_step(self, gang, house, corruption):
        """The charter may hand out another carrier, which hands out the
        rule. Cancelling the charter takes both: a grant is only there
        while something still gives it, all the way down."""
        _, charter, _ = house
        ritual = create_hidden("Escher rites")
        modifier(
            "Escher: fighters keep the rites",
            targets_every_model(),
            ef_adds(ritual),
            carried_by=charter,
        )
        modifier(
            "Rites: fighters have Blood Debt",
            targets_model(),
            ef_adds(create_rule("Blood Debt")),
            carried_by=ritual,
        )
        assert "Blood Debt" in [line.name for line in card_for(member(gang)).rules]

        assign(corruption, gang=gang)

        assert card_for(member(gang)).rules == []

    def test_working_out_a_removal_costs_no_queries(
        self, gang, corruption, django_assert_num_queries
    ):
        """Suppressing rows and following the chain are reading, on rows
        the card build already holds — so a corrupted gang's sheet asks
        the database exactly what an untouched one does."""
        assign(corruption, gang=gang)
        gang_card = build_gang_card(gang)
        index = build_modifier_index(
            [node.assignable for node in gang_card.all_nodes()]
        )

        with django_assert_num_queries(0):
            from n26.core.effects import compute_gang

            assert compute_gang(gang_card, index).rules == []

    def test_the_plan_says_what_the_removal_took(self, gang, corruption):
        assign(corruption, gang=gang)

        took = [step for step in plan_for(gang) if step.took_away]
        assert [step.took_away for step in took] == [("Escher gang rules",)]
        # The charter's own grants ran, and then the charter went: the
        # plan says so rather than leaving them reading as reached.
        assert {step.outcome for step in plan_for(gang) if step.granted} == {
            "retracted"
        }


class TestTwoGivers:
    """A thing two carriers give survives losing one of them."""

    @pytest.fixture
    def both(self, gang, house):
        """A second carrier giving one of the house rules as well."""
        _, _, rules = house
        totem = create_wargear("Ancestral totem")
        modifier(
            "Totem gives Quicksilver",
            targets_model(),
            ef_adds(rules["Quicksilver"]),
            carried_by=totem,
        )
        assign(totem, miniature=member(gang), paid=15)
        return totem

    def test_the_rule_stays_when_only_one_giver_is_cancelled(
        self, gang, corruption, both
    ):
        assign(corruption, gang=gang)

        rules = card_for(member(gang)).rules
        assert [line.name for line in rules] == ["Quicksilver"]

    def test_the_row_names_the_giver_still_standing(self, gang, corruption, both):
        assign(corruption, gang=gang)

        (line,) = card_for(member(gang)).rules
        assert line.provenance.source == "Ancestral totem"


class TestInnateRows:
    """Built-in kit is a row nobody paid for, and a removal reaches it."""

    @pytest.fixture
    def shotgun(self, db):
        return create_weapon("Shotgun", profiles=[("", 0)], price=30)

    @pytest.fixture
    def armed(self, house, fighter_type, shotgun):
        """A fighter entry whose kit includes the gun, free with the hire."""
        gang_type, _, _ = house
        profile = create_profile("Escher Champion", fighter_type, gang_type, price=80)
        profile.built_ins = create_default_set("Champion kit", members=[shotgun])
        profile.save()
        return profile

    @pytest.fixture
    def confiscation(self, shotgun):
        return create_affiliation(
            "Disarmed",
            effects=[(targets_every_model(), ef_removes(shotgun))],
        )

    @pytest.fixture
    def champion(self, gang, armed):
        return hire(gang, armed, "Ysolde", paid=80)

    def test_the_built_in_gun_is_on_the_card_until_something_takes_it(
        self, champion, gang
    ):
        assert [weapon.name for weapon in card_for(champion).weapons] == ["Shotgun"]

    def test_a_removal_takes_the_built_in_gun_off_the_card(
        self, champion, gang, confiscation
    ):
        assign(confiscation, gang=gang)

        assert card_for(champion).weapons == []

    def test_the_equipment_screen_stops_offering_to_sell_it(
        self, champion, gang, confiscation
    ):
        """A screen must not sell a gun the card says the fighter has not
        got. The owned rows are what the listing joins its lines to."""
        assert owned_names(champion) == ["Shotgun"]

        assign(confiscation, gang=gang)

        assert owned_names(champion) == []

    def test_asking_whether_a_row_was_paid_for_costs_no_queries(
        self, champion, gang, confiscation, django_assert_num_queries
    ):
        """The ledger entry a removal reads to decide is on the row the
        card build already fetched — computing may not query."""
        assign(confiscation, gang=gang)
        card = build_card(champion, with_statlines=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])

        with django_assert_num_queries(0):
            compute(card, index)
        assert all(node.suppressed for node in card.roots if node.name == "Shotgun")

    def test_the_row_is_never_deleted(self, champion, gang, confiscation, shotgun):
        assign(confiscation, gang=gang)
        card_for(champion)

        assert Assignment.objects.filter(
            miniature_root=champion, weapon=shotgun, archived=False
        ).exists()

    def test_a_rank_taken_away_stops_being_something_rules_match_on(
        self, gang, house, fighter_type
    ):
        """A fighter's rank arrives with the hire, as a row. Take it away
        and a rule written for that rank stops reaching them: what the
        card says the fighter is, is what scopes ask."""
        gang_type, _, _ = house
        rank = create_subtype("Ganger")
        profile = create_profile("Escher Juve", fighter_type, gang_type, price=25)
        profile.built_ins = create_default_set("Juve rank", members=[rank])
        profile.save()
        juve = hire(gang, profile, "Nessa", paid=25)

        badge = create_wargear("Gang badge")
        modifier(
            "Badge: gangers have Reputation",
            targets_model(with_subtypes=[rank]),
            ef_adds(create_rule("Reputation")),
            carried_by=badge,
        )
        assign(badge, miniature=juve, paid=5)
        assert "Reputation" in [line.name for line in card_for(juve).rules]

        demoted = create_affiliation(
            "Demoted", effects=[(targets_every_model(), ef_removes(rank))]
        )
        assign(demoted, gang=gang)

        card = card_for(juve)
        assert card.subtypes == []
        assert "Reputation" not in [line.name for line in card.rules]

    def test_a_built_in_rule_goes_the_same_way(self, gang, house, fighter_type):
        """Innate is not only kit: a rule that arrived with the hire is a
        row like any other, and a removal reaches it too."""
        gang_type, _, _ = house
        oath = create_rule("Sworn Oath")
        profile = create_profile("Escher Sister", fighter_type, gang_type, price=60)
        profile.built_ins = create_default_set("Sister vows", members=[oath])
        profile.save()
        sister = hire(gang, profile, "Kal", paid=60)
        assert "Sworn Oath" in [line.name for line in card_for(sister).rules]

        forsworn = create_affiliation(
            "Forsworn", effects=[(targets_every_model(), ef_removes(oath))]
        )
        assign(forsworn, gang=gang)

        assert "Sworn Oath" not in [line.name for line in card_for(sister).rules]


class TestWhatMoneyProtects:
    """A purchase is parted with by an operation, never by a read."""

    @pytest.fixture
    def autogun(self, db):
        return create_weapon("Autogun", profiles=[("", 0)], price=20)

    @pytest.fixture
    def confiscation(self, autogun):
        return create_affiliation(
            "Disarmed",
            effects=[(targets_every_model(), ef_removes(autogun))],
        )

    def test_a_gun_the_gang_bought_stays_put(self, gang, autogun, confiscation):
        give_weapon(member(gang), autogun, paid=20)
        assign(confiscation, gang=gang)

        assert [weapon.name for weapon in card_for(member(gang)).weapons] == ["Autogun"]
        assert_reconciled(gang)

    def test_the_plan_says_the_removal_refused(self, gang, autogun, confiscation):
        give_weapon(member(gang), autogun, paid=20)
        assign(confiscation, gang=gang)

        card = build_card(member(gang), with_statlines=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        computed = compute(card, index)
        refusals = [step for step in computed.plan if step.refused]
        assert [step.outcome for step in refusals] == ["refused"]
        assert refusals[0].refused == ("Autogun",)

    def test_free_kit_with_a_bought_accessory_stays_too(
        self, gang, house, fighter_type, autogun, confiscation
    ):
        """Nothing paid for may be stranded: a sight somebody bought for a
        built-in gun has to keep the gun it is bolted to."""
        gang_type, _, _ = house
        profile = create_profile("Escher Gunner", fighter_type, gang_type, price=70)
        profile.built_ins = create_default_set("Gunner kit", members=[autogun])
        profile.save()
        gunner = hire(gang, profile, "Mira", paid=70)
        gun = Assignment.objects.get(miniature_root=gunner, weapon=autogun)
        attach(gun, create_weapon_accessory("Telescopic sight", price=25), paid=25)

        assign(confiscation, gang=gang)

        (weapon,) = card_for(gunner).weapons
        assert weapon.name == "Autogun"
        assert [line.name for line in weapon.accessories] == ["Telescopic sight"]
        assert_reconciled(gang)

    def test_the_same_gun_bought_by_another_fighter_is_untouched(
        self, gang, house, fighter_type, autogun, confiscation
    ):
        """Being taken away is a fact about one row, not about the weapon:
        the gang may hold two of these, one free and one bought."""
        gang_type, _, _ = house
        profile = create_profile("Escher Gunner", fighter_type, gang_type, price=70)
        profile.built_ins = create_default_set("Gunner kit", members=[autogun])
        profile.save()
        gunner = hire(gang, profile, "Mira", paid=70)
        give_weapon(member(gang), autogun, paid=20)

        assign(confiscation, gang=gang)

        assert card_for(gunner).weapons == []
        assert [weapon.name for weapon in card_for(member(gang)).weapons] == ["Autogun"]
        # Hiding a row moves no money and changes no rating — the free gun
        # was worth nothing to begin with, which is why it could go.
        assert_reconciled(gang)
