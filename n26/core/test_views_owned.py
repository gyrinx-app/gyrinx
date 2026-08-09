"""What a gang already owns: selling it, handing it on, taking it off.

The three routes are addressed by assignment rather than by fighter, so
what is pinned here is the wiring around ``Operation.sell``, ``move`` and
``remove`` — that a press writes the right one, that the books still
agree afterwards, that nobody reaches another player's rows, and that a
GET writes nothing at all.

The arithmetic itself has its own tests, in the sandbox suite where the
operations live.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Assignment, Gang, Miniature
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import create_wargear

pytestmark = pytest.mark.django_db

#: A page a reader could be on. Every control an owned row draws is a
#: confirmation over the page it was drawn on, so building one takes an
#: address; these tests supply a fixed one rather than a real request's.
AT = "/n26/fighters/vex/equip/?list=1"


@pytest.fixture
def tester(db):
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang(gang_type, tester):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=200,
        credits=200,
    )


@pytest.fixture
def profile(make_profile, make_statline):
    entry = make_profile("Ganger", price=0)
    make_statline(entry, movement=5, weapon_skill=4, toughness=3)
    return entry


@pytest.fixture
def fighter(gang, profile, tester):
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex")


@pytest.fixture
def other(gang, profile, tester):
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Nell")


@pytest.fixture
def stash(gang):
    from n26.core.models import Stash

    held, _ = Stash.objects.get_or_create(gang=gang)
    return held


@pytest.fixture
def sword(gang, fighter, tester):
    """A hundred credits of sword, haggled down to sixty."""
    thing = create_wargear("Sword", price=100)
    with operation(gang, actor=tester) as op:
        return op.buy(fighter, thing=thing, paid=60, list_price=100, discount=40)


def url(name, assignment):
    return reverse(name, args=[assignment.pk])


class TestSelling:
    """Half of what the thing is worth, into the gang's credits, and the
    thing off the card."""

    def test_a_sale_credits_the_gang_and_leaves_the_books_straight(
        self, client, tester, gang, sword
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(url("n26-sell", sword))

        assert response.status_code == 302
        gang.refresh_from_db()
        # Half of the hundred it is worth, not half of the sixty paid.
        assert gang.credits == before + 50
        assert gang.rating == 0
        sword.refresh_from_db()
        assert sword.archived is True
        assert_reconciled(gang)

    def test_the_press_lands_back_on_the_shop_it_came_from(
        self, client, tester, fighter, sword, house_list
    ):
        client.force_login(tester)
        response = client.post(url("n26-sell", sword), {"list": str(house_list.pk)})
        assert response.url == (
            reverse("n26-equip", args=[fighter.pk]) + f"?list={house_list.pk}"
        )

    def test_a_second_press_of_a_stale_button_sells_nothing_twice(
        self, client, tester, gang, sword
    ):
        """The archived row is gone as far as these routes are concerned,
        so a reloaded confirmation cannot pay the gang a second time."""
        client.force_login(tester)
        client.post(url("n26-sell", sword))
        gang.refresh_from_db()
        after_one = gang.credits

        assert client.post(url("n26-sell", sword)).status_code == 404

        gang.refresh_from_db()
        assert gang.credits == after_one
        assert_reconciled(gang)


class TestReassigning:
    """A move changes where a thing lives and nothing else."""

    def test_a_thing_moves_to_another_model_at_the_same_rating(
        self, client, tester, gang, fighter, other, sword
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(url("n26-reassign", sword), {"miniature": str(other.pk)})

        assert response.status_code == 302
        sword.refresh_from_db()
        assert sword.miniature_id == other.pk
        gang.refresh_from_db()
        assert gang.credits == before
        # A move never re-prices: the gang is worth what it was.
        assert gang.rating == 100
        fighter.refresh_from_db()
        other.refresh_from_db()
        assert fighter.rating == 0
        assert other.rating == 100
        assert_reconciled(gang)

    def test_a_thing_moves_to_the_stash(self, client, tester, gang, sword, stash):
        client.force_login(tester)

        response = client.post(url("n26-reassign", sword), {"to": "stash"})

        assert response.status_code == 302
        sword.refresh_from_db()
        assert sword.stash_id == stash.pk
        gang.refresh_from_db()
        stash.refresh_from_db()
        # Stashed gear is wealth, not rating.
        assert gang.rating == 0
        assert stash.rating == 100
        assert_reconciled(gang)

    def test_somebody_elses_model_is_nowhere_to_move_it_to(
        self, client, tester, gang, sword, make_profile
    ):
        """The select only offers this gang's roster, so this can only be a
        hand-made press — and it moves nothing."""
        stranger = User.objects.create_user("stranger")
        theirs = Gang.objects.create(
            name="Their Gang",
            owner=stranger,
            gang_type=gang.gang_type,
            starting_credits=200,
            credits=200,
        )
        with operation(theirs, actor=stranger) as op:
            outsider = op.hire(make_profile("Bruiser", price=0), "Grud")

        client.force_login(tester)
        response = client.post(
            url("n26-reassign", sword), {"miniature": str(outsider.pk)}
        )

        assert response.status_code == 302
        sword.refresh_from_db()
        assert sword.miniature_id is not None
        assert sword.gang_root_id == gang.pk
        assert_reconciled(gang)

    def test_a_part_cannot_be_re_homed_on_its_own(
        self, client, tester, gang, fighter, other
    ):
        """Ammo belongs to its gun. The listing offers no control for this,
        and the route refuses it rather than raising."""
        from n26.library.authoring import add_weapon_profile, create_weapon

        autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
        warp = add_weapon_profile(autogun, name="warp round", price=10)
        with operation(gang, actor=tester) as op:
            gun = op.give_weapon(fighter, autogun, paid=20)
            ammo = op.buy_weapon_profile(gun, warp)

        client.force_login(tester)
        response = client.post(url("n26-reassign", ammo), {"miniature": str(other.pk)})

        assert response.status_code == 302
        ammo.refresh_from_db()
        assert ammo.parent_id == gun.pk
        assert_reconciled(gang)


class TestRemoving:
    """Off the card, and the money stays spent."""

    def test_removing_keeps_the_spend_and_drops_the_rating(
        self, client, tester, gang, sword
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(url("n26-remove", sword))

        assert response.status_code == 302
        gang.refresh_from_db()
        assert gang.credits == before
        assert gang.rating == 0
        sword.refresh_from_db()
        assert sword.archived is True
        assert_reconciled(gang)

    def test_a_part_goes_and_leaves_its_gun_behind(self, client, tester, gang, fighter):
        from n26.library.authoring import add_weapon_profile, create_weapon

        autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
        warp = add_weapon_profile(autogun, name="warp round", price=10)
        with operation(gang, actor=tester) as op:
            gun = op.give_weapon(fighter, autogun, paid=20)
            ammo = op.buy_weapon_profile(gun, warp)

        client.force_login(tester)
        client.post(url("n26-remove", ammo))

        ammo.refresh_from_db()
        gun.refresh_from_db()
        assert ammo.archived is True
        assert gun.archived is False
        gang.refresh_from_db()
        assert gang.rating == 20
        assert_reconciled(gang)


class TestWhatMayBePressedOn:
    """These acts are about kit, and a gang holds a great deal that is not
    kit — every bit of it an assignment with a primary key of its own.

    The row naming a model's profile *is* the model: selling it would take
    the fighter off the roster with everything they carry, and pay half the
    price of the profile for the lot. The row naming the gang's type is the
    gang. A skill is what a fighter knows, an equipment list is where they
    shop. None of them is a possession, and none of these routes will touch
    one — whatever a hand-made URL says.
    """

    @pytest.mark.parametrize("route", ["n26-sell", "n26-reassign", "n26-remove"])
    def test_a_fighter_is_not_kit(self, client, tester, gang, fighter, sword, route):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        assert client.post(url("n26-sell", fighter.membership)).status_code == 404
        assert client.post(url(route, fighter.membership)).status_code == 404

        fighter.membership.refresh_from_db()
        sword.refresh_from_db()
        gang.refresh_from_db()
        # Still on the roster, still holding their sword, and the gang is
        # neither richer nor poorer for the attempt.
        assert fighter.membership.archived is False
        assert sword.archived is False
        assert list(Miniature.objects.filter(membership__gang=gang)) == [fighter]
        assert gang.credits == before
        assert gang.rating == 100
        assert_reconciled(gang)

    @pytest.mark.parametrize("route", ["n26-sell", "n26-reassign", "n26-remove"])
    def test_the_gang_itself_is_not_kit(self, client, tester, gang, route):
        """The founding row carries the gang's type, its equipment lists and
        every gang-wide rule. Taking it away would take all of that."""
        from n26.core.operations import operation as write

        with write(gang, actor=tester) as op:
            founding = op.found(gang.gang_type)

        client.force_login(tester)
        assert client.post(url(route, founding)).status_code == 404

        founding.refresh_from_db()
        gang.refresh_from_db()
        assert founding.archived is False
        assert gang.founding_id == founding.pk
        assert_reconciled(gang)

    @pytest.mark.parametrize("route", ["n26-sell", "n26-reassign", "n26-remove"])
    def test_what_a_fighter_knows_is_not_kit(
        self, client, tester, gang, fighter, route
    ):
        """A skill for five credits would be a tap, not a trade — and a
        removal here would be a way to unlearn by URL."""
        from n26.library.authoring import create_skill

        with operation(gang, actor=tester) as op:
            learned = op.learn(fighter, create_skill("Marksman"))

        client.force_login(tester)
        assert client.post(url(route, learned)).status_code == 404

        learned.refresh_from_db()
        assert learned.archived is False
        assert_reconciled(gang)

    def test_the_shop_offers_none_of_them_either(self, gang, fighter, tester, sword):
        """One rule, read by the listing that draws the controls and by the
        routes behind them, so a screen can never offer what a press would
        refuse."""
        from n26.core.card import build_card
        from n26.core.owned import owned_things, thing_key
        from n26.library.authoring import create_skill

        with operation(gang, actor=tester) as op:
            op.learn(fighter, create_skill("Marksman"))

        held = owned_things(build_card(fighter), AT)
        assert thing_key(sword.assignable) in held
        assert thing_key(fighter.membership.assignable) not in held
        assert not [key for key in held if key.startswith("library.skill:")]


class TestWhoMayPress:
    """Every one of these writes, so every one of them is guarded — and
    none of them is a GET."""

    @pytest.mark.parametrize("route", ["n26-sell", "n26-reassign", "n26-remove"])
    def test_a_stranger_finds_nothing(self, client, gang, sword, route):
        stranger = User.objects.create_user("stranger")
        client.force_login(stranger)

        assert client.post(url(route, sword)).status_code == 404

        sword.refresh_from_db()
        assert sword.archived is False
        assert_reconciled(gang)

    @pytest.mark.parametrize("route", ["n26-sell", "n26-reassign", "n26-remove"])
    def test_signing_out_is_signing_out(self, client, sword, route):
        response = client.post(url(route, sword))
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    @pytest.mark.parametrize("route", ["n26-sell", "n26-reassign", "n26-remove"])
    def test_a_get_writes_nothing(self, client, tester, gang, sword, route):
        """A link that spent money by being followed would be spent by a
        crawler, a prefetch, or a reload of the wrong page."""
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        assert client.get(url(route, sword)).status_code == 405

        sword.refresh_from_db()
        gang.refresh_from_db()
        assert sword.archived is False
        assert gang.credits == before
        assert_reconciled(gang)

    @pytest.mark.parametrize("route", ["n26-sell", "n26-reassign", "n26-remove"])
    def test_a_pk_that_is_not_a_ulid_is_not_found(self, client, tester, route):
        client.force_login(tester)
        assert client.post(reverse(route, args=["nonsense"])).status_code == 404


@pytest.fixture
def house_list(gang, tester):
    thing = create_wargear("Knife", price=10)
    from n26.library.authoring import create_collection

    collection = create_collection("House List", entries=[thing])
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


def test_the_things_a_fighter_holds_are_counted_off_the_card(
    gang, fighter, tester, sword
):
    """The count a listing row shows is of live rows on this fighter, read
    from the card the page already built — no query per row."""
    from n26.core.card import build_card
    from n26.core.owned import owned_things, thing_key

    held = owned_things(build_card(fighter), AT)
    assert len(held[thing_key(sword.assignable)]) == 1

    with operation(gang, actor=tester) as op:
        op.buy(fighter, thing=sword.assignable, paid=100)
    assert len(owned_things(build_card(fighter), AT)[thing_key(sword.assignable)]) == 2

    with operation(gang, actor=tester) as op:
        op.remove(sword)
    # Archived rows are not held: the fighter has one sword, not two.
    assert len(owned_things(build_card(fighter), AT)[thing_key(sword.assignable)]) == 1
    assert_reconciled(gang)


def test_a_part_is_offered_no_move(gang, fighter, tester):
    """A part hangs off its parent and cannot be re-homed alone, so the
    structure a row draws from has no move for it to offer."""
    from n26.core.card import build_card
    from n26.core.owned import owned_things, thing_key
    from n26.library.authoring import add_weapon_profile, create_weapon

    autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
    warp = add_weapon_profile(autogun, name="warp round", price=10)
    with operation(gang, actor=tester) as op:
        gun = op.give_weapon(fighter, autogun, paid=20)
        op.buy_weapon_profile(gun, warp)

    (held,) = owned_things(build_card(fighter), AT)[thing_key(autogun)]
    (part,) = held.parts
    assert part.key == thing_key(warp)
    assert hasattr(held, "reassign_href")
    assert not hasattr(part, "reassign_href")


def test_a_part_goes_by_its_own_name_under_the_thing_it_hangs_off(
    gang, fighter, tester
):
    """A card prints "warp round (Autogun)" because nothing above the
    line says which gun. Drawn under the gun's own row the bracket only
    repeats it, so the part reads as the shop's row for the same ammo
    reads — and the two agree."""
    from n26.core.card import build_card
    from n26.core.owned import owned_things, thing_key
    from n26.library.authoring import add_weapon_profile, create_weapon

    autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
    warp = add_weapon_profile(autogun, name="warp round", price=10)
    with operation(gang, actor=tester) as op:
        gun = op.give_weapon(fighter, autogun, paid=20)
        op.buy_weapon_profile(gun, warp)

    (held,) = owned_things(build_card(fighter), AT)[thing_key(autogun)]
    (part,) = held.parts
    assert part.name == "warp round"
    assert str(warp) == "warp round (Autogun)"


def test_every_copy_arrives_with_its_controls_already_pointed_somewhere(
    gang, fighter, tester
):
    """One pass, complete rows. A caller that had to walk the index
    afterwards to fill the links in would be a caller who could forget,
    and a row with an empty address draws a control that goes nowhere."""
    from n26.core.card import build_card
    from n26.core.owned import owned_things, thing_key
    from n26.library.authoring import add_weapon_profile, create_weapon

    autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
    warp = add_weapon_profile(autogun, name="warp round", price=10)
    with operation(gang, actor=tester) as op:
        gun = op.give_weapon(fighter, autogun, paid=20)
        ammo = op.buy_weapon_profile(gun, warp)

    (held,) = owned_things(build_card(fighter), AT)[thing_key(autogun)]
    (part,) = held.parts

    assert held.key == thing_key(autogun)
    assert held.id == str(gun.pk)
    assert held.sell_href == f"{AT}&sell={gun.pk}"
    assert held.reassign_href == f"{AT}&reassign={gun.pk}"
    assert held.remove_href == f"{AT}&remove={gun.pk}"
    assert part.sell_href == f"{AT}&sell={ammo.pk}"
    assert part.remove_href == f"{AT}&remove={ammo.pk}"


def test_a_copy_cannot_be_edited_after_it_is_built(gang, fighter, tester, sword):
    """Frozen, because there is no second phase to change one in. What a
    fighter holds is read off a card and handed on; a surface that wants
    it said differently builds its own row."""
    import dataclasses

    from n26.core.card import build_card
    from n26.core.owned import owned_things, thing_key

    (held,) = owned_things(build_card(fighter), AT)[thing_key(sword.assignable)]
    with pytest.raises(dataclasses.FrozenInstanceError):
        held.sell_href = "#"


def test_the_gangs_own_rows_are_not_the_fighters_to_sell(gang, fighter, tester):
    """A gang's kit rides every member's card so gang-wide rules reach it.
    It is still the gang's, and no fighter's row may offer it for sale."""
    from n26.core.card import build_card
    from n26.core.owned import owned_things, thing_key

    crate = create_wargear("Ammo Crate", price=30)
    with operation(gang, actor=tester) as op:
        op.assign(crate, gang=gang, paid=30)

    assert thing_key(crate) not in owned_things(build_card(fighter), AT)


def test_an_unowned_row_is_counted_as_nothing(gang, fighter):
    from n26.core.card import build_card
    from n26.core.owned import owned_things, thing_key

    unheld = create_wargear("Rope", price=5)
    assert owned_things(build_card(fighter), AT).get(thing_key(unheld)) is None


def test_a_miniature_that_is_not_this_gangs_is_no_destination(gang, fighter):
    """Sanity on the fixture the move tests lean on: everyone offered is on
    this roster."""
    from n26.core.views.owned import _other_models

    assert _other_models(gang, fighter) == []
    assert list(Miniature.objects.filter(membership__gang=gang)) == [fighter]
    assert Assignment.objects.filter(gang_root=gang, archived=False).exists()
