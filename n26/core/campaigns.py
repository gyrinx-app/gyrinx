"""Changing a campaign, and saying so in its log.

The same shape a gang's writes have, one level up. A gang's story is written
by ``n26.core.operations``; a campaign's own story is written here, because
the two are different subjects with different readers: the arbitrator changing
what a campaign is has not touched anybody's gang.

The rule that keeps them apart, and keeps anything from being recorded twice:
**an act that changes a gang is written to that gang's ledger; an act that
changes only the campaign is written here.** A campaign's log is read from
both.

Nothing here is priced and no totals are pinned, so there is no settling step
— but the writes still run together, under the campaign's own line, so two
people editing at once cannot each save a form built from what they read
before the other's change landed.

Use it as a context manager::

    with campaign_operation(campaign, actor=arbitrator) as act:
        act.rename("Dust Falls II")
        act.set_budget(1200)
"""

from contextlib import contextmanager
from uuid import uuid4

from django.db import transaction

from n26.core.models import CampaignEvent


def budget_word(credits):
    """A gang budget as the log says it: a figure, or no ceiling at all."""
    return "unlimited" if credits is None else str(credits)


class CampaignOperation:
    """Writes to one campaign, and the log entries that explain them."""

    def __init__(self, campaign, actor=None):
        self.campaign = campaign
        self.actor = actor
        #: Every event this operation writes carries the same mark, so a
        #: reader can tell one submit's changes from the next one's.
        self.batch = uuid4()

    def event(self, kind, note=""):
        """Append to the log. Nothing already written is ever altered."""
        return CampaignEvent.objects.create(
            campaign=self.campaign,
            kind=kind,
            actor=self.actor,
            note=note[:255],
            batch=self.batch,
        )

    def created(self):
        """Record that the campaign was set up. Its first line."""
        return self.event(CampaignEvent.Kind.CREATED)

    def rename(self, name):
        """Give the campaign a new name, and say so in its log.

        The note keeps both names, since the whole of what a reader wants
        from a rename is what it was and what it became.
        """
        campaign = self.campaign
        was = campaign.name
        if was == name:
            return campaign
        campaign.name = name
        campaign.save(update_fields=["name", "modified"])
        self.event(CampaignEvent.Kind.RENAMED, note=f"{was} → {name}")
        return campaign

    def set_budget(self, credits):
        """Change what a gang may spend to join, and record it.

        ``credits`` is the new budget, or ``None`` for no ceiling at all.
        Nothing moves and no gang is touched: this is the figure a gang is
        measured against on its way in, so a reader owed an explanation of
        why a gang could not join is owed this.
        """
        campaign = self.campaign
        was = campaign.budget
        if was == credits:
            return campaign
        campaign.budget = credits
        campaign.save(update_fields=["budget", "modified"])
        self.event(
            CampaignEvent.Kind.BUDGET_SET,
            note=f"{budget_word(was)} → {budget_word(credits)}",
        )
        return campaign

    def edit_summary(self, summary):
        """Change the campaign's own words.

        The log records that the summary moved and never what it says: the
        words are the arbitrator's, and the log is a list of acts rather than
        a copy of the prose. An unchanged field writes nothing at all — no
        save, no event — so saving a form around an untouched box leaves no
        trace.
        """
        campaign = self.campaign
        if campaign.summary == summary:
            return campaign
        campaign.summary = summary
        campaign.save(update_fields=["summary", "modified"])
        self.event(CampaignEvent.Kind.SUMMARY_EDITED)
        return campaign

    def archive(self):
        """Take the campaign off the arbitrator's list, and say so.

        Nothing is destroyed, so the log keeps reading: what a campaign
        recorded stays true whether or not it is still on show.
        """
        campaign = self.campaign
        if campaign.archived:
            return campaign
        campaign.archive()
        self.event(CampaignEvent.Kind.ARCHIVED)
        return campaign


@contextmanager
def campaign_operation(campaign, actor=None):
    """One transaction, under the campaign's own line."""
    from n26.core.models import Campaign

    with transaction.atomic():
        if campaign.pk is not None:
            # Taken before anything is read back, so two arbitrators editing
            # at once queue rather than each saving a form built from what
            # they saw before the other's change landed.
            Campaign.objects.select_for_update().filter(pk=campaign.pk).first()
        yield CampaignOperation(campaign, actor=actor)
