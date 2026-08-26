"""Spending Trade Points a gang has not got: the question, then the act.

The third answer a click can get. A note says something and lets it
through; a refusal stops it dead; this stops it until the reader says
they meant it. Credits stay the only enforced resource — nothing here
refuses, and confirming buys exactly what the first click asked for.

The page is a navigation rather than a prompt, so Back is a real answer
and a reload does not lose it. What makes the second post identical to
the first is that it carries the first one's fields, and what makes that
safe is that the view re-derives the whole click from the listing
anyway.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Assignment, Gang
from n26.core.operations import operation
from n26.library.authoring import create_trading_post, create_wargear

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def fighter(tester, gang, make_profile, make_statline):
    profile = make_profile("Ganger", price=50)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex")


@pytest.fixture
def post(db):
    """A post holding one thing, priced in credits and in Trade Points."""
    from n26.library.models import Wargear

    create_wargear("Mesh armour", price=15, trade_point_price=3)
    return create_trading_post("Trading Post", contains=[Wargear])


@pytest.fixture
def buying(post):
    """The click that buys the one thing the post lists."""
    from n26.core.owned import thing_key
    from n26.library.models import Wargear

    return {"thing": thing_key(Wargear.objects.get(name="Mesh armour"))}


def equip_url(fighter, post):
    return f"{reverse('n26-equip', args=[fighter.pk])}?list={post.pk}"


def held(gang):
    return Assignment.objects.filter(gang_root=gang, wargear__isnull=False).count()


class TestWhenTheVisitCovers:
    def test_the_purchase_goes_straight_through(
        self, client, tester, gang, fighter, post, buying
    ):
        with operation(gang, actor=tester) as op:
            op.visit_trading_post(brought=5)

        client.force_login(tester)
        answer = client.post(equip_url(fighter, post), buying)

        assert answer.status_code == 302
        assert held(gang) == 1
        gang.refresh_from_db()
        assert gang.trade_points_left == 2


class TestWhenItDoesNot:
    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_the_click_is_answered_with_a_question(
        self, client, gang, fighter, post, buying
    ):
        answer = client.post(equip_url(fighter, post), buying)

        assert answer.status_code == 200
        assert b"Buy Mesh armour anyway" in answer.content
        assert b"Not enough Trade Points" in answer.content

    def test_nothing_is_bought_by_asking(self, client, gang, fighter, post, buying):
        client.post(equip_url(fighter, post), buying)

        assert held(gang) == 0
        gang.refresh_from_db()
        assert gang.visiting_trading_post is False

    def test_the_arithmetic_is_on_the_page(self, client, gang, fighter, post, buying):
        """A name is a weak thing to check a decision against, so the page
        shows the figures the decision is actually made on."""
        with operation(gang, actor=fighter.gang.owner) as op:
            op.visit_trading_post(brought=1)

        body = client.post(equip_url(fighter, post), buying).content.decode()

        # The same tally the Visit Trading Post card draws, with the
        # purchase and what it leaves added under it.
        for label in (
            "Available",
            "Spent",
            "Remaining",
            "This purchase",
            "Remaining after",
        ):
            assert label in body
        assert "-2" in body
        assert "You don&#x27;t have enough TP" in body or "don't have enough TP" in body
        assert "You can buy it anyway." in body

    def test_confirming_buys_it(self, client, gang, fighter, post, buying):
        answer = client.post(equip_url(fighter, post), {**buying, "confirmed": "1"})

        assert answer.status_code == 302
        assert held(gang) == 1
        gang.refresh_from_db()
        # The post was shut, so the points are recorded against nothing.
        assert gang.visiting_trading_post is False

    def test_the_question_carries_the_click_forward(
        self, client, gang, fighter, post, buying
    ):
        """The confirming form re-sends what was submitted, so the second
        post is the first one with a yes attached."""
        body = client.post(equip_url(fighter, post), buying).content.decode()

        assert buying["thing"] in body
        assert 'name="confirmed"' in body

    def test_the_csrf_token_is_not_carried_forward(
        self, client, gang, fighter, post, buying
    ):
        """The token belongs to the form being drawn now, and Django puts a
        fresh one in it; re-emitting the old one would put two in the page."""
        body = client.post(equip_url(fighter, post), buying).content.decode()

        assert body.count('name="csrfmiddlewaretoken"') == 1


class TestWhenNoPointsAreCharged:
    def test_a_list_that_charges_none_never_asks(self, client, tester, gang, fighter):
        """The same sort of item on an equipment list is bought for credits
        alone, so there is nothing to overspend and nothing to confirm."""
        from n26.core.owned import thing_key
        from n26.library.authoring import add_entry, create_collection

        armour = create_wargear("Flak plate", price=15, trade_point_price=3)
        listed = create_collection("Escher Equipment List")
        add_entry(listed, armour)
        # Held by the gang, because a buying screen only offers the lists
        # its reader can actually reach.
        with operation(gang, actor=tester) as op:
            op.assign(listed, gang=gang)

        client.force_login(tester)
        answer = client.post(equip_url(fighter, listed), {"thing": thing_key(armour)})

        assert answer.status_code == 302
        assert held(gang) == 1
        gang.refresh_from_db()
        assert gang.visiting_trading_post is False


class TestWhatTheGangIsShown:
    def test_the_message_names_the_points_as_well_as_the_credits(
        self, client, tester, gang, fighter, post, buying
    ):
        with operation(gang, actor=tester) as op:
            op.visit_trading_post(brought=5)
        client.force_login(tester)

        answer = client.post(equip_url(fighter, post), buying, follow=True)

        told = [str(m) for m in answer.context["messages"]]
        assert any("15¢ and 3 TP" in line for line in told)
