"""What a campaign's log records, and how it reads.

The write side and the prose, with no page in the way. The screens that reach
these are covered where the feature flag can be opened.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history, campaign_history_size
from n26.core.models import Campaign, CampaignEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def campaign(arbitrator):
    return Campaign.objects.create(name="Dust Falls", owner=arbitrator, budget=1000)


def kinds_of(campaign):
    return list(
        campaign.events.order_by("created", "id").values_list("kind", flat=True)
    )


def told(campaign, viewer=None, limit=None):
    """Each act as one plain sentence, the way a page draws it."""
    return [
        "".join(span.text for span in act.spans)
        for act in campaign_history(campaign, viewer=viewer, limit=limit)
    ]


class TestWhatGetsRecorded:
    def test_setting_a_campaign_up_is_its_first_line(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.created()
        assert kinds_of(campaign) == [CampaignEvent.Kind.CREATED]

    def test_a_rename_keeps_both_names(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename("Dust Falls II")
        (event,) = campaign.events.all()
        assert event.kind == CampaignEvent.Kind.RENAMED
        assert event.note == "Dust Falls → Dust Falls II"
        campaign.refresh_from_db()
        assert campaign.name == "Dust Falls II"

    def test_a_budget_change_keeps_both_figures(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(1200)
        (event,) = campaign.events.all()
        assert event.kind == CampaignEvent.Kind.BUDGET_SET
        assert event.note == "1000 → 1200"

    def test_lifting_the_budget_says_so(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(None)
        (event,) = campaign.events.all()
        assert event.note == "1000 → unlimited"

    def test_the_summary_records_that_it_moved_never_what_it_says(
        self, campaign, arbitrator
    ):
        """The words are the arbitrator's. The log is a list of acts."""
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.edit_summary("<p>A quiet stretch of the underhive.</p>")
        (event,) = campaign.events.all()
        assert event.kind == CampaignEvent.Kind.SUMMARY_EDITED
        assert event.note == ""

    def test_archiving_is_recorded_and_the_log_survives_it(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.archive()
        campaign.refresh_from_db()
        assert campaign.archived
        assert kinds_of(campaign) == [CampaignEvent.Kind.ARCHIVED]

    def test_who_did_it_is_kept(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename("Dust Falls II")
        assert campaign.events.get().actor == arbitrator


class TestWhatGetsNoRecord:
    """An unchanged field writes nothing at all — no save, no event — so
    saving a form around an untouched box leaves no trace."""

    def test_the_same_name_again_records_nothing(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename("Dust Falls")
        assert kinds_of(campaign) == []

    def test_the_same_budget_again_records_nothing(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(1000)
        assert kinds_of(campaign) == []

    def test_the_same_summary_again_records_nothing(self, campaign, arbitrator):
        campaign.summary = "<p>Unchanged.</p>"
        campaign.save()
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.edit_summary("<p>Unchanged.</p>")
        assert kinds_of(campaign) == []

    def test_archiving_twice_records_once(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.archive()
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.archive()
        assert kinds_of(campaign) == [CampaignEvent.Kind.ARCHIVED]

    def test_a_submit_that_changes_one_field_records_one_act(
        self, campaign, arbitrator
    ):
        """The whole point of the guard: a form saves every box it holds."""
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename("Dust Falls")
            act.set_budget(1200)
            act.edit_summary("")
        assert kinds_of(campaign) == [CampaignEvent.Kind.BUDGET_SET]


class TestOneSubmitIsOneAct:
    def test_everything_written_together_shares_one_mark(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename("Dust Falls II")
            act.set_budget(1200)
        marks = {event.batch for event in campaign.events.all()}
        assert len(marks) == 1
        assert None not in marks

    def test_a_second_submit_is_a_second_mark(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename("Dust Falls II")
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(1200)
        assert len({event.batch for event in campaign.events.all()}) == 2


class TestHowTheLogReads:
    def test_the_acts_come_oldest_first(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.created()
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename("Dust Falls II")
        assert told(campaign) == [
            "set the campaign up",
            "renamed the campaign Dust Falls to Dust Falls II",
        ]

    def test_a_budget_reads_in_the_mark_the_page_uses(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(1200)
        assert told(campaign) == ["set the gang budget to 1200¢"]

    def test_lifting_the_budget_reads_as_no_ceiling(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(None)
        assert told(campaign) == [
            "removed the gang budget — gangs enter at whatever they are worth"
        ]

    def test_the_reader_is_named_as_themselves(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.created()
        (mine,) = campaign_history(campaign, viewer=arbitrator)
        (theirs,) = campaign_history(campaign, viewer=None)
        assert mine.actor == "You"
        assert theirs.actor == "arbitrator"

    def test_every_kind_has_a_sentence_of_its_own(self, campaign):
        """A kind added without prose would fall through to a sentence that
        says nothing. Each must say what actually happened."""
        for kind in CampaignEvent.Kind:
            CampaignEvent.objects.create(campaign=campaign, kind=kind)
        sentences = told(campaign)
        assert len(sentences) == len(CampaignEvent.Kind)
        assert "changed the campaign" not in sentences
        assert len(set(sentences)) == len(sentences)

    def test_no_money_is_ever_reported(self, campaign, arbitrator):
        """Nothing here moves any: a budget is what a gang is measured
        against, not a payment."""
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_budget(1200)
        (act_,) = campaign_history(campaign)
        assert (act_.credits, act_.trade_points, act_.rating) == (0, 0, 0)


class TestTheLogIsOneCampaignsOwn:
    def test_another_campaigns_acts_do_not_appear(self, campaign, arbitrator):
        other = Campaign.objects.create(name="Sump City", owner=arbitrator)
        with campaign_operation(other, actor=arbitrator) as act:
            act.created()
        assert told(campaign) == []
        assert told(other) == ["set the campaign up"]


class TestTwoArbitratorsAtOnce:
    """What changed is measured against the row as it stands, never against
    whatever the reader had on screen. Without that, one arbitrator's save
    silently reverts another's, and the note names a name that had already
    been replaced — in a log nothing can go back and correct."""

    def test_a_stale_instance_is_read_back_before_anything_is_decided(
        self, campaign, arbitrator
    ):
        stale = Campaign.objects.get(pk=campaign.pk)
        Campaign.objects.filter(pk=campaign.pk).update(name="Renamed Elsewhere")

        with campaign_operation(stale, actor=arbitrator) as act:
            act.rename("Dust Falls III")

        (event,) = campaign.events.all()
        assert event.note == "Renamed Elsewhere → Dust Falls III"

    def test_a_change_somebody_else_already_made_records_nothing(
        self, campaign, arbitrator
    ):
        stale = Campaign.objects.get(pk=campaign.pk)
        Campaign.objects.filter(pk=campaign.pk).update(budget=1200)

        with campaign_operation(stale, actor=arbitrator) as act:
            act.set_budget(1200)

        assert kinds_of(campaign) == []

    def test_archiving_a_stale_instance_keeps_the_other_change(
        self, campaign, arbitrator
    ):
        """Archiving saves the whole row, so a stale one would put back every
        field it was holding."""
        stale = Campaign.objects.get(pk=campaign.pk)
        Campaign.objects.filter(pk=campaign.pk).update(name="Renamed Elsewhere")

        with campaign_operation(stale, actor=arbitrator) as act:
            act.archive()

        campaign.refresh_from_db()
        assert (campaign.name, campaign.archived) == ("Renamed Elsewhere", True)


class TestReadingOnlyPartOfTheLog:
    def test_a_limit_takes_the_most_recent_acts(self, campaign, arbitrator):
        for number in range(5):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.set_budget(1001 + number)

        assert told(campaign, limit=2) == [
            "set the gang budget to 1004¢",
            "set the gang budget to 1005¢",
        ]

    def test_a_limit_larger_than_the_log_returns_all_of_it(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.created()
        assert told(campaign, limit=10) == ["set the campaign up"]

    def test_the_size_is_counted_without_building_the_acts(self, campaign, arbitrator):
        for number in range(4):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.set_budget(1001 + number)
        assert campaign_history_size(campaign) == 4

    def test_a_limited_read_asks_for_one_page_of_events(self, campaign, arbitrator):
        """The point of the limit: a campaign played for a year opens as
        cheaply as one set up this morning."""
        for number in range(30):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.set_budget(1001 + number)

        with CaptureQueriesContext(connection) as queries:
            campaign_history(campaign, limit=5)
        (fetch,) = [q["sql"] for q in queries.captured_queries]
        assert "LIMIT 5" in fetch


class TestALongRename:
    def test_both_names_are_kept_in_full(self, campaign, arbitrator):
        """A campaign name may run to 200 characters, so a rename note holds
        two of them and the mark between. Nothing here is ever rewritten, so
        a note cut short would leave a reader with half a name for good."""
        was = "A" * 200
        now = "B" * 200
        campaign.name = was
        campaign.save()

        with campaign_operation(campaign, actor=arbitrator) as act:
            act.rename(now)

        (event,) = campaign.events.all()
        assert event.note == f"{was} → {now}"
        assert told(campaign) == [f"renamed the campaign {was} to {now}"]
