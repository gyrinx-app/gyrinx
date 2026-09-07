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
                "and an arbitrator cannot also be a player."
            )
        player, made = CampaignParticipant.objects.get_or_create(
            campaign=campaign,
            user=user,
            defaults={
                "message": message,
                "invited_by": self.actor,
                "state": CampaignParticipant.State.INVITED,
            },
        )
        if not made:
            if player.state == CampaignParticipant.State.ACCEPTED:
                return player
            player.state = CampaignParticipant.State.INVITED
            player.message = message
            player.invited_by = self.actor
            player.answered = None
            player.save(
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
            about=player,
        )
        return player

    def answer_invitation(self, user, accepted):
        """Record somebody's answer to their invitation.

        The arbitrator is told, because they asked and are owed the answer.
        An invitation already answered is not asked again: a second click on
        a stale page settles nothing twice.
        """
        from n26.core.models import CampaignParticipant
        from n26.notifications import deliver

        campaign = self.campaign
        player = CampaignParticipant.objects.filter(
            campaign=campaign, user=user, state=CampaignParticipant.State.INVITED
        ).first()
        if player is None:
            return None

        states = CampaignParticipant.State
        player.state = states.ACCEPTED if accepted else states.DECLINED
        player.answered = _now()
        player.save(update_fields=["state", "answered", "modified"])

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
            about=player,
        )
        return player

    def remove_player(self, player):
        """Take somebody out of the campaign.

        The row goes rather than being marked: a person who is not in a
        campaign has no standing in it, and keeping a row saying so would
        make them look like somebody who declined. What happened stays in
        the log, which is where it belongs.
        """
        user = player.user
        player.delete()
        self.event(CampaignEvent.Kind.PLAYER_REMOVED, about_user=user)

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
        """Add one of an asset to the campaign, held by nobody.

        Only an asset of a Holding asset type of this campaign's type or of
        its own additions. A possession is every member gang's own, given on
        joining, and the campaign keeps none; an asset of another campaign
        type is not one this campaign deals in — either arriving here is a
        caller's mistake, not a choice a screen offers. Nothing changes for
        any gang: an asset nobody holds is the campaign's own act, and only
        its log carries it.
        """
        asset_type = asset.asset_type
        if not asset_type.is_holding:
            raise ValueError(
                f"{asset} is a {asset_type}, which every gang has its own of. "
                "Only an asset type with Holding ownership can be added to a "
                "campaign."
            )
        if asset_type.campaign_type_id not in (
            self.campaign.campaign_type_id,
            self.campaign.additions_id,
        ):
            raise ValueError(
                f"{asset} is a {asset_type}, an asset type of "
                f"{asset_type.campaign_type}, not of this campaign's type or "
                "the campaign's own."
            )
        # A shared asset type may hold another campaign's own assets, written
        # into that campaign's pack. Only this campaign's pack and the type's
        # own are this campaign's to deal in.
        if asset.pack_id not in (
            self.campaign.pack_id,
            self.campaign.campaign_type.pack_id,
        ):
            raise ValueError(
                f"{asset} is in the {asset.pack} pack, which is not this "
                "campaign's own or its type's."
            )
        campaign_asset = self._keep(asset, name)
        self.event(CampaignEvent.Kind.ASSET_ADDED, note=str(campaign_asset))
        return campaign_asset

    def _keep(self, asset, name=""):
        """The campaign asset itself, held by nobody. Written by the two
        acts that bring an asset in — adding one by hand and rolling one —
        each of which records itself."""
        return CampaignAsset.objects.create(
            campaign=self.campaign, asset=asset, name=(name or "").strip()
        )

    def roll_asset(self, table, *, membership=None, rolled=None, rng=None):
        """Roll on an asset table and add what the roll lands on.

        Without a membership this is the arbitrator generating the pool:
        the table has to be one the campaign itself holds — built into
        its type or into its additions — and the asset the roll lands on
        is added held by nobody, exactly as :meth:`add_asset` adds one.
        With a membership it is a gang's starting roll: the table has to
        be one that gang holds, on its card as stored or granted, and the
        asset is assigned to the gang as :meth:`assign` would, so the
        gang's ledger gets its GAINED. The two rolls are independent, and
        a roll may land on an asset the campaign already has: the rules
        allow the same territory to come up more than once, and the
        campaign asset's own name is what tells the two apart.

        ``rolled`` is a roll made at the table and entered here rather
        than generated; it has to be one the die can make, and the record
        says it was entered. ``rng`` is for a test that wants the dice
        loaded.

        One log line for one act: the roll is recorded as ASSET_ROLLED
        with the asset in its note, and no ASSET_ADDED beside it.
        Refused in words where the table is not one the roller holds,
        names no dice, or has no entry for the roll.
        """
        from n26.core.operations import ROLL_ENTERED, Refusal
        from n26.library.models import Dice

        if membership is not None and (
            membership.campaign_id != self.campaign.pk or not membership.playing
        ):
            raise ValueError(f"{membership} is not playing {self.campaign}.")
        if not table.dice:
            raise Refusal(
                f"You cannot roll on {table}. It is a list with no dice: nothing "
                "on it is rolled for."
            )
        if membership is None:
            if not tables_in_play(self.campaign).filter(pk=table.pk).exists():
                raise Refusal(
                    f"You cannot roll on {table} for {self.campaign.name}. Only a "
                    "table built into the campaign can be rolled on for it."
                )
        elif table.pk not in {held.pk for held in tables_held_by(membership.gang)}:
            raise Refusal(
                f"{membership.gang.name} cannot roll on {table}. Only a gang "
                "that holds that table can."
            )

        dice = Dice(table.dice)
        entered = rolled is not None
        if not entered:
            rolled = Dice.roll(dice, rng)
        elif rolled not in Dice.rolls(dice):
            raise Refusal(f"You cannot roll {rolled} on a {dice.label}.")

        entries = list(table.entries.select_related("asset__asset_type"))
        entry = table.landing(rolled, entries)
        if entry is None:
            raise Refusal(
                f"No entry on {table} is rolled by {rolled}. Fill that gap in the "
                "table first."
            )
        campaign_asset = self._keep(entry.asset)
        who = f" for {membership.gang.name}" if membership is not None else ""
        note = f"Rolled {rolled} on {_table_named(table)}{who}: {campaign_asset}."
        if entered:
            note = f"{note} {ROLL_ENTERED}"
        self.event(CampaignEvent.Kind.ASSET_ROLLED, note=note)
        if membership is not None:
            campaign_asset = self.assign(campaign_asset, membership)
        return AssetRoll(
            roll=rolled, dice=dice, table=table, campaign_asset=campaign_asset
        )

    def remove_asset(self, campaign_asset):
        """Take an asset nobody holds out of the campaign.

        A held asset is refused in words: removing it would take the asset
        off the holding gang with nothing in that gang's history saying so.
        Unassigning it first writes that line. An asset already gone removes
        nothing and says nothing: the second of two clicks on one button
        finds the first one's work done.
        """
        from n26.core.operations import Refusal

        campaign_asset = _asset_under_the_lock(campaign_asset)
        if campaign_asset is None:
            return None
        if campaign_asset.held:
            raise Refusal(
                f"You cannot remove {campaign_asset} while "
                f"{campaign_asset.holder.gang.name} holds it. Unassign it first."
            )
        self.event(CampaignEvent.Kind.ASSET_REMOVED, note=str(campaign_asset))
        campaign_asset.delete()
        return campaign_asset

    def assign(self, campaign_asset, membership):
        """Give an asset nobody holds to a gang playing this campaign.

        The asset's holder is set under the campaign's line, and the gang's
        own line is taken inside it — campaign first, then gang, for every
        writer that takes both; a gang's own writes only reference the
        campaign, which the campaign's lock strength leaves alone — so two
        acts touching one asset and one gang never wait on each other in
        opposite orders. The gang's history gets a journal-only GAINED event
        about the asset: it holds the asset and never owns it, so there is
        no ledger entry, no price and nothing for the books to fold. An
        asset another gang holds is refused in words, and one this gang
        already holds is assigned nothing twice.
        """
        from n26.core.operations import Refusal, operation

        if membership.campaign_id != self.campaign.pk or not membership.playing:
            raise ValueError(f"{membership} is not playing {self.campaign}.")
        campaign_asset = _asset_under_the_lock(campaign_asset)
        if campaign_asset is None:
            return None
        if campaign_asset.campaign_id != self.campaign.pk:
            raise ValueError(
                f"{campaign_asset} is not one of {self.campaign}'s assets."
            )
        if campaign_asset.held:
            if campaign_asset.holder_id == membership.pk:
                return campaign_asset
            raise Refusal(
                f"{campaign_asset} is held by {campaign_asset.holder.gang.name}. "
                "Unassign it from them first."
            )
        campaign_asset.holder = membership
        campaign_asset.save(update_fields=["holder", "modified"])
        with operation(membership.gang, actor=self.actor) as op:
            op.event(campaign_asset, LedgerEvent.Kind.GAINED, note=str(campaign_asset))
        return campaign_asset

    def unassign(self, campaign_asset, by_holder=None):
        """Take an asset back from the gang holding it, so nobody holds it.

        The same two lines in the same order as assigning, and the matching
        record on the gang — a journal-only LOST event. An asset nobody
        holds is left as it is, and the caller gets None back: nothing
        happened, so nothing is written.

        ``by_holder`` is the membership the caller was allowed to act for.
        The holding gang's owner may hand an asset back, and the page that
        let them read the holder before this line was taken; if another
        gang holds it by now, the act is refused in words rather than done
        to that gang's asset. The arbitrator passes nothing.
        """
        from n26.core.operations import operation

        campaign_asset = _asset_under_the_lock(campaign_asset)
        if campaign_asset is None or not campaign_asset.held:
            return None
        _still_held_by(campaign_asset, by_holder)
        holder = campaign_asset.holder
        campaign_asset.holder = None
        campaign_asset.save(update_fields=["holder", "modified"])
        with operation(holder.gang, actor=self.actor) as op:
            op.event(campaign_asset, LedgerEvent.Kind.LOST, note=str(campaign_asset))
        return campaign_asset

    def transfer(self, campaign_asset, membership, by_holder=None):
        """Hand a held asset from the gang holding it to another gang
        playing this campaign.

        One change to the asset under the campaign's line, then a record on
        each gang inside it — LOST on the one it left, GAINED on the one it
        went to — in the order the gangs are named, so both histories say
        what happened and neither says it twice. The two records share one
        mark, which is how the campaign's log reads them as one act.

        An asset nobody holds cannot be handed over: assigning is the act
        for that. An asset already held by the receiving gang is refused
        too, in words, since nothing would change hands.
        """
        from n26.core.operations import Refusal, operation

        if membership.campaign_id != self.campaign.pk or not membership.playing:
            raise ValueError(f"{membership} is not playing {self.campaign}.")
        campaign_asset = _asset_under_the_lock(campaign_asset)
        if campaign_asset is None:
            return None
        if campaign_asset.campaign_id != self.campaign.pk:
            raise ValueError(
                f"{campaign_asset} is not one of {self.campaign}'s assets."
            )
        if not campaign_asset.held:
            raise Refusal(
                f"{campaign_asset} is not held by any gang, so it cannot be "
                "handed over. Assign it instead."
            )
        if campaign_asset.holder_id == membership.pk:
            raise Refusal(f"{membership.gang.name} already holds {campaign_asset}.")
        _still_held_by(campaign_asset, by_holder)
        loser = campaign_asset.holder
        campaign_asset.holder = membership
        campaign_asset.save(update_fields=["holder", "modified"])
        mark = uuid4()
        with operation(loser.gang, actor=self.actor, batch=mark) as op:
            op.event(campaign_asset, LedgerEvent.Kind.LOST, note=str(campaign_asset))
        with operation(membership.gang, actor=self.actor, batch=mark) as op:
            op.event(campaign_asset, LedgerEvent.Kind.GAINED, note=str(campaign_asset))
        return campaign_asset

    # --- What the arbitrator adds ------------------------------------------
    #
    # Everything below writes library content into the campaign's own pack
    # and onto its additions type, so it reaches member gangs by the path a
    # gang type's built-ins take. Nothing here touches the shared type.

    def add_asset_type(self, label_singular, ownership, label_plural=""):
        """Declare a new asset type for this campaign alone.

        The asset type lands on the additions type, in the campaign's pack.
        A label the campaign already uses — on the shared type or on its own
        additions — is refused in words, because the page would print two
        headings that read the same.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import add_asset_type
        from n26.library.models import AssetType

        label_singular = (label_singular or "").strip()
        taken = AssetType.objects.filter(
            campaign_type_id__in=(
                self.campaign.campaign_type_id,
                self.campaign.additions_id,
            ),
            label_singular__iexact=label_singular,
        ).exists()
        if taken:
            raise Refusal(
                f"{self.campaign.name} already has an asset type called "
                f"{label_singular}."
            )
        asset_type = add_asset_type(
            self.campaign.additions,
            label_singular,
            ownership,
            label_plural=(label_plural or "").strip(),
            pack=self.campaign.pack,
        )
        self.event(CampaignEvent.Kind.ASSET_TYPE_ADDED, note=asset_type.label_singular)
        return asset_type

    def create_asset(self, asset_type, name, annotation="", income=0):
        """Write a new asset under one of this campaign's asset types.

        The asset type may be the shared type's or the campaign's own: a
        campaign's own Territory is as much a Territory as the book's. The
        asset lands in the campaign's pack whichever asset type it is under,
        so it never reaches another campaign; a system asset type pointing
        at nothing of the arbitrator's is what keeps that direction clean.
        What holding the asset does is not written here beyond its income,
        which lands as the asset's Income contribution: it has a name, its
        words and that figure, and nothing else.

        An asset of a Possession asset type is every gang's own, so it is
        built into the campaign's additions type as it is made, no matter
        which campaign type its asset type belongs to, because the
        additions type is the only campaign type in the campaign's pack.
        It arrives on every gang that joins from now on; gangs already
        playing are given it by the propagation pass that every built-in
        edit files, marked as caught up.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import create_asset
        from n26.library.models import Asset

        if asset_type.campaign_type_id not in (
            self.campaign.campaign_type_id,
            self.campaign.additions_id,
        ):
            raise ValueError(
                f"{asset_type} is an asset type of {asset_type.campaign_type}, "
                "not of this campaign's type or the campaign's own."
            )
        name = (name or "").strip()
        if Asset.objects.filter(pack=self.campaign.pack, name__iexact=name).exists():
            raise Refusal(f"{self.campaign.name} already has an asset called {name}.")
        asset = create_asset(
            name,
            asset_type,
            annotation=(annotation or "").strip(),
            income=income or 0,
            pack=self.campaign.pack,
            given_by=self.campaign.additions,
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

    def open_table(self, table):
        """Let every gang in the campaign roll on an asset table, by
        building it into the campaign's additions.

        The table is one of a system pack's or the campaign's own, of an
        asset type the campaign deals in. The member lands on the
        additions type's built-ins, so gangs joining from now on hold the
        table as they join and gangs already playing are given it by the
        propagation pass every built-in edit files. A member closing took
        out is revived rather than replaced, for the reason a possession's
        is: every copy already on a gang names it as its provenance. A
        table the campaign's own type already gives, or one already open,
        changes nothing and says nothing.
        """
        from n26.core.operations import Refusal
        from n26.core.propagation import file_propagation_task
        from n26.library.authoring import add_built_in
        from n26.library.models import DefaultAssignment

        if table.asset_type.campaign_type_id not in (
            self.campaign.campaign_type_id,
            self.campaign.additions_id,
        ):
            raise Refusal(
                f"You cannot open {table} here. It lists "
                f"{table.asset_type.plural}, which {self.campaign.name} does "
                "not deal in."
            )
        if tables_in_play(self.campaign).filter(pk=table.pk).exists():
            return None
        members = DefaultAssignment.objects.filter(
            default_set_id=self.campaign.additions.built_ins_id, asset_table=table
        )
        closed = list(members.filter(archived=True))
        if closed:
            for member in closed:
                member.unarchive()
                file_propagation_task(member.default_set)
            member = closed[0]
        else:
            member = add_built_in(
                self.campaign.additions, table, pack=self.campaign.pack
            )
        self.event(CampaignEvent.Kind.TABLE_OPENED, note=str(table))
        return member

    def close_table(self, table):
        """Stop every gang in the campaign rolling on a table the
        arbitrator opened.

        The additions' member is taken out the way any built-in is —
        archived where a gang was given the table through it, deleted
        where none was. Nothing is taken back: a gang that holds the
        table keeps it, and a territory already rolled on it stays. A
        table the campaign's type gives is not the arbitrator's to close,
        and one not open changes nothing.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import remove_default_member
        from n26.library.models import DefaultAssignment

        if DefaultAssignment.objects.filter(
            default_set_id=self.campaign.campaign_type.built_ins_id,
            asset_table=table,
            archived=False,
        ).exists():
            raise Refusal(
                f"You cannot close {table}. {self.campaign.campaign_type} gives "
                "it to every gang."
            )
        members = list(
            DefaultAssignment.objects.filter(
                default_set_id=self.campaign.additions.built_ins_id,
                asset_table=table,
                archived=False,
            )
        )
        if not members:
            return None
        for member in members:
            remove_default_member(member)
        self.event(CampaignEvent.Kind.TABLE_CLOSED, note=str(table))
        return members[0]

    def create_table(self, asset_type, name, dice=""):
        """Write a new asset table for this campaign alone.

        The table lands in the campaign's pack under one of the Holding
        asset types the campaign deals in, and is built into the
        campaign's additions as it is made, so every gang at the table
        holds it: a table an arbitrator writes is one they mean to roll
        on. ``dice`` names the die; blank makes an ordered list. Entries
        are added afterwards with :meth:`add_table_entry`. A name the
        campaign's pack already uses is refused in words.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import create_asset_table
        from n26.library.models import AssetTable

        if asset_type.campaign_type_id not in (
            self.campaign.campaign_type_id,
            self.campaign.additions_id,
        ):
            raise ValueError(
                f"{asset_type} is an asset type of {asset_type.campaign_type}, "
                "not of this campaign's type or the campaign's own."
            )
        if not asset_type.is_holding:
            raise Refusal(
                f"You cannot make a table of {asset_type.plural}. Every gang has "
                "its own, so there is nothing to roll for."
            )
        name = (name or "").strip()
        if AssetTable.objects.filter(
            pack=self.campaign.pack, name__iexact=name
        ).exists():
            raise Refusal(f"{self.campaign.name} already has a table called {name}.")
        table = create_asset_table(
            name,
            asset_type,
            dice=dice or "",
            pack=self.campaign.pack,
            given_by=self.campaign.additions,
        )
        self.event(CampaignEvent.Kind.TABLE_CREATED, note=str(table))
        return table

    def add_table_entry(self, table, asset, roll_low=None, roll_high=None):
        """One more asset on one of the campaign's own tables.

        Only a table in the campaign's pack: a system table is the
        book's, and an arbitrator narrows it by writing their own. The
        asset is one the campaign may add by hand (the catalogue reads
        the same rule), and on a rolled table the band says which rolls
        land here. What an entry is not allowed to be — another type's
        asset, a band on an unrolled table, one running downwards — the
        authoring verb refuses, and the words reach the form.
        """
        from n26.library.authoring import add_asset_table_entry

        _own_table(self.campaign, table)
        return add_asset_table_entry(
            table, asset, roll_low=roll_low, roll_high=roll_high
        )

    def remove_table_entry(self, entry):
        """Take one asset off one of the campaign's own tables. What was
        already rolled stays in the campaign."""
        from n26.library.authoring import remove_asset_table_entry

        _own_table(self.campaign, entry.table)
        remove_asset_table_entry(entry)

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


@dataclass(frozen=True)
class AssetRoll:
    """What one roll on an asset table came to: the number, the die, the
    table, and the campaign asset it added."""

    roll: int
    dice: object
    table: object
    campaign_asset: object


def _table_named(table):
    """A table as a sentence names it: "the Territory Selection Table",
    but "Goliath Territories". The article follows the name's own last
    word, since the name is the author's."""
    name = str(table)
    return f"the {name}" if name.lower().endswith("table") else name


def _own_table(campaign, table):
    """Refuse a write to a table that is not this campaign's own. A
    system table is the book's; only what the arbitrator wrote into the
    campaign's pack is theirs to change."""
    if table.pack_id != campaign.pack_id:
        raise ValueError(f"{table} is not one of {campaign}'s own tables.")


def tables_in_play(campaign):
    """The asset tables the campaign itself holds, and so generates its
    pool from: the live built-in members of its type and of its
    additions that name a table. One query."""
    from n26.library.models import AssetTable, CampaignType, DefaultAssignment

    # The two types' built-in sets are read by query rather than off the
    # instances in hand: opening a table may have founded the additions'
    # set a moment ago, on a copy of the type the caller never saw.
    sets = CampaignType.objects.filter(
        pk__in=(campaign.campaign_type_id, campaign.additions_id),
        built_ins__isnull=False,
    ).values("built_ins_id")
    members = DefaultAssignment.objects.filter(
        default_set_id__in=sets, archived=False, asset_table__isnull=False
    )
    return AssetTable.objects.filter(pk__in=members.values("asset_table_id"))


def tables_on(card, computed, withdrawn=frozenset()):
    """The asset tables a gang may roll on, read off its card: the stored
    assignments naming one and the tables a grant dealt onto it, each
    once, in the order they stand. Query-free, so a page that has the
    cards in hand asks this for every gang without another query.

    ``withdrawn`` is what :func:`withdrawn_members` returns for these
    cards. A copy given through a built-in member the arbitrator has
    since closed stays on the gang — nothing is taken back — but the
    offer is withdrawn, so it is not a table the gang may roll on.
    """
    from n26.library.models import AssetTable

    held = {}
    for node in card.all_nodes():
        if not isinstance(node.assignable, AssetTable) or node.suppressed:
            continue
        given_by = getattr(node.assignment, "materialised_from_id", None)
        if given_by is not None and given_by in withdrawn:
            continue
        held.setdefault(node.assignable.pk, node.assignable)
    for contribution in computed.tables:
        held.setdefault(contribution.thing.pk, contribution.thing)
    return list(held.values())


def withdrawn_members(*cards):
    """The built-in members, since archived, that table copies on these
    cards came from. One query for however many cards, and none where no
    card holds a table by a member."""
    from n26.library.models import AssetTable, DefaultAssignment

    given_by = {
        node.assignment.materialised_from_id
        for card in cards
        for node in card.all_nodes()
        if isinstance(node.assignable, AssetTable)
        and node.assignment is not None
        and node.assignment.materialised_from_id is not None
    }
    if not given_by:
        return frozenset()
    return frozenset(
        DefaultAssignment.objects.filter(pk__in=given_by, archived=True).values_list(
            "pk", flat=True
        )
    )


def tables_held_by(gang):
    """The asset tables one gang may roll on — its starting territory's
    tables. Builds the gang's card and computes it, so this is for an act
    on one gang; a page listing several reads ``tables_on`` off cards it
    already has."""
    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute

    card = build_gang_card(gang, with_statlines=False)
    computed = compute(card, build_modifier_index(carriers(card)))
    return tables_on(card, computed, withdrawn_members(card))


def _still_held_by(campaign_asset, membership_id):
    """Refuse in words where the asset has left the gang the caller was
    acting for since they read the page. ``None`` asks nothing: the
    arbitrator may move any held asset whoever holds it now."""
    from n26.core.operations import Refusal

    if membership_id is not None and campaign_asset.holder_id != membership_id:
        raise Refusal(
            f"{campaign_asset} is now held by {campaign_asset.holder.gang.name}, "
            "so you cannot hand it over."
        )


def _asset_under_the_lock(campaign_asset):
    """The campaign asset as it stands now that the campaign's line is held,
    or None where it has gone.

    Whoever clicked read the page before this transaction began, and two
    clicks on one button arrive together often enough. Every writer to a
    campaign asset holds its campaign's line first, so a row read under
    that line is the row as it is; the holder rides along because every
    decision here asks who has it.
    """
    return (
        CampaignAsset.objects.select_related("holder__gang", "asset__asset_type")
        .filter(pk=campaign_asset.pk)
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
    assigning an asset while the gang's owner is buying something would
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
    sentence composed from several rows — an asset type's label and its
    ownership, a built-in member and its opening value, a modifier's scope
    and effect — and the words belong with the facts they are made from.

    ``kinds`` is one sentence per asset type, in the type's own order.
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

    Reads the type's asset types, its built-in members and its modifiers, each
    once. Three or four queries per type; the screen offers a handful.
    """
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS
    from n26.library.prose import GANG, sentence_for
    from n26.library.references import reading_sentences

    kinds = tuple(
        _asset_type_sentence(asset_type)
        for asset_type in campaign_type.asset_types.all()
    )
    # A table is drawn nowhere, the founding page included: it is how a
    # gang comes to roll, not something the gang starts with.
    members = (
        campaign_type.built_in_members.filter(asset_table__isnull=True)
        .select_related(*DEFAULT_ASSIGNABLE_FIELDS)
        .order_by("position")
    )
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


def _asset_type_sentence(asset_type):
    """How assets of one type behave, in one sentence: "one" rather than
    an article, so the label needs no a/an."""
    if asset_type.is_holding:
        return f"One gang holds each {asset_type.label_singular} at a time."
    return f"Every gang has its own {asset_type.label_singular}."


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
