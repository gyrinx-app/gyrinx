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
    return User.objects.create_user("player", is_staff=True)


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
        stranger = User.objects.create_user("stranger", is_staff=True)
        client.force_login(stranger)
        assert client.get(print_url(gang)).status_code == 404
        assert client.get(setup_url(gang)).status_code == 404

    def test_the_sheet_links_to_the_setup(self, client, tester, gang, roster):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert setup_url(gang) in body
