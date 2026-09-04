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

Founding is the one act that starts from a campaign not yet saved: it
writes the campaign's own pack and additions type before the row itself,
so a campaign never exists without them::

    campaign = Campaign(name="Dust Falls", owner=arbitrator)
    with campaign_operation(campaign, actor=arbitrator) as act:
        act.found(n26_core)
"""

from contextlib import contextmanager
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from n26.core.models import Campaign, CampaignAsset, CampaignEvent, LedgerEvent

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

    def found(self, campaign_type):
        """Set the campaign up on a type, and give it its own pack.

        What ``Operation.found`` is to a gang. The campaign is saved here
        for the first time, with three things it never exists without: the
        shared type it was founded on, a pack of its own that the
        arbitrator owns, and an **additions** type created empty in that
        pack. The pack and the additions are named for the campaign; the
        pack's slug is keyed by the campaign's id, so two campaigns of one
        name cannot collide on it. The pack is the arbitrator's own: what
        they create for the campaign is theirs to edit, and a pack picker
        offers the system pack alone, so none of it reaches anybody else.

        Nothing is assigned to anybody yet. Joining is what puts the two
        types on a gang (``Operation.join_campaign``), and the log's first
        line names the type so a reader knows what the campaign was
        founded on.
        """
        from n26.library.authoring import create_campaign_type, create_pack

        campaign = self.campaign
        if not campaign._state.adding:
            raise ValueError(f"{campaign} has already been founded.")
        pack = create_pack(
            campaign.name,
            slug=f"campaign-{str(campaign.pk).lower()}",
            owner=campaign.owner,
        )
        additions = create_campaign_type(campaign.name, pack=pack)
        campaign.campaign_type = campaign_type
        campaign.pack = pack
        campaign.additions = additions
        campaign.save()
        self.event(CampaignEvent.Kind.CREATED, note=campaign_type.name)
        return campaign

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
                f"You cannot invite {user.username}. They run {campaign.name}, "
                "and an arbitrator cannot also be a participant."
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

    def add_asset(self, asset, name=""):
        """Put one copy of a pooled asset into the pool, held by nobody.

        Only an asset of a pooled kind. A held-one-each asset is every
        member gang's own, given on joining, and has no pool to sit in —
        so one arriving here is a caller's mistake, not a choice a screen
        offers. Nothing changes for any gang: a copy nobody holds is the
        campaign's own act, and only its log carries it.
        """
        if not asset.kind.is_pooled:
            raise ValueError(
                f"{asset} is of the kind {asset.kind}, which every gang holds one "
                "of. Only a pooled kind has copies to add."
            )
        token = CampaignAsset.objects.create(
            campaign=self.campaign, asset=asset, name=(name or "").strip()
        )
        self.event(CampaignEvent.Kind.ASSET_ADDED, note=str(token))
        return token

    def drop_asset(self, token):
        """Take a copy nobody holds out of the pool.

        A held copy is refused in words: dropping it would take the asset
        off the holding gang with nothing in that gang's history saying
        so. Taking it away first writes that line. A copy already gone
        drops nothing and says nothing: the second of two clicks on one
        button finds the first one's work done.
        """
        from n26.core.operations import Refusal

        token = _token_under_the_lock(token)
        if token is None:
            return None
        if token.held:
            raise Refusal(
                f"You cannot drop {token} while {token.holder.gang.name} holds it. "
                "Take it away first."
            )
        self.event(CampaignEvent.Kind.ASSET_DROPPED, note=str(token))
        token.delete()
        return token

    def grant(self, token, membership):
        """Give a copy in the pool to a gang playing this campaign.

        The token changes hands under the campaign's line, and the gang's
        own line is taken inside it — campaign first, then gang, for every
        writer that takes both; a gang's own writes only reference the
        campaign, which the campaign's lock strength leaves alone — so
        two acts touching one token and one gang never wait on each other
        in opposite orders. The gang's history gets a
        journal-only event about the token: it holds the copy and never
        owns it, so there is no entry, no price and nothing for the books
        to fold. A copy another gang holds is refused in words, and one
        this gang already holds is granted nothing twice.
        """
        from n26.core.operations import Refusal, operation

        if membership.campaign_id != self.campaign.pk or not membership.playing:
            raise ValueError(f"{membership} is not playing {self.campaign}.")
        token = _token_under_the_lock(token)
        if token is None:
            return None
        if token.campaign_id != self.campaign.pk:
            raise ValueError(f"{token} is not in {self.campaign}'s pool.")
        if token.held:
            if token.holder_id == membership.pk:
                return token
            raise Refusal(
                f"{token} is held by {token.holder.gang.name}. Take it away "
                "from them first."
            )
        token.holder = membership
        token.save(update_fields=["holder", "modified"])
        with operation(membership.gang, actor=self.actor) as op:
            op.event(token, LedgerEvent.Kind.GRANTED, note=str(token))
        return token

    def take_away(self, token):
        """Take a copy back from the gang holding it, into the pool.

        The same two lines in the same order as a grant, and the same
        kind of record on the gang — one saying the copy went. A copy
        nobody holds is left as it is, and the caller gets None back:
        nothing happened, so nothing is written.
        """
        from n26.core.operations import operation

        token = _token_under_the_lock(token)
        if token is None or not token.held:
            return None
        holder = token.holder
        token.holder = None
        token.save(update_fields=["holder", "modified"])
        with operation(holder.gang, actor=self.actor) as op:
            op.event(token, LedgerEvent.Kind.TOOK_AWAY, note=str(token))
        return token

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


def _token_under_the_lock(token):
    """The token as it stands now that the campaign's line is held, or
    None where it has gone.

    Whoever clicked read the pool before this transaction began, and two
    clicks on one button arrive together often enough. Every writer to a
    token holds its campaign's line first, so a row read under that line
    is the row as it is; the holder rides along because every decision
    here asks who has it.
    """
    return (
        CampaignAsset.objects.select_related("holder__gang", "asset__kind")
        .filter(pk=token.pk)
        .first()
    )


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

    Taken at the strength that serialises campaign operations against each
    other and nothing else. Every ledger event a gang writes names its
    campaign, and inserting that reference takes the database's own share
    lock on the campaign row after the gang's line. A full lock here would
    sit on the other side of that — campaign then gang — and an arbitrator
    granting a token while the gang's owner is buying something would
    deadlock one of them. Nothing here ever changes the campaign's key, so
    the weaker lock loses nothing.
    """
    with transaction.atomic():
        # A campaign being founded has a key already and no row yet, so
        # there is nothing to lock and nothing to read back.
        if not campaign._state.adding:
            Campaign.objects.select_for_update(no_key=True).filter(
                pk=campaign.pk
            ).first()
            campaign.refresh_from_db()
        yield CampaignOperation(campaign, actor=actor)
