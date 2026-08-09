"""Hiring a fighter: the picker's form contract, server side.

``build_hire_list`` and ``Operation.hire`` have their own tests — these
are about the wiring. A hire is three requests: a press says which
profile, the URL it lands on draws the name dialog, and the dialog's
submit hires and comes back for the next one. Each step is pinned here,
along with the refusals, because every one of them is a way a fighter
could be bought at the wrong price or not at all.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify

from n26.core.browse import UNCATEGORISED
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


@pytest.fixture
def armament(ganger):
    """A named choose-one group on the ganger: a knife, or a chainsword
    for 25 more. The case where ``build_hire_entry`` synthesises a default
    group in front, so the named one is group 1."""
    group = OptionGroup.objects.create(profile=ganger, name="Armament", choose="one")
    plain = DefaultAssignmentSet.objects.create(name="Knife", price=0)
    fancy = DefaultAssignmentSet.objects.create(name="Chainsword", price=25)
    ganger.options.create(profile=ganger, group=group, default_set=plain, position=0)
    ganger.options.create(profile=ganger, group=group, default_set=fancy, position=1)
    return plain, fancy


def hire_url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def dialog_url(gang, profile, options=()):
    """The URL a press lands on: the list, with the dialog open.

    ``options`` are (group index, option index) pairs, scoped the way the
    rows scope theirs.
    """
    query = "&".join(
        f"{slugify(str(profile.pk))}:{group}={option}" for group, option in options
    )
    return f"{hire_url(gang)}?hire={profile.pk}{'&' + query if query else ''}"


def press(client, gang, profile, **data):
    """Press Hire on a row, as the picker's form does."""
    return client.post(hire_url(gang), {"hire": str(profile.pk), **data})


def test_the_list_draws_with_prices(client, tester, gang, ganger):
    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert "Ganger" in body
    assert "55" in body


def test_the_list_asks_for_no_name(client, tester, gang, ganger):
    """Naming is the dialog's question, and asking it twice would mean two
    places a name could be typed and only one of them read."""
    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert 'name="name"' not in body


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


def test_a_press_lands_on_the_dialogs_url(client, tester, gang, ganger):
    """Which profile was pressed is a URL, not a hidden state: that is what
    makes the dialog survive a reload and a press work without scripting."""
    client.force_login(tester)
    response = press(client, gang, ganger)
    assert response.status_code == 302
    assert response.url == dialog_url(gang, ganger)
    assert not Miniature.objects.filter(membership__gang=gang).exists()


def test_the_dialog_names_the_profile_and_its_price(client, tester, gang, ganger):
    client.force_login(tester)
    body = client.get(dialog_url(gang, ganger)).content.decode()
    assert "Hire a Ganger" in body
    assert "55¢" in body
    assert f'value="{ganger.pk}"' in body
    assert 'name="name"' in body


def test_the_screen_offers_more_than_one_hire(client, tester, gang, ganger):
    """A reader can hire a whole gang without leaving, so the heading, the
    tab and the breadcrumb all say so rather than promising one fighter."""
    client.force_login(tester)
    body = client.get(hire_url(gang)).content.decode()
    assert body.count("Hire Fighters") >= 3
    assert "Hire a fighter" not in body


def test_the_dialog_is_a_panel_a_reader_without_scripting_can_still_use(
    client, tester, gang, ganger
):
    """Whether the dialog is open is the server's answer, so it arrives in
    the HTML rather than behind a trigger. `static m-0` is how it draws
    with no script running: a panel in the flow of the page, above the
    list, which is the whole of the scriptless fallback.
    """
    client.force_login(tester)
    body = client.get(dialog_url(gang, ganger)).content.decode()
    assert "<dialog open" in body
    assert "static m-0" in body


def test_the_dialog_promotes_itself_by_calling_a_method(client, tester, gang, ganger):
    """The promotion is a call, never statements written into the
    directive. Alpine compiles a directive's value as an expression, and a
    statement there is a syntax error it reports to the browser console
    and nowhere else — the page would serve 200 with the panel sitting
    unpromoted above the list and nothing to say why.

    ``test_template_expressions`` guards that rule across the edition;
    this pins the shape the dialog relies on.
    """
    client.force_login(tester)
    body = client.get(dialog_url(gang, ganger)).content.decode()
    assert 'x-init="promote($el)"' in body
    assert "showModal()" in body


def test_dismissing_the_dialog_navigates(client, tester, gang, ganger):
    """Closing in place would leave the list on screen while the URL still
    named a profile, so both Cancel and a dismissal go to the page with no
    profile named — and the address bar keeps agreeing with the screen."""
    client.force_login(tester)
    body = client.get(dialog_url(gang, ganger)).content.decode()
    assert f"window.location = '{hire_url(gang)}'" in body
    assert f'href="{hire_url(gang)}"' in body


def test_the_list_carries_no_dialog_until_one_is_asked_for(
    client, tester, gang, ganger
):
    client.force_login(tester)
    assert client.get(hire_url(gang)).context["dialog"] is None
    assert client.get(dialog_url(gang, ganger)).context["dialog"] is not None


def test_the_dialog_hires_and_comes_back_for_the_next_one(client, tester, gang, ganger):
    """The gang sheet is not where a hire lands. The answer to "who else?"
    is this screen, so the confirmation is drawn on it."""
    client.force_login(tester)
    response = client.post(hire_url(gang), {"profile": str(ganger.pk), "name": "Vex"})
    assert response.status_code == 302
    assert response.url == hire_url(gang)

    fighter = Miniature.objects.get(membership__gang=gang)
    assert fighter.name == "Vex"
    gang.refresh_from_db()
    assert gang.credits == 145  # 200 - 55
    assert gang.rating == 55

    body = client.get(response.url).content.decode()
    assert "Hired Vex — Ganger, 55¢." in body


def test_the_confirmation_is_drawn_once_and_inside_the_form(
    client, tester, gang, ganger
):
    """The layout draws messages above everything; this screen wants its
    confirmation beside the list the press came from. Both would be the
    same message twice, so the page empties the layout's block — and the
    only way to tell is where the alert sits relative to the form.
    """
    client.force_login(tester)
    client.post(hire_url(gang), {"profile": str(ganger.pk), "name": "Vex"})
    body = client.get(hire_url(gang)).content.decode()

    assert body.count("Hired Vex") == 1
    assert body.index("<form") < body.index("Hired Vex") < body.index("Ganger</span>")


def test_hiring_twice_running_needs_no_detour(client, tester, gang, ganger):
    client.force_login(tester)
    for name in ("Vex", "Sull"):
        assert press(client, gang, ganger).url == dialog_url(gang, ganger)
        client.post(hire_url(gang), {"profile": str(ganger.pk), "name": name})

    assert sorted(
        model.name for model in Miniature.objects.filter(membership__gang=gang)
    ) == ["Sull", "Vex"]
    gang.refresh_from_db()
    assert gang.credits == 90  # 200 - 55 - 55


def test_an_unnamed_hire_takes_the_profiles_name(client, tester, gang, ganger):
    client.force_login(tester)
    client.post(hire_url(gang), {"profile": str(ganger.pk), "name": ""})
    assert Miniature.objects.get(membership__gang=gang).name == "Ganger"

    body = client.get(hire_url(gang)).content.decode()
    assert "Hired Ganger for 55¢." in body


def test_a_press_carries_the_ticked_option_into_the_dialogs_url(
    client, tester, gang, ganger, armament
):
    """The row's controls are answered before the press, so the dialog must
    inherit them: dropping one here would quote and charge the base price
    for a fighter the player configured otherwise.
    """
    client.force_login(tester)
    response = press(client, gang, ganger, **{f"{slugify(str(ganger.pk))}:1": "1"})
    assert response.url == dialog_url(gang, ganger, [(1, 1)])

    body = client.get(response.url).content.decode()
    assert "80¢" in body  # 55 + 25
    assert "Chainsword" in body


def test_a_name_the_field_refuses_comes_back_in_the_dialog(
    client, tester, gang, ganger, armament
):
    """A rejected name must not cost the reader their selection: the dialog
    is redrawn with the option still in its hidden fields, so the only
    thing to do again is the one thing that was wrong."""
    scoped = f"{slugify(str(ganger.pk))}:1"
    client.force_login(tester)
    response = client.post(
        hire_url(gang), {"profile": str(ganger.pk), "name": "V" * 300, scoped: "1"}
    )
    assert response.status_code == 200
    assert not Miniature.objects.filter(membership__gang=gang).exists()

    body = response.content.decode()
    assert f'<input type="hidden" name="{scoped}" value="1">' in body
    assert "80¢" in body
    assert "at most 200 characters" in body


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
        {"profile": str(ganger.pk), "name": "Vex", f"{slugify(str(ganger.pk))}:1": "1"},
    )
    assert response.status_code == 302

    fighter = Miniature.objects.get(membership__gang=gang)
    chosen = ChosenProfileOption.objects.filter(assignment=fighter.membership)
    assert [row.default_set for row in chosen] == [fancy]
    gang.refresh_from_db()
    assert gang.credits == 120  # 200 - (55 + 25)


def test_the_option_keys_match_what_the_template_renders(
    client, tester, gang, ganger, armament
):
    """The rendered input names and the parser must agree on case.

    The row template scopes inputs with ``value|slugify``, which lowercases
    the ULID; a parser reading the raw pk finds no keys, and every option
    ticked in a real browser is silently dropped — the fighter hires as
    default at base price, no error anywhere. So the page's HTML is the
    fixture here: the name this asserts on is the name the parser reads.

    The dialog then repeats those names as hidden fields, which is how the
    answer crosses the redirect: no script copies it, so nothing is lost
    when none is running.
    """
    client.force_login(tester)
    scoped = f"{slugify(str(ganger.pk))}:1"
    assert f'name="{scoped}"' in client.get(hire_url(gang)).content.decode()

    dialog = client.get(dialog_url(gang, ganger, [(1, 1)])).content.decode()
    assert f'<input type="hidden" name="{scoped}" value="1">' in dialog


def test_a_dialog_reached_by_hand_hires_the_option_it_names(
    client, tester, gang, ganger, armament
):
    """The no-script path end to end: a plain GET of the dialog's URL, then
    the POST its own fields describe."""
    _, fancy = armament
    client.force_login(tester)
    assert client.get(dialog_url(gang, ganger, [(1, 1)])).status_code == 200

    client.post(
        hire_url(gang),
        {"profile": str(ganger.pk), "name": "Vex", f"{slugify(str(ganger.pk))}:1": "1"},
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
            hire_url(gang), {"profile": str(ganger.pk), "name": "Vex", scoped: "7"}
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
    assert response.context["sections"] == ["Gang List", UNCATEGORISED]

    # Reachability, the thing the strip can silently cost: every section
    # drawn must have a tab, and every row must register under a name the
    # category filter starts with on.
    drawn = {row["section"]["name"] for row in response.context["section_rows"]}
    assert drawn <= set(response.context["sections"])
    registration_names = {
        category["name"] or row["section"]["name"]
        for row in response.context["section_rows"]
        for category in row["section"]["categories"]
    }
    assert registration_names <= set(response.context["categories"])


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

    # The refusal is drawn where the confirmation would have been.
    assert "credits" in client.get(response.url).content.decode()


def test_a_profile_of_another_gang_type_is_refused(
    client, tester, gang, make_profile, person_type
):
    """The list is the gang type's; a tampered POST naming someone
    else's profile must not hire it — at either step."""
    from n26.library.models import GangType

    other = GangType.objects.create(name="Goliath")
    outsider = make_profile("Forge Tyrant", gang_type=other, price=10)

    client.force_login(tester)
    response = client.post(
        hire_url(gang), {"profile": str(outsider.pk), "name": "Wrong"}
    )
    assert response.status_code == 200  # redisplays the list
    assert Miniature.objects.filter(membership__gang=gang).count() == 0

    assert press(client, gang, outsider).status_code == 200
    assert client.get(dialog_url(gang, outsider)).context["dialog"] is None


def test_a_profile_that_is_not_a_ulid_draws_no_dialog(client, tester, gang, ganger):
    """A pk that is not a ULID at all reaches the field's to_python; the
    genuine buttons never send one, so it names nothing."""
    client.force_login(tester)
    assert client.get(f"{hire_url(gang)}?hire=nonsense").context["dialog"] is None
    response = client.post(hire_url(gang), {"profile": "nonsense", "name": "Vex"})
    assert response.status_code == 200
    assert not Miniature.objects.filter(membership__gang=gang).exists()


def test_someone_elses_gang_is_not_found(client, gang, ganger):
    stranger = User.objects.create_user("stranger", is_staff=True)
    client.force_login(stranger)
    assert client.get(hire_url(gang)).status_code == 404
    assert client.get(dialog_url(gang, ganger)).status_code == 404
    assert client.post(hire_url(gang), {"profile": str(ganger.pk)}).status_code == 404
    assert press(client, gang, ganger).status_code == 404


def test_a_pk_that_is_not_a_ulid_is_not_found(client, tester):
    client.force_login(tester)
    assert client.get("/n26/gangs/nonsense/hire/").status_code == 404


def test_the_sheet_links_to_the_hire_page(client, tester, gang):
    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert hire_url(gang) in body
