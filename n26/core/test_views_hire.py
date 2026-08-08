"""Hiring a fighter: the picker's form contract, server side.

``build_hire_list`` and ``Operation.hire`` have their own tests — these
are about the wiring: the list draws, a press hires the right thing at
the right price, options map back to the sets they were drawn from, and
an overspend refuses cleanly.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import ChosenProfileOption, Gang, Miniature
from n26.library.models import DefaultAssignmentSet, OptionGroup

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
        starting_credits=200,
        credits=200,
    )


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return profile


def hire_url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def test_the_list_draws_with_prices(client, tester, gang, ganger):
    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert "Ganger" in body
    assert "55" in body


def test_every_registration_name_is_a_known_category(client, tester, gang, ganger):
    """The picker filters rows by ``categoryOn(name)`` client-side, and a
    row in an unnamed category registers under its *section's* name —
    possibly "". A categories list that omits a registration name hides
    every such row silently: the page serves the rows, Alpine never shows
    them, and no HTML assertion notices. So the context is pinned
    instead: every name a row will register under must be in the list.
    """
    client.force_login(tester)
    response = client.get(hire_url(gang))
    registration_names = {
        category["name"] or row["section"]["name"]
        for row in response.context["section_rows"]
        for category in row["section"]["categories"]
    }
    assert registration_names <= set(response.context["categories"])


def test_a_press_hires_and_lands_on_the_sheet(client, tester, gang, ganger):
    client.force_login(tester)
    response = client.post(hire_url(gang), {"profile": str(ganger.pk), "name": "Vex"})
    assert response.status_code == 302
    assert response.url == reverse("n26-gang", args=[gang.pk])

    fighter = Miniature.objects.get(membership__gang=gang)
    assert fighter.name == "Vex"
    gang.refresh_from_db()
    assert gang.credits == 145  # 200 - 55
    assert gang.rating == 55


def test_an_unnamed_hire_takes_the_profiles_name(client, tester, gang, ganger):
    client.force_login(tester)
    client.post(hire_url(gang), {"profile": str(ganger.pk), "name": ""})
    assert Miniature.objects.get(membership__gang=gang).name == "Ganger"


def test_an_option_maps_back_to_its_set(client, tester, gang, ganger):
    """The picker submits option *indices*; the server must resolve them
    against the same ordering the rows were drawn from.

    The profile here has only a named group, which is exactly the case
    where ``build_hire_entry`` synthesises a default group in front —
    so a parser reading raw ``grouped_options()`` would be off by one.
    """
    group = OptionGroup.objects.create(profile=ganger, name="Armament", choose="one")
    plain = DefaultAssignmentSet.objects.create(name="Knife", price=0)
    fancy = DefaultAssignmentSet.objects.create(name="Chainsword", price=25)
    ganger.options.create(profile=ganger, group=group, default_set=plain, position=0)
    ganger.options.create(profile=ganger, group=group, default_set=fancy, position=1)

    client.force_login(tester)
    # Group 0 is the synthesised "As standard"; the named group is 1. The
    # key is slugified — lowercased — because that is what the template
    # actually renders (`value|slugify` scopes the row's inputs). Posting
    # the raw uppercase pk here would pass against a parser that no real
    # browser can reach.
    from django.utils.text import slugify

    response = client.post(
        hire_url(gang),
        {"profile": str(ganger.pk), "name": "Vex", f"{slugify(str(ganger.pk))}:1": "1"},
    )
    assert response.status_code == 302

    fighter = Miniature.objects.get(membership__gang=gang)
    chosen = ChosenProfileOption.objects.filter(assignment=fighter.membership)
    assert [row.default_set for row in chosen] == [fancy]
    gang.refresh_from_db()
    assert gang.credits == 120  # 200 - (55 + 25)


def test_the_option_keys_match_what_the_template_renders(client, tester, gang, ganger):
    """The rendered input names and the parser must agree on case.

    The row template scopes inputs with `value|slugify`, which lowercases
    the ULID; a parser reading the raw pk finds no keys, and every option
    ticked in a real browser is silently dropped — the fighter hires as
    default at base price, no error anywhere. So the page's HTML is the
    fixture here: the name this asserts on is the name the parser reads.
    """
    from django.utils.text import slugify

    group = OptionGroup.objects.create(profile=ganger, name="Armament", choose="one")
    plain = DefaultAssignmentSet.objects.create(name="Knife", price=0)
    ganger.options.create(profile=ganger, group=group, default_set=plain, position=0)

    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert f'name="{slugify(str(ganger.pk))}:1"' in body


def test_a_double_pick_in_a_choose_one_group_is_refused(client, tester, gang, ganger):
    """Radios stop this in a browser; a tampered POST naming two options
    of a choose-one group must 404 like any other broken submission,
    not 500 out of resolve_selection."""
    from django.utils.text import slugify

    group = OptionGroup.objects.create(profile=ganger, name="Armament", choose="one")
    plain = DefaultAssignmentSet.objects.create(name="Knife", price=0)
    fancy = DefaultAssignmentSet.objects.create(name="Chainsword", price=25)
    ganger.options.create(profile=ganger, group=group, default_set=plain, position=0)
    ganger.options.create(profile=ganger, group=group, default_set=fancy, position=1)

    client.force_login(tester)
    response = client.post(
        hire_url(gang),
        {
            "profile": str(ganger.pk),
            "name": "Vex",
            f"{slugify(str(ganger.pk))}:1": ["0", "1"],
        },
    )
    assert response.status_code == 404
    assert not Miniature.objects.filter(membership__gang=gang).exists()


def test_mixed_sections_fall_back_to_untabbed(
    client, tester, gang, ganger, make_profile
):
    """Tabs are the picker's whole navigation once on, and only named
    sections can be tabs — so content where some profiles have a home
    and some do not must not tab, or the homeless shelf is served in
    the HTML and unreachable in the UI."""
    from n26.library.models import Category, Section

    section = Section.objects.create(name="Gang List", position=0)
    category = Category.objects.create(section=section, name="Champions", position=0)
    homed = make_profile("Champion", price=95)
    homed.category = category
    homed.save()
    # `ganger` stays homeless.

    client.force_login(tester)
    response = client.get(hire_url(gang))
    assert response.context["sections"] == []


def test_the_gang_list_tab_comes_before_the_supplementary_one(
    client, tester, gang, make_profile
):
    """The headings are tabs in the order the sections carry, not the
    order the profiles were written: a gang's own list reads first,
    everyone hired beside it after."""
    from n26.library.models import Category, Section

    supplementary = Section.objects.create(name="Supplementary Fighters", position=1)
    gang_list = Section.objects.create(name="Gang List", position=0)
    beasts = Category.objects.create(section=supplementary, name="Beasts", position=0)
    gangers = Category.objects.create(section=gang_list, name="Gangers", position=0)
    make_profile("Sumpkroc", price=65, category=beasts)
    make_profile("Ganger", price=55, category=gangers)

    client.force_login(tester)
    response = client.get(hire_url(gang))
    assert response.context["sections"] == ["Gang List", "Supplementary Fighters"]


def test_an_overspend_refuses_and_writes_nothing(client, tester, gang, make_profile):
    expensive = make_profile("Gang Queen", price=500)

    client.force_login(tester)
    response = client.post(
        hire_url(gang), {"profile": str(expensive.pk), "name": "Vesna"}
    )
    # Back to the hire page with a message, and no half-written rows.
    assert response.status_code == 302
    assert response.url == hire_url(gang)
    assert Miniature.objects.filter(membership__gang=gang).count() == 0
    gang.refresh_from_db()
    assert gang.credits == 200


def test_a_profile_of_another_gang_type_is_refused(
    client, tester, gang, make_profile, person_type
):
    """The list is the gang type's; a tampered POST naming someone
    else's profile must not hire it."""
    from n26.library.models import GangType

    other = GangType.objects.create(name="Goliath")
    outsider = make_profile("Forge Tyrant", gang_type=other, price=10)

    client.force_login(tester)
    response = client.post(
        hire_url(gang), {"profile": str(outsider.pk), "name": "Wrong"}
    )
    assert response.status_code == 200  # redisplays the list
    assert Miniature.objects.filter(membership__gang=gang).count() == 0


def test_someone_elses_gang_is_not_found(client, gang, ganger):
    stranger = User.objects.create_user("stranger", is_staff=True)
    client.force_login(stranger)
    assert client.get(hire_url(gang)).status_code == 404
    assert client.post(hire_url(gang), {"profile": str(ganger.pk)}).status_code == 404


def test_a_pk_that_is_not_a_ulid_is_not_found(client, tester):
    client.force_login(tester)
    assert client.get("/n26/gangs/nonsense/hire/").status_code == 404


def test_the_sheet_links_to_the_hire_page(client, tester, gang):
    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert hire_url(gang) in body
