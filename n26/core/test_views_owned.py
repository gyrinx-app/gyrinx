"""What a gang already owns: selling it, handing it on, taking it off.

The four routes are addressed by assignment rather than by fighter, so
what is pinned here is the wiring around ``Operation.sell``, ``move``,
``refund`` and ``remove`` — that a click writes the right one, that the
books still agree afterwards, that nobody reaches another player's
assignments,
and that a GET writes nothing at all.

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
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


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

    def test_the_click_lands_back_on_the_equip_page_it_came_from(
        self, client, tester, fighter, sword, house_list
    ):
        client.force_login(tester)
        response = client.post(url("n26-sell", sword), {"list": str(house_list.pk)})
        assert response.url == (
            reverse("n26-equip", args=[fighter.pk]) + f"?list={house_list.pk}"
        )

    def test_a_second_click_of_a_stale_button_sells_nothing_twice(
        self, client, tester, gang, sword
    ):
        """The archived assignment is gone as far as these routes are concerned,
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
        hand-made click — and it moves nothing."""
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


class TestRefunding:
    """Undoing a purchase: the thing goes and every credit paid comes back.

    The act that is easy to confuse with the other two that take a thing
    away, so what is pinned here is the money. A removal keeps it, a sale
    returns half of what the thing is worth, and this returns what was
    handed over — which for a haggled sword is a third number again.
    """

    def test_a_refund_returns_what_was_paid_and_not_what_it_is_worth(
        self, client, tester, gang, sword
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(url("n26-refund", sword))

        assert response.status_code == 302
        gang.refresh_from_db()
        # The sixty that was paid, not the hundred it is worth and not the
        # fifty a sale would have fetched.
        assert gang.credits == before + 60
        assert gang.rating == 0
        sword.refresh_from_db()
        assert sword.archived is True
        assert_reconciled(gang)

    def test_a_gang_with_no_budget_is_answered_with_a_removal(
        self, client, tester, gang, fighter, sword
    ):
        """No budget, no refund: the money never left a budget, so the
        credits stay where they are and the thing simply goes — the same
        degradation the fighter-level flow makes."""
        gang.starting_credits = None
        gang.save(update_fields=["starting_credits"])
        with operation(gang, actor=tester) as op:
            op.settle()
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(url("n26-refund", sword))

        assert response.status_code == 302
        gang.refresh_from_db()
        assert gang.credits == before
        sword.refresh_from_db()
        assert sword.archived is True
        assert_reconciled(gang)

    def test_a_gun_and_its_ammo_are_refunded_together(
        self, client, tester, gang, fighter
    ):
        """They were bought on one click, so they come back on one."""
        from n26.library.authoring import add_weapon_profile, create_weapon

        autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
        warp = add_weapon_profile(autogun, name="warp round", price=10)
        with operation(gang, actor=tester) as op:
            gun = op.give_weapon(fighter, autogun, paid=20)
            ammo = op.buy_weapon_profile(gun, warp)
        gang.refresh_from_db()
        before = gang.credits

        client.force_login(tester)
        client.post(url("n26-refund", gun))

        gang.refresh_from_db()
        assert gang.credits == before + 30
        gun.refresh_from_db()
        ammo.refresh_from_db()
        assert gun.archived is True
        assert ammo.archived is True
        assert_reconciled(gang)

    def test_ammo_can_be_refunded_without_the_gun(self, client, tester, gang, fighter):
        """Buying the wrong ammunition is as easy a mistake as buying the
        wrong gun, and undoing it leaves the fighter their gun."""
        from n26.library.authoring import add_weapon_profile, create_weapon

        autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
        warp = add_weapon_profile(autogun, name="warp round", price=10)
        with operation(gang, actor=tester) as op:
            gun = op.give_weapon(fighter, autogun, paid=20)
            ammo = op.buy_weapon_profile(gun, warp)
        gang.refresh_from_db()
        before = gang.credits

        client.force_login(tester)
        client.post(url("n26-refund", ammo))

        gang.refresh_from_db()
        assert gang.credits == before + 10
        gun.refresh_from_db()
        ammo.refresh_from_db()
        assert ammo.archived is True
        assert gun.archived is False
        assert gang.rating == 20
        assert_reconciled(gang)

    def test_something_nobody_paid_for_refunds_nothing_and_still_goes(
        self, client, tester, gang, fighter
    ):
        """A gift is not a purchase, so there is nothing to undo — but the
        thing still leaves the card, because that is the other half of
        what the act does."""
        gift = create_wargear("Charm", price=15)
        with operation(gang, actor=tester) as op:
            given = op.buy(fighter, thing=gift, paid=0, list_price=15, discount=15)
        gang.refresh_from_db()
        before = gang.credits

        client.force_login(tester)
        client.post(url("n26-refund", given))

        gang.refresh_from_db()
        assert gang.credits == before
        given.refresh_from_db()
        assert given.archived is True
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


class TestWhatMayBeClickedOn:
    """These acts are about kit, and a gang holds a great deal that is not
    kit — every bit of it an assignment with a primary key of its own.

    The assignment naming a model's profile *is* the model: selling it would
    take the fighter off the roster with everything they carry, and pay half
    the price of the profile for the lot. The one naming the gang's type is
    the gang. A skill is what a fighter knows, an equipment list is where they
    buy from. None of them is a possession, and none of these routes will touch
    one — whatever a hand-made URL says.
    """

    @pytest.mark.parametrize(
        "route",
        ["n26-sell", "n26-reassign", "n26-refund", "n26-remove", "n26-rechoose"],
    )
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

    @pytest.mark.parametrize(
        "route",
        ["n26-sell", "n26-reassign", "n26-refund", "n26-remove", "n26-rechoose"],
    )
    def test_the_gang_itself_is_not_kit(self, client, tester, gang, route):
        """The founding assignment carries the gang's type, its equipment
        lists and every gang-wide rule. Taking it away would take all of
        that."""
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

    @pytest.mark.parametrize(
        "route",
        ["n26-sell", "n26-reassign", "n26-refund", "n26-remove", "n26-rechoose"],
    )
    def test_what_a_fighter_knows_is_not_kit(
        self, client, tester, gang, fighter, route
    ):
        """A skill for five credits would be a tap, not a trade — and a
        removal here would be a way to give one back by URL."""
        from n26.library.authoring import create_skill

        with operation(gang, actor=tester) as op:
            learned = op.learn(fighter, create_skill("Marksman"))

        client.force_login(tester)
        assert client.post(url(route, learned)).status_code == 404

        learned.refresh_from_db()
        assert learned.archived is False
        assert_reconciled(gang)

    def test_the_equip_page_offers_none_of_them_either(
        self, gang, fighter, tester, sword
    ):
        """One rule, read by the listing that draws the controls and by the
        routes behind them, so a screen can never offer what a click would
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


class TestWhoMayClick:
    """Every one of these writes, so every one of them is guarded — and
    none of them is a GET."""

    @pytest.mark.parametrize(
        "route",
        ["n26-sell", "n26-reassign", "n26-refund", "n26-remove", "n26-rechoose"],
    )
    def test_a_stranger_finds_nothing(self, client, gang, sword, route):
        stranger = User.objects.create_user("stranger")
        client.force_login(stranger)

        assert client.post(url(route, sword)).status_code == 404

        sword.refresh_from_db()
        assert sword.archived is False
        assert_reconciled(gang)

    @pytest.mark.parametrize(
        "route",
        ["n26-sell", "n26-reassign", "n26-refund", "n26-remove", "n26-rechoose"],
    )
    def test_signing_out_is_signing_out(self, client, sword, route):
        response = client.post(url(route, sword))
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    @pytest.mark.parametrize(
        "route",
        ["n26-sell", "n26-reassign", "n26-refund", "n26-remove", "n26-rechoose"],
    )
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

    @pytest.mark.parametrize(
        "route",
        [
            "n26-sell",
            "n26-reassign",
            "n26-refund",
            "n26-remove",
            "n26-accessorise",
            "n26-rechoose",
        ],
    )
    def test_a_pk_that_is_not_a_ulid_is_not_found(self, client, tester, route):
        client.force_login(tester)
        assert client.post(reverse(route, args=["nonsense"])).status_code == 404


@pytest.fixture
def sight(db):
    """Twenty-five credits of telescopic sight, fitting anything."""
    from n26.library.authoring import create_weapon_accessory

    return create_weapon_accessory("Telescopic sight", price=25)


@pytest.fixture
def gun(gang, fighter, tester):
    """A lasgun on the fighter, bought at its list price of fifteen."""
    from n26.library.authoring import create_weapon

    weapon = create_weapon("Lasgun", price=15, profiles=[("", 0)])
    with operation(gang, actor=tester) as op:
        return op.buy(fighter, thing=weapon, paid=15)


class TestFittingAnAccessory:
    """Bought onto the weapon's own row, at the price the library says."""

    def test_a_click_bolts_it_onto_the_weapon(
        self, client, tester, gang, fighter, gun, sight
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(
            url("n26-accessorise", gun), {"accessory": str(sight.pk)}
        )

        assert response.status_code == 302
        bolted = Assignment.objects.get(weapon_accessory=sight)
        assert bolted.parent_id == gun.pk
        assert bolted.miniature_root_id == fighter.pk
        gang.refresh_from_db()
        assert gang.credits == before - 25
        assert_reconciled(gang)

    def test_the_form_never_says_what_it_costs(self, client, tester, gang, gun, sight):
        """A figure in the click buys nothing at a figure nobody offered:
        the server reads the price off the library."""
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        client.post(
            url("n26-accessorise", gun), {"accessory": str(sight.pk), "paid": "0"}
        )

        gang.refresh_from_db()
        assert gang.credits == before - 25
        assert_reconciled(gang)

    def test_the_click_lands_back_on_the_list_and_tab_it_came_from(
        self, client, tester, fighter, gun, sight, house_list
    ):
        client.force_login(tester)
        response = client.post(
            url("n26-accessorise", gun),
            {
                "accessory": str(sight.pk),
                "list": str(house_list.pk),
                "section": "Weapons",
            },
        )
        assert response.url == (
            reverse("n26-equip", args=[fighter.pk])
            + f"?list={house_list.pk}&section=Weapons"
        )

    def test_something_that_is_not_a_weapon_is_nowhere_to_fit_one(
        self, client, tester, sword, sight
    ):
        """No control draws this address for anything but a gun, so a click
        that arrives is a hand-made URL."""
        client.force_login(tester)
        response = client.post(
            url("n26-accessorise", sword), {"accessory": str(sight.pk)}
        )
        assert response.status_code == 404

    def test_an_accessory_nobody_offered_fits_nothing(self, client, tester, gang, gun):
        client.force_login(tester)
        response = client.post(url("n26-accessorise", gun), {"accessory": "nonsense"})

        assert response.status_code == 302
        assert not Assignment.objects.filter(parent=gun, weapon_accessory__isnull=False)
        assert_reconciled(gang)

    def test_a_get_fits_nothing(self, client, tester, gun, sight):
        client.force_login(tester)
        response = client.get(url("n26-accessorise", gun), {"accessory": str(sight.pk)})
        assert response.status_code == 405
        assert not Assignment.objects.filter(weapon_accessory=sight).exists()

    def test_somebody_elses_gun_is_not_found(self, client, gun, sight):
        stranger = User.objects.create_user("stranger")
        client.force_login(stranger)
        response = client.post(
            url("n26-accessorise", gun), {"accessory": str(sight.pk)}
        )
        assert response.status_code == 404


class TestSellingAGunWithSomethingBoltedToIt:
    """Two answers, and the form carries which was meant. Keeping is the
    default because a stashed sight can still be sold and a sold one is
    gone."""

    @pytest.fixture
    def bolted(self, gang, tester, gun, sight, stash):
        """A sight on the gun, and somewhere for it to go — a gang with no
        stash is offered no choice at all."""
        with operation(gang, actor=tester) as op:
            return op.buy(gun, thing=sight)

    def test_by_default_the_accessory_is_stashed_and_survives(
        self, client, tester, gang, gun, bolted, stash
    ):
        client.force_login(tester)

        response = client.post(url("n26-sell", gun))

        assert response.status_code == 302
        gun.refresh_from_db()
        bolted.refresh_from_db()
        assert gun.archived is True
        assert bolted.archived is False
        assert bolted.stash_id == stash.pk
        stash.refresh_from_db()
        assert stash.rating == 25
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_gang_is_paid_for_the_gun_alone(
        self, client, tester, gang, gun, bolted
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        client.post(url("n26-sell", gun))

        gang.refresh_from_db()
        # Half of fifteen, rounded up — the sight was kept, so nothing is
        # paid for it.
        assert gang.credits == before + 8
        assert_reconciled(gang)

    def test_saying_so_sells_the_accessory_too(
        self, client, tester, gang, gun, bolted, stash
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        client.post(url("n26-sell", gun), {"accessories": "sell"})

        bolted.refresh_from_db()
        assert bolted.archived is True
        stash.refresh_from_db()
        assert stash.rating == 0
        gang.refresh_from_db()
        # Forty credits of gun and sight, halved.
        assert gang.credits == before + 20
        assert_reconciled(gang)

    def test_a_gun_with_nothing_on_it_sells_as_it_always_did(
        self, client, tester, gang, gun, stash
    ):
        """No accessories, no question — and the same eight credits."""
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        client.post(url("n26-sell", gun))

        gang.refresh_from_db()
        stash.refresh_from_db()
        assert gang.credits == before + 8
        assert stash.rating == 0
        assert_reconciled(gang)

    def test_the_firing_line_is_sold_with_the_gun_either_way(
        self, client, tester, gang, gun, bolted
    ):
        """A weapon's own profile is not gear that could be kept: it names
        this gun and is nothing away from it."""
        client.force_login(tester)
        line = gun.children.exclude(weapon_profile=None).get()

        client.post(url("n26-sell", gun))

        line.refresh_from_db()
        assert line.archived is True
        assert line.parent_id == gun.pk
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestFittingOneBackOntoAGun:
    """A stashed accessory goes back onto a weapon through the same move
    that put it in the stash, one level down the chain."""

    @pytest.fixture
    def stashed(self, gang, tester, gun, sight, stash):
        with operation(gang, actor=tester) as op:
            bolted = op.buy(gun, thing=sight)
            op.move(bolted, stash)
        return bolted

    def test_a_click_fits_it_to_the_named_weapon(
        self, client, tester, gang, fighter, gun, stashed, stash
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(
            url("n26-reassign", stashed), {"to": "weapon", "weapon": str(gun.pk)}
        )

        assert response.status_code == 302
        stashed.refresh_from_db()
        assert stashed.parent_id == gun.pk
        assert stashed.stash_root_id is None
        assert stashed.miniature_root_id == fighter.pk
        stash.refresh_from_db()
        gang.refresh_from_db()
        # A move never re-prices, and nothing is charged for one.
        assert stash.rating == 0
        assert gang.credits == before
        assert_reconciled(gang)

    def test_the_click_lands_on_the_stash_equip_page_without_a_return_field(
        self, client, tester, gang, gun, stashed
    ):
        client.force_login(tester)
        response = client.post(
            url("n26-reassign", stashed), {"to": "weapon", "weapon": str(gun.pk)}
        )
        assert response.url.startswith(reverse("n26-equip-gang", args=[gang.pk]))

    def test_a_return_field_sends_the_reader_back_to_the_sheet(
        self, client, tester, gang, gun, stashed
    ):
        client.force_login(tester)
        sheet = reverse("n26-gang", args=[gang.pk])
        response = client.post(
            url("n26-reassign", stashed),
            {"to": "weapon", "weapon": str(gun.pk), "return": sheet},
        )
        assert response.url == sheet

    def test_an_external_return_field_is_ignored(
        self, client, tester, gang, gun, stashed
    ):
        client.force_login(tester)
        response = client.post(
            url("n26-reassign", stashed),
            {
                "to": "weapon",
                "weapon": str(gun.pk),
                "return": "https://example.com/elsewhere",
            },
        )

        assert response.url.startswith(reverse("n26-equip-gang", args=[gang.pk]))

    def test_a_weapon_in_another_gang_is_nowhere_to_fit_it(
        self, client, tester, gang, stashed, gang_type, make_profile, make_statline
    ):
        """The select offers this gang's guns alone, so this can only be a
        hand-made click — and it fits nothing."""
        from n26.library.authoring import create_weapon

        stranger = User.objects.create_user("stranger")
        theirs = Gang.objects.create(
            name="Their Gang", owner=stranger, gang_type=gang_type
        )
        entry = make_profile("Their Ganger", price=0)
        make_statline(entry, movement=5)
        with operation(theirs, actor=stranger) as op:
            mine = op.hire(entry, "Theirs")
            their_gun = op.buy(
                mine, thing=create_weapon("Their Lasgun", price=15, profiles=[("", 0)])
            )

        client.force_login(tester)
        response = client.post(
            url("n26-reassign", stashed),
            {"to": "weapon", "weapon": str(their_gun.pk)},
        )

        assert response.status_code == 302
        stashed.refresh_from_db()
        assert stashed.parent_id is None
        assert_reconciled(gang)

    def test_the_gun_it_lands_on_is_not_a_row_of_the_screen_it_left(
        self, client, tester, gang, fighter, gun, stashed
    ):
        """The stash screen holds no row for a fighter's gun, and an
        update naming one would tell the page to remove a row that is not
        there."""
        from n26.core.owned import thing_key

        client.force_login(tester)
        response = client.post(
            url("n26-reassign", stashed),
            {"to": "weapon", "weapon": str(gun.pk)},
            headers={"HX-Request": "true"},
        )

        assert (
            f'data-row="{thing_key(gun.assignable)}"' not in response.content.decode()
        )

    def test_a_firing_line_is_refused_in_words(self, client, tester, gang, gun, stash):
        """The listing offers no control for this, so a click that reaches
        it is hand-made — and it is answered with a sentence rather than a
        traceback."""
        client.force_login(tester)
        line = gun.children.exclude(weapon_profile=None).get()

        response = client.post(url("n26-reassign", line), {"to": "stash"}, follow=True)

        line.refresh_from_db()
        assert line.parent_id == gun.pk
        assert "is part of" in response.content.decode()


class TestFittingOneTheFighterIsCarrying:
    """An accessory bought on a model's own equip page is loose on the
    card until somebody bolts it to something. The question is the one the
    stash asks, narrowed to the guns that model is carrying — and it is
    asked on its own, so Reassign goes on meaning which model holds it."""

    @pytest.fixture
    def loose(self, gang, tester, fighter, sight):
        with operation(gang, actor=tester) as op:
            return op.buy(fighter, thing=sight)

    @staticmethod
    def dialog(fighter, **query):
        from django.test import RequestFactory

        from n26.core.card import build_card
        from n26.core.owned import EquipHost
        from n26.core.views.owned import owned_dialog

        request = RequestFactory().get(AT, query)
        host = EquipHost.fighter(fighter.gang, build_card(fighter), fighter, AT)
        return owned_dialog(request, host)

    @staticmethod
    def copy_of(fighter, assignment):
        from n26.core.card import build_card
        from n26.core.owned import owned_things, thing_key

        held = owned_things(build_card(fighter), AT)
        (copy,) = held[thing_key(assignment.assignable)]
        return copy

    def test_a_loose_accessory_offers_the_fitting(self, fighter, gun, loose):
        assert self.copy_of(fighter, loose).fit_href == f"{AT}&fit={loose.pk}"

    def test_a_fighter_with_no_gun_is_offered_nowhere_to_fit_it(self, fighter, loose):
        """A screen must not ask a question its answer refuses."""
        assert self.copy_of(fighter, loose).fit_href == ""

    def test_nothing_but_an_accessory_offers_it(self, fighter, gun, sword, loose):
        assert self.copy_of(fighter, gun).fit_href == ""
        assert self.copy_of(fighter, sword).fit_href == ""

    def test_the_question_offers_the_guns_this_model_is_carrying(
        self, gang, tester, fighter, other, gun, loose, stash
    ):
        """Somebody else's gun and the gang's spare are both places this
        could end up, and neither is on the screen the question was asked
        from."""
        from n26.library.authoring import create_weapon

        with operation(gang, actor=tester) as op:
            op.buy(other, thing=create_weapon("Autogun", price=20, profiles=[("", 0)]))
            op.buy(stash, thing=create_weapon("Stub gun", price=5, profiles=[("", 0)]))

        dialog = self.dialog(fighter, fit=str(loose.pk))

        assert dialog["title"] == "Fit Telescopic sight to a weapon"
        assert dialog["weapons"] == [{"pk": str(gun.pk), "label": "Lasgun"}]

    def test_the_question_is_answered_by_the_move_that_does_it(
        self, fighter, gun, loose
    ):
        dialog = self.dialog(fighter, fit=str(loose.pk))

        assert dialog["action"] == reverse("n26-reassign", args=[loose.pk])
        assert dialog["submit_label"] == "Fit"

    def test_a_hand_made_address_with_no_gun_to_name_draws_no_submit(
        self, fighter, loose
    ):
        dialog = self.dialog(fighter, fit=str(loose.pk))

        assert dialog["weapons"] == []
        assert dialog["submit_label"] == ""

    def test_the_panel_with_no_gun_to_offer_carries_no_destination(
        self, client, tester, fighter, loose
    ):
        """Rendered rather than read off the dialog: the destinations are
        one if/elif chain, and a fitting that fell through to its end
        would carry the move's hidden stash field — a panel asking to fit
        something, quietly posting a move instead."""
        client.force_login(tester)

        response = client.get(
            reverse("n26-equip", args=[fighter.pk]), {"fit": str(loose.pk)}
        )

        body = response.content.decode()
        assert "Fit Telescopic sight to a weapon" in body
        assert 'name="to"' not in body

    def test_only_an_accessory_is_asked_the_question(self, fighter, gun, sword, loose):
        """A gun's own address would otherwise open a picker holding that
        same gun, and fitting a thing to itself is not an act."""
        assert self.dialog(fighter, fit=str(gun.pk)) is None
        assert self.dialog(fighter, fit=str(sword.pk)) is None

    def test_a_hand_made_click_naming_its_own_weapon_is_answered_in_words(
        self, client, tester, gang, gun
    ):
        """Nothing draws this address for a gun, so a click that arrives
        is hand-made — and it gets a sentence rather than a traceback."""
        client.force_login(tester)

        response = client.post(
            url("n26-reassign", gun),
            {"to": "weapon", "weapon": str(gun.pk)},
            follow=True,
        )

        assert response.status_code == 200
        assert "There is nowhere to move" in response.content.decode()
        gun.refresh_from_db()
        assert gun.parent_id is None
        assert_reconciled(gang)

    def test_a_click_bolts_it_onto_the_named_gun(
        self, client, tester, gang, fighter, gun, loose
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(
            url("n26-reassign", loose), {"to": "weapon", "weapon": str(gun.pk)}
        )

        assert response.status_code == 302
        loose.refresh_from_db()
        assert loose.parent_id == gun.pk
        assert loose.miniature_root_id == fighter.pk
        gang.refresh_from_db()
        # A move never re-prices, and nothing is charged for one.
        assert gang.credits == before
        assert_reconciled(gang)

    def test_the_click_lands_back_on_the_fighters_equip_page(
        self, client, tester, fighter, gun, loose
    ):
        client.force_login(tester)
        response = client.post(
            url("n26-reassign", loose), {"to": "weapon", "weapon": str(gun.pk)}
        )
        assert response.url.startswith(reverse("n26-equip", args=[fighter.pk]))

    def test_the_screen_is_told_about_both_rows_it_changed(
        self, client, tester, fighter, gun, loose
    ):
        """Both keys are delivered: the gun's row redrawn with the sight
        under it, and the accessory's own row answered for."""
        from n26.core.owned import thing_key

        client.force_login(tester)
        response = client.post(
            url("n26-reassign", loose),
            {"to": "weapon", "weapon": str(gun.pk)},
            headers={"HX-Request": "true"},
        )

        from n26.core.templatetags.listing import row_dom_id

        body = response.content.decode()
        assert f'data-row="{thing_key(gun.assignable)}"' in body
        # Inside the gun's row rather than anywhere in the response: the
        # update also re-delivers every accessory panel, and the panel
        # for this gun offers the sight by name whether or not the second
        # row was drawn at all.
        gun_row = body.split(f'data-row="{thing_key(gun.assignable)}"', 1)[1]
        gun_row = gun_row.split("n26-accessorise-host", 1)[0]
        assert "Telescopic sight" in gun_row
        # This listing does not sell the sight, so with nothing holding it
        # the screen has no row for it at all and the update says to take
        # it away. One string, because an id and a delete asserted apart
        # are both satisfied by a response carrying only the first row.
        gone = row_dom_id(thing_key(loose.assignable))
        assert f'id="{gone}" hx-swap-oob="delete"' in body


class TestDetachingAnAccessory:
    """A bought sight can come off the gun and stay on the fighter. The
    write is the same move that fitted it; the kebab asks it as its own
    question so Reassign stays about which model holds a thing."""

    @pytest.fixture
    def bolted(self, gang, tester, gun, sight):
        with operation(gang, actor=tester) as op:
            return op.buy(gun, thing=sight)

    @pytest.fixture
    def other_gun(self, gang, tester, fighter):
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Stub gun", price=5, profiles=[("", 0)])
        with operation(gang, actor=tester) as op:
            return op.buy(fighter, thing=weapon, paid=5)

    @staticmethod
    def dialog(fighter, **query):
        from django.test import RequestFactory

        from n26.core.card import build_card
        from n26.core.owned import EquipHost
        from n26.core.views.owned import owned_dialog

        request = RequestFactory().get(AT, query)
        host = EquipHost.fighter(fighter.gang, build_card(fighter), fighter, AT)
        return owned_dialog(request, host)

    @staticmethod
    def part_of(fighter, assignment):
        from n26.core.card import build_card
        from n26.core.owned import owned_things

        held = owned_things(build_card(fighter), AT)
        for copies in held.values():
            for copy in copies:
                for part in copy.parts:
                    if part.id == str(assignment.pk):
                        return part
        raise AssertionError(f"no part {assignment.pk}")

    def test_a_bolted_accessory_offers_detach(self, fighter, gun, bolted):
        part = self.part_of(fighter, bolted)
        assert part.detach_href == f"{AT}&detach={bolted.pk}"

    def test_a_card_with_another_gun_also_offers_to_fit_it(
        self, fighter, gun, bolted, other_gun
    ):
        part = self.part_of(fighter, bolted)
        assert part.fit_href == f"{AT}&fit={bolted.pk}"

    def test_a_card_with_one_gun_is_offered_nowhere_else_to_fit_it(
        self, fighter, gun, bolted
    ):
        """Fitting it to the gun it already hangs off is not a move."""
        part = self.part_of(fighter, bolted)
        assert part.fit_href == ""

    def test_ammo_is_offered_neither(self, gang, tester, fighter, gun):
        from n26.library.authoring import add_weapon_profile

        warp = add_weapon_profile(gun.assignable, name="hot-shot", price=10)
        with operation(gang, actor=tester) as op:
            ammo = op.buy_weapon_profile(gun, warp)

        part = self.part_of(fighter, ammo)
        assert part.detach_href == ""
        assert part.fit_href == ""

    def test_a_sight_the_gun_came_with_is_offered_neither(
        self, gang, tester, fighter, gun, sight
    ):
        from n26.core.models import Reason

        with operation(gang, actor=tester) as op:
            builtin = op.assign(
                sight, parent=gun, caused_by=gun, paid=0, reason=Reason.DEFAULT
            )

        part = self.part_of(fighter, builtin)
        assert part.detach_href == ""
        assert part.fit_href == ""

    def test_the_question_is_answered_by_the_move_that_does_it(self, fighter, bolted):
        dialog = self.dialog(fighter, detach=str(bolted.pk))

        assert dialog["title"] == "Detach Telescopic sight?"
        assert dialog["action"] == reverse("n26-reassign", args=[bolted.pk])
        assert dialog["submit_label"] == "Detach"
        assert dialog["submit_variant"] == "primary"

    def test_the_fit_question_omits_the_gun_it_already_hangs_off(
        self, fighter, gun, bolted, other_gun
    ):
        dialog = self.dialog(fighter, fit=str(bolted.pk))

        assert dialog["title"] == "Fit Telescopic sight to a weapon"
        assert dialog["weapons"] == [{"pk": str(other_gun.pk), "label": "Stub gun"}]

    def test_one_gun_is_nowhere_to_fit_a_bolted_accessory(self, fighter, gun, bolted):
        """The control is not drawn, so a hand-made address opens no
        panel — not an empty picker that says there is no weapon."""
        assert self.dialog(fighter, fit=str(bolted.pk)) is None

    def test_a_built_in_sight_is_asked_neither_question(
        self, gang, tester, fighter, gun, sight
    ):
        from n26.core.models import Reason

        with operation(gang, actor=tester) as op:
            builtin = op.assign(
                sight, parent=gun, caused_by=gun, paid=0, reason=Reason.DEFAULT
            )

        assert self.dialog(fighter, detach=str(builtin.pk)) is None
        assert self.dialog(fighter, fit=str(builtin.pk)) is None

    def test_a_click_leaves_it_held_on_the_fighter(
        self, client, tester, gang, fighter, gun, bolted
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(url("n26-reassign", bolted), {"to": "detach"})

        assert response.status_code == 302
        bolted.refresh_from_db()
        assert bolted.parent_id is None
        assert bolted.miniature_id == fighter.pk
        assert bolted.archived is False
        gang.refresh_from_db()
        assert gang.credits == before
        assert_reconciled(gang)

    def test_the_click_says_so(self, client, tester, fighter, gun, bolted):
        client.force_login(tester)
        response = client.post(
            url("n26-reassign", bolted), {"to": "detach"}, follow=True
        )

        assert "Detached Telescopic sight." in response.content.decode()

    def test_a_click_fits_it_to_the_other_gun(
        self, client, tester, gang, fighter, gun, bolted, other_gun
    ):
        client.force_login(tester)
        gang.refresh_from_db()
        before = gang.credits

        response = client.post(
            url("n26-reassign", bolted),
            {"to": "weapon", "weapon": str(other_gun.pk)},
        )

        assert response.status_code == 302
        bolted.refresh_from_db()
        assert bolted.parent_id == other_gun.pk
        assert bolted.miniature_root_id == fighter.pk
        gang.refresh_from_db()
        assert gang.credits == before
        assert_reconciled(gang)

    def test_the_screen_is_told_about_both_rows_it_changed(
        self, client, tester, fighter, gun, bolted
    ):
        """The gun loses the part; the accessory becomes a row of its own."""
        from n26.core.owned import thing_key

        client.force_login(tester)
        response = client.post(
            url("n26-reassign", bolted),
            {"to": "detach"},
            headers={"HX-Request": "true"},
        )

        body = response.content.decode()
        assert f'data-row="{thing_key(gun.assignable)}"' in body
        assert f'data-row="{thing_key(bolted.assignable)}"' in body

    def test_a_built_in_sight_cannot_be_taken_off(
        self, client, tester, gang, fighter, gun, sight
    ):
        from n26.core.models import Reason

        with operation(gang, actor=tester) as op:
            builtin = op.assign(
                sight, parent=gun, caused_by=gun, paid=0, reason=Reason.DEFAULT
            )

        client.force_login(tester)
        response = client.post(
            url("n26-reassign", builtin), {"to": "detach"}, follow=True
        )

        builtin.refresh_from_db()
        assert builtin.parent_id == gun.pk
        assert "You cannot take Telescopic sight off the weapon." in (
            response.content.decode()
        )
        assert_reconciled(gang)

    def test_a_stash_gun_offers_the_part_no_fit_or_detach(
        self, gang, tester, sight, stash
    ):
        """Stash accessories are fitted through Reassign, which lists
        every gun on the roster. A ?fit= address would only see stash
        guns, and Detach would ask to unbolt onto a fighter who is not
        holding it."""
        from n26.core.card import build_gang_card
        from n26.core.owned import EquipHost, possessions
        from n26.library.authoring import create_weapon

        with operation(gang, actor=tester) as op:
            stash_gun = op.buy(
                stash,
                thing=create_weapon("Stub gun", price=5, profiles=[("", 0)]),
                paid=5,
            )
            bolted = op.buy(stash_gun, thing=sight)
            op.buy(
                stash,
                thing=create_weapon("Autogun", price=20, profiles=[("", 0)]),
                paid=20,
            )

        host = EquipHost.stash(gang, build_gang_card(gang), AT)
        part = None
        for copies in possessions(host).values():
            for copy in copies:
                for child in copy.parts:
                    if child.id == str(bolted.pk):
                        part = child
        assert part is not None
        assert part.detach_href == ""
        assert part.fit_href == ""

    def test_a_stash_address_does_not_open_the_fighter_fit_question(
        self, gang, tester, sight, stash
    ):
        """Hand-made ?fit= on the stash must not draw the fighter picker."""
        from django.test import RequestFactory

        from n26.core.card import build_gang_card
        from n26.core.owned import EquipHost
        from n26.core.views.owned import owned_dialog
        from n26.library.authoring import create_weapon

        with operation(gang, actor=tester) as op:
            stash_gun = op.buy(
                stash,
                thing=create_weapon("Stub gun", price=5, profiles=[("", 0)]),
                paid=5,
            )
            bolted = op.buy(stash_gun, thing=sight)

        request = RequestFactory().get(AT, {"fit": str(bolted.pk)})
        host = EquipHost.stash(gang, build_gang_card(gang), AT)
        assert owned_dialog(request, host) is None

    def test_a_stash_click_is_told_detach_is_for_a_fighter(
        self, client, tester, gang, sight, stash
    ):
        from n26.library.authoring import create_weapon

        with operation(gang, actor=tester) as op:
            stash_gun = op.buy(
                stash,
                thing=create_weapon("Stub gun", price=5, profiles=[("", 0)]),
                paid=5,
            )
            bolted = op.buy(stash_gun, thing=sight)

        client.force_login(tester)
        response = client.post(
            url("n26-reassign", bolted), {"to": "detach"}, follow=True
        )

        bolted.refresh_from_db()
        assert bolted.parent_id == stash_gun.pk
        assert "You cannot take Telescopic sight off here." in response.content.decode()
        assert_reconciled(gang)

    def test_the_gun_it_already_hangs_off_is_nowhere_to_fit_it(
        self, client, tester, gang, gun, bolted
    ):
        client.force_login(tester)
        response = client.post(
            url("n26-reassign", bolted),
            {"to": "weapon", "weapon": str(gun.pk)},
            follow=True,
        )

        bolted.refresh_from_db()
        assert bolted.parent_id == gun.pk
        assert "There is nowhere to move" in response.content.decode()
        assert_reconciled(gang)


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
    """The count a listing row shows is of live assignments on this fighter, read
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
    # Archived assignments are not held: the fighter has one sword, not two.
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
    repeats it, so the part reads as the equip row for the same ammo
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


def test_a_suppressed_possession_has_no_dialog(fighter, sword):
    from django.test import RequestFactory

    from n26.core.card import build_card
    from n26.core.owned import EquipHost
    from n26.core.views.owned import owned_dialog

    card = build_card(fighter)
    node = next(
        node
        for node in card.all_nodes()
        if node.assignment is not None and node.assignment.pk == sword.pk
    )
    node.suppressed = True
    request = RequestFactory().get(AT, {"sell": str(sword.pk)})

    assert (
        owned_dialog(request, EquipHost.fighter(fighter.gang, card, fighter, AT))
        is None
    )


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


def test_link_possession_actions_fills_the_card_from_what_it_holds(
    gang, fighter, tester, sword
):
    """The model's own page draws the same acts the listing does, pointed
    at itself. Granted lines and a hire preview never call this, and stay
    names with nothing to click."""
    from n26.core.card import build_card
    from n26.core.owned import EquipHost
    from n26.core.render import build_model_card
    from n26.core.views.owned import link_possession_actions

    own = build_card(fighter)
    card = build_model_card(fighter, card=own)
    assert all(not line.sell for line in card.equipment)

    host = EquipHost.fighter(gang, own, fighter, AT)
    link_possession_actions(card, host)

    (line,) = [item for item in card.equipment if item.name == "Sword"]
    assert line.sell.target == f"{AT}&sell={sword.pk}"
    assert line.sell.label == "Sell"
    assert [act.label for act in line.more] == ["Reassign", "Refund", "Delete"]


class TestThePanelsAPageCarries:
    """The accessory question is built for every gun on a card rather than
    for the one an address names, so the click that opens one has nothing
    to wait for. Which is *open* is still the address's answer alone."""

    @staticmethod
    def panels(fighter, **query):
        from django.test import RequestFactory

        from n26.core.card import build_card
        from n26.core.owned import EquipHost
        from n26.core.views.owned import accessorise_dialogs

        card = build_card(fighter)
        request = RequestFactory().get(AT, query)
        host = EquipHost.fighter(fighter.gang, card, fighter, AT)
        return accessorise_dialogs(request, host)

    def test_every_gun_gets_one_and_nothing_else_does(self, fighter, gun, sight, sword):
        """A sword is a possession, and a gun is somewhere to bolt a sight
        onto. Only the second is a question worth drawing."""
        panels = self.panels(fighter)

        assert [panel["id"] for panel in panels] == [str(gun.pk)]
        assert panels[0]["accessories"] == [
            {"pk": str(sight.pk), "name": "Telescopic sight", "price": 25}
        ]

    def test_none_of_them_is_open_until_the_address_says_so(self, fighter, gun, sight):
        (closed,) = self.panels(fighter)
        (asked,) = self.panels(fighter, accessorise=str(gun.pk))

        assert closed["open"] is False
        assert asked["open"] is True

    def test_a_name_that_is_not_on_the_card_opens_nothing(self, fighter, gun, sight):
        """A stale link, or an address made by hand. The page comes back
        with its panels closed rather than with an error worth a screen —
        and the name is compared, never looked up, so nonsense is not a
        crash either."""
        for named in ("nonsense", str(sight.pk)):
            (panel,) = self.panels(fighter, accessorise=named)
            assert panel["open"] is False

    def test_another_question_wins_the_screen(self, fighter, gun, sight):
        """Two open panels is not a state a page can mean, and the order
        in DIALOGS settles which one an address naming both answers."""
        (panel,) = self.panels(fighter, sell=str(gun.pk), accessorise=str(gun.pk))

        assert panel["open"] is False

    def test_the_gangs_own_guns_are_not_the_fighters_to_kit_out(
        self, gang, fighter, tester
    ):
        """The gang's own assignments ride every member's card so gang-wide rules
        reach them. They are still the gang's, and no fighter's screen
        may offer to bolt something onto one."""
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Stub gun", price=10, profiles=[("", 0)])
        with operation(gang, actor=tester) as op:
            op.assign(weapon, gang=gang, paid=10)

        assert self.panels(fighter) == []

    def test_a_panel_carries_the_list_and_tab_it_was_drawn_on(
        self, fighter, gun, sight
    ):
        """The answer lands where the question was asked: an accessory
        bought from the third tab of a list comes back to it."""
        (panel,) = self.panels(fighter, list="7", section="Weapons")

        assert panel["list"] == "7"
        assert panel["section"] == "Weapons"
