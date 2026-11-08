"""Hiring a fighter: the picker's form contract, server side.

``build_hire_list`` and ``Operation.hire`` have their own tests — these
are about the wiring. A hire is three requests: a click says which
profile, the URL it lands on draws the name dialog, and the dialog's
submit hires and comes back for the next one. Each step is pinned here,
along with the refusals, because every one of them is a way a fighter
could be bought at the wrong price or not at all.
"""

import json
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify

from n26.core.models import ChosenProfileOption, Gang, Miniature
from n26.core.reconcile import assert_reconciled
from n26.core.taxonomy import UNCATEGORISED
from n26.library.models import DefaultAssignmentSet, OptionGroup

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
        starting_credits=200,
        credits=200,
    )


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return profile


@pytest.fixture
def armament(ganger):
    """A named choose-one group on the ganger: a knife, or a chainsword
    for 25 more. The case where ``build_hire_entry`` synthesises a default
    group in front, so the named one is group 1."""
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


def hire_url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def page_props(response):
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="hire"]')
    assert host is not None
    return json.loads(page.find(id=host["data-react-props"]).string)


def catalogue_entries(data):
    return [
        entry
        for section in data["sections"]
        for category in section["categories"]
        for entry in category["entries"]
    ]


def dialog_url(gang, profile, options=()):
    """The URL a click lands on: the list, with the dialog open.

    ``options`` are (group index, option index) pairs, scoped the way the
    rows scope theirs.
    """
    query = "&".join(
        f"{slugify(str(profile.pk))}:{group}={option}" for group, option in options
    )
    return f"{hire_url(gang)}?hire={profile.pk}{'&' + query if query else ''}"


def click(client, gang, profile, **data):
    """Click Hire on a row, as the picker's form does."""
    return client.post(hire_url(gang), {"hire": str(profile.pk), **data})


def test_the_list_draws_with_prices(client, tester, gang, ganger):
    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert "Ganger" in body
    assert "55" in body


def test_the_searchable_catalogue_has_one_react_owner(client, tester, gang, ganger):
    client.force_login(tester)
    response = client.get(hire_url(gang))
    page = BeautifulSoup(response.content, "html.parser")
    assert len(page.select('[data-react-name="hire"]')) == 1
    assert catalogue_entries(page_props(response))[0]["name"] == "Ganger"


def card_url(gang, profile):
    return reverse("n26-hire-card", args=[gang.pk, profile.pk])


def test_the_list_ships_no_cards_and_says_where_each_lives(
    client, tester, gang, ganger
):
    client.force_login(tester)
    response = client.get(hire_url(gang))
    (entry,) = catalogue_entries(page_props(response))
    assert entry["previewHref"] == reverse(
        "n26-hire-preview", args=[gang.pk, ganger.pk]
    )
    assert "card" not in entry
    assert "Weapon Skill" not in response.content.decode()


def test_a_cards_fragment_is_the_card_itself(client, tester, gang, ganger):
    client.force_login(tester)
    body = client.get(card_url(gang, ganger)).content.decode()
    assert "Ganger" in body
    assert "Weapon Skill" in body
    assert "<!DOCTYPE" not in body


def test_the_fragment_draws_the_option_it_is_asked_for(
    client, tester, gang, ganger, armament
):
    """The card behind the chainsword option carries the chainsword,
    and the default card does not — each fragment is the card that
    exact pick would produce."""
    from n26.library.authoring import create_weapon
    from n26.library.models import DefaultAssignment

    plain, fancy = armament
    sword = create_weapon("Chainsword", profiles=[("Standard", 0)], price=25)
    DefaultAssignment.objects.create(default_set=fancy, assignable=sword, position=0)

    client.force_login(tester)
    fancy_body = client.get(
        f"{card_url(gang, ganger)}?option={fancy.pk}"
    ).content.decode()
    default_body = client.get(card_url(gang, ganger)).content.decode()
    assert "Chainsword" in fancy_body
    assert "Chainsword" not in default_body


def test_an_option_the_profile_does_not_offer_is_a_broken_link(
    client, tester, gang, ganger
):
    stray = DefaultAssignmentSet.objects.create(name="Someone else's", price=10)
    client.force_login(tester)
    response = client.get(f"{card_url(gang, ganger)}?option={stray.pk}")
    assert response.status_code == 404


def test_someone_elses_gang_serves_no_cards(client, gang, ganger):
    from django.contrib.auth.models import User

    stranger = User.objects.create_user("stranger")
    client.force_login(stranger)
    assert client.get(card_url(gang, ganger)).status_code == 404


def test_the_other_scopes_are_offered_to_the_browser_early(
    client, tester, gang, ganger
):
    """Prefetch alternate scope documents on intent without rendering hidden copies.

    Exclude the current tab, whose document is already loaded.
    """
    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert '<script type="speculationrules">' in body
    assert '"prefetch"' in body
    assert '"prerender"' not in body
    assert "nav[data-speculate='who-can-be-hired'] a:not([aria-current])" in body


def test_all_three_scopes_are_delivered_for_the_visible_navigation(
    client, tester, gang, ganger
):
    client.force_login(tester)
    data = page_props(client.get(hire_url(gang)))
    assert [tab["label"] for tab in data["scopeTabs"]] == [
        "Gang list",
        "Supplementary",
        "All profiles",
    ]
    assert data["scopeTabs"][-1]["href"] == hire_url(gang) + "?list=all"


def test_the_list_asks_for_no_name(client, tester, gang, ganger):
    """Naming is the dialog's question, and asking it twice would mean two
    places a name could be typed and only one of them read."""
    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert 'name="name"' not in body


def test_every_registration_name_is_a_known_category(client, tester, gang, ganger):
    client.force_login(tester)
    data = page_props(client.get(hire_url(gang)))
    registration_names = {
        category["name"] or section["name"]
        for section in data["sections"]
        for category in section["categories"]
    }
    assert registration_names <= set(data["categories"])


def test_a_click_lands_on_the_dialogs_url(client, tester, gang, ganger):
    """Which profile was clicked is a URL, not a hidden state: that is what
    makes the dialog survive a reload and a click work without scripting."""
    client.force_login(tester)
    response = click(client, gang, ganger)
    assert response.status_code == 302
    assert response.url == dialog_url(gang, ganger)
    assert not Miniature.objects.filter(membership__gang=gang).exists()


def test_the_dialog_names_the_profile_and_its_price(client, tester, gang, ganger):
    client.force_login(tester)
    data = page_props(client.get(dialog_url(gang, ganger)))
    assert data["confirmation"]
    assert data["values"]["profile_name"] == "Ganger"
    assert data["values"]["profile"] == str(ganger.pk)
    assert data["values"]["quoted"] == data["values"]["paid"] == "55"
    assert data["values"]["name"] == ""


def test_the_screen_offers_more_than_one_hire(client, tester, gang, ganger):
    client.force_login(tester)
    response = client.get(hire_url(gang))
    assert "Hire Fighters" in response.content.decode()
    assert page_props(response)["action"] == hire_url(gang)


def test_the_confirmation_contains_credentials_and_a_recoverable_command_key(
    client, tester, gang, ganger
):
    client.force_login(tester)
    data = page_props(client.get(dialog_url(gang, ganger)))
    assert data["confirmation"]
    assert data["csrfToken"]
    assert data["values"]["request_key"]
    assert data["recoveryKey"] == f"hire:{tester.pk}:{gang.pk}"


def test_the_confirmation_has_no_nested_alpine_or_react_owner(
    client, tester, gang, ganger
):
    client.force_login(tester)
    page = BeautifulSoup(client.get(dialog_url(gang, ganger)).content, "html.parser")
    host = page.select_one('[data-react-name="hire"]')
    assert not host.select("[x-init], [x-data], [data-react-name]")


def test_dismissing_the_dialog_navigates(client, tester, gang, ganger):
    client.force_login(tester)
    data = page_props(client.get(dialog_url(gang, ganger)))
    assert data["back"] == hire_url(gang)
    assert data["action"] == hire_url(gang)


def test_the_list_carries_no_dialog_until_one_is_asked_for(
    client, tester, gang, ganger
):
    client.force_login(tester)
    assert page_props(client.get(hire_url(gang)))["confirmation"] is False
    assert page_props(client.get(dialog_url(gang, ganger)))["confirmation"] is True


def test_the_dialog_hires_and_comes_back_for_the_next_one(client, tester, gang, ganger):
    """The gang sheet is not where a hire lands. The answer to "who else?"
    is this screen, so the confirmation is drawn on it."""
    client.force_login(tester)
    response = client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(ganger.pk), "name": "Vex"},
    )
    assert response.status_code == 302
    assert response.url == hire_url(gang)

    fighter = Miniature.objects.get(membership__gang=gang)
    assert fighter.name == "Vex"
    gang.refresh_from_db()
    assert gang.credits == 145  # 200 - 55
    assert gang.rating == 55

    body = client.get(response.url).content.decode()
    assert "Hired Vex" in body
    assert "55" in body


def test_the_success_is_delivered_once_to_the_workflow_owner(
    client, tester, gang, ganger
):
    client.force_login(tester)
    client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(ganger.pk), "name": "Vex"},
    )
    data = page_props(client.get(hire_url(gang)))
    assert data["messages"] == [{"text": "Hired Vex — Ganger, 55¢.", "tone": "success"}]
    assert not data["confirmation"]


def test_hiring_twice_running_needs_no_detour(client, tester, gang, ganger):
    client.force_login(tester)
    for name in ("Vex", "Sull"):
        assert click(client, gang, ganger).url == dialog_url(gang, ganger)
        client.post(
            hire_url(gang),
            {"request_key": str(uuid4()), "profile": str(ganger.pk), "name": name},
        )

    assert sorted(
        model.name for model in Miniature.objects.filter(membership__gang=gang)
    ) == ["Sull", "Vex"]
    gang.refresh_from_db()
    assert gang.credits == 90  # 200 - 55 - 55


def test_an_unnamed_hire_takes_the_profiles_name(client, tester, gang, ganger):
    client.force_login(tester)
    client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(ganger.pk), "name": ""},
    )
    assert Miniature.objects.get(membership__gang=gang).name == "Ganger"

    body = client.get(hire_url(gang)).content.decode()
    assert "Hired Ganger for 55" in body


def test_a_click_carries_the_ticked_option_into_the_dialogs_url(
    client, tester, gang, ganger, armament
):
    client.force_login(tester)
    response = click(client, gang, ganger, **{f"{slugify(str(ganger.pk))}:1": "1"})
    assert response.url == dialog_url(gang, ganger, [(1, 1)])
    data = page_props(client.get(response.url))
    assert data["values"]["quoted"] == "80"
    assert json.loads(data["values"]["choice_names"]) == ["Chainsword"]


def test_a_name_the_field_refuses_comes_back_in_the_dialog(
    client, tester, gang, ganger, armament
):
    """Retain the selected hire option when name validation fails."""
    _, fancy = armament
    client.force_login(tester)
    response = client.post(
        hire_url(gang),
        {
            "request_key": str(uuid4()),
            "profile": str(ganger.pk),
            "name": "V" * 300,
            f"{slugify(str(ganger.pk))}:1": "1",
        },
    )
    assert response.status_code == 200
    assert not Miniature.objects.filter(membership__gang=gang).exists()
    data = page_props(response)
    assert data["confirmation"]
    assert data["values"]["name"] == "V" * 300
    assert data["values"]["quoted"] == "80"
    assert json.loads(data["values"]["selection"]) == [
        str(ganger.options.get(default_set=fancy).pk)
    ]
    assert "at most 200 characters" in data["errors"]["name"][0]


def test_an_option_maps_back_to_its_set(client, tester, gang, ganger, armament):
    """The picker submits option *indices*; the server must resolve them
    against the same ordering the rows were drawn from.

    The profile here has only a named group, which is exactly the case
    where ``build_hire_entry`` synthesises a default group in front —
    so a parser reading raw ``grouped_options()`` would be off by one.

    The key is slugified — lowercased — because that is what the template
    actually renders (``value|slugify`` scopes the row's inputs). Posting
    the raw uppercase pk here would pass against a parser that no real
    browser can reach.
    """
    _, fancy = armament
    client.force_login(tester)
    response = client.post(
        hire_url(gang),
        {
            "request_key": str(uuid4()),
            "profile": str(ganger.pk),
            "name": "Vex",
            f"{slugify(str(ganger.pk))}:1": "1",
        },
    )
    assert response.status_code == 302

    fighter = Miniature.objects.get(membership__gang=gang)
    chosen = ChosenProfileOption.objects.filter(assignment=fighter.membership)
    assert [row.default_set for row in chosen] == [fancy]
    gang.refresh_from_db()
    assert gang.credits == 120  # 200 - (55 + 25)


def test_legacy_indices_become_the_same_stable_options_the_react_controls_use(
    client, tester, gang, ganger, armament
):
    """Retain the selected hire option when name validation fails."""
    _, fancy = armament
    client.force_login(tester)
    data = page_props(client.get(hire_url(gang)))
    (entry,) = catalogue_entries(data)
    assert {
        option["key"]
        for group in entry["groups"]
        for option in group["options"]
        if option["key"]
    } == {str(option.pk) for option in ganger.options.all()}
    confirmation = page_props(client.get(dialog_url(gang, ganger, [(1, 1)])))
    assert json.loads(confirmation["values"]["selection"]) == [
        str(ganger.options.get(default_set=fancy).pk)
    ]


def test_a_dialog_reached_by_hand_hires_the_option_it_names(
    client, tester, gang, ganger, armament
):
    """Bookmarked indexed confirmations retain their native POST contract."""
    _, fancy = armament
    client.force_login(tester)
    assert client.get(dialog_url(gang, ganger, [(1, 1)])).status_code == 200

    client.post(
        hire_url(gang),
        {
            "request_key": str(uuid4()),
            "profile": str(ganger.pk),
            "name": "Vex",
            f"{slugify(str(ganger.pk))}:1": "1",
        },
    )
    fighter = Miniature.objects.get(membership__gang=gang)
    assert [
        row.default_set
        for row in ChosenProfileOption.objects.filter(assignment=fighter.membership)
    ] == [fancy]


def test_a_double_pick_in_a_choose_one_group_is_refused(
    client, tester, gang, ganger, armament
):
    """Radios stop this in a browser; a tampered POST naming two options
    of a choose-one group must 404 like any other broken submission,
    not 500 out of resolve_selection."""
    client.force_login(tester)
    response = client.post(
        hire_url(gang),
        {
            "request_key": str(uuid4()),
            "profile": str(ganger.pk),
            "name": "Vex",
            f"{slugify(str(ganger.pk))}:1": ["0", "1"],
        },
    )
    assert response.status_code == 404
    assert not Miniature.objects.filter(membership__gang=gang).exists()


def test_a_double_pick_is_refused_before_the_dialog_too(
    client, tester, gang, ganger, armament
):
    """A hand-built dialog URL is the same tampering one step earlier, and
    a dialog that opened on it would quote a price for a hire that cannot
    happen."""
    client.force_login(tester)
    url = f"{dialog_url(gang, ganger, [(1, 1)])}&{slugify(str(ganger.pk))}:1=0"
    assert client.get(url).status_code == 404


def test_an_option_index_that_does_not_exist_is_refused(
    client, tester, gang, ganger, armament
):
    client.force_login(tester)
    scoped = f"{slugify(str(ganger.pk))}:1"
    assert (
        client.get(f"{hire_url(gang)}?hire={ganger.pk}&{scoped}=7").status_code == 404
    )
    assert (
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Vex",
                scoped: "7",
            },
        ).status_code
        == 404
    )
    assert not Miniature.objects.filter(membership__gang=gang).exists()


def test_a_homeless_profile_gets_a_tab_of_its_own(
    client, tester, gang, ganger, make_profile
):
    """One profile the content gave no category must not cost every other
    section its tab.

    Tabs are the picker's whole navigation once on, and a section missing
    from the strip can never be the active one — its rows are served in
    the HTML with no way to reach them. The homeless section is therefore
    named rather than the strip being switched off, and both claims are
    pinned here: the strip is drawn, and every section is on it.
    """
    from n26.library.models import Category, Section

    section = Section.objects.create(name="Gang List", position=0)
    category = Category.objects.create(section=section, name="Champions", position=0)
    homed = make_profile("Champion", price=95)
    homed.category = category
    homed.save()
    # `ganger` stays homeless.

    client.force_login(tester)
    response = client.get(hire_url(gang))
    assert [
        section["name"] for section in response.context["hire_props"]["sections"]
    ] == ["Gang List", UNCATEGORISED]

    # Reachability, the thing the strip can silently cost: every section
    # drawn must have a tab, and every row must register under a name the
    # category filter starts with on.
    drawn = {section["name"] for section in response.context["hire_props"]["sections"]}
    assert drawn <= set(
        [section["name"] for section in response.context["hire_props"]["sections"]]
    )
    registration_names = {
        category["name"] or section["name"]
        for section in response.context["hire_props"]["sections"]
        for category in section["categories"]
    }
    assert registration_names <= set(response.context["hire_props"]["categories"])


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
    assert [
        section["name"] for section in response.context["hire_props"]["sections"]
    ] == ["Gang List", "Supplementary Fighters"]


def test_an_overspend_refuses_and_writes_nothing(client, tester, gang, make_profile):
    expensive = make_profile("Gang Queen", price=500)

    client.force_login(tester)
    response = client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(expensive.pk), "name": "Vesna"},
    )
    # Back to the hire page with a message, and nothing half-written.
    assert response.status_code == 302
    assert response.url == hire_url(gang)
    assert Miniature.objects.filter(membership__gang=gang).count() == 0
    gang.refresh_from_db()
    assert gang.credits == 200

    # The refusal is drawn where the confirmation would have been.
    assert "credits" in client.get(response.url).content.decode()


def test_another_gang_types_profile_hires_but_an_unhireable_one_never_does(
    client, tester, gang, make_profile, make_statline, person_type
):
    """Any gang may hire any hireable profile — every one of them is
    legitimately on the all-profiles scope — so the line the view holds
    is hireability itself: a pet still arrives behind its collar, never
    off this screen."""
    from n26.library.models import GangType

    other = GangType.objects.create(name="Goliath")
    outsider = make_profile("Forge Tyrant", gang_type=other, price=10)
    make_statline(outsider)
    collared = make_profile("Gyrinx Cat", gang_type=other, price=10, hireable=False)

    client.force_login(tester)
    response = client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(outsider.pk), "name": "Poached"},
    )
    assert response.status_code == 302
    assert Miniature.objects.filter(membership__gang=gang).count() == 1

    refused = client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(collared.pk), "name": "Wrong"},
    )
    assert refused.status_code == 200  # redisplays the list
    assert Miniature.objects.filter(membership__gang=gang).count() == 1
    assert page_props(client.get(dialog_url(gang, collared)))["confirmation"] is False


def test_an_archived_profile_is_neither_offered_nor_hired(
    client, tester, gang, make_profile, make_statline
):
    """Archiving is an author's soft delete: a gang that has the fighter keeps
    them, and no gang is offered them again — on the list, in the dialog,
    or by typing the id."""
    gone = make_profile("Forgotten Juve", price=10)
    make_statline(gone)
    gone.archive()

    client.force_login(tester)
    assert "Forgotten Juve" not in client.get(hire_url(gang)).content.decode()
    assert page_props(client.get(dialog_url(gang, gone)))["confirmation"] is False
    refused = client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(gone.pk), "name": "Ghost"},
    )
    assert refused.status_code == 200
    assert not Miniature.objects.filter(membership__gang=gang).exists()
    assert (
        client.get(reverse("n26-hire-card", args=[gang.pk, gone.pk])).status_code == 404
    )


def test_a_profile_that_is_not_a_ulid_draws_no_dialog(client, tester, gang, ganger):
    """A pk that is not a ULID at all reaches the field's to_python; the
    genuine buttons never send one, so it names nothing."""
    client.force_login(tester)
    assert (
        page_props(client.get(f"{hire_url(gang)}?hire=nonsense"))["confirmation"]
        is False
    )
    response = client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": "nonsense", "name": "Vex"},
    )
    assert response.status_code == 200
    assert not Miniature.objects.filter(membership__gang=gang).exists()


def test_someone_elses_gang_is_not_found(client, gang, ganger):
    stranger = User.objects.create_user("stranger")
    client.force_login(stranger)
    assert client.get(hire_url(gang)).status_code == 404
    assert client.get(dialog_url(gang, ganger)).status_code == 404
    assert (
        client.post(
            hire_url(gang), {"request_key": str(uuid4()), "profile": str(ganger.pk)}
        ).status_code
        == 404
    )
    assert click(client, gang, ganger).status_code == 404


def test_a_pk_that_is_not_a_ulid_is_not_found(client, tester):
    client.force_login(tester)
    assert client.get("/n26/gangs/nonsense/hire/").status_code == 404


def test_the_sheet_links_to_the_hire_page(client, tester, gang):
    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert hire_url(gang) in body


def test_the_figures_strip_counts_the_roster_and_quotes_the_books(
    client, tester, gang, ganger
):
    client.force_login(tester)
    before = page_props(client.get(hire_url(gang)))["figures"]
    assert before["roster"]["count"] == 0
    assert (
        next(item for item in before["items"] if item["short"] == "Cr")["value"]
        == f"{gang.credits}¢"
    )
    client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(ganger.pk), "name": "Vex"},
    )
    gang.refresh_from_db()
    after = page_props(client.get(hire_url(gang)))["figures"]
    assert after["roster"]["count"] == 1
    assert (
        next(item for item in after["items"] if item["short"] == "Cr")["value"]
        == f"{gang.credits}¢"
    )


def test_a_profile_not_offered_for_hire_is_not_on_the_screen(
    client, tester, gang, ganger
):
    """A pet arrives behind its collar, not off the hire screen: the flag
    takes it out of the list, and a POST naming it anyway is answered like
    a profile from somebody else's list."""
    ganger.hireable = False
    ganger.save(update_fields=["hireable"])
    client.force_login(tester)
    assert str(ganger.pk) not in client.get(hire_url(gang)).content.decode()
    response = client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": str(ganger.pk), "name": "Vex"},
    )
    assert response.status_code == 200
    assert not Miniature.objects.filter(membership__gang=gang).exists()


class TestTheTypedPrice:
    """The dialog's price box is the purchase's control: what is typed is
    what leaves the bank. Read like every typed price: whole credits in
    range, or the hire is refused and nothing is written.

    These post no rating box, which is an untick — so the quote stays the
    list price and the rating, as it does everywhere else. What the box
    does when it is ticked is TestRatingTheHire's.
    """

    def test_the_dialog_offers_the_quote_in_a_box(self, client, tester, gang, ganger):
        client.force_login(tester)
        data = page_props(client.get(dialog_url(gang, ganger)))
        assert data["values"]["paid"] == data["values"]["quoted"] == "55"

    def test_a_typed_price_is_charged_and_the_quote_is_the_rating(
        self, client, tester, gang, ganger
    ):
        client.force_login(tester)
        response = client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Vex",
                "paid": "30",
            },
        )
        assert response.status_code == 302

        entry = Miniature.objects.get(name="Vex").membership.ledger_entry
        assert entry.paid == 30
        assert entry.list_price == 55
        assert entry.discount == 25
        assert entry.rating_contribution == 55
        gang.refresh_from_db()
        assert gang.credits == 170

    def test_overpaying_is_the_same_arithmetic(self, client, tester, gang, ganger):
        client.force_login(tester)
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Dear",
                "paid": "80",
            },
        )
        entry = Miniature.objects.get(name="Dear").membership.ledger_entry
        assert entry.paid == 80
        assert entry.discount == -25
        assert entry.rating_contribution == 55

    def test_a_price_that_is_not_whole_credits_hires_nobody(
        self, client, tester, gang, ganger
    ):
        client.force_login(tester)
        for bad in ("-5", "5.5", "9999999"):
            response = client.post(
                hire_url(gang),
                {
                    "request_key": str(uuid4()),
                    "profile": str(ganger.pk),
                    "name": "Nix",
                    "paid": bad,
                },
            )
            assert response.status_code == 302
        assert not Miniature.objects.filter(name="Nix").exists()
        gang.refresh_from_db()
        assert gang.credits == 200

    def test_an_empty_box_charges_the_quote(self, client, tester, gang, ganger):
        client.force_login(tester)
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Plain",
                "paid": "",
            },
        )
        entry = Miniature.objects.get(name="Plain").membership.ledger_entry
        assert entry.paid == 55
        assert entry.discount == 0


class TestRatingTheHire:
    """The box under the price decides which figure the fighter is worth.

    Ticked — which is how the dialog draws it — the gang takes them on at
    what it paid: the rating follows the money, and so does what they
    fetch if they are sold on. Unticked, the quote stands and the gap is
    a discount, which is what every other purchase does.
    """

    def test_the_dialog_offers_the_box_ready_ticked(self, client, tester, gang, ganger):
        client.force_login(tester)
        data = page_props(client.get(dialog_url(gang, ganger)))
        assert data["values"]["rate"] == "paid"

    def test_rating_help_receives_the_quote_and_initial_mode(
        self, client, tester, gang, ganger
    ):
        client.force_login(tester)
        data = page_props(client.get(dialog_url(gang, ganger)))
        assert data["values"]["quoted"] == "55"
        assert data["values"]["rate"] == "paid"

    def test_ticked_the_price_paid_becomes_the_rating(
        self, client, tester, gang, ganger
    ):
        client.force_login(tester)
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Cheap",
                "paid": "30",
                "rate": "paid",
            },
        )

        entry = Miniature.objects.get(name="Cheap").membership.ledger_entry
        assert entry.paid == 30
        assert entry.list_price == 30
        assert entry.discount == 0
        assert entry.rating_contribution == 30
        gang.refresh_from_db()
        # The money leaving the bank is the same either way; only what the
        # gang is reckoned to be worth moves.
        assert gang.credits == 170

    def test_the_ledger_still_reconciles_either_way(self, client, tester, gang, ganger):
        """``paid = list_price - discount`` is the invariant reconcile
        checks, and both answers have to keep it."""
        client.force_login(tester)
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Paid",
                "paid": "30",
                "rate": "paid",
            },
        )
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Quoted",
                "paid": "40",
            },
        )

        gang.refresh_from_db()
        assert_reconciled(gang)
        rated = {
            m.name: m.membership.ledger_entry.rating_contribution
            for m in Miniature.objects.filter(membership__gang=gang)
        }
        assert rated == {"Paid": 30, "Quoted": 55}

    def test_overpaying_can_be_taken_at_the_higher_figure(
        self, client, tester, gang, ganger
    ):
        client.force_login(tester)
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Dear",
                "paid": "80",
                "rate": "paid",
            },
        )
        entry = Miniature.objects.get(name="Dear").membership.ledger_entry
        assert entry.rating_contribution == 80
        assert entry.discount == 0

    def test_unticked_the_quote_stands_and_the_gap_is_a_discount(
        self, client, tester, gang, ganger
    ):
        """An unticked box posts nothing at all, which is the only thing
        absence can mean here."""
        client.force_login(tester)
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Bargain",
                "paid": "30",
            },
        )
        entry = Miniature.objects.get(name="Bargain").membership.ledger_entry
        assert entry.rating_contribution == 55
        assert entry.discount == 25

    def test_a_hire_at_the_quoted_price_is_unaffected_either_way(
        self, client, tester, gang, ganger
    ):
        """Nobody haggling means the two figures are the same number, so
        the box being ticked by default changes nothing for them."""
        client.force_login(tester)
        client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "Plain",
                "rate": "paid",
            },
        )
        entry = Miniature.objects.get(name="Plain").membership.ledger_entry
        assert entry.paid == 55
        assert entry.rating_contribution == 55
        assert entry.discount == 0

    def test_a_redrawn_dialog_keeps_an_untick(self, client, tester, gang, ganger):
        client.force_login(tester)
        response = client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(ganger.pk),
                "name": "x" * 500,
                "paid": "30",
            },
        )
        data = page_props(response)
        assert data["confirmation"]
        assert data["values"]["rate"] == ""
        assert data["values"]["paid"] == "30"


class TestTheScopes:
    """Whose profiles are on offer: the gang list, the supplementary
    profiles every gang may hire, or everyone in the library. Being
    supplementary is a fact of the taxonomy — a home category under the
    supplementary section — so the scope follows the content."""

    @pytest.fixture
    def elsewhere(self, ganger, make_profile, make_statline):
        """A supplementary profile and an ordinary one, both authored on
        another gang type entirely."""
        from n26.library.models import Category, GangType, Section
        from n26.library.standard_content import SUPPLEMENTARY_SECTION

        other = GangType.objects.create(name="Brutes, Hangers-on & Pets")
        section = Section.objects.create(name=SUPPLEMENTARY_SECTION, position=7)
        hanger_on = Category.objects.create(
            name="Hanger-on", section=section, position=0
        )
        supplementary = make_profile("Claim Jumper", price=90)
        supplementary.gang_type = other
        supplementary.category = hanger_on
        supplementary.save()
        make_statline(supplementary)
        ordinary = make_profile("Their Ganger", price=40)
        ordinary.gang_type = other
        ordinary.save()
        make_statline(ordinary)
        return supplementary, ordinary

    def test_the_gang_list_is_the_default_and_offers_no_strangers(
        self, client, tester, gang, ganger, elsewhere
    ):
        client.force_login(tester)
        body = client.get(hire_url(gang)).content.decode()
        assert "Ganger" in body
        assert "Claim Jumper" not in body

    def test_the_supplementary_scope_offers_the_sections_profiles_alone(
        self, client, tester, gang, ganger, elsewhere
    ):
        client.force_login(tester)
        body = client.get(f"{hire_url(gang)}?list=supplementary").content.decode()
        assert "Claim Jumper" in body
        assert "Their Ganger" not in body
        assert "Ganger" not in body

    def test_the_all_scope_offers_everyone_by_gang_type(
        self, client, tester, gang, ganger, elsewhere
    ):
        client.force_login(tester)
        response = client.get(f"{hire_url(gang)}?list=all")
        body = response.content.decode()
        assert "Claim Jumper" in body
        assert "Their Ganger" in body
        assert "Ganger" in body
        # Sectioned by whose list each is, so 160 profiles stay findable.
        sections = [
            section["name"] for section in response.context["hire_props"]["sections"]
        ]
        assert "Brutes, Hangers-on & Pets" in sections

    def test_a_hire_from_another_scope_lands_back_on_it(
        self, client, tester, gang, elsewhere
    ):
        supplementary, _ = elsewhere
        client.force_login(tester)
        clicked = client.post(
            f"{hire_url(gang)}?list=supplementary",
            {"hire": str(supplementary.pk), "list": "supplementary"},
        )
        assert clicked.status_code == 302
        assert "list=supplementary" in clicked.url

        hired = client.post(
            hire_url(gang),
            {
                "request_key": str(uuid4()),
                "profile": str(supplementary.pk),
                "list": "supplementary",
                "name": "",
            },
        )
        assert hired.status_code == 302
        assert "list=supplementary" in hired.url
        fighter = Miniature.objects.get(name="Claim Jumper")
        assert fighter.membership.profile == supplementary

    def test_an_unknown_scope_is_the_gang_list(self, client, tester, gang, ganger):
        client.force_login(tester)
        response = client.get(f"{hire_url(gang)}?list=nonsense")
        assert response.status_code == 200
        assert response.context["hire_props"]["scope"] == "gang"

    def test_the_forms_post_to_the_scoped_address(
        self, client, tester, gang, ganger, elsewhere
    ):
        client.force_login(tester)
        data = page_props(client.get(f"{hire_url(gang)}?list=supplementary"))
        assert data["action"] == f"{hire_url(gang)}?list=supplementary"
        assert data["values"]["list"] == "supplementary"

    def test_the_scope_needs_nothing_in_the_body(self, client, tester, gang, elsewhere):
        """Preserve scope in the command URL throughout the submission flow."""
        supplementary, _ = elsewhere
        client.force_login(tester)
        clicked = client.post(
            f"{hire_url(gang)}?list=supplementary", {"hire": str(supplementary.pk)}
        )
        assert clicked.status_code == 302
        assert "list=supplementary" in clicked.url

        hired = client.post(
            f"{hire_url(gang)}?list=supplementary",
            {"request_key": str(uuid4()), "profile": str(supplementary.pk), "name": ""},
        )
        assert hired.status_code == 302
        assert "list=supplementary" in hired.url

    def test_the_section_tab_rides_the_round_trip(
        self, client, tester, gang, elsewhere
    ):
        """Retain the selected section tab after hiring and redirecting."""
        supplementary, _ = elsewhere
        client.force_login(tester)
        clicked = client.post(
            f"{hire_url(gang)}?list=supplementary",
            {"hire": str(supplementary.pk), "section": "Supplementary Profiles"},
        )
        assert clicked.status_code == 302
        assert "section=Supplementary+Profiles" in clicked.url

        hired = client.post(
            clicked.url,
            {"request_key": str(uuid4()), "profile": str(supplementary.pk), "name": ""},
        )
        assert hired.status_code == 302
        assert "list=supplementary" in hired.url
        assert "section=Supplementary+Profiles" in hired.url
