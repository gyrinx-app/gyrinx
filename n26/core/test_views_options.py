"""The Options face of a model's own page: the hire row's choices,
reopened, with what the model currently takes checked.

``op.rechoose`` has its own suite; these tests are the seam — the page
draws the current answer, and a Save parses through the hire's own
field scheme into the operation.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify

from n26.core.models import Gang
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.models import DefaultAssignmentSet, OptionGroup

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=200,
        credits=200,
    )


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile)
    return profile


@pytest.fixture
def armament(ganger):
    """A named choose-one group: a knife, or a chainsword for 25 more.
    ``build_hire_entry`` synthesises a default group in front, so the
    named one is group 1 — the same offset the hire rows carry."""
    group = OptionGroup.objects.create(profile=ganger, name="Armament", choose="one")
    plain = DefaultAssignmentSet.objects.create(name="Knife", price=0)
    fancy = DefaultAssignmentSet.objects.create(name="Chainsword", price=25)
    ganger.options.create(
        profile=ganger, group=group, default_set=plain, name="Knife", position=0
    )
    ganger.options.create(
        profile=ganger, group=group, default_set=fancy, name="Chainsword", position=1
    )
    return plain, fancy


@pytest.fixture
def vex(tester, gang, ganger, armament):
    with operation(gang, actor=tester) as op:
        return op.hire(ganger, "Vex")


def options_url(miniature):
    return reverse("n26-fighter-options", args=[miniature.pk])


def field(profile, group):
    return f"{slugify(str(profile.pk))}:{group}"


class TestThePage:
    def test_it_draws_the_groups_with_the_current_answer_checked(
        self, client, tester, gang, ganger, vex
    ):
        client.force_login(tester)
        response = client.get(options_url(vex))
        body = response.content.decode()
        assert "Chainsword" in body
        assert "+25¢" in body
        assert "Save options" in body
        # Nothing recorded, so the one-of group is on its head.
        (group,) = response.context["groups"]
        assert [option["checked"] for option in group["options"]] == [True, False]

    def test_the_page_is_the_models_third_tab(self, client, tester, gang, vex):
        client.force_login(tester)
        body = client.get(reverse("n26-edit-fighter", args=[vex.pk])).content.decode()
        assert options_url(vex) in body

    def test_a_profile_with_no_options_gets_no_tab(
        self, client, tester, gang, make_profile, make_statline
    ):
        """A tab whose page could only say "nothing to choose" is chrome
        on every fighter for a feature most profiles lack — the strip
        offers Options only where there is a choice to reopen. The page
        itself still answers a direct address honestly."""
        plain = make_profile("Juve", price=20)
        make_statline(plain)
        with operation(gang, actor=tester) as op:
            fighter = op.hire(plain, "Kid")
        client.force_login(tester)
        body = client.get(
            reverse("n26-edit-fighter", args=[fighter.pk])
        ).content.decode()
        assert options_url(fighter) not in body

        body = client.get(options_url(fighter)).content.decode()
        assert "offers no options" in body
        assert "Save options" not in body

    def test_a_stranger_gets_a_404(self, client, gang, vex):
        client.force_login(User.objects.create_user("someone-else"))
        assert client.get(options_url(vex)).status_code == 404


class TestSaving:
    def test_a_new_choice_charges_the_difference_and_lands_back_here(
        self, client, tester, gang, ganger, vex
    ):
        client.force_login(tester)
        response = client.post(options_url(vex), {field(ganger, 1): "1"})
        assert response.status_code == 302
        assert response.url == options_url(vex)
        gang.refresh_from_db()
        assert gang.credits == 200 - 55 - 25
        vex.refresh_from_db()
        assert vex.rating == 80
        # And the page comes back with the new answer checked.
        (group,) = client.get(options_url(vex)).context["groups"]
        assert [option["checked"] for option in group["options"]] == [False, True]
        assert_reconciled(gang)

    def test_changing_back_returns_the_difference(
        self, client, tester, gang, ganger, armament, vex
    ):
        _, fancy = armament
        with operation(gang, actor=tester) as op:
            op.rechoose(vex.membership, option=fancy)
        client.force_login(tester)

        response = client.post(options_url(vex), {field(ganger, 1): "0"})

        assert response.status_code == 302
        gang.refresh_from_db()
        assert gang.credits == 200 - 55
        assert_reconciled(gang)

    def test_an_unaffordable_upgrade_is_a_message_not_a_change(
        self, client, tester, gang, ganger, vex
    ):
        gang.starting_credits = 55
        gang.save(update_fields=["starting_credits"])
        with operation(gang, actor=tester) as op:
            op.settle()
        client.force_login(tester)

        response = client.post(options_url(vex), {field(ganger, 1): "1"})

        assert response.status_code == 302
        gang.refresh_from_db()
        assert gang.credits == 0
        taken = [row.default_set.name for row in vex.membership.chosen_options.all()]
        assert taken == ["Knife"]
        assert_reconciled(gang)

    def test_a_tampered_index_is_refused(self, client, tester, gang, ganger, vex):
        client.force_login(tester)
        assert client.post(options_url(vex), {field(ganger, 1): "9"}).status_code == 404
        assert (
            client.post(options_url(vex), {field(ganger, 1): "-1"}).status_code == 404
        )

    def test_a_stranger_saves_nothing(self, client, gang, ganger, vex):
        client.force_login(User.objects.create_user("someone-else"))
        assert client.post(options_url(vex), {field(ganger, 1): "1"}).status_code == 404
        taken = [row.default_set.name for row in vex.membership.chosen_options.all()]
        assert taken == ["Knife"]
