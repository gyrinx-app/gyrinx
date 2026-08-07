"""Pets: wargear that brings another model into the gang.

The first **stored** effect. Everything modifier-shaped so far has been
computed on read, but a pet cannot be — it has XP, injuries and gear of its
own, so it needs real rows. The rulebook's Designer's Note says as much:
pets are treated as wargear, but are put on the roster "so that they can
keep track of their XP, Lasting Injuries, whether they are In Recovery".

The money: the pet's cost rides on the wargear that brought it, so its
membership is ledgered at full list price with a full discount — the entry
says what the pet is worth and that nothing was paid for it there. Gear
bought for the pet afterwards counts normally, on the pet's own card.
"""

import pytest
from django.contrib.auth.models import User

from n26.library.models import Profile
from n26.core.models import Miniature
from n26.core.reconcile import assert_reconciled, ledger_for_gang
from n26.core.render import build_model_card, render_gang
from n26.core.render_text import gang_to_text
from n26.tests.sandbox.actions import (
    assign,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    op_adds_model,
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def mastiff_profile(person_type, gang_type, default_pack):
    return Profile.objects.create(
        name="Cyber-mastiff",
        profile_type=person_type,
        gang_type=gang_type,
        price=100,
    )


@pytest.fixture
def mastiff_wargear(mastiff_profile):
    """Wargear that brings a pet. The wargear carries the whole cost."""
    wargear = create_wargear("Cyber-mastiff (pet)")
    modifier(
        "Cyber-mastiff wargear brings a pet",
        targets_model(),
        op_adds_model(mastiff_profile),
        carried_by=wargear,
    )
    return wargear


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def yolanda(gang, make_profile):
    return hire(gang, make_profile("Escher Ganger"), "Yolanda", paid=55)


@pytest.fixture
def bought(yolanda, mastiff_wargear):
    """Yolanda buys the pet wargear for 100cr."""
    return assign(mastiff_wargear, miniature=yolanda, paid=100)


def pet_of(gang):
    return Miniature.objects.get(name="Cyber-mastiff", membership__gang=gang)


class TestBuyingAPet:
    def test_the_pet_appears_on_the_roster(self, gang, bought):
        pet = pet_of(gang)
        assert pet.gang == gang
        assert pet.membership.profile.name == "Cyber-mastiff"

    def test_it_is_a_real_model_not_a_computed_one(self, gang, bought):
        """It needs rows: XP, injuries and gear of its own all hang off it."""
        pet = pet_of(gang)
        pet.xp = 3
        pet.save(update_fields=["xp"])
        assert Miniature.objects.get(pk=pet.pk).xp == 3

    def test_the_purchase_caused_the_membership(self, gang, bought):
        assert pet_of(gang).membership.caused_by == bought

    def test_the_owner_is_derived_from_that(self, gang, bought, yolanda):
        assert pet_of(gang).owned_by == yolanda
        assert yolanda.owned_by is None


class TestTheMoney:
    def test_the_wargear_carries_the_cost(self, gang, bought):
        assert bought.ledger_entry.paid == 100
        assert bought.ledger_entry.rating_contribution == 100

    def test_the_pet_costs_nothing_but_says_what_it_is_worth(self, gang, bought):
        entry = pet_of(gang).membership.ledger_entry
        assert entry.list_price == 100
        assert entry.discount == 100
        assert entry.paid == 0
        assert entry.rating_contribution == 0
        assert entry.reason == "granted"

    def test_nothing_is_counted_twice(self, gang, bought, yolanda):
        gang.refresh_from_db()
        assert gang.rating == 55 + 100
        assert gang.credits == 1000 - 155
        assert_reconciled(gang)

    def test_the_pet_s_own_rating_is_zero(self, gang, bought):
        pet = pet_of(gang)
        pet.refresh_from_db()
        assert pet.rating == 0

    def test_the_ledger_shows_both_lines(self, gang, bought):
        lines = {str(entry.assignable): entry.paid for entry in ledger_for_gang(gang)}
        assert lines["Cyber-mastiff (pet)"] == 100
        assert lines["Cyber-mastiff"] == 0


class TestThePetsOwnGear:
    def test_gear_bought_for_the_pet_counts_on_its_card(self, gang, bought):
        pet = pet_of(gang)
        assign(create_wargear("Spiked collar"), miniature=pet, paid=15)
        pet.refresh_from_db()
        gang.refresh_from_db()

        assert pet.rating == 15  # the membership is 0, the collar is 15
        assert [e.name for e in build_model_card(pet).equipment] == ["Spiked collar"]
        assert gang.rating == 55 + 100 + 15
        assert_reconciled(gang)

    def test_the_pet_gets_its_own_card(self, gang, bought):
        pet = pet_of(gang)
        give_weapon(pet, create_weapon("Savage bite", profiles=[("Bite", 0)]), paid=0)
        card = build_model_card(pet)
        assert card.name == "Cyber-mastiff"
        assert [w.name for w in card.weapons] == ["Savage bite"]


class TestSellingTheWargear:
    def test_the_pet_leaves_with_it(self, gang, bought):
        pet = pet_of(gang)
        remove(bought)
        pet.refresh_from_db()

        assert pet.membership.archived is True
        assert pet.membership.caused_by == bought

    def test_the_gang_rating_drops_correctly(self, gang, bought, yolanda):
        pet = pet_of(gang)
        assign(create_wargear("Spiked collar"), miniature=pet, paid=15)
        gang.refresh_from_db()
        assert gang.rating == 170

        remove(bought)
        gang.refresh_from_db()

        # The wargear, the pet and the pet's collar all stop counting.
        assert gang.rating == 55
        assert_reconciled(gang)

    def test_the_ledger_remembers_everything(self, gang, bought):
        pet = pet_of(gang)
        assign(create_wargear("Spiked collar"), miniature=pet, paid=15)
        remove(bought, note="sold the mastiff")

        names = sorted(str(entry.assignable) for entry in ledger_for_gang(gang))
        assert "Cyber-mastiff" in names
        assert "Spiked collar" in names

    def test_the_pet_s_gear_is_left_in_limbo(self, gang, bought):
        """Documents current behaviour, which is not yet the right answer.

        Removing the wargear cascades to the pet's membership, because that
        was *caused by* the purchase. The collar was not — it is merely
        hosted on the pet — so it stays unarchived on a model that is no
        longer on the roster. It correctly stops counting towards rating,
        but the rulebook says discarded gear goes to the gang's Stash, and
        the stash does not exist yet. See open questions.
        """
        pet = pet_of(gang)
        collar = assign(create_wargear("Spiked collar"), miniature=pet, paid=15)
        remove(bought)

        collar.refresh_from_db()
        assert collar.archived is False
        assert pet_of(gang).membership.archived is True
        gang.refresh_from_db()
        assert gang.rating == 55  # but it does not count

    def test_the_money_stays_spent(self, gang, bought):
        remove(bought)
        gang.refresh_from_db()
        assert gang.credits == 1000 - 155


class TestGuards:
    def test_stored_effects_do_not_run_at_read_time(self, gang, bought):
        """compute() must ignore them, or every render would breed pets."""
        from n26.core.card import build_card, build_modifier_index
        from n26.core.effects import compute

        before = Miniature.objects.count()
        card = build_card(yolanda_of(gang), with_statlines=True)
        index = build_modifier_index([n.assignable for n in card.all_nodes()])
        compute(card, index)
        compute(card, index)
        assert Miniature.objects.count() == before

    def test_one_assignment_brings_exactly_one_model(
        self, gang, yolanda, mastiff_profile
    ):
        """No re-entrancy: assigning once hires once.

        A genuine content cycle — a pet whose own default kit brings a pet —
        is not constructible yet, because default equipment does not exist.
        The depth guard in Operation is there for when it does; it is
        deliberately untested until something can exercise it.
        """
        another = create_wargear("Second collar")
        modifier(
            "Second collar brings a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=another,
        )
        assign(another, miniature=yolanda, paid=50)
        assert Miniature.objects.filter(name="Cyber-mastiff").count() == 1


def yolanda_of(gang):
    return Miniature.objects.get(name="Yolanda", membership__gang=gang)


class TestRendering:
    def test_the_roster_shows_the_pet_and_its_owner(self, gang, bought):
        pet = pet_of(gang)
        assign(create_wargear("Spiked collar"), miniature=pet, paid=15)
        gang.refresh_from_db()

        sheet = render_gang(gang)
        by_name = {card.name: card for card in sheet.models}
        assert by_name["Cyber-mastiff"].owned_by == "Yolanda"
        assert by_name["Yolanda"].owned_by is None

        text = gang_to_text(gang)
        print("\n" + text)
        assert "Cyber-mastiff — 15cr  (owned by Yolanda)" in text
        assert "Yolanda — 155cr" in text

    def test_the_owner_s_card_says_the_wargear_brought_a_model(self, gang, bought):
        """A stored effect is noted by compute, never run by it."""
        sheet = render_gang(gang)
        yolanda = next(card for card in sheet.models if card.name == "Yolanda")

        (effect,) = yolanda.effects
        assert effect.description == "adds a Cyber-mastiff"
        assert effect.happened is True
        assert effect.provenance.source == "Cyber-mastiff (pet)"
        assert effect.provenance.source_kind == "wargear"

    def test_rendering_still_breeds_no_pets(self, gang, bought):
        from n26.core.models import Miniature

        before = Miniature.objects.count()
        render_gang(gang)
        render_gang(gang)
        assert Miniature.objects.count() == before
