"""Which campaign a gang is playing, and what that puts in each log.

The write side and the reading, with no page in the way. The screens that
reach these are covered where the feature flag can be opened.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from n26.core.campaigns import campaign_operation, over_budget
from n26.core.history import build, campaign_history, campaign_history_size
from n26.core.models import CampaignMembership, Gang, LedgerEvent
from n26.core.operations import AlreadyInACampaign, operation
from n26.library.authoring import create_wargear
from n26.tests.sandbox.actions import assign, found_campaign, found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def gang(gang_type):
    player = User.objects.create_user("player")
    return found_gang("The Ashen Choir", gang_type, owner=player)


@pytest.fixture
def campaign(arbitrator, campaign_type):
    return found_campaign("Dust Falls", campaign_type, owner=arbitrator, budget=1000)


@pytest.fixture
def other_campaign(arbitrator, campaign_type):
    return found_campaign("Sump City", campaign_type, owner=arbitrator)


#: The log's first line, which founding writes before any test here acts.
FOUNDED = "set the campaign up on Territory campaign"


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


class TestWhatCountsAgainstTheBudget:
    """A budget is a size the table agreed on, and nothing is refused for
    being over it. What it is measured against is the gang's wealth: its
    rating, its stash and the credits it has not spent. Spending moves
    credits into rating or stash and changes none of the total, so wealth
    today is what a gang's rating and stash come to once it has bought
    everything it can.
    """

    @pytest.fixture
    def gang(self, gang_type, make_profile):
        """A gang with one hired model and no budget of its own, so its
        wealth is exactly what it holds."""
        player = User.objects.create_user("player")
        founded = found_gang("The Ashen Choir", gang_type, owner=player)
        hire(founded, make_profile("Escher Ganger"), "Yolanda", paid=55)
        return Gang.objects.get(pk=founded.pk)

    @pytest.fixture(autouse=True)
    def _type(self, campaign_type):
        self.campaign_type = campaign_type

    def campaign_of(self, arbitrator, budget):
        return found_campaign(
            f"Budget {budget}", self.campaign_type, owner=arbitrator, budget=budget
        )

    def test_a_gang_that_fits_is_not_over(self, gang, arbitrator):
        assert gang.wealth == 55
        assert over_budget(self.campaign_of(arbitrator, 1000), gang) is False

    def test_exactly_the_budget_is_not_over(self, gang, arbitrator):
        """Up to the number, not short of it."""
        assert over_budget(self.campaign_of(arbitrator, gang.wealth), gang) is False

    def test_a_penny_more_is_over(self, gang, arbitrator):
        assert over_budget(self.campaign_of(arbitrator, gang.wealth - 1), gang) is True

    def test_a_campaign_with_no_budget_is_never_over(self, gang, arbitrator):
        assert over_budget(self.campaign_of(arbitrator, None), gang) is False

    def test_the_stash_counts(self, gang, arbitrator):
        """Gear put aside still belongs to the gang."""
        before = gang.wealth
        assign(create_wargear("Ammo crate", price=25), stash=gang.stash, paid=25)
        grown = Gang.objects.get(pk=gang.pk)
        assert grown.wealth == before + 25
        assert over_budget(self.campaign_of(arbitrator, before), grown) is True

    def test_credits_not_yet_spent_count(self, gang_type, make_profile, arbitrator):
        """The case the whole measure turns on: a gang founded on a large
        budget that has spent almost none of it is not small. It will be
        as big as its founding budget the moment it goes shopping."""
        player = User.objects.create_user("spender")
        rich = found_gang("Deep Pockets", gang_type, owner=player, budget=5000)
        hire(rich, make_profile("Escher Ganger"), "Yolanda", paid=55)
        rich = Gang.objects.get(pk=rich.pk)

        assert rich.rating == 55
        assert rich.stash_rating == 0
        assert rich.credits == 4945
        assert rich.wealth == 5000

        # What it holds today would fit; what it can buy will not.
        assert over_budget(self.campaign_of(arbitrator, 1000), rich) is True

    def test_a_gang_over_the_budget_still_joins(self, gang, arbitrator):
        """Nothing is refused for being over: the budget informs."""
        snug = self.campaign_of(arbitrator, gang.wealth - 1)
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(snug)
        assert CampaignMembership.objects.filter(
            gang=gang, campaign=snug, left__isnull=True
        ).exists()


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

        assert sentences(campaign_history(campaign)) == [FOUNDED]

    def test_the_two_sources_are_merged_in_time_order(self, gang, campaign, arbitrator):
        with operation(gang, actor=arbitrator) as op:
            op.join_campaign(campaign)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(1200)

        assert sentences(campaign_history(campaign)) == [
            FOUNDED,
            "added the gang to Dust Falls",
            "set the gang budget to 1200¢",
        ]

    def test_the_size_counts_both_sources(self, gang, campaign, arbitrator):
        """The founding line and the joining. The campaign types the
        joining put on the gang ride that act rather than counting as
        acts of their own, so the size says what the page would draw."""
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

        named = {act.gang_name for act in campaign_history(campaign) if act.gang_name}
        assert named == {"The Ashen Choir", "Rust Kings"}
