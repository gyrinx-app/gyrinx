"""The badge beside a name, in this edition's markup.

A badge belongs to the person, not to the edition they happen to be
looking at. Which one someone shows is derived from their live supporter
standing and their staff flag against the platform's registry, plus
whichever of the ones they are entitled to they picked — so an n26 page
asks the platform that question rather than answering it itself. What
crosses the boundary is the answer, not the markup: the artwork and the
wording arrive as data, and <c-n26.user-link> draws them in this
edition's own terms.

The bug these pin: the gang sheet used to draw a hardcoded staff icon
whenever the owner was staff, which showed every supporter no badge at
all and would have gone wrong again on the next tier.
"""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import Group, User

from gyrinx.accounts.models import PatreonStatus, UserProfile
from gyrinx.badges import STAFF_BADGE, badge_by_slug
from gyrinx.middleware import N26_TESTERS_GROUP
from gyrinx.site.templatetags.badge_tags import badge_svg

pytestmark = pytest.mark.django_db

GUILDER = badge_by_slug("guilder")

# The wrapper <c-n26.flair-link> puts round a badge. Nothing else in the
# edition emits it, so its absence is the claim that no empty span was
# drawn where a badge would have gone.
FLAIR_WRAPPER = 'class="ml-[0.25em] inline-block'


@pytest.fixture
def tester(client):
    def _make(username, **kwargs):
        user = User.objects.create_user(username, **kwargs)
        group, _ = Group.objects.get_or_create(name=N26_TESTERS_GROUP)
        user.groups.add(group)
        client.force_login(user)
        return user

    return _make


@pytest.fixture
def supporter(tester):
    """Someone entitled to a tier badge, showing it."""
    user = tester("patron")
    UserProfile.objects.create(
        user=user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    return user


class TestTheBadgeBesideAName:
    """Whatever the registry says this person shows, drawn in n26's own
    component — never a mark this edition picked for them."""

    def test_a_supporter_sees_their_own_tier_badge(
        self, supporter, client, default_pack
    ):
        body = client.get("/n26/gangs/new/").content.decode()
        assert badge_svg(GUILDER).strip() in body

    def test_a_staff_member_who_has_chosen_nothing_gets_the_staff_mark(
        self, tester, client, default_pack
    ):
        """Staff outranks the tiers, so it is what an unchosen staff
        account defaults to."""
        UserProfile.objects.create(user=tester("boss", is_staff=True))

        body = client.get("/n26/gangs/new/").content.decode()
        assert badge_svg(STAFF_BADGE).strip() in body

    def test_someone_entitled_to_nothing_gets_no_mark_and_no_empty_span(
        self, tester, client, default_pack
    ):
        """Not an invisible badge: the wrapper is drawn only when there
        is artwork to put in it, so the name is followed by the next
        thing on the line rather than by a quarter-em of nothing."""
        tester("nobody")

        body = client.get("/n26/gangs/new/").content.decode()
        assert "nobody" in body
        assert FLAIR_WRAPPER not in body

    def test_a_lapsed_supporter_loses_the_badge_they_picked(
        self, tester, client, default_pack
    ):
        """Eligibility is derived every time it is drawn, so a
        subscription ending takes the mark with it — the stored pick
        outlives the entitlement and must not be trusted on its own."""
        user = tester("former-patron")
        UserProfile.objects.create(
            user=user,
            patreon_status=PatreonStatus.FORMER,
            patreon_tier="Guilder",
            selected_badge="guilder",
        )

        body = client.get("/n26/gangs/new/").content.decode()
        assert FLAIR_WRAPPER not in body

    def test_the_account_menu_names_the_reader_and_marks_them(
        self, supporter, client, default_pack
    ):
        """The bar's button drops the name on a phone, so the menu behind
        it is the only place left that says which account this is — and
        the badge goes with the name, out of the same registry rather
        than out of a second guess made here."""
        body = client.get("/n26/gangs/new/").content.decode()
        bar = body[: body.index("</header>")]
        # The last role="menu" in the bar: the switcher's panel is one
        # too, and the account menu sits at the far end, after it.
        menu = bar[bar.rindex('role="menu"') :]
        assert "patron" in menu
        assert badge_svg(GUILDER).strip() in menu

    def test_the_bars_account_button_marks_the_name_it_shows(
        self, supporter, client, default_pack
    ):
        """The button carries the name at any width the page can spare
        it, and a name shown there without its badge would be the one
        place in the chrome that disagreed about who this is."""
        body = client.get("/n26/gangs/new/").content.decode()
        # Everything before the account menu, which is the last
        # role="menu" in the header — the bar's switcher panel is an
        # earlier one, and nothing in it carries a badge.
        button = body[: body[: body.index("</header>")].rindex('role="menu"')]
        assert "patron" in button
        assert badge_svg(GUILDER).strip() in button

    def test_the_badge_says_what_the_registry_says_it_means(
        self, supporter, client, default_pack
    ):
        """The accessible name and the tooltip are the registry's own
        wording. A label written into a template would be this edition
        guessing at what someone else's badge means, and would say the
        old thing after a tier was renamed."""
        body = client.get("/n26/gangs/new/").content.decode()
        assert f'aria-label="{GUILDER.description}"' in body
        assert f'title="{GUILDER.description}"' in body


class TestTheHomePageGreeting:
    """The home page opens by naming whoever is reading, so the name
    there carries the same mark it carries everywhere else."""

    def test_the_greeting_marks_the_reader(self, supporter, client, default_pack):
        body = client.get("/n26/").content.decode()
        heading = body[body.index("Hello,") :]
        heading = heading[: heading.index("</h1>")]
        assert "patron" in heading
        assert badge_svg(GUILDER).strip() in heading

    def test_the_badge_is_inside_the_heading_and_scales_with_it(
        self, supporter, client, default_pack
    ):
        """Sized in em rather than pixels, so it grows with the h1
        instead of sitting beside it at the size of body text."""
        body = client.get("/n26/").content.decode()
        heading = body[body.index("Hello,") :]
        heading = heading[: heading.index("</h1>")]
        assert FLAIR_WRAPPER in heading
        assert "size-[1em]" in heading

    def test_a_reader_entitled_to_nothing_is_greeted_by_name_alone(
        self, tester, client, default_pack
    ):
        """The common case: no mark, and no quarter-em of nothing after
        the name where one would have gone."""
        tester("nobody")

        body = client.get("/n26/").content.decode()
        assert "Hello," in body
        assert "nobody" in body
        assert FLAIR_WRAPPER not in body


class TestTheOwnerOfAGang:
    """A gang's breadcrumb names its owner, so it carries the owner's
    badge — the same answer the owner's own pages give."""

    @pytest.fixture
    def gang(self, supporter, gang_type, make_profile):
        from n26.tests.sandbox.actions import found_gang, hire

        gang = found_gang("The Bad Girls", gang_type, owner=supporter)
        hire(gang, make_profile("Ganger"), "Vex")
        return gang

    def test_the_sheet_shows_the_owners_badge(self, gang, client, default_pack):
        body = client.get(f"/n26/gangs/{gang.pk}/").content.decode()
        assert "patron" in body
        assert badge_svg(GUILDER).strip() in body
        assert f'aria-label="{GUILDER.description}"' in body

    def test_every_trail_into_the_gang_shows_it_too(self, gang, client, default_pack):
        """Every trail into a gang starts with the same person, so a
        badge that appeared on one screen and not the next would read as
        two different accounts."""
        from n26.core.models import Miniature

        fighter = Miniature.objects.get(name="Vex")
        for path in (
            f"/n26/gangs/{gang.pk}/hire/",
            f"/n26/gangs/{gang.pk}/print/setup/",
            f"/n26/fighters/{fighter.pk}/equip/",
        ):
            body = client.get(path).content.decode()
            assert badge_svg(GUILDER).strip() in body, path

    def test_a_gang_has_no_badge_of_its_own_to_show(self, gang, client, default_pack):
        """The house artwork in the set is one house's, and nothing in
        the library records which drawing a gang type owns — so a gang
        carries its type as text and no mark. The only badge on the
        sheet is the owner's.

        Counted below the bar: the chrome names the signed-in reader at
        the top of the account menu and draws their badge there too,
        which is a fact about the account rather than about this gang.
        """
        body = client.get(f"/n26/gangs/{gang.pk}/").content.decode()
        sheet = body.split("</header>")[-1]
        assert sheet.count(FLAIR_WRAPPER) == 1


class TestNoPageDecidesForItself:
    """A discovering guard, not a list: any page that draws a person's
    name must go through <c-n26.user-link>, because the moment one draws
    its own the two disagree about the same person."""

    # Every template but the one that is the answer: user-link is a
    # flair-link with a username on it, and has to be.
    PAGES = sorted(
        path
        for path in (Path(__file__).resolve().parents[1] / "core" / "templates").rglob(
            "*.html"
        )
        if path.name != "user_link.html"
    )
    NAMED_FLAIR = re.compile(r"<c-n26\.flair-link[^>]*username", re.DOTALL)

    def test_there_is_something_to_check(self):
        assert len(self.PAGES) > 50

    def test_no_template_hangs_a_persons_name_on_a_bare_flair_link(self):
        offenders = [
            str(path)
            for path in self.PAGES
            if self.NAMED_FLAIR.search(path.read_text())
        ]
        assert not offenders, (
            "These draw a username with a badge slot they fill themselves. Use "
            '<c-n26.user-link :user="…" />, which asks the platform\'s registry '
            f"which badge that person actually holds: {offenders}"
        )
