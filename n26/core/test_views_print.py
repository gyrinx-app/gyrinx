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

    def test_the_sheet_links_to_the_setup(self, client, tester, gang, roster):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert setup_url(gang) in body


class TestPrintingSomebodyElsesGang:
    """Printing a gang and saving a setup on it are two permissions.

    Players print rosters for each other, and paper says nothing the sheet
    has not already shown — so whoever can read a gang can print it. What
    stays the owner's is the saving: a reader who does not own the gang
    ticks the same boxes and carries the answer in the address.
    """

    @pytest.fixture
    def stranger(self, db):
        return User.objects.create_user("stranger")

    def test_a_stranger_prints_the_whole_gang(self, client, stranger, gang, roster):
        client.force_login(stranger)

        body = client.get(print_url(gang)).content.decode()

        assert "Vex" in body
        assert "Sull" in body

    def test_a_stranger_opens_the_setup_screen(self, client, stranger, gang, roster):
        client.force_login(stranger)

        body = client.get(setup_url(gang)).content.decode()

        assert "Vex" in body
        assert "Lasgun" in body

    def test_a_stranger_is_offered_the_setups_the_owner_saved(
        self, client, stranger, gang, roster
    ):
        """A named setup is the gang as its owner meant it to go on paper,
        so it is one click for whoever is doing the printing."""
        vex, _ = roster
        config = PrintConfig.objects.create(gang=gang, name="Tournament crew")
        config.miniatures.set([vex])

        client.force_login(stranger)
        body = client.get(setup_url(gang)).content.decode()

        assert "Tournament crew" in body
        # The count is counted in the view; a missing one would draw as
        # nothing here rather than raising.
        assert "1 model" in body
        assert f"{print_url(gang)}?config={config.pk}" in body
        # Editing it would mean saving it, which is not theirs to do.
        assert f"{setup_url(gang)}?config={config.pk}" not in body

    def test_a_stranger_is_offered_nowhere_to_save(
        self, client, stranger, gang, roster
    ):
        """No name field, and the boxes go to the paper rather than here:
        the screen offers exactly what they may do with it."""
        client.force_login(stranger)

        body = client.get(setup_url(gang)).content.decode()

        assert 'name="name"' not in body
        assert f'action="{print_url(gang)}"' in body
        assert 'method="get"' in body
        # A token in a GET form would ride in the address, and so into
        # history and into any link the reader sends on.
        assert "csrfmiddlewaretoken" not in body

    def test_the_owners_screen_still_saves(self, client, tester, gang, roster):
        """The other side of the test above, which alone would stay green
        if the owner's form regressed to the reader's arm — their Print
        would then quietly print without saving, or refuse on the token."""
        client.force_login(tester)

        body = client.get(setup_url(gang)).content.decode()

        assert f'action="{setup_url(gang)}"' in body
        assert 'method="post"' in body
        assert "csrfmiddlewaretoken" in body
        assert 'name="name"' in body

    def test_the_boxes_on_the_screen_print_what_they_say(
        self, client, stranger, gang, roster
    ):
        """The screen and the paper are wired to each other.

        Submitted the way a browser would — the form's own address, its
        own ticked boxes, one of them unticked first — so a renamed box
        or a missing ``pick`` fails here rather than quietly printing the
        whole gang in place of the pick, which is the shape of the bug a
        both-boxes-ticked submission cannot see.
        """
        import re
        from urllib.parse import urlencode

        _, sull = roster
        client.force_login(stranger)
        body = client.get(setup_url(gang)).content.decode()

        # The print form alone, found by the marker only it carries — the
        # layout's own forms and inputs would otherwise be read as part of
        # this one, and a retargeted action would go unnoticed.
        form = next(
            piece for piece in body.split("<form ")[1:] if 'name="pick"' in piece
        )
        opening = form.split(">")[0]
        assert 'method="get"' in opening
        action = re.search(r'action="([^"]*)"', opening).group(1)
        sent = []
        for chunk in form.split("<input")[1:]:
            chunk = chunk.split(">")[0]
            name = re.search(r'name="([^"]+)"', chunk)
            if name is None:
                continue
            value = re.search(r'value="([^"]*)"', chunk)
            if 'type="hidden"' in chunk:
                sent.append((name.group(1), value.group(1)))
            elif "checked" in chunk:
                sent.append((name.group(1), value.group(1) if value else "on"))

        # As if the reader had unticked one of the two models.
        sent = [pair for pair in sent if pair[1] != str(sull.pk)]
        paper = client.get(f"{action}?{urlencode(sent)}").content.decode()

        assert "Vex" in paper
        assert "Sull" not in paper
        # Vex's weapons rode along, and the header block with them —
        # nothing else on the page can put either there.
        assert "Lasgun" in paper
        assert "Stub Gun" in paper
        assert "Rating" in paper

    def test_an_unreadable_id_costs_that_id_when_the_owner_saves_too(
        self, client, tester, gang, roster
    ):
        """The owner's save reads ids the same way the reader's print
        does. Handed one that is not an id, it drops that one rather than
        raising the field's refusal up as a 500."""
        vex, _ = roster
        client.force_login(tester)

        response = client.post(
            setup_url(gang),
            {"name": "Vex alone", "fighters": [str(vex.pk), "not-an-id"]},
        )

        assert response.status_code == 302
        config = PrintConfig.objects.get(gang=gang, name="Vex alone")
        assert list(config.miniatures.all()) == [vex]

    def test_a_strangers_post_saves_nothing(self, client, stranger, gang, roster):
        vex, _ = roster
        client.force_login(stranger)

        response = client.post(setup_url(gang), {"fighters": [str(vex.pk)]})

        assert response.status_code == 404
        assert not PrintConfig.objects.filter(gang=gang).exists()

    def test_a_strangers_pick_prints_only_what_it_names(
        self, client, stranger, gang, roster
    ):
        vex, _ = roster
        client.force_login(stranger)

        body = client.get(
            print_url(gang),
            {"pick": "1", "fighters": [str(vex.pk)], "include_header": "on"},
        ).content.decode()

        assert "Vex" in body
        assert "Sull" not in body

    def test_a_strangers_pick_drops_the_weapons_it_leaves_out(
        self, client, stranger, gang, roster
    ):
        vex, _ = roster
        lasgun = vex.assignments.get(weapon__name="Lasgun")
        client.force_login(stranger)

        body = client.get(
            print_url(gang),
            {
                "pick": "1",
                "fighters": [str(vex.pk)],
                "weapons": [str(lasgun.pk)],
            },
        ).content.decode()

        assert "Lasgun" in body
        assert "Stub Gun" not in body

    def test_a_strangers_pick_can_turn_the_blocks_off(
        self, client, stranger, gang, roster
    ):
        """An unticked box sends nothing, so the toggles are read as
        absent-means-off — which is only safe because ``pick`` says the
        address carries a choice at all."""
        vex, _ = roster
        client.force_login(stranger)

        body = client.get(
            print_url(gang), {"pick": "1", "fighters": [str(vex.pk)]}
        ).content.decode()

        assert "Vex" in body
        assert "Rating" not in body  # the header's figure strip

    def test_an_address_that_ticked_nothing_prints_nothing(
        self, client, stranger, gang, roster
    ):
        """Not the same as the plain print address, which prints the lot."""
        client.force_login(stranger)

        body = client.get(print_url(gang), {"pick": "1"}).content.decode()

        assert "Vex" not in body
        assert "Sull" not in body

    def test_an_unreadable_id_costs_that_id_and_not_the_print(
        self, client, stranger, gang, roster
    ):
        """An address is a thing people edit and links get mangled in
        chat, so a weapon id that is not an id at all leaves the rest of
        the print standing."""
        vex, _ = roster
        lasgun = vex.assignments.get(weapon__name="Lasgun")
        client.force_login(stranger)

        body = client.get(
            print_url(gang),
            {
                "pick": "1",
                "fighters": [str(vex.pk)],
                "weapons": [str(lasgun.pk), "not-an-id"],
            },
        ).content.decode()

        assert "Vex" in body
        assert "Lasgun" in body

    def test_either_spelling_of_an_id_names_the_same_model(
        self, client, stranger, gang, roster
    ):
        """An id has a short spelling and a long one, and an address is a
        thing people build. Weapons have always read both; models reading
        only one would print an empty sheet for a link that named them."""
        vex, _ = roster
        client.force_login(stranger)

        body = client.get(
            print_url(gang),
            {"pick": "1", "fighters": [str(vex.pk.to_uuid())]},
        ).content.decode()

        assert "Vex" in body
        assert "Sull" not in body

    def test_another_gangs_weapon_cannot_be_smuggled_onto_the_paper(
        self, client, stranger, gang, roster, gang_type, make_profile
    ):
        vex, _ = roster
        other = Gang.objects.create(
            name="Elsewhere",
            owner=User.objects.create_user("other"),
            gang_type=gang_type,
        )
        from n26.library.authoring import create_weapon

        with operation(other, actor=other.owner) as op:
            intruder = op.hire(make_profile("Drifter", price=0), "Intruder")
            op.give_weapon(intruder, create_weapon("Boltgun", price=55), paid=55)
        theirs = intruder.assignments.get(weapon__name="Boltgun")

        client.force_login(stranger)
        body = client.get(
            print_url(gang),
            {"pick": "1", "fighters": [str(vex.pk)], "weapons": [str(theirs.pk)]},
        ).content.decode()

        assert "Boltgun" not in body

    def test_an_archived_gang_is_nobodys_to_print(self, client, stranger, gang, roster):
        gang.archived = True
        gang.save()

        client.force_login(stranger)

        assert client.get(print_url(gang)).status_code == 404
        assert client.get(setup_url(gang)).status_code == 404


class TestPrintingNeedsSigningIn:
    """A roster may be read by a visitor and printed by a player.

    The sheet itself is open to whoever holds its address; printing is
    where the line falls, so the print address is worth sending to a
    person rather than to whatever follows links.
    """

    def test_the_paper_sends_a_signed_out_reader_to_sign_in(self, client, gang, roster):
        response = client.get(print_url(gang))

        assert response.status_code == 302
        assert reverse("account_login") in response.url

    def test_the_setup_screen_does_the_same(self, client, gang, roster):
        response = client.get(setup_url(gang))

        assert response.status_code == 302
        assert reverse("account_login") in response.url


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
