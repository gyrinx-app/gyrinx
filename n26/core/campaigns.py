"""Changing a campaign, and saying so in its log.

The same shape a gang's writes have, one level up. A gang's story is written
by ``n26.core.operations``; a campaign's own story is written here, because
the two are different subjects with different readers: the arbitrator changing
what a campaign is has not touched anybody's gang.

The rule that keeps them apart, and keeps anything from being recorded twice:
**an act that changes a gang is written to that gang's ledger; an act that
changes only the campaign is written here.** A campaign's log is read from
both.

Nothing here is priced and no totals are pinned, so there is no settling
step — but the writes still run together, under the campaign's own line, and
the campaign is read back under that line before anything is decided. What
changed is measured against the row as it stands, never against whatever the
reader had on screen.

Use it as a context manager::

    with campaign_operation(campaign, actor=arbitrator) as act:
        act.rename("Dust Falls II")
        act.set_budget(1200)
"""

from contextlib import contextmanager
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from n26.core.models import Campaign, CampaignEvent

#: What the log stores for a budget that is not set. The reader matches on it
#: to say "no ceiling" in words, so the two must be the same string.
NO_CEILING = "unlimited"


def _now():
    return timezone.now()


def budget_word(credits):
    """A gang budget as the log stores it: a figure, or no ceiling at all."""
    return NO_CEILING if credits is None else str(credits)


class CampaignOperation:
    """Writes to one campaign, and the log entries that explain them."""

    def __init__(self, campaign, actor=None):
        self.campaign = campaign
        self.actor = actor
        #: Every event this operation writes carries the same mark, so what
        #: was written together stays recognisable as one submit.
        self.batch = uuid4()

    def event(self, kind, note="", battle=None, about_user=None):
        """Append to the log. Nothing already written is ever altered."""
        return CampaignEvent.objects.create(
            campaign=self.campaign,
            kind=kind,
            actor=self.actor,
            battle=battle,
            about_user=about_user,
            note=note[: CampaignEvent.NOTE_LENGTH],
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
        """Change what a gang is founded with here, and record it.

        ``credits`` is the new budget, or ``None`` for none at all. Nothing
        moves and no gang already playing is touched: this settles what the
        next gang founded for this campaign has to spend, and so what it is
        worth on the day it starts.
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

    def invite(self, user, message=""):
        """Ask somebody into the campaign, and tell them.

        Asking again somebody who declined puts the same question back rather
        than starting a second conversation, so a campaign holds one row per
        person however many times the arbitrator changes their mind. Asking
        somebody who has already accepted changes nothing.

        The notification is how they hear; the log is the record that it
        happened. An inbox that is having a bad day loses the first and
        never the second.
        """
        from n26.core.models import CampaignParticipant
        from n26.core.operations import Refusal
        from n26.notifications import deliver

        campaign = self.campaign
        if user.pk == campaign.owner_id:
            raise Refusal(
                f"{user.username} runs {campaign.name}. "
                "An arbitrator is not a participant of their own campaign."
            )
        participant, made = CampaignParticipant.objects.get_or_create(
            campaign=campaign,
            user=user,
            defaults={
                "message": message,
                "invited_by": self.actor,
                "state": CampaignParticipant.State.INVITED,
            },
        )
        if not made:
            if participant.state == CampaignParticipant.State.ACCEPTED:
                return participant
            participant.state = CampaignParticipant.State.INVITED
            participant.message = message
            participant.invited_by = self.actor
            participant.answered = None
            participant.save(
                update_fields=[
                    "state",
                    "message",
                    "invited_by",
                    "answered",
                    "modified",
                ]
            )

        self.event(CampaignEvent.Kind.INVITED, about_user=user)
        asked_by = self.actor.username if self.actor else "An arbitrator"
        deliver(
            user,
            subject=f"{asked_by} invited you to {campaign.name}",
            content=message,
            sender=self.actor,
            about=participant,
        )
        return participant

    def answer_invitation(self, user, accepted):
        """Record somebody's answer to their invitation.

        The arbitrator is told, because they asked and are owed the answer.
        An invitation already answered is not asked again: a second click on
        a stale page settles nothing twice.
        """
        from n26.core.models import CampaignParticipant
        from n26.notifications import deliver

        campaign = self.campaign
        participant = CampaignParticipant.objects.filter(
            campaign=campaign, user=user, state=CampaignParticipant.State.INVITED
        ).first()
        if participant is None:
            return None

        states = CampaignParticipant.State
        participant.state = states.ACCEPTED if accepted else states.DECLINED
        participant.answered = _now()
        participant.save(update_fields=["state", "answered", "modified"])

        self.event(
            CampaignEvent.Kind.INVITE_ACCEPTED
            if accepted
            else CampaignEvent.Kind.INVITE_DECLINED,
            about_user=user,
        )
        word = "accepted" if accepted else "declined"
        deliver(
            campaign.owner,
            subject=f"{user.username} {word} your invitation to {campaign.name}",
            sender=user,
            about=participant,
        )
        return participant

    def remove_participant(self, participant):
        """Take somebody out of the campaign.

        The row goes rather than being marked: a person who is not in a
        campaign has no standing in it, and keeping a row saying so would
        make them look like somebody who declined. What happened stays in
        the log, which is where it belongs.
        """
        user = participant.user
        participant.delete()
        self.event(CampaignEvent.Kind.PARTICIPANT_REMOVED, about_user=user)

    def record_battle(self, date, gangs=()):
        """Write down a battle that was fought, and who was in it.

        Recording one changes no gang: it says a thing happened, and what it
        did to anybody is written against that gang afterwards. So this is the
        campaign's own act, and only the campaign's log carries it.
        """
        from n26.core.models import Battle

        battle = Battle.objects.create(campaign=self.campaign, date=date)
        battle.gangs.set(gangs)
        self.event(CampaignEvent.Kind.BATTLE_RECORDED, battle=battle)
        return battle

    def remove_battle(self, battle):
        """Take a battle off the campaign, for one written down in error.

        What the gangs did in it keeps its own records; those simply stop
        naming a battle. The log says the battle was removed rather than
        losing the line that said it happened, because both are true.
        """
        self.event(CampaignEvent.Kind.BATTLE_REMOVED, note=str(battle.date))
        battle.delete()

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


def over_budget(campaign, gang):
    """Whether this gang is bigger than the campaign's stated size.

    Measured on the gang's wealth: its rating, its stash and the credits it
    has not spent. Spending moves credits into rating or stash and changes
    none of the total, so wealth today is what the gang's rating and stash
    come to once it has bought everything it can — which is the number a
    budget is about. A campaign with no budget is never over it.
    """
    return campaign.budget is not None and gang.wealth > campaign.budget


@contextmanager
def campaign_operation(campaign, actor=None):
    """One transaction, under the campaign's own line.

    The line is taken first and the campaign read back under it. Whoever
    opened the form read the row before this transaction began, and deciding
    what changed against those values would let one arbitrator overwrite
    another and record a note naming a name that had already been replaced.
    """
    with transaction.atomic():
        if campaign.pk is not None:
            Campaign.objects.select_for_update().filter(pk=campaign.pk).first()
            campaign.refresh_from_db()
        yield CampaignOperation(campaign, actor=actor)
