"""Which campaign a gang is playing, and what that puts in each log.

The write side and the reading, with no page in the way. The screens that
reach these are covered where the feature flag can be opened.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from n26.core.campaigns import campaign_operation
from n26.core.history import build, campaign_history, campaign_history_size
from n26.core.models import Campaign, CampaignMembership, Gang, LedgerEvent
from n26.core.operations import AlreadyInACampaign, OverCampaignBudget, operation
from n26.library.authoring import create_wargear
from n26.tests.sandbox.actions import assign, found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def gang(gang_type):
    player = User.objects.create_user("player")
    return found_gang("The Ashen Choir", gang_type, owner=player)


@pytest.fixture
def campaign(arbitrator):
    return Campaign.objects.create(name="Dust Falls", owner=arbitrator, budget=1000)


@pytest.fixture
def other_campaign(arbitrator):
    return Campaign.objects.create(name="Sump City", owner=arbitrator)


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


class TestJoiningACampaign:
    def test_the_gang_is_playing_it(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        membership = CampaignMembership.objects.get(gang=gang)
        assert membership.campaign == campaign
        assert membership.playing

    def test_the_gangs_own_history_says_so(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        assert "added the gang to Dust Falls" in sentences(build(gang))

    def test_the_campaigns_log_says_so_from_the_same_record(
        self, gang, campaign, arbitrator
    ):
        """One record, two readers — never a copy in each."""
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        assert "added the gang to Dust Falls" in sentences(campaign_history(campaign))
        assert (
            LedgerEvent.objects.filter(kind=LedgerEvent.Kind.JOINED_CAMPAIGN).count()
            == 1
        )

    def test_joining_the_same_campaign_again_changes_nothing(
        self, gang, campaign, arbitrator
    ):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        assert CampaignMembership.objects.filter(gang=gang).count() == 1

    def test_a_second_campaign_is_refused_with_a_sentence(
        self, gang, campaign, other_campaign, arbitrator
    ):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        with pytest.raises(AlreadyInACampaign) as refused:
            with operation(gang, actor=arbitrator) as op:
                op.join_campaign(other_campaign)

        assert "already playing Dust Falls" in str(refused.value)
        assert CampaignMembership.objects.filter(gang=gang).count() == 1

    def test_the_database_holds_the_same_line(self, gang, campaign, other_campaign):
        """The refusal is the sentence a player reads; this is what stops a
        second open membership however it is written."""
        CampaignMembership.objects.create(campaign=campaign, gang=gang)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CampaignMembership.objects.create(campaign=other_campaign, gang=gang)


class TestTheBudgetAtTheDoor:
    """What a campaign says it will take, and who may go past it."""

    @pytest.fixture
    def gang(self, gang_type, make_profile):
        """A gang with somebody in it, so it is worth something to weigh."""
        player = User.objects.create_user("player")
        founded = found_gang("The Ashen Choir", gang_type, owner=player)
        hire(founded, make_profile("Escher Ganger"), "Yolanda", paid=55)
        founded.refresh_from_db()
        return founded

    @pytest.fixture
    def shoestring(self, arbitrator):
        """A campaign nobody's gang fits into."""
        return Campaign.objects.create(name="Shoestring", owner=arbitrator, budget=1)

    def test_the_gang_is_worth_what_it_holds(self, gang):
        """The premise the rest of the class rests on."""
        assert gang.rating_with_stash == gang.rating + gang.stash_rating
        assert gang.rating_with_stash > 1

    def test_a_gang_worth_more_is_refused(self, gang, shoestring, arbitrator):
        with pytest.raises(OverCampaignBudget) as refused:
            with operation(gang, actor=arbitrator) as op:
                op.join_campaign(shoestring)
        said = str(refused.value)
        assert "Shoestring" in said
        assert str(gang.rating_with_stash) in said
        assert not CampaignMembership.objects.filter(gang=gang).exists()

    def test_the_arbitrator_may_seat_it_anyway(self, gang, shoestring, arbitrator):
        """They set the number, so they are the one who may go past it."""
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(shoestring, over_budget_allowed=True)
        assert CampaignMembership.objects.filter(
            gang=gang, campaign=shoestring, left__isnull=True
        ).exists()

    def test_a_gang_that_fits_walks_in(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        assert CampaignMembership.objects.filter(
            gang=gang, campaign=campaign, left__isnull=True
        ).exists()

    def test_a_campaign_with_no_budget_takes_anything(
        self, gang, other_campaign, arbitrator
    ):
        assert other_campaign.budget is None
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(other_campaign)
        assert CampaignMembership.objects.filter(
            gang=gang, campaign=other_campaign, left__isnull=True
        ).exists()

    def test_the_stash_is_counted(self, gang, arbitrator):
        """Gear put aside still belongs to the gang, so it still weighs."""
        before = gang.rating_with_stash
        assign(create_wargear("Ammo crate", price=25), stash=gang.stash, paid=25)
        # Fetched again rather than refreshed: the stash is a cached reverse
        # relation, and its pinned rating is what changed.
        gang = Gang.objects.get(pk=gang.pk)
        assert gang.rating_with_stash == before + 25

        snug = Campaign.objects.create(name="Snug", owner=arbitrator, budget=before)
        with pytest.raises(OverCampaignBudget):
            with operation(gang, actor=arbitrator) as op:
                op.join_campaign(snug)

    def test_cash_in_hand_is_not_counted(self, gang, arbitrator):
        """The cap is on what the gang owns, so money it has not spent
        cannot put it over one."""
        gang.credits = 100_000
        gang.save()
        roomy = Campaign.objects.create(
            name="Roomy", owner=arbitrator, budget=gang.rating_with_stash
        )
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(roomy)
        assert CampaignMembership.objects.filter(gang=gang, campaign=roomy).exists()

    def test_worth_exactly_the_budget_fits(self, gang, arbitrator):
        """Up to the number, not short of it."""
        exact = Campaign.objects.create(
            name="Exact", owner=arbitrator, budget=gang.rating_with_stash
        )
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(exact)
        assert CampaignMembership.objects.filter(gang=gang, campaign=exact).exists()


class TestLeavingACampaign:
    def test_the_membership_closes_rather_than_going(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.leave_campaign()

        membership = CampaignMembership.objects.get(gang=gang)
        assert membership.left is not None
        assert not membership.playing

    def test_the_leaving_names_what_was_left(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.leave_campaign()

        assert "took the gang out of Dust Falls" in sentences(build(gang))
        assert "took the gang out of Dust Falls" in sentences(
            campaign_history(campaign)
        )

    def test_a_gang_playing_nothing_leaves_nothing(self, gang, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            assert op.leave_campaign() is None
        assert not CampaignMembership.objects.exists()

    def test_the_gang_may_then_join_another(
        self, gang, campaign, other_campaign, arbitrator
    ):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.leave_campaign()
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(other_campaign)

        assert CampaignMembership.objects.filter(gang=gang).count() == 2
        assert CampaignMembership.objects.get(
            gang=gang, left__isnull=True
        ).campaign == (other_campaign)


class TestWhatTheCampaignSees:
    def test_what_a_gang_did_while_playing_reads_in_the_campaigns_log(
        self, gang, campaign, arbitrator
    ):
        """No call site marks these — the operation reads the gang's
        membership, so nothing has to remember."""
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.rename_gang("The Ashen Chorus")

        assert "renamed the gang" in " ".join(sentences(campaign_history(campaign)))

    def test_what_it_did_before_joining_does_not(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.rename_gang("Before")
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        told = " ".join(sentences(campaign_history(campaign)))
        assert "renamed the gang" not in told

    def test_what_it_does_after_leaving_does_not(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.leave_campaign()
        with operation(gang, actor=arbitrator) as op:
            op.rename_gang("After")

        told = " ".join(sentences(campaign_history(campaign)))
        assert "renamed the gang" not in told

    def test_another_campaigns_gangs_do_not_appear(
        self, gang, campaign, other_campaign, arbitrator
    ):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(other_campaign)

        assert sentences(campaign_history(campaign)) == []

    def test_the_two_sources_are_merged_in_time_order(self, gang, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.created()
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(1200)

        assert sentences(campaign_history(campaign)) == [
            "set the campaign up",
            "added the gang to Dust Falls",
            "set the gang budget to 1200¢",
        ]

    def test_the_size_counts_both_sources(self, gang, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.created()
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        assert campaign_history_size(campaign) == 2

    def test_an_act_says_which_gang_it_was(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)

        (act,) = [a for a in campaign_history(campaign) if a.gang_name]
        assert act.gang_name == gang.name
        assert act.gang_pk == str(gang.pk)

    def test_the_campaigns_own_acts_name_no_gang(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.created()

        (act_,) = campaign_history(campaign)
        assert act_.gang_name == ""


class TestTheCampaignsLogFoldsWhatTheGangsDoes:
    """Both pages are told by the same machinery, so a hire is one line with
    its kit beneath it in each. Reading them differently would mean two
    accounts of the same act."""

    def test_a_hire_is_one_act_not_one_per_thing_it_brought(
        self, gang, campaign, arbitrator, make_profile
    ):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.hire(make_profile("Ganger", price=25), "Vex")

        hires = [
            act
            for act in campaign_history(campaign)
            if "hired Vex" in "".join(span.text for span in act.spans)
        ]
        assert len(hires) == 1

    def test_the_campaign_tells_it_the_way_the_gang_does(
        self, gang, campaign, arbitrator, make_profile
    ):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with operation(gang, actor=arbitrator) as op:
            op.hire(make_profile("Ganger", price=25), "Vex")

        def hire_of(acts):
            (found,) = [
                a for a in acts if "hired Vex" in "".join(s.text for s in a.spans)
            ]
            return "".join(s.text for s in found.spans), sorted(
                sub.name for sub in found.subs
            )

        assert hire_of(campaign_history(campaign)) == hire_of(build(gang))

    def test_one_gangs_riders_never_fold_under_anothers_act(
        self, gang, campaign, arbitrator, gang_type, make_profile
    ):
        other = found_gang("Rust Kings", gang_type, owner=arbitrator)
        for each in (gang, other):
            with operation(each, actor=arbitrator) as op:
                op.join_campaign(campaign)
        for each, role in ((gang, "Ganger"), (other, "Juve")):
            with operation(each, actor=arbitrator) as op:
                op.hire(make_profile(role, price=25), f"Vex of {each.name}")

        named = {act.gang_name for act in campaign_history(campaign)}
        assert named == {"The Ashen Choir", "Rust Kings"}
