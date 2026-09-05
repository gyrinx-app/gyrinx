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
        act.found(territory_campaign)
"""

from contextlib import contextmanager
from dataclasses import dataclass
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

        Only an asset of a pooled kind of this campaign's type or of its
        additions. A held-one-each asset is every member gang's own, given
        on joining, and has no pool to sit in; an asset of another type is
        not one this campaign deals in — either arriving here is a caller's
        mistake, not a choice a screen offers. Nothing changes for any
        gang: a copy nobody holds is the campaign's own act, and only its
        log carries it.
        """
        if not asset.kind.is_pooled:
            raise ValueError(
                f"{asset} is of the kind {asset.kind}, which every gang holds one "
                "of. Only a pooled kind has copies to add."
            )
        if asset.kind.campaign_type_id not in (
            self.campaign.campaign_type_id,
            self.campaign.additions_id,
        ):
            raise ValueError(
                f"{asset} is of the kind {asset.kind}, which belongs to "
                f"{asset.kind.campaign_type}, not to this campaign's type or "
                "its additions."
            )
        # A shared kind may hold another campaign's own assets, written into
        # that campaign's pack. Only this campaign's pack and the type's own
        # are this campaign's to deal in.
        if asset.pack_id not in (
            self.campaign.pack_id,
            self.campaign.campaign_type.pack_id,
        ):
            raise ValueError(
                f"{asset} is in the {asset.pack} pack, which is not this "
                "campaign's own or its type's."
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

    def transfer(self, token, membership):
        """Hand a held copy from the gang holding it to another gang
        playing this campaign.

        One change to the token under the campaign's line, then a record
        on each gang inside it — the copy went from one, the copy came to
        the other — in the order the gangs are named, so both histories
        say what happened and neither says it twice. Each gang's record
        is the same kind a grant or a taking away writes, since that is
        what happened to each of them.

        A copy nobody holds cannot be handed over: granting is the act
        for that. A copy already held by the receiving gang is refused
        too, in words, since nothing would change hands.
        """
        from n26.core.operations import Refusal, operation

        if membership.campaign_id != self.campaign.pk or not membership.playing:
            raise ValueError(f"{membership} is not playing {self.campaign}.")
        token = _token_under_the_lock(token)
        if token is None:
            return None
        if token.campaign_id != self.campaign.pk:
            raise ValueError(f"{token} is not one of {self.campaign}'s copies.")
        if not token.held:
            raise Refusal(
                f"{token} is not held by any gang, so it cannot be handed over. "
                "Assign it instead."
            )
        if token.holder_id == membership.pk:
            raise Refusal(f"{membership.gang.name} already holds {token}.")
        loser = token.holder
        token.holder = membership
        token.save(update_fields=["holder", "modified"])
        with operation(loser.gang, actor=self.actor) as op:
            op.event(token, LedgerEvent.Kind.TOOK_AWAY, note=str(token))
        with operation(membership.gang, actor=self.actor) as op:
            op.event(token, LedgerEvent.Kind.GRANTED, note=str(token))
        return token

    # --- The arbitrator's additions --------------------------------------
    #
    # Everything below writes library content into the campaign's own pack
    # and onto its additions type, so it reaches member gangs by the path a
    # gang type's built-ins take. Nothing here touches the shared type.

    def add_kind(self, label_singular, mode, label_plural=""):
        """Declare a new class of asset for this campaign alone.

        The kind lands on the additions type, in the campaign's pack. A
        label the campaign already uses — on the shared type or on the
        additions — is refused in words, because the page would print two
        headings that read the same.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import add_asset_kind
        from n26.library.models import AssetKind

        label_singular = (label_singular or "").strip()
        taken = AssetKind.objects.filter(
            campaign_type_id__in=(
                self.campaign.campaign_type_id,
                self.campaign.additions_id,
            ),
            label_singular__iexact=label_singular,
        ).exists()
        if taken:
            raise Refusal(
                f"{self.campaign.name} already has a kind of asset called "
                f"{label_singular}."
            )
        kind = add_asset_kind(
            self.campaign.additions,
            label_singular,
            mode,
            label_plural=(label_plural or "").strip(),
            pack=self.campaign.pack,
        )
        self.event(CampaignEvent.Kind.KIND_ADDED, note=kind.label_singular)
        return kind

    def create_asset(self, kind, name, annotation="", income=0):
        """Write a new asset under one of this campaign's kinds.

        The kind may be the shared type's or the additions': a campaign's
        own Territory is as much a Territory as the book's. The asset
        lands in the campaign's pack whichever kind it is under, so it
        never reaches another campaign; a system kind pointing at nothing
        of the arbitrator's is what keeps that direction clean. What
        holding the asset does is not written here: it has a name, its
        words and an income figure, and nothing else.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import create_asset
        from n26.library.models import Asset

        if kind.campaign_type_id not in (
            self.campaign.campaign_type_id,
            self.campaign.additions_id,
        ):
            raise ValueError(
                f"{kind} belongs to {kind.campaign_type}, not to this "
                "campaign's type or its additions."
            )
        name = (name or "").strip()
        if Asset.objects.filter(pack=self.campaign.pack, name__iexact=name).exists():
            raise Refusal(f"{self.campaign.name} already has an asset called {name}.")
        asset = create_asset(
            name,
            kind,
            annotation=(annotation or "").strip(),
            income=income or 0,
            pack=self.campaign.pack,
        )
        self.event(CampaignEvent.Kind.ASSET_CREATED, note=str(asset))
        return asset

    def add_counter(self, name, opening=0):
        """Give every gang in the campaign a new counter, opening at a
        value.

        The counter is created in the campaign's pack and built into the
        additions type at that amount. Gangs joining from now on receive
        it as they join; gangs already playing receive it by the built-in
        propagation pass that every built-in edit files, marked as caught
        up. A name the pack already uses is refused in words, and so is
        the name of a counter the shared type already gives every gang:
        the gangs table keys its columns by what a counter is called, and
        two counters reading alike would share one column.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import add_built_in, create_counter
        from n26.library.models import Counter, DefaultAssignment

        name = (name or "").strip()
        taken = (
            Counter.objects.filter(pack=self.campaign.pack, name__iexact=name).exists()
            or DefaultAssignment.objects.filter(
                default_set_id=self.campaign.campaign_type.built_ins_id,
                archived=False,
                counter__name__iexact=name,
            ).exists()
        )
        if taken:
            raise Refusal(f"{self.campaign.name} already has a counter called {name}.")
        counter = create_counter(name, pack=self.campaign.pack)
        add_built_in(
            self.campaign.additions, counter, amount=opening, pack=self.campaign.pack
        )
        self.event(CampaignEvent.Kind.COUNTER_ADDED, note=f"{name} → {opening}")
        return counter

    def add_label(self, name, options):
        """Ask every gang in the campaign one question, with a fixed set
        of options — an Alignment, an Allegiance.

        Four library rows in the campaign's pack: a slot type named for
        the question, one pickable per option, a picklist holding them in
        the order given, and a slot assigned to the gang built into the
        additions type. The slot lands on member gangs as a counter does,
        and each gang's owner picks on the gang sheet. Options are told
        apart by the question's name in their qualifier, so two questions
        may both offer "None". A name the pack already asks is refused in
        words.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import (
            add_built_in,
            create_pickable,
            create_picklist,
            create_slot,
            create_slot_type,
        )
        from n26.library.models import SlotType

        name = (name or "").strip()
        options = [option.strip() for option in options if option and option.strip()]
        if not options:
            raise ValueError("A label needs at least one option.")
        pack = self.campaign.pack
        if SlotType.objects.filter(pack=pack, name__iexact=name).exists():
            raise Refusal(f"{self.campaign.name} already has a label called {name}.")
        slot_type = create_slot_type(name, pack=pack, allows_repeats=False)
        pickables = [
            create_pickable(option, slot_type, qualifier=name, pack=pack)
            for option in options
        ]
        picklist = create_picklist(
            f"{name} options", slot_type, members=pickables, pack=pack
        )
        slot = create_slot(
            name,
            slot_type,
            picklist,
            label=name,
            min_picks=1,
            max_picks=1,
            assigned_to="bearer",
            pack=pack,
        )
        add_built_in(self.campaign.additions, slot, pack=pack)
        self.event(
            CampaignEvent.Kind.LABEL_ADDED, note=f"{name} → {', '.join(options)}"
        )
        return slot

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


# --- What a type gives, for the screen that offers it ------------------------


@dataclass(frozen=True)
class CampaignTypeSummary:
    """One campaign type as the set-up screen offers it: what a campaign
    of it is about, and what a gang that joins is given.

    Built here rather than in the template because each line is a
    sentence composed from several rows — a kind's label and its mode, a
    built-in member and its opening value, a modifier's scope and effect
    — and the words belong with the facts they are made from.

    ``kinds`` is one sentence per asset kind, in the type's own order.
    ``starts_with`` is one sentence for the whole built-in set, or empty
    where the type builds nothing in. ``rules`` is one sentence per
    campaign-wide modifier, in the words the authoring pages use.
    """

    pk: str
    name: str
    description: str
    kinds: tuple[str, ...] = ()
    starts_with: str = ""
    rules: tuple[str, ...] = ()
    checked: bool = False


def summarise_campaign_type(campaign_type, checked=False):
    """What founding a campaign on this type gives, in sentences.

    Reads the type's kinds, its built-in members and its modifiers, each
    once. Three or four queries per type; the screen offers a handful.
    """
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS
    from n26.library.prose import GANG, sentence_for
    from n26.library.references import reading_sentences

    kinds = tuple(_kind_sentence(kind) for kind in campaign_type.asset_kinds.all())
    members = campaign_type.built_in_members.select_related(
        *DEFAULT_ASSIGNABLE_FIELDS
    ).order_by("position")
    given = [_given(member) for member in members]
    starts_with = f"Every gang starts with {_and(given)}." if given else ""
    rules = tuple(
        sentence_for(modifier, GANG, thing=campaign_type).text
        for modifier in reading_sentences(campaign_type.modifiers.all())
    )
    return CampaignTypeSummary(
        pk=str(campaign_type.pk),
        name=str(campaign_type),
        description=campaign_type.description,
        kinds=kinds,
        starts_with=starts_with,
        rules=rules,
        checked=checked,
    )


def _kind_sentence(kind):
    """How assets of one kind behave, in one sentence: "one" rather than
    an article, so the label needs no a/an."""
    if kind.is_pooled:
        return f"{kind.plural} change hands."
    return f"Every gang gets one {kind.label_singular} and keeps it."


def _given(member):
    """One built-in member as a gang receives it: a counter with its
    opening value, an asset by the one, anything else by name."""
    thing = member.assignable
    if member.counter_id is not None:
        return f"{thing} at {member.amount}"
    if member.asset_id is not None:
        return f"one {thing}"
    return str(thing)


def _and(words):
    words = list(words)
    if len(words) == 1:
        return words[0]
    return f"{', '.join(words[:-1])} and {words[-1]}"
