"""The gang sheet: the design system's view over real rows.

Everything the page draws comes from ``render_gang``, which has its own
tests — these are about the wiring: who may see a gang, what a bad URL
does, and that the dashboard's rows actually reach it.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang
from n26.core.operations import operation

pytestmark = pytest.mark.django_db


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
        starting_credits=1000,
        credits=340,
    )


def test_draws_the_gang(client, tester, gang):
    client.force_login(tester)
    response = client.get(reverse("n26-gang", args=[gang.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert gang.name in body
    assert str(gang.gang_type) in body


def test_the_way_to_the_gang_list_is_named_for_what_it_offers(client, tester, gang):
    """The screen it leads to holds a reader through several hires, so the
    control says so. Hiring a vehicle is its own control and stays
    singular — that one is a single act."""
    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "Hire Fighters" in body
    assert "Hire fighter" not in body


def test_draws_each_member(client, tester, gang, make_profile, make_statline):
    """A hired fighter reaches the page as a card of its own."""
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    with operation(gang, actor=tester) as op:
        op.hire(profile, "Vex")
        op.hire(profile, "Sull")

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "Vex" in body
    assert "Sull" in body


def test_draws_the_gangs_standing_facts(client, tester, gang):
    """A counter the gang keeps reaches the details list, name and value."""
    from n26.library.authoring import create_counter
    from n26.tests.sandbox.actions import assign, tally

    tally(assign(create_counter("Meat"), gang=gang, actor=tester), +3)

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "Meat" in body


def test_no_empty_details_list_when_there_is_nothing_to_list(client, tester, gang):
    """The sheet spaces its sections, so an empty <dl> costs a visible gap.

    Pinned because the fix is a conditional slot, and a slot that turns
    out always to be filled would look identical in every other test.
    """
    client.force_login(tester)
    before = (
        client.get(reverse("n26-gang", args=[gang.pk])).content.decode().count("<dl")
    )

    from n26.library.authoring import create_counter
    from n26.tests.sandbox.actions import assign, tally

    tally(assign(create_counter("Meat"), gang=gang, actor=tester), +3)
    after = (
        client.get(reverse("n26-gang", args=[gang.pk])).content.decode().count("<dl")
    )

    assert after == before + 1


def test_someone_elses_gang_is_there_to_be_read(client, gang):
    """A roster is shareable: the address shows the same gang to whoever
    opens it, and owning it is what adds the controls."""
    stranger = User.objects.create_user("stranger")
    client.force_login(stranger)
    response = client.get(reverse("n26-gang", args=[gang.pk]))

    assert response.status_code == 200
    assert gang.name in response.content.decode()


def test_a_gang_reads_without_signing_in_at_all(client, gang):
    response = client.get(reverse("n26-gang", args=[gang.pk]))

    assert response.status_code == 200
    assert gang.name in response.content.decode()


def test_an_archived_gang_is_not_found(client, tester, gang):
    gang.archived = True
    gang.save()
    client.force_login(tester)
    assert client.get(reverse("n26-gang", args=[gang.pk])).status_code == 404


def test_a_pk_that_is_not_a_ulid_is_not_found(client, tester):
    """The id reaches ULIDField, which raises rather than missing.

    Without the view catching that, a mistyped URL is a 500 and an
    error report, for what is only ever somebody's bad link.
    """
    client.force_login(tester)
    assert client.get("/n26/gangs/nonsense/").status_code == 404


def test_founding_still_wins_over_the_id_route(client, tester):
    """`gangs/new/` must not resolve "new" as a gang id."""
    client.force_login(tester)
    assert client.get(reverse("n26-create-gang")).status_code == 200


def test_the_dashboard_links_to_the_sheet(client, tester, gang):
    """The row's href is the whole point of the screen being reachable."""
    client.force_login(tester)
    body = client.get(reverse("n26-dashboard")).content.decode()
    assert reverse("n26-gang", args=[gang.pk]) in body


def test_a_card_states_what_a_fighter_is_worth_and_no_other_money(
    client, tester, gang, make_profile, make_statline
):
    """A card is read while playing, where what a gun cost the gang months ago
    answers nothing at the table. So the fighter's own rating stays — it is
    what they are worth now — and the per-item prices go."""
    from n26.library.authoring import create_weapon

    profile = make_profile("Ganger", price=55)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        fighter = op.hire(profile, "Vex", paid=55)
        op.give_weapon(fighter, create_weapon("Autogun", price=30), paid=30)

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

    assert "Autogun" in body
    # The fighter's rating, on the header badge.
    assert "85¢" in body
    # Not the gun's price beside its name, in either shape the card had.
    assert "(30¢)" not in body
    assert "(+30¢)" not in body


def test_the_stash_keeps_its_prices(client, tester, gang):
    """The card and the stash read the same component; only the card asked it
    to stop. A stash is read while deciding what to sell, where the figure is
    the whole point."""
    from n26.core.browse import browse
    from n26.core.models import Stash
    from n26.library.authoring import create_collection, create_wargear

    # This file's gang is built directly rather than founded, so it has no
    # storage yet; founding is what normally makes one.
    Stash.objects.create(gang=gang)
    crate = create_wargear("Ammo crate", price=25)
    listing = create_collection("Trading Post", entries=[(crate, {})])
    with operation(gang, actor=tester) as op:
        op.buy(gang.stash, next(browse(listing).all_lines()))

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "Ammo crate" in body
    assert "25¢" in body


def test_a_weapon_with_no_stats_of_its_own_gives_its_name_the_whole_row(
    client, tester, gang, make_profile, make_statline
):
    """A combi-weapon carries an unnamed profile that is the weapon's identity
    and does its shooting through the named ones beneath, so its own row has
    nothing for the stat columns. The name takes the width rather than wrapping
    in the first column with nine empty ones beside it.

    Having an unnamed profile and having stats to print are two different
    facts; this is where they part company.
    """
    from n26.library.authoring import add_weapon_profile, create_weapon

    profile = make_profile("Ganger", price=55)
    make_statline(profile)

    combi = create_weapon("Combi-weapon (laspistol/meltagun)", price=115)
    # The weapon's own line: named for nothing, and with no characteristics —
    # the shape a combi-weapon really has in the library.
    add_weapon_profile(combi, name="")
    for name in ("laspistol", "meltagun"):
        add_weapon_profile(combi, name=name)

    with operation(gang, actor=tester) as op:
        fighter = op.hire(profile, "Vex", paid=55)
        op.give_weapon(fighter, combi, paid=115)

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

    assert "Combi-weapon (laspistol/meltagun)" in body
    # The name's cell spans the table rather than sitting in column one.
    start = body.index("Combi-weapon (laspistol/meltagun)")
    cell = body.rindex("<td", 0, start)
    assert "colspan" in body[cell:start]


def test_a_named_profile_opens_with_a_dash_under_its_weapon(
    client, tester, gang, make_profile, make_statline
):
    """The book prints an ammo type as a dash and a name beneath the gun it
    belongs to, and the card says it the same way: with no mark, a reader has
    only a few pixels of indent to tell an ammo type from a gun of its own.
    The weapon's own row carries no mark, so the two cannot be confused.

    The mark is decorative, so a card read aloud announces the ammo type's
    name and not a stray hyphen.
    """
    from n26.library.authoring import add_weapon_profile, create_weapon

    profile = make_profile("Ganger", price=55)
    make_statline(profile)

    launcher = create_weapon("Grenade launcher", price=65)
    for name in ("frag", "krak"):
        add_weapon_profile(launcher, name=name)

    with operation(gang, actor=tester) as op:
        fighter = op.hire(profile, "Vex", paid=55)
        op.give_weapon(fighter, launcher, paid=65)

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    # Scoped to the weapon table, so a name drawn elsewhere on the page
    # cannot stand in for the row being read here.
    table = body[body.index("Weapons") :]

    for name in ("frag", "krak"):
        start = table.index(f"{name}</span>")
        opened = table.rindex("<span", 0, start)
        assert '<span aria-hidden="true">-</span>&nbsp;' in table[opened:start], (
            f"{name} is drawn without the dash that says it hangs off the gun"
        )

    # The weapon's own row is the gun itself, and opens with no mark.
    gun = table.index("Grenade launcher")
    assert "aria-hidden" not in table[table.rindex("<td", 0, gun) : gun]


class TestRefittingAStashedAccessory:
    """A sight kept back from a sale is gear waiting for a gun, and the
    sheet is where the gang's spare kit is read — so the way back onto a
    gun is here."""

    @pytest.fixture
    def kit(self, gang, tester, make_profile, make_statline):
        """A fighter with an autogun, and a telescopic sight in the stash."""
        from n26.core.models import Stash
        from n26.library.authoring import create_weapon, create_weapon_accessory

        profile = make_profile("Ganger", price=55)
        make_statline(profile)
        stash, _ = Stash.objects.get_or_create(gang=gang)
        sight = create_weapon_accessory("Telescopic sight", price=25)
        with operation(gang, actor=tester) as op:
            fighter = op.hire(profile, "Vex", paid=55)
            gun = op.give_weapon(
                fighter, create_weapon("Autogun", price=20, profiles=[("", 0)]), paid=20
            )
            bolted = op.buy(gun, thing=sight)
            op.move(bolted, stash)
        return gun, bolted

    def test_the_stash_line_offers_a_way_back_onto_a_gun(
        self, client, tester, gang, kit
    ):
        _, bolted = kit
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Telescopic sight" in body
        assert f"?refit={bolted.pk}" in body
        assert "Fit to a weapon" in body

    def test_the_address_opens_a_picker_over_the_gangs_guns(
        self, client, tester, gang, kit
    ):
        gun, bolted = kit
        client.force_login(tester)
        response = client.get(
            reverse("n26-gang", args=[gang.pk]) + f"?refit={bolted.pk}"
        )
        body = response.content.decode()

        assert response.context["refitting"]["weapons"] == [
            {"pk": str(gun.pk), "label": "Autogun (Vex)"}
        ]
        assert "<dialog open" in body
        # The picker posts the same move a fighter's row does, one level
        # down the chain.
        assert reverse("n26-reassign", args=[bolted.pk]) in body
        assert 'name="to" value="weapon"' in body

    def test_something_that_is_not_a_stashed_accessory_opens_nothing(
        self, client, tester, gang, kit
    ):
        gun, _ = kit
        client.force_login(tester)
        response = client.get(reverse("n26-gang", args=[gang.pk]) + f"?refit={gun.pk}")
        assert response.context["refitting"] is None

    def test_a_pk_that_is_not_a_ulid_opens_nothing(self, client, tester, gang, kit):
        client.force_login(tester)
        response = client.get(reverse("n26-gang", args=[gang.pk]) + "?refit=nonsense")
        assert response.context["refitting"] is None

    def test_another_gangs_stash_is_not_reachable(
        self, client, tester, gang, kit, gang_type
    ):
        """Scoped to this gang's own stash: the address names an assignment,
        and one belonging to somebody else is not on this sheet."""
        from n26.core.models import Stash
        from n26.library.authoring import create_weapon_accessory

        _, _ = kit
        stranger = User.objects.create_user("stranger")
        theirs = Gang.objects.create(
            name="Their Gang", owner=stranger, gang_type=gang_type
        )
        their_stash, _ = Stash.objects.get_or_create(gang=theirs)
        with operation(theirs, actor=stranger) as op:
            hidden = op.buy(
                their_stash, thing=create_weapon_accessory("Suspensors", price=30)
            )

        client.force_login(tester)
        response = client.get(
            reverse("n26-gang", args=[gang.pk]) + f"?refit={hidden.pk}"
        )
        assert response.context["refitting"] is None
