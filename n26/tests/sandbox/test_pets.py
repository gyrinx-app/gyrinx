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

from n26.core.capture import differences, gang_state
from n26.core.models import Miniature
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled, ledger_for_gang
from n26.core.render import build_model_card, render_gang
from n26.core.render_text import gang_to_text
from n26.core.status import Status
from n26.library.authoring import targets_gang
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    assign,
    attach,
    buy_weapon_profile,
    create_counter,
    create_rule,
    create_wargear,
    create_weapon,
    create_weapon_accessory,
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

    def test_the_pets_own_page_costs_what_any_fighters_does(
        self, client, gang, bought, make_profile
    ):
        """Naming the owner reads the cause of the pet's membership and
        the model behind it, and both arrive with the page's own read of
        the model: a pet's page asks the database nothing a plain
        fighter's page does not."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        plain = hire(gang, make_profile("Plain ganger"), "Plain")
        client.force_login(gang.owner)

        def measure(miniature):
            url = reverse("n26-edit-fighter", args=[miniature.pk])
            assert client.get(url).status_code == 200
            with CaptureQueriesContext(connection) as captured:
                assert client.get(url).status_code == 200
            return len(captured.captured_queries)

        assert measure(pet_of(gang)) == measure(plain)

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
        assert (line.brought_in, line.brought_mark) == ((), "")

    def test_the_line_names_the_pet_once_it_is_named(self, client, gang, bought):
        rename(gang, pet_of(gang), "Fang")

        (line,) = pet_lines(card_of(render_gang(gang), "Yolanda"))
        assert (line.brought_in, line.brought_mark) == (("Fang",), " (Fang)")

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Cyber-mastiff (pet) (Fang)" in body
        assert "Equipment: Cyber-mastiff (pet) (Fang)" in gang_to_text(gang)

    def test_the_stash_line_names_the_pet(self, client, gang, mastiff_wargear):
        assign(mastiff_wargear, stash=gang.stash, paid=100)
        rename(gang, pet_of(gang), "Fang")

        (line,) = render_gang(gang).stash
        assert (line.name, line.brought_in) == ("Cyber-mastiff (pet)", ("Fang",))

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
        assert line.brought_in == ()
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

        assert pet_lines(told)[0].brought_in == ()
        assert pet_lines(found)[0].brought_in == ("Fang",)
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
        assert all(line.brought_in == () for line in sheet.stash)
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
        assert [(line.brought_mark, line.count) for line in on_card] == [
            (" (Fang)", 1),
            (" (Fang)", 1),
        ]
        assert [(line.brought_mark, line.count) for line in sheet.stash] == [
            (" (Fang)", 1),
            (" (Fang)", 1),
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
        assert sorted(line.brought_mark for line in on_card) == [" (Claw)", " (Fang)"]
        assert [line.count for line in on_card] == [1, 1]
        stashed = sheet.stash
        assert sorted(line.brought_mark for line in stashed) == [
            " (Rust)",
            " (Sprocket)",
        ]
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
        assert line.brought_in == ("Fang",)


class TestKitThatBringsTwoModels:
    """One piece of kit may carry two model-adding effects, and every
    model they hire names the same purchase. The line names them all,
    in roster order — "Twin collar (Fang, Rex)" — and stands alone as
    any pet-bearing line does."""

    @pytest.fixture
    def twin_collar(self, mastiff_profile, make_profile):
        collar = create_wargear("Twin collar", price=150)
        modifier(
            "The twin collar brings a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=collar,
        )
        modifier(
            "The twin collar brings a rat too",
            targets_model(),
            op_adds_model(make_profile("Giant rat", price=25)),
            carried_by=collar,
        )
        return collar

    def test_the_line_names_both_pets(self, gang, yolanda, twin_collar):
        assign(twin_collar, miniature=yolanda, paid=150)
        pets = Miniature.objects.filter(
            membership__gang=gang, membership__caused_by__isnull=False
        )
        assert pets.count() == 2
        rename(gang, pets.get(name="Cyber-mastiff"), "Fang")
        rename(gang, pets.get(name="Giant rat"), "Rex")

        (line,) = [
            line
            for line in card_of(render_gang(gang), "Yolanda").equipment
            if line.name == "Twin collar"
        ]
        assert line.brought_in == ("Fang", "Rex")
        assert line.brought_mark == " (Fang, Rex)"
        assert "Twin collar (Fang, Rex)" in gang_to_text(gang)

    def test_one_named_and_one_not_names_the_one(self, gang, yolanda, twin_collar):
        assign(twin_collar, miniature=yolanda, paid=150)
        rename(
            gang, Miniature.objects.get(membership__gang=gang, name="Giant rat"), "Rex"
        )
        (line,) = [
            line
            for line in card_of(render_gang(gang), "Yolanda").equipment
            if line.name == "Twin collar"
        ]
        assert line.brought_in == ("Rex",)

    def test_two_such_collars_in_the_stash_are_two_lines(self, gang, twin_collar):
        assign(twin_collar, stash=gang.stash, paid=150)
        assign(twin_collar, stash=gang.stash, paid=150)
        assert [line.count for line in render_gang(gang).stash] == [1, 1]

    def test_a_lone_card_finds_both_in_one_query(self, gang, yolanda, twin_collar):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute

        assign(twin_collar, miniature=yolanda, paid=150)
        for pet, name in (("Cyber-mastiff", "Fang"), ("Giant rat", "Rex")):
            rename(gang, Miniature.objects.get(membership__gang=gang, name=pet), name)
        owner = Miniature.objects.select_related("membership").get(pk=yolanda.pk)
        own = build_card(owner, with_statlines=True)
        computed = compute(own, build_modifier_index(carriers(own)))

        with CaptureQueriesContext(connection) as alone:
            found = build_model_card(owner, card=own, computed=computed)
        (line,) = [line for line in found.equipment if line.name == "Twin collar"]
        assert line.brought_in == ("Fang", "Rex")
        assert len(alone.captured_queries) == 1


class TestAModelTheGangBrings:
    """A collar the gang holds brings its pet to the gang, and its
    effect rides every member's card as the gang's — so no member's own
    card has a pet to look up."""

    def test_a_members_lone_card_looks_nothing_up(self, gang, yolanda, mastiff_profile):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute

        token = create_wargear("Beastmaster's token", price=100)
        modifier(
            "The token brings the gang a mastiff",
            targets_gang(),
            op_adds_model(mastiff_profile),
            carried_by=token,
        )
        assign(token, gang=gang, paid=100)
        assert Miniature.objects.filter(
            membership__gang=gang, name="Cyber-mastiff"
        ).exists()

        owner = Miniature.objects.select_related("membership").get(pk=yolanda.pk)
        own = build_card(owner, with_statlines=True)
        computed = compute(own, build_modifier_index(carriers(own)))
        assert any(
            isinstance(step.modifier.effect, type(token.modifiers.first().effect))
            for step in computed.plan
        )

        with CaptureQueriesContext(connection) as alone:
            build_model_card(owner, card=own, computed=computed)
        assert len(alone.captured_queries) == 0


class TestAnAccessoryThatBringsAModel:
    """A fitting is an assignable like any other, so one may bring a
    model. Its line under the weapon names the pet as a gear line would,
    on the sheet, the print and the text card."""

    @pytest.fixture
    def fitted(self, gang, yolanda, mastiff_profile):
        gun = create_weapon("Lasgun", price=15, profiles=[("", 0)])
        leash = create_weapon_accessory("Leash mount", price=100)
        modifier(
            "The leash mount brings a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=leash,
        )
        held = give_weapon(yolanda, gun, paid=15)
        attach(held, leash, paid=100)
        rename(gang, pet_of(gang), "Fang")
        return held

    def test_the_accessory_line_names_the_pet(self, client, gang, yolanda, fitted):
        (weapon,) = card_of(render_gang(gang), "Yolanda").weapons
        (accessory,) = weapon.accessories
        assert (accessory.name, accessory.brought_in) == ("Leash mount", ("Fang",))

        assert "+ Leash mount (Fang)" in gang_to_text(gang)

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Leash mount (Fang)" in body
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        assert "+ Leash mount (Fang)" in paper
        page = client.get(
            reverse("n26-edit-fighter", args=[yolanda.pk])
        ).content.decode()
        assert 'aria-label="More for Leash mount (Fang)"' in page


class TestAWeaponThatBringsAModel:
    """A weapon carries modifiers as any assignable does, so one may
    bring a model. Its line names the pet after the slot mark wherever
    the weapon's name is drawn — the sheet, the menu's label, the print
    card, the print picker and the text card — while a fitting that
    brought one still names its own."""

    @pytest.fixture
    def lash(self, mastiff_profile):
        lash = create_weapon("Beast lash", price=60, profiles=[("", 0)], slots=2)
        modifier(
            "The lash brings a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=lash,
        )
        return lash

    @pytest.fixture
    def armed(self, gang, yolanda, lash):
        held = give_weapon(yolanda, lash, paid=60)
        rename(gang, pet_of(gang), "Fang")
        return held

    def test_the_weapon_line_names_the_pet_after_its_mark(self, gang, armed):
        (weapon,) = card_of(render_gang(gang), "Yolanda").weapons
        assert (weapon.name, weapon.slot_mark, weapon.brought_in) == (
            "Beast lash",
            "*",
            ("Fang",),
        )
        assert weapon.brought_mark == " (Fang)"
        assert "    Beast lash* (Fang) — 60cr" in gang_to_text(gang)

    def test_every_page_that_draws_the_weapons_name_draws_the_pet(
        self, client, gang, yolanda, armed
    ):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Beast lash* (Fang)" in body
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        assert "Beast lash* (Fang)" in paper
        setup = client.get(reverse("n26-print-setup", args=[gang.pk])).content.decode()
        assert "Beast lash* (Fang)" in setup
        page = client.get(
            reverse("n26-edit-fighter", args=[yolanda.pk])
        ).content.decode()
        assert 'aria-label="More for Beast lash* (Fang)"' in page

    def test_the_line_reads_bare_until_the_pet_is_named(self, gang, yolanda, lash):
        give_weapon(yolanda, lash, paid=60)
        (weapon,) = card_of(render_gang(gang), "Yolanda").weapons
        assert weapon.brought_in == ()
        assert "Beast lash*" in gang_to_text(gang)
        assert "Beast lash* (" not in gang_to_text(gang)

    def test_a_fitting_names_its_own_pet_and_the_weapon_does_not(
        self, gang, yolanda, armed, make_profile
    ):
        leash = create_weapon_accessory("Leash mount", price=100)
        modifier(
            "The leash mount brings a rat",
            targets_model(),
            op_adds_model(make_profile("Giant rat", price=25)),
            carried_by=leash,
        )
        attach(armed, leash, paid=100)
        rename(
            gang, Miniature.objects.get(membership__gang=gang, name="Giant rat"), "Rex"
        )

        (weapon,) = card_of(render_gang(gang), "Yolanda").weapons
        (accessory,) = weapon.accessories
        assert (weapon.brought_in, accessory.brought_in) == (("Fang",), ("Rex",))
        text = gang_to_text(gang)
        assert "Beast lash* (Fang)" in text
        assert "+ Leash mount (Rex)" in text

    def test_a_lone_card_finds_the_pet_in_one_query(self, gang, yolanda, armed):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute

        owner = Miniature.objects.select_related("membership").get(pk=yolanda.pk)
        own = build_card(owner, with_statlines=True)
        computed = compute(own, build_modifier_index(carriers(own)))

        with CaptureQueriesContext(connection) as alone:
            (weapon,) = build_model_card(owner, card=own, computed=computed).weapons
        assert weapon.brought_in == ("Fang",)
        assert len(alone.captured_queries) == 1


class TestARuleThatBringsAModel:
    """A rule is an assignable too, so one may bring a model, and the
    Rules row names the pet as the screen draws it — the text card says
    the same words as the sheet."""

    def test_the_text_card_names_the_pet_as_the_sheet_does(
        self, client, gang, yolanda, mastiff_profile
    ):
        handler = create_rule("Beast handler")
        modifier(
            "A beast handler keeps a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=handler,
        )
        assign(handler, miniature=yolanda)
        rename(gang, pet_of(gang), "Fang")

        (rule,) = card_of(render_gang(gang), "Yolanda").rules
        assert (rule.name, rule.brought_in) == ("Beast handler", ("Fang",))
        assert "  Rules: Beast handler (Fang)" in gang_to_text(gang)

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Beast handler (Fang)" in body


class TestANamedProfileThatBringsAModel:
    """A weapon's profile is an assignable too, so a named one — paid
    ammo — may bring a model. The pet is named on the profile's own
    line, the one with the profile's menu, and not on the weapon's:
    the sheet, the print card, the text card and the fighter page all
    put it there. The unnamed line shares the weapon's row, so what it
    brought is written after the weapon's name."""

    @pytest.fixture
    def autogun(self, mastiff_profile):
        gun = create_weapon(
            "Autogun", price=15, profiles=[("", 0), ("Beast rounds", 10)]
        )
        modifier(
            "Beast rounds bring a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=gun.profiles.get(name="Beast rounds"),
        )
        return gun

    @pytest.fixture
    def loaded(self, gang, yolanda, autogun):
        held = give_weapon(yolanda, autogun, paid=15)
        buy_weapon_profile(held, autogun.profiles.get(name="Beast rounds"))
        rename(gang, pet_of(gang), "Fang")
        return held

    def test_the_profiles_line_names_the_pet_and_the_weapons_does_not(
        self, gang, loaded
    ):
        (weapon,) = card_of(render_gang(gang), "Yolanda").weapons
        (rounds,) = weapon.named_profiles
        assert (weapon.brought_in, rounds.name, rounds.brought_in) == (
            (),
            "Beast rounds",
            ("Fang",),
        )
        assert rounds.brought_mark == " (Fang)"
        text = gang_to_text(gang)
        assert "      - Beast rounds (Fang) (+10cr)" in text
        assert "Autogun (" not in text

    def test_every_page_that_draws_the_profile_draws_the_pet(
        self, client, gang, yolanda, loaded
    ):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Beast rounds (Fang)" in body
        assert "Autogun (Fang)" not in body
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        assert "Beast rounds (Fang)" in paper
        assert "Autogun (Fang)" not in paper
        page = client.get(
            reverse("n26-edit-fighter", args=[yolanda.pk])
        ).content.decode()
        assert 'aria-label="More for Beast rounds (Fang)"' in page
        assert 'aria-label="More for Autogun (Fang)"' not in page

    def test_what_the_unnamed_line_brought_is_written_on_the_weapon(
        self, gang, yolanda, mastiff_profile
    ):
        gun = create_weapon("Lasgun", price=15, profiles=[("", 0)])
        modifier(
            "The lasgun's own line brings a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=gun.profiles.get(name=""),
        )
        give_weapon(yolanda, gun, paid=15)
        rename(gang, pet_of(gang), "Fang")

        (weapon,) = card_of(render_gang(gang), "Yolanda").weapons
        assert (weapon.brought_in, weapon.own_line.brought_in) == (("Fang",), ())
        assert "    Lasgun (Fang) — 15cr" in gang_to_text(gang)

    def test_a_profile_assigned_straight_to_the_model_names_it_on_its_own_line(
        self, gang, yolanda, autogun
    ):
        rounds = autogun.profiles.get(name="Beast rounds")
        assign(rounds, miniature=yolanda, paid=10)
        rename(gang, pet_of(gang), "Fang")

        (weapon,) = card_of(render_gang(gang), "Yolanda").weapons
        (line,) = weapon.named_profiles
        assert (weapon.brought_in, line.brought_in) == ((), ("Fang",))
        assert "- Beast rounds (Fang)" in gang_to_text(gang)

    def test_a_lone_card_finds_the_pet_in_one_query(self, gang, yolanda, loaded):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute

        owner = Miniature.objects.select_related("membership").get(pk=yolanda.pk)
        own = build_card(owner, with_statlines=True)
        computed = compute(own, build_modifier_index(carriers(own)))

        with CaptureQueriesContext(connection) as alone:
            (weapon,) = build_model_card(owner, card=own, computed=computed).weapons
        (rounds,) = weapon.named_profiles
        assert rounds.brought_in == ("Fang",)
        assert len(alone.captured_queries) == 1


class TestTheCaptureNamesThePet:
    """A conversion proves itself by comparing a gang's pages before and
    after, and a kit line is what the reader is told: "Collar (Fang)"
    and "Collar" say different things, so the capture writes the pet's
    name with the kit's and a conversion that lost the link is a
    difference rather than a silence."""

    def owner_state(self, gang):
        return next(
            model
            for model in gang_state(gang)["models"].values()
            if model["name"] == "Yolanda"
        )

    def test_a_gear_line_is_captured_with_the_pets_name(self, gang, bought):
        rename(gang, pet_of(gang), "Fang")
        assert ("Cyber-mastiff (pet) (Fang)", 100) in self.owner_state(gang)[
            "equipment"
        ]

    def test_losing_the_link_is_a_difference_on_the_owners_line(
        self, gang, yolanda, bought
    ):
        pet = pet_of(gang)
        rename(gang, pet, "Fang")
        before = gang_state(gang)
        rename(gang, pet, "Claw")
        after = gang_state(gang)

        found = differences(before, after)
        assert any(
            path.startswith(f"models.{yolanda.pk}.equipment") for path in found
        ), found

    def test_a_weapon_its_fitting_and_its_profile_are_captured_with_theirs(
        self, gang, yolanda, mastiff_profile, make_profile
    ):
        gun = create_weapon("Beast lash", price=60, profiles=[("", 0), ("Barbs", 10)])
        modifier(
            "The lash brings a mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=gun,
        )
        modifier(
            "The barbs bring a rat",
            targets_model(),
            op_adds_model(make_profile("Giant rat", price=25)),
            carried_by=gun.profiles.get(name="Barbs"),
        )
        leash = create_weapon_accessory("Leash mount", price=100)
        modifier(
            "The leash mount brings a hound",
            targets_model(),
            op_adds_model(make_profile("Hound", price=30)),
            carried_by=leash,
        )
        held = give_weapon(yolanda, gun, paid=60)
        buy_weapon_profile(held, gun.profiles.get(name="Barbs"))
        attach(held, leash, paid=100)
        for pet, name in (
            ("Cyber-mastiff", "Fang"),
            ("Giant rat", "Rex"),
            ("Hound", "Bo"),
        ):
            rename(gang, Miniature.objects.get(membership__gang=gang, name=pet), name)

        (weapon,) = self.owner_state(gang)["weapons"]
        name, _, profiles, accessories, _ = weapon
        assert name == "Beast lash (Fang)"
        assert [profile[0] for profile in profiles] == ["", "Barbs (Rex)"]
        assert accessories == ("Leash mount (Bo)",)
