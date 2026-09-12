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
from django.urls import reverse

from n26.core.models import Miniature
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled, ledger_for_gang
from n26.core.render import build_model_card, render_gang
from n26.core.render_text import gang_to_text
from n26.core.status import Status
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    assign,
    create_counter,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    op_adds_model,
    op_changes_counter,
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
        assert "Cyber-mastiff — 15cr  (Owned by Yolanda)" in text
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


def rename(gang, miniature, name):
    with operation(gang, actor=gang.owner) as op:
        op.rename(miniature, name)


def card_of(sheet, name):
    return next(card for card in [*sheet.models, *sheet.dead] if card.name == name)


def pet_lines(card):
    return [line for line in card.equipment if line.name == "Cyber-mastiff (pet)"]


class TestThePetCardNamesItsOwner:
    """The link between a pet and its keeper is derived, and both cards
    say it: the pet names its owner, under the profile name, and the
    gang sheet makes that name a link to the owner's card. Where the
    collar was bought into the stash there is no owner, and the card
    says where the collar is instead."""

    def test_the_card_carries_the_owner_and_the_owners_id(self, gang, bought, yolanda):
        sheet = render_gang(gang)
        pet = card_of(sheet, "Cyber-mastiff")
        assert (pet.owned_by, pet.owned_by_id, pet.in_stash) == (
            "Yolanda",
            str(yolanda.pk),
            False,
        )
        assert pet.owner_line == "Owned by Yolanda"
        owner = card_of(sheet, "Yolanda")
        assert (owner.owned_by, owner.owned_by_id, owner.owner_line) == (
            None,
            "",
            "",
        )

    def test_the_gang_sheet_links_the_owners_card(self, client, gang, bought, yolanda):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert f'id="model-{yolanda.pk}"' in body
        assert f'href="#model-{yolanda.pk}"' in body
        assert "Owned by" in body

    def test_a_reader_who_does_not_own_the_gang_gets_the_link_too(
        self, client, gang, bought, yolanda
    ):
        client.force_login(User.objects.create_user("reader"))
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert f'href="#model-{yolanda.pk}"' in body

    def test_the_models_own_page_says_it_in_words(self, client, gang, bought):
        client.force_login(gang.owner)
        url = reverse("n26-edit-fighter", args=[pet_of(gang).pk])
        body = client.get(url).content.decode()

        assert "Owned by" in body
        assert "Yolanda" in body
        assert 'href="#model-' not in body

    def test_a_pet_bought_into_the_stash_says_so(self, gang, mastiff_wargear):
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        sheet = render_gang(gang)
        pet = card_of(sheet, "Cyber-mastiff")
        assert (pet.owned_by, pet.owned_by_id, pet.in_stash) == (None, "", True)
        assert pet.owner_line == "In the stash"
        assert "Cyber-mastiff — 0cr  (In the stash)" in gang_to_text(gang)

    def test_an_owner_who_has_left_the_roster_is_named_in_words(
        self, client, gang, bought, yolanda
    ):
        """The collar stays live when its bearer leaves, and the pet still
        names them — but a link to a card the sheet does not draw lands
        nowhere, so the name is words."""
        remove(yolanda.membership)

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Owned by" in body
        assert "Yolanda" in body
        assert f'href="#model-{yolanda.pk}"' not in body
        assert "Yolanda" not in [card.name for card in render_gang(gang).models]

    def test_the_print_page_and_the_text_card_say_the_same_words(
        self, client, gang, bought
    ):
        client.force_login(gang.owner)
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        assert "Cyber-mastiff · Owned by Yolanda" in paper
        assert "(Owned by Yolanda)" in gang_to_text(gang)


class TestTheWargearLineNamesThePet:
    """The kit that brought a pet says which model it brought, after its
    own name — "Cyber-mastiff (pet) (Fang)" — once the owner has named
    the pet. Until then the pet's name is its profile's, which the line
    already says, so it reads bare. The same words go on the stash line,
    the print page and the text card, and a dead pet comes off the line:
    the line is what the model carries, and a dead pet is not that."""

    def test_the_line_reads_bare_until_the_pet_is_named(self, gang, bought):
        (line,) = pet_lines(card_of(render_gang(gang), "Yolanda"))
        assert (line.brought_in, line.brought_mark) == ("", "")

    def test_the_line_names_the_pet_once_it_is_named(self, client, gang, bought):
        rename(gang, pet_of(gang), "Fang")

        (line,) = pet_lines(card_of(render_gang(gang), "Yolanda"))
        assert (line.brought_in, line.brought_mark) == ("Fang", " (Fang)")

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Cyber-mastiff (pet) (Fang)" in body
        assert "Equipment: Cyber-mastiff (pet) (Fang)" in gang_to_text(gang)

    def test_the_stash_line_names_the_pet(self, client, gang, mastiff_wargear):
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        rename(gang, pet_of(gang), "Fang")

        (line,) = render_gang(gang).stash
        assert (line.name, line.brought_in) == ("Cyber-mastiff (pet)", "Fang")

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Cyber-mastiff (pet) (Fang)" in body
        assert 'aria-label="Actions for Cyber-mastiff (pet) (Fang)"' in body
        assert "  Cyber-mastiff (pet) (Fang) — 100cr" in gang_to_text(gang)

    def test_the_print_page_names_the_pet_on_the_card_and_in_the_stash(
        self, client, gang, bought, mastiff_wargear
    ):
        rename(gang, pet_of(gang), "Fang")
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        rename(
            gang,
            Miniature.objects.get(
                membership__gang=gang,
                membership__caused_by__stash_root__isnull=False,
            ),
            "Claw",
        )

        client.force_login(gang.owner)
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        assert "Cyber-mastiff (pet) (Fang)" in paper
        assert "Cyber-mastiff (pet) (Claw)" in paper

    def test_a_pet_left_out_of_the_print_is_still_named_on_its_owner(
        self, client, gang, bought, yolanda
    ):
        rename(gang, pet_of(gang), "Fang")
        client.force_login(gang.owner)
        url = reverse("n26-print", args=[gang.pk]) + f"?pick=1&fighters={yolanda.pk}"
        paper = client.get(url).content.decode()
        assert "Cyber-mastiff (pet) (Fang)" in paper
        assert "Owned by" not in paper

    def test_a_dead_pet_comes_off_the_line(self, gang, bought):
        pet = pet_of(gang)
        rename(gang, pet, "Fang")
        with operation(gang, actor=gang.owner) as op:
            op.set_status(pet, Status.DEAD)

        sheet = render_gang(gang)
        (line,) = pet_lines(card_of(sheet, "Yolanda"))
        assert line.brought_in == ""
        # The dead pet keeps its card, and its card still says whose it was.
        assert card_of(sheet, "Fang").owned_by == "Yolanda"

    def test_the_models_own_page_names_the_pet(self, client, gang, bought, yolanda):
        rename(gang, pet_of(gang), "Fang")
        client.force_login(gang.owner)
        url = reverse("n26-edit-fighter", args=[yolanda.pk])
        body = client.get(url).content.decode()
        assert "Cyber-mastiff (pet) (Fang)" in body
        assert 'aria-label="More for Cyber-mastiff (pet) (Fang)"' in body

    def test_a_card_built_alone_looks_the_pet_up_once(self, gang, bought, yolanda):
        """A card with no roster to hand asks one question for its
        pets, and a card given the roster's answer asks none."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute

        rename(gang, pet_of(gang), "Fang")
        owner = Miniature.objects.select_related("membership").get(pk=yolanda.pk)
        own = build_card(owner, with_statlines=True)
        computed = compute(own, build_modifier_index(carriers(own)))

        with CaptureQueriesContext(connection) as given:
            told = build_model_card(owner, card=own, computed=computed, brought_in={})
        with CaptureQueriesContext(connection) as alone:
            found = build_model_card(owner, card=own, computed=computed)

        assert pet_lines(told)[0].brought_in == ""
        assert pet_lines(found)[0].brought_in == "Fang"
        assert len(alone.captured_queries) == len(given.captured_queries) + 1

    def test_a_card_whose_kit_brings_nothing_looks_nothing_up(self, gang, yolanda):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute

        assign(create_wargear("Respirator"), miniature=yolanda, paid=15)
        owner = Miniature.objects.select_related("membership").get(pk=yolanda.pk)
        own = build_card(owner, with_statlines=True)
        computed = compute(own, build_modifier_index(carriers(own)))

        with CaptureQueriesContext(connection) as alone:
            build_model_card(owner, card=own, computed=computed)
        assert len(alone.captured_queries) == 0

    def test_two_collars_with_unnamed_pets_are_two_lines(
        self, gang, bought, yolanda, mastiff_wargear
    ):
        """A line for one collar never stands for another: what each
        brought is on the roster under its own card, whatever it is
        called. So two collars whose pets are still named for their
        profile stay apart, on the card and in the stash alike."""
        assign(mastiff_wargear, miniature=yolanda, paid=100)
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        assign(mastiff_wargear, stash=gang.stash, paid=100)

        sheet = render_gang(gang)
        assert [line.count for line in pet_lines(card_of(sheet, "Yolanda"))] == [1, 1]
        assert [line.count for line in sheet.stash] == [1, 1]
        assert all(line.brought_in == "" for line in sheet.stash)
        assert "(x2)" not in gang_to_text(gang)

    def test_two_collars_with_pets_of_one_name_are_two_lines(
        self, gang, bought, yolanda, mastiff_wargear
    ):
        assign(mastiff_wargear, miniature=yolanda, paid=100)
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        for pet in Miniature.objects.filter(
            membership__gang=gang, membership__caused_by__isnull=False
        ):
            rename(gang, pet, "Fang")

        sheet = render_gang(gang)
        on_card = pet_lines(card_of(sheet, "Yolanda"))
        assert [(line.brought_in, line.count) for line in on_card] == [
            ("Fang", 1),
            ("Fang", 1),
        ]
        assert [(line.brought_in, line.count) for line in sheet.stash] == [
            ("Fang", 1),
            ("Fang", 1),
        ]

    def test_two_collars_whose_pets_have_died_are_two_lines_in_the_stash(
        self, gang, mastiff_wargear
    ):
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        with operation(gang, actor=gang.owner) as op:
            for pet in Miniature.objects.filter(membership__gang=gang):
                op.set_status(pet, Status.DEAD)

        assert [line.count for line in render_gang(gang).stash] == [1, 1]

    def test_a_card_with_a_stored_effect_but_no_pet_looks_nothing_up(
        self, gang, yolanda, default_pack
    ):
        """Moving a counter is a stored effect too, and a card carrying
        one has no pet to ask after."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute

        kills = create_counter("Kill Count")
        trophy = create_wargear("Trophy rack", price=10)
        modifier(
            "The rack marks a kill",
            targets_model(),
            op_changes_counter(kills, "add", 1),
            carried_by=trophy,
        )
        assign(kills, miniature=yolanda)
        assign(trophy, miniature=yolanda, paid=10)
        owner = Miniature.objects.select_related("membership").get(pk=yolanda.pk)
        own = build_card(owner, with_statlines=True)
        computed = compute(own, build_modifier_index(carriers(own)))
        assert any(
            getattr(step.modifier.effect, "is_stored", False) for step in computed.plan
        )

        with CaptureQueriesContext(connection) as alone:
            build_model_card(owner, card=own, computed=computed)
        assert len(alone.captured_queries) == 0

    def test_two_named_pets_are_two_lines_on_the_card_and_in_the_stash(
        self, gang, bought, yolanda, mastiff_wargear
    ):
        assign(mastiff_wargear, miniature=yolanda, paid=100)
        for pet, name in zip(
            Miniature.objects.filter(
                membership__gang=gang, membership__caused_by__miniature_root=yolanda
            ).order_by("membership__created"),
            ("Fang", "Claw"),
            strict=True,
        ):
            rename(gang, pet, name)
        for name in ("Rust", "Sprocket"):
            assign(mastiff_wargear, stash=gang.stash, paid=100)
            rename(
                gang,
                Miniature.objects.get(
                    membership__gang=gang,
                    membership__caused_by__stash_root__isnull=False,
                    name="Cyber-mastiff",
                ),
                name,
            )

        sheet = render_gang(gang)
        on_card = pet_lines(card_of(sheet, "Yolanda"))
        assert sorted(line.brought_in for line in on_card) == ["Claw", "Fang"]
        assert [line.count for line in on_card] == [1, 1]
        stashed = sheet.stash
        assert sorted(line.brought_in for line in stashed) == ["Rust", "Sprocket"]
        assert [line.count for line in stashed] == [1, 1]
        assert "(x2)" not in gang_to_text(gang)


class TestAPetBroughtByAHiddenPart:
    """The purchase that a pet's membership names may be a hidden carrier
    riding under the visible kit rather than the kit itself. The kit's
    line names the pet all the same: the whole of the line is asked."""

    def test_the_kit_line_names_the_pet(self, gang, yolanda, mastiff_profile):
        from n26.tests.sandbox.actions import create_hidden

        tag = create_hidden("The collar's tag brings a mastiff")
        modifier(
            "Collar tag brings a pet",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=tag,
        )
        collar = create_wargear("Mastiff collar", price=100)
        held = assign(collar, miniature=yolanda, paid=100)
        with operation(gang, actor=gang.owner) as op:
            op.assign(tag, parent=held, caused_by=held)
        rename(gang, pet_of(gang), "Fang")

        (line,) = [
            line
            for line in card_of(render_gang(gang), "Yolanda").equipment
            if line.name == "Mastiff collar"
        ]
        assert line.brought_in == "Fang"
