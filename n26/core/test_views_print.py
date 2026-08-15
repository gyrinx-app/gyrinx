"""Printing a gang: the setup screen's memory and the sheet it drives.

``render_gang``, ``build_card`` and the print components have their own
tests — these are about the wiring: a config remembers what was ticked,
the print page draws exactly that, and a weapon left unticked takes its
effects off the paper with it.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang, PrintConfig
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
        starting_credits=500,
        credits=500,
    )


@pytest.fixture
def roster(gang, make_profile, make_statline, tester):
    """Two fighters; the first carries two weapons."""
    from n26.library.authoring import create_weapon

    profile = make_profile("Ganger", price=50)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    lasgun = create_weapon("Lasgun", price=15)
    stub = create_weapon("Stub Gun", price=5)
    with operation(gang, actor=tester) as op:
        vex = op.hire(profile, "Vex")
        sull = op.hire(profile, "Sull")
        op.give_weapon(vex, lasgun, paid=15)
        op.give_weapon(vex, stub, paid=5)
    return vex, sull


def setup_url(gang):
    return reverse("n26-print-setup", args=[gang.pk])


def print_url(gang):
    return reverse("n26-print", args=[gang.pk])


class TestTheSetupScreen:
    def test_draws_every_model_with_its_weapons_ticked(
        self, client, tester, gang, roster
    ):
        client.force_login(tester)
        body = client.get(setup_url(gang)).content.decode()
        assert "Vex" in body
        assert "Sull" in body
        assert "Lasgun" in body
        # Everything starts ticked — asserted per input kind, because a
        # bare count was once satisfied by the weapons and toggles alone
        # while every model rendered unticked: a cotton :prop had been
        # handed an `in` expression, which evaluates to nothing without
        # erroring.
        model_inputs = [
            chunk for chunk in body.split("<input") if 'name="fighters"' in chunk
        ]
        weapon_inputs = [
            chunk for chunk in body.split("<input") if 'name="weapons"' in chunk
        ]
        assert len(model_inputs) == 2
        assert all("checked" in chunk for chunk in model_inputs)
        assert len(weapon_inputs) == 2
        assert all("checked" in chunk for chunk in weapon_inputs)

    def test_an_unnamed_post_rewrites_the_scratch_config(
        self, client, tester, gang, roster
    ):
        vex, sull = roster
        client.force_login(tester)
        client.post(setup_url(gang), {"fighters": [str(vex.pk)]})
        client.post(setup_url(gang), {"fighters": [str(sull.pk)]})

        scratches = PrintConfig.objects.filter(gang=gang, name="")
        assert scratches.count() == 1
        assert list(scratches.get().miniatures.all()) == [sull]

    def test_a_named_post_saves_and_is_listed(self, client, tester, gang, roster):
        vex, _ = roster
        client.force_login(tester)
        response = client.post(
            setup_url(gang),
            {"name": "Tournament crew", "fighters": [str(vex.pk)]},
        )
        config = PrintConfig.objects.get(gang=gang, name="Tournament crew")
        assert response.url == f"{print_url(gang)}?config={config.pk}"

        body = client.get(setup_url(gang)).content.decode()
        assert "Tournament crew" in body

    def test_resaving_under_another_casing_overwrites_the_same_setup(
        self, client, tester, gang, roster
    ):
        """A gang is unique over its configs' lowercased names, so a
        name differing only in case is the same setup — matching it
        exactly would miss, insert, and trip the constraint."""
        vex, sull = roster
        client.force_login(tester)
        client.post(setup_url(gang), {"name": "Roster", "fighters": [str(vex.pk)]})
        client.post(setup_url(gang), {"name": "roster", "fighters": [str(sull.pk)]})

        configs = PrintConfig.objects.filter(gang=gang, name__iexact="roster")
        assert configs.count() == 1
        # Overwritten in place, keeping the name it was first saved under.
        assert configs.get().name == "Roster"
        assert list(configs.get().miniatures.all()) == [sull]

    def test_loading_a_config_prefills_the_form(self, client, tester, gang, roster):
        vex, sull = roster
        config = PrintConfig.objects.create(gang=gang, name="Crew", include_stash=False)
        config.miniatures.set([vex])

        client.force_login(tester)
        response = client.get(f"{setup_url(gang)}?config={config.pk}")
        assert str(vex.pk) in response.context["ticked_models"]
        assert str(sull.pk) not in response.context["ticked_models"]
        assert response.context["include_stash"] is False
        assert response.context["setup_name"] == "Crew"

    def test_another_gangs_rows_cannot_be_smuggled_in(
        self, client, tester, gang, roster, gang_type, make_profile
    ):
        """A POST naming a stranger's fighter writes a config without it."""
        vex, _ = roster
        other = Gang.objects.create(
            name="Someone else's",
            owner=User.objects.create_user("other"),
            gang_type=gang_type,
        )
        with operation(other, actor=other.owner) as op:
            intruder = op.hire(make_profile("Drifter", price=0), "Intruder")

        client.force_login(tester)
        client.post(
            setup_url(gang),
            {"fighters": [str(vex.pk), str(intruder.pk)]},
        )
        config = PrintConfig.objects.get(gang=gang, name="")
        assert list(config.miniatures.all()) == [vex]


class TestThePrintPage:
    def test_prints_everything_without_a_config(self, client, tester, gang, roster):
        client.force_login(tester)
        body = client.get(print_url(gang)).content.decode()
        assert gang.name in body
        assert "Vex" in body
        assert "Sull" in body
        assert "Lasgun" in body

    def test_a_config_narrows_the_fighters(self, client, tester, gang, roster):
        vex, sull = roster
        config = PrintConfig.objects.create(gang=gang, name="Crew")
        config.miniatures.set([vex])
        config.assignments.set(vex.assignments.filter(weapon__isnull=False))

        client.force_login(tester)
        body = client.get(f"{print_url(gang)}?config={config.pk}").content.decode()
        assert "Vex" in body
        assert "Sull" not in body

    def test_an_unticked_weapon_stays_off_the_paper(self, client, tester, gang, roster):
        vex, _ = roster
        lasgun_row = vex.assignments.get(weapon__name="Lasgun")
        config = PrintConfig.objects.create(gang=gang, name="Light kit")
        config.miniatures.set([vex])
        config.assignments.set([lasgun_row])  # the stub gun is unticked

        client.force_login(tester)
        body = client.get(f"{print_url(gang)}?config={config.pk}").content.decode()
        assert "Lasgun" in body
        assert "Stub Gun" not in body

    def test_the_toggles_remove_their_blocks(self, client, tester, gang, roster):
        vex, _ = roster
        config = PrintConfig.objects.create(
            gang=gang, name="Cards only", include_header=False, include_stash=False
        )
        config.miniatures.set([vex])

        client.force_login(tester)
        body = client.get(f"{print_url(gang)}?config={config.pk}").content.decode()
        assert "Vex" in body
        assert "Rating" not in body  # the header's figure strip

    def test_the_weapon_table_keeps_its_headings(
        self, client, tester, gang, roster, make_stat
    ):
        """A weapon with no stats of its own must not cost the table its
        headings.

        The columns are the statline type's, and one weapon having nothing
        to put in them says nothing about the others: a combi-weapon
        sorting to the top of a card once left the whole table headless
        while every row beneath it printed five numbers.
        """
        from n26.library.authoring import create_weapon
        from n26.library.models import StatlineType, StatlineTypeStat

        vex, _ = roster
        shape = StatlineType.objects.create(name="Weapon")
        for position, (short, full) in enumerate(
            [("SR", "Short Range"), ("Str", "Strength")]
        ):
            StatlineTypeStat.objects.create(
                statline_type=shape,
                stat=make_stat(short, full),
                position=position,
            )
        # Sorts before Lasgun, and its own line carries no characteristics.
        combi = create_weapon(
            "Combi-weapon", price=30, profiles=[("", 0), ("meltagun", 0)]
        )
        combi.statline_type = shape
        combi.save()
        from n26.library.authoring import set_statline

        set_statline(combi.profiles.get(name="meltagun"), short_range=6, strength=8)
        with operation(gang, actor=tester) as op:
            op.give_weapon(vex, combi, paid=30)

        client.force_login(tester)
        body = client.get(print_url(gang)).content.decode()
        assert 'title="Short Range"' in body
        assert 'title="Strength"' in body

    def test_a_bigger_roster_costs_no_more_queries_to_print(
        self, client, tester, gang, roster, make_profile
    ):
        """The page derives the gang once — header, stash and every card
        from one build — so printing costs the same queries however many
        models are on the paper or how much they carry."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import create_weapon

        client.force_login(tester)
        profile = make_profile("Reinforcement", price=40)
        axe = create_weapon("Axe", price=10)

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert client.get(print_url(gang)).status_code == 200
            return len(captured.captured_queries)

        # The first request pays one-time caches nothing after it does;
        # what is measured is the page's own budget.
        measure()
        few = measure()
        for index in range(3):
            with operation(gang, actor=tester) as op:
                hired = op.hire(profile, f"More {index}")
                op.give_weapon(hired, axe, paid=10)
        assert measure() == few

    def test_the_page_fetches_the_gangs_rows_once(self, client, tester, gang, roster):
        """One derivation serves the header, the stash and every card:
        the gang's assignments are fetched exactly twice — its own and
        its stash's — not once per block that draws them."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(tester)
        client.get(print_url(gang))
        with CaptureQueriesContext(connection) as captured:
            assert client.get(print_url(gang)).status_code == 200
        row_fetches = [
            query["sql"]
            for query in captured.captured_queries
            if query["sql"].startswith("SELECT")
            and 'FROM "n26_assignment"' in query["sql"]
        ]
        assert len(row_fetches) == 2

    def test_someone_elses_config_is_ignored(self, client, tester, gang, roster):
        """A config id belonging to another gang falls back to printing
        everything — the URL names a thing the viewer does not hold."""
        other = Gang.objects.create(
            name="Elsewhere",
            owner=User.objects.create_user("other"),
            gang_type=gang.gang_type,
        )
        foreign = PrintConfig.objects.create(gang=other, name="Theirs")

        client.force_login(tester)
        body = client.get(f"{print_url(gang)}?config={foreign.pk}").content.decode()
        assert "Vex" in body
        assert "Sull" in body

    def test_someone_elses_gang_is_not_found(self, client, gang, roster):
        stranger = User.objects.create_user("stranger")
        client.force_login(stranger)
        assert client.get(print_url(gang)).status_code == 404
        assert client.get(setup_url(gang)).status_code == 404

    def test_the_sheet_links_to_the_setup(self, client, tester, gang, roster):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert setup_url(gang) in body


class TestWhatPaperLeavesOut:
    """A printed card says what the model can do, not what the app can do
    with it.

    What a player saw: "BUYS FROM — Delaque Equipment List" printed under
    Gear on every card of the roster. Nobody buys from a card in their
    hand, and the row spends space the rules need.
    """

    @pytest.fixture
    def buyer(self, gang, make_profile, make_statline, tester):
        """A fighter who arrives holding their house list, as a hire does."""
        from n26.library.authoring import (
            create_collection,
            create_default_set,
            create_weapon,
        )

        profile = make_profile("Delaque Ganger", price=50)
        make_statline(profile, movement=5, weapon_skill=4, toughness=3)
        house_list = create_collection(
            "Delaque Equipment List", entries=[create_weapon("Web pistol", price=30)]
        )
        profile.built_ins = create_default_set("Delaque kit", members=[house_list])
        profile.save()
        with operation(gang, actor=tester) as op:
            return op.hire(profile, "Nyla")

    def test_the_card_still_holds_the_lists_it_buys_from(self, buyer):
        """The fact stays on the structure — it is what the app reads to
        offer Equip. Only paper leaves it out."""
        from n26.core.render import build_model_card

        drawn = build_model_card(buyer)

        assert [line.name for line in drawn.collections] == ["Delaque Equipment List"]

    def test_the_paper_carries_no_buys_from_row(self, client, tester, gang, buyer):
        client.force_login(tester)

        body = client.get(print_url(gang)).content.decode()

        assert "Nyla" in body  # the card is on the paper
        assert "Buys from" not in body
        assert "Delaque Equipment List" not in body
