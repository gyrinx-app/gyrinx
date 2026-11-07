"""Write campaign changes and their append-only campaign events.

Gang changes belong to gang ledgers through ``n26.core.operations``.
Campaign-only changes are recorded here. The campaign history combines
both sources without duplicating the events.

Each operation locks and reloads the campaign before deciding changes.
Campaign metadata moves no credits and needs no settlement step.

Use it as a context manager::

    with campaign_operation(campaign, actor=arbitrator) as act:
        act.rename("Dust Falls II")
        act.set_budget(1200)

Founding accepts an unsaved campaign and creates its pack and additions
type before saving the campaign::

    campaign = Campaign(name="Dust Falls", owner=arbitrator)
    with campaign_operation(campaign, actor=arbitrator) as act:
        act.found(territory_campaign)
"""

from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from n26.core.models import Campaign, CampaignAsset, CampaignEvent, LedgerEvent

#: What the log stores for a budget that is not set. The reader matches on it
#: to say "no ceiling" in words, so the two must be the same string.
NO_CEILING = "unlimited"


#: Left as it is: what ``edit_battle`` takes for a stake it is not given.
KEEP = object()

#: Marks the note on the removal a gang is written when the arbitrator
#: archives a counter: the value the counter stood at, which the gang's
#: history prints as "(was 4)". A marker rather than a bare figure, so the
#: history never mistakes a player's reason for a value.
ARCHIVED_COUNTER_NOTE_PREFIX = "archived-counter:v1:"


def _now():
    return timezone.now()


def budget_word(credits):
    """A gang budget as the log stores it: a figure, or no ceiling at all."""
    return NO_CEILING if credits is None else str(credits)


class CampaignOperation:
    """Write one campaign's changes and corresponding log entries."""

    def __init__(self, campaign, actor=None):
        self.campaign = campaign
        self.actor = actor
        #: Every event this operation writes carries the same mark, so what
        #: was written together stays recognisable as one submit.
        self.batch = uuid4()

    def event(self, kind, note="", battle=None, about_user=None, roll=None):
        """Append to the log. Nothing already written is ever altered."""
        return CampaignEvent.objects.create(
            campaign=self.campaign,
            kind=kind,
            actor=self.actor,
            battle=battle,
            about_user=about_user,
            roll=roll,
            note=note[: CampaignEvent.NOTE_LENGTH],
            batch=self.batch,
        )

    def created(self):
        """Record that the campaign was set up. Its first line."""
        return self.event(CampaignEvent.Kind.CREATED)

    def found(self, campaign_type):
        """Create the campaign with its shared type, owned pack and additions type.

        Name the pack and additions after the campaign. Key the pack slug by
        campaign ID so duplicate names cannot collide. Record the founding type
        in the first event. Member gangs receive the two types when they join.
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
        """Rename the campaign and record its old and new names."""
        campaign = self.campaign
        was = campaign.name
        if was == name:
            return campaign
        campaign.name = name
        campaign.save(update_fields=["name", "modified"])
        self.event(CampaignEvent.Kind.RENAMED, note=f"{was} → {name}")
        return campaign

    def set_status(self, status):
        """Change the campaign's status without changing its gangs or credits."""
        from n26.core.operations import Refusal

        if status not in Campaign.Status.values:
            raise Refusal("Select a campaign status.")
        campaign = self.campaign
        if campaign.status == status:
            return campaign
        was = campaign.get_status_display()
        campaign.status = status
        campaign.save(update_fields=["status", "modified"])
        self.event(
            CampaignEvent.Kind.STATUS_CHANGED,
            note=f"{was} → {campaign.get_status_display()}",
        )
        return campaign

    def set_gang_grouping(self, grouping, colours):
        """Set the campaign's default label grouping and its group colours."""
        from n26.core.campaign_table import label_options
        from n26.core.colours import GANG_COLOURS
        from n26.core.operations import Refusal
        from n26.core.render import _arbitrators_additions

        _, slots = _arbitrators_additions(self.campaign)
        available = {str(slot.pk): slot for slot in slots}
        if grouping and grouping not in available:
            raise Refusal("Select a label from this campaign.")
        options = label_options(self.campaign, slots)
        for slot_id, values in colours.items():
            if slot_id not in available:
                raise Refusal("Select a label from this campaign.")
            allowed = {option["id"] for option in options[slot_id]}
            if any(
                option_id not in allowed or colour not in GANG_COLOURS
                for option_id, colour in values.items()
            ):
                raise Refusal("Choose one of the colours shown.")
        if (
            str(self.campaign.gang_grouping_id or "") == grouping
            and self.campaign.group_colours == colours
        ):
            return None
        self.campaign.gang_grouping = available.get(grouping)
        self.campaign.group_colours = colours
        self.campaign.save(update_fields=["gang_grouping", "group_colours", "modified"])
        self.event(CampaignEvent.Kind.GROUPING_CHANGED)
        return self.campaign

    def set_budget(self, credits):
        """Set the starting credit budget for future gangs founded in this campaign.

        ``credits=None`` means unlimited. Existing gangs and their balances are unchanged.
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
        """Save the campaign summary and journal the change without copying its prose.

        An unchanged value produces neither a save nor an event.
        """
        campaign = self.campaign
        if campaign.summary == summary:
            return campaign
        campaign.summary = summary
        campaign.save(update_fields=["summary", "modified"])
        self.event(CampaignEvent.Kind.SUMMARY_EDITED)
        return campaign

    def set_starting_from_pool(self, enabled):
        """Choose where future starting territories come from; leave completed ones alone."""
        campaign = self.campaign
        if campaign.starting_from_pool == enabled:
            return campaign
        campaign.starting_from_pool = enabled
        campaign.save(update_fields=["starting_from_pool", "modified"])
        self.event(
            CampaignEvent.Kind.STARTING_MODE_SET,
            note="From the unclaimed pool" if enabled else "Additional territories",
        )
        return campaign

    def invite(self, user, message=""):
        """Invite a person, retaining one invitation record per campaign and person.

        Reinvite declined players through that record; accepted invitations remain
        unchanged. Record the event independently of delivering the notification.
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
        """Record the invitation's first answer and notify the arbitrator.

        Repeated submissions for an answered invitation make no change.
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

    def remove_player(self, player, *, with_gangs=False):
        """Remove a player and optionally their gangs, retaining the history.

        Delete the invitation record so removal is distinct from declining.
        ``with_gangs`` removes their gangs through remove_gang and returns them.
        Return None if the player is already absent.
        """
        from n26.core.models import CampaignParticipant

        player = (
            CampaignParticipant.objects.select_related("user")
            .filter(pk=player.pk, campaign=self.campaign)
            .first()
        )
        if player is None:
            return None
        user = player.user
        gangs = self._remove_gangs_of(user) if with_gangs else []
        player.delete()
        self.event(CampaignEvent.Kind.PLAYER_REMOVED, about_user=user)
        return gangs

    def leave(self):
        """Remove the actor's accepted player membership and all their gangs.

        Return removed gangs, or None when the actor is absent or is the arbitrator.
        """
        from n26.core.models import CampaignParticipant

        player = CampaignParticipant.objects.filter(
            campaign=self.campaign,
            user=self.actor,
            state=CampaignParticipant.State.ACCEPTED,
        ).first()
        if player is None:
            return None
        gangs = self._remove_gangs_of(self.actor)
        player.delete()
        self.event(CampaignEvent.Kind.PLAYER_LEFT, about_user=self.actor)
        return gangs

    def _remove_gangs_of(self, user):
        """Take every gang this person owns out of the campaign, in key
        order, and return them."""
        removed = []
        # Each gang's line stays held until the transaction commits, so they
        # are taken in key order, the order every multi-gang operation uses.
        for membership in (
            self.campaign.memberships.filter(left__isnull=True, gang__owner=user)
            .select_related("gang")
            .order_by("gang_id")
        ):
            if self.remove_gang(membership) is not None:
                removed.append(membership.gang)
        return removed

    def _battle_details(self, *, scenario, result, gangs, winners, battle=None):
        """Validate shared metadata without changing any gang."""
        from django.core.exceptions import ValidationError

        from n26.core.models import Battle, CampaignMembership
        from n26.core.operations import Refusal

        gangs, winners = list(gangs), list(winners)
        scenario = scenario.strip()
        if not scenario or len(scenario) > 200:
            raise Refusal("Enter a scenario name of up to 200 characters.")
        allowed = set(
            CampaignMembership.objects.filter(
                campaign=self.campaign, left__isnull=True
            ).values_list("gang_id", flat=True)
        )
        if battle is not None:
            allowed.update(battle.gangs.values_list("pk", flat=True))
        if {gang.pk for gang in gangs} - allowed:
            raise Refusal("Select gangs from this campaign.")
        try:
            Battle.validate_outcome(result=result, gangs=gangs, winners=winners)
        except ValidationError as exc:
            raise Refusal(" ".join(exc.messages)) from exc
        return scenario, gangs, winners

    def record_battle(
        self,
        date,
        gangs=(),
        *,
        scenario,
        result="not_recorded",
        winners=(),
        scenario_rolls=None,
    ):
        """Record a battle without applying rewards or changing any gang.

        ``scenario_rolls`` is what each scenario generator table landed on,
        as ``{key: roll}``. A table left out is not named; a roll that is not
        on its table refuses the battle rather than dropping that part.
        """
        from n26.core.models import Battle
        from n26.core.operations import Refusal
        from n26.core.scenarios import parse, rolls_of

        self._require_recorder()
        scenario = (
            scenario or ""
        ).strip() or f"Battle #{self.campaign.battles.count() + 1}"
        scenario_found, wrong = parse(scenario_rolls or {})
        if wrong:
            raise Refusal(
                "A scenario component is not on its table. Generate the scenario again."
            )
        scenario, gangs, winners = self._battle_details(
            scenario=scenario, result=result, gangs=gangs, winners=winners
        )
        battle = Battle.objects.create(
            campaign=self.campaign,
            date=date,
            scenario=scenario,
            result=result,
            scenario_rolls=rolls_of(scenario_found),
        )
        battle.gangs.set(gangs)
        battle.winners.set(winners)
        self.event(
            CampaignEvent.Kind.BATTLE_RECORDED,
            battle=battle,
            note=f"{scenario} on {date.isoformat()}",
        )
        return battle

    def _require_recorder(self):
        from n26.core.campaign_permissions import may_record_campaign
        from n26.core.operations import Refusal

        if not may_record_campaign(self.campaign, self.actor):
            raise Refusal(
                "Only the arbitrator and accepted players can record battles and dice rolls."
            )

    def record_roll(
        self,
        *,
        request_key,
        reason,
        dice,
        source,
        modifier=0,
        count=1,
        modifier_application="total",
        rolled=None,
        gang=None,
        miniature=None,
        battle=None,
        rng=None,
    ):
        """Save one result per submission, including when a POST is retried.

        The campaign lock serialises recording with player removal. Check
        the key before generating, so a retry never rerolls.
        """
        from uuid import UUID

        from n26.core.models import Battle, CampaignMembership, CampaignRoll, Miniature
        from n26.core.operations import Refusal
        from n26.library.models import Dice

        self._require_recorder()
        try:
            request_key = UUID(str(request_key))
        except ValueError, TypeError, AttributeError:
            raise Refusal("Reload the page before recording this roll.") from None
        prior = CampaignRoll.objects.filter(
            campaign=self.campaign, request_key=request_key
        ).first()
        if prior is not None:
            if prior.actor_id != self.actor.pk:
                raise Refusal("Reload the page before recording this roll.")
            return prior
        reason = reason.strip()
        if not reason or len(reason) > 200:
            raise Refusal("Enter a reason of up to 200 characters.")
        if dice not in CampaignRoll.Dice.values:
            raise Refusal("Select D3, D6 or D66.")
        if type(count) is not int or not 1 <= count <= CampaignRoll.MAX_DICE:
            raise Refusal(f"Enter a number of dice from 1 to {CampaignRoll.MAX_DICE}.")
        if modifier_application not in CampaignRoll.ModifierApplication.values:
            raise Refusal(
                "Select whether the modifier applies to each die or the total."
            )
        if source not in CampaignRoll.Source.values:
            raise Refusal("Select how to roll the dice.")
        if type(modifier) is not int or not -2147483648 <= modifier <= 2147483647:
            raise Refusal(
                "Enter a whole-number modifier between −2147483648 and 2147483647."
            )
        if (
            gang is not None
            and not CampaignMembership.objects.filter(
                campaign=self.campaign,
                gang=gang,
                left__isnull=True,
                gang__archived=False,
            ).exists()
        ):
            raise Refusal("Select a gang currently in this campaign.")
        if miniature is not None:
            if gang is None:
                raise Refusal("Select a related gang before selecting a model.")
            miniature = (
                Miniature.objects.select_for_update()
                .filter(
                    pk=miniature.pk, membership__gang=gang, membership__archived=False
                )
                .first()
            )
            if miniature is None:
                raise Refusal("Select a model currently in the related gang.")
        if (
            battle is not None
            and not Battle.objects.filter(
                pk=battle.pk, campaign=self.campaign, archived=False
            ).exists()
        ):
            raise Refusal("Select a battle from this campaign.")
        results = []
        if source == CampaignRoll.Source.MANUAL:
            if not CampaignRoll.valid_total(dice, count, rolled):
                raise Refusal("Enter a valid result for the selected dice.")
        else:
            if rolled is not None:
                raise Refusal("Leave the result blank to generate a roll.")
            results = [Dice.roll(dice, rng=rng) for _ in range(count)]
            rolled = sum(results)
        roll = CampaignRoll.objects.create(
            campaign=self.campaign,
            actor=self.actor,
            request_key=request_key,
            reason=reason,
            dice=dice,
            source=source,
            rolled=rolled,
            modifier=modifier,
            count=count,
            results=results,
            modifier_application=modifier_application,
            gang=gang,
            miniature=miniature,
            battle=battle,
        )
        self.event(CampaignEvent.Kind.DICE_ROLLED, roll=roll, battle=battle)
        return roll

    def note_roll(self, roll, outcome):
        """Update the recorder's note, preserving previous notes in the log."""
        from n26.core.models import CampaignRoll
        from n26.core.operations import Refusal

        self._require_recorder()
        roll = (
            CampaignRoll.objects.select_related("battle")
            .filter(pk=roll.pk, campaign=self.campaign, actor=self.actor)
            .first()
        )
        if roll is None:
            raise Refusal("You can only add notes to your own dice rolls.")
        if roll.battle_id and roll.battle.archived:
            raise Refusal(
                "This battle is archived. Restore it before changing its rolls."
            )
        outcome = outcome.strip()
        if len(outcome) > CampaignEvent.NOTE_LENGTH:
            raise Refusal("Enter an outcome note of up to 512 characters.")
        if roll.outcome == outcome:
            return roll
        roll.outcome = outcome
        roll.save(update_fields=["outcome", "modified"])
        self.event(
            CampaignEvent.Kind.DICE_ROLL_NOTED,
            roll=roll,
            battle=roll.battle,
            note=outcome,
        )
        return roll

    def save_scenario(self, rolls, *, name):
        """Save a named generated scenario and its table rolls for the arbitrator.

        ``rolls`` maps table keys to rolls. Use battle scenario name validation
        and battle-recording permissions, recording one event for the scenario.
        """
        from n26.core.operations import Refusal
        from n26.core.scenarios import history_note, parse, rolls_of

        self._require_recorder()
        name = (name or "").strip()
        if not name or len(name) > 200:
            raise Refusal("Enter a scenario name of up to 200 characters.")
        found, wrong = parse(rolls)
        if wrong:
            raise Refusal(
                "A scenario component is not on its table. Generate the scenario again."
            )
        if not found:
            raise Refusal("There is no scenario to save. Generate one first.")
        return self.event(
            CampaignEvent.Kind.SCENARIO_SAVED,
            note=history_note(rolls_of(found), name),
        )

    def connect_scenario(self, battle, rolls, *, revision):
        """Attach generated components without changing the battle's name or outcome."""
        from n26.core.operations import Refusal
        from n26.core.scenarios import parse, rolls_of

        self._require_recorder()
        if self.actor.pk != self.campaign.owner_id:
            raise Refusal("Only the arbitrator can connect a scenario to a battle.")
        battle = self._locked_battle(battle)
        if battle.revision != revision:
            raise Refusal("This battle changed. Reload it before saving your changes.")
        found, wrong = parse(rolls)
        if wrong or not found:
            raise Refusal("Generate a valid scenario before connecting it to a battle.")
        rolls = rolls_of(found)
        if battle.scenario_rolls == rolls:
            return battle
        battle.scenario_rolls = rolls
        battle.revision += 1
        battle.save(update_fields=["scenario_rolls", "revision", "modified"])
        self.event(
            CampaignEvent.Kind.BATTLE_EDITED,
            battle=battle,
            note=f"{battle.title} on {battle.date.isoformat()}",
        )
        return battle

    def edit_battle(
        self,
        battle,
        *,
        scenario,
        date,
        gangs,
        result,
        winners,
        revision,
        stake=KEEP,
        stake_awarded_to=KEEP,
        stake_revision=None,
    ):
        """Amend the battle record, retaining its gang history.

        ``stake`` and ``stake_awarded_to`` are left as they are unless
        given. See ``_settle_stake`` for what changing them moves.
        """
        from n26.core.operations import Refusal

        battle = self._locked_battle(battle)
        if battle.revision != revision:
            raise Refusal("This battle changed. Reload it before saving your changes.")
        scenario, gangs, winners = self._battle_details(
            scenario=scenario,
            result=result,
            gangs=gangs,
            winners=winners,
            battle=battle,
        )
        gang_ids = {gang.pk for gang in gangs}
        previous_gangs = set(battle.gangs.values_list("pk", flat=True))
        removed_ids = previous_gangs - gang_ids
        if (
            battle.gang_events.filter(gang_id__in=removed_ids).exists()
            or battle.reports.filter(gang_id__in=removed_ids).exists()
            or battle.crews.filter(gang_id__in=removed_ids).exists()
        ):
            raise Refusal(
                "You cannot remove a participant with recorded battle history, a saved crew or a post-battle report."
            )
        if stake is KEEP:
            stake = battle.stake
        if stake_awarded_to is KEEP:
            stake_awarded_to = battle.stake_awarded_to
        stake, stake_awarded_to = self._stake_details(
            battle,
            stake=stake,
            awarded_to=stake_awarded_to,
            gang_ids=gang_ids,
            expected_revision=stake_revision,
        )
        stake_changed = (
            getattr(stake, "pk", None),
            getattr(stake_awarded_to, "pk", None),
        ) != (battle.stake_id, battle.stake_awarded_to_id)
        before = (battle.scenario, battle.date, battle.result)
        if (
            before == (scenario, date, result)
            and previous_gangs == gang_ids
            and set(battle.winners.values_list("pk", flat=True))
            == {gang.pk for gang in winners}
            and not stake_changed
        ):
            return battle
        if stake_changed:
            self._settle_stake(battle, stake, stake_awarded_to, gang_ids)
        battle.scenario, battle.date, battle.result = scenario, date, result
        battle.revision += 1
        battle.save(
            update_fields=[
                "scenario",
                "date",
                "result",
                "revision",
                "stake",
                "stake_awarded_to",
                "stake_transfer_mark",
                "modified",
            ]
        )
        battle.gangs.set(gangs)
        battle.winners.set(winners)
        self.event(
            CampaignEvent.Kind.BATTLE_EDITED,
            battle=battle,
            note=f"{scenario} on {date.isoformat()}",
        )
        return battle

    def record_outcome(self, battle, *, result, winners, revision):
        """Record the first outcome, preserving the battle's metadata and stake."""
        from django.core.exceptions import ValidationError

        from n26.core.campaign_permissions import may_record_outcome
        from n26.core.models import Battle
        from n26.core.operations import Refusal

        battle = self._locked_battle(battle)
        if not may_record_outcome(battle, self.actor):
            raise Refusal(
                "The outcome is already recorded, or this battle is not yours "
                "to record. Ask the arbitrator to change it."
            )
        if result == Battle.Result.NOT_RECORDED:
            raise Refusal("Select an outcome.")
        if battle.revision != revision:
            raise Refusal("This battle changed. Reload it before saving your changes.")
        winners = list(winners)
        try:
            Battle.validate_outcome(
                result=result, gangs=battle.gangs.all(), winners=winners
            )
        except ValidationError as exc:
            raise Refusal(" ".join(exc.messages)) from exc
        battle.result = result
        battle.revision += 1
        battle.save(update_fields=["result", "revision", "modified"])
        battle.winners.set(winners)
        self.event(
            CampaignEvent.Kind.BATTLE_EDITED,
            battle=battle,
            note=f"{battle.title} on {battle.date.isoformat()}",
        )
        return battle

    def _stake_details(
        self, battle, *, stake, awarded_to, gang_ids, expected_revision=None
    ):
        """Validate the current battle stake and recipient under the campaign lock.

        A new stake must be unclaimed or held by a participant. Its recipient
        must be a participant.
        """
        from n26.core.operations import Refusal

        if stake is None:
            if awarded_to is not None:
                raise Refusal(
                    "Select what was staked before selecting which gang it goes to."
                )
            return None, None
        stake = _asset_under_the_lock(stake)
        if stake is None or stake.campaign_id != self.campaign.pk:
            raise Refusal("Select an asset from this campaign.")
        if (
            expected_revision is not None
            and stake.ownership_revision != expected_revision
        ):
            raise Refusal("This stake changed hands. Reload the battle before saving.")
        if (
            stake.pk != battle.stake_id
            and stake.held
            and stake.holder.gang_id not in gang_ids
        ):
            noun = a_stake(stake.asset.asset_type.label_singular)
            raise Refusal(
                f"No participant holds {stake}. Select {noun} that is unclaimed or held by a participant."
            )
        if awarded_to is not None and awarded_to.pk not in gang_ids:
            raise Refusal(f"Select a participant to give {stake} to.")
        return stake, awarded_to

    def _settle_stake(self, battle, stake, awarded_to, gang_ids):
        """Apply a battle's asset transfer idempotently.

        Reverse an earlier transfer only while its recipient still holds the
        asset. Transfer to the new recipient only if needed, and retain the
        transfer mark so repeated saves cannot repeat it.
        """
        from n26.core.operations import Refusal, _hold

        # A correction retains its reversal locks until commit. Take every
        # involved gang together, in the same order as a payment.
        gangs = [awarded_to]
        for asset in (battle.stake, stake):
            if asset is not None and asset.held:
                gangs.append(asset.holder.gang)
        if battle.stake_transfer_mark is not None:
            gangs.extend(
                event.gang
                for event in LedgerEvent.objects.filter(
                    batch=battle.stake_transfer_mark,
                    campaign_asset_id=battle.stake_id,
                ).select_related("gang")
            )
        _hold(*gangs)
        if battle.stake_transfer_mark is not None:
            self._reverse_stake(battle)
        battle.stake, battle.stake_awarded_to = stake, awarded_to
        if stake is None or awarded_to is None:
            return
        stake = _asset_under_the_lock(stake)
        if stake.held and stake.holder.gang_id == awarded_to.pk:
            return
        if stake.held and stake.holder.gang_id not in gang_ids:
            raise Refusal(
                f"{stake} is not held by a participant any more. "
                "Transfer it on the campaign page."
            )
        mark = uuid4()
        membership = self._playing(awarded_to, stake)
        if stake.held:
            self.transfer(stake, membership, battle=battle, mark=mark)
        else:
            self.assign(stake, membership, battle=battle, mark=mark)
        battle.stake_transfer_mark = mark

    def _reverse_stake(self, battle):
        from n26.core.models import LedgerEvent
        from n26.core.operations import Refusal

        stake = battle.stake and _asset_under_the_lock(battle.stake)
        if stake is not None:
            if not (
                stake.held
                and battle.stake_awarded_to_id is not None
                and stake.holder.gang_id == battle.stake_awarded_to_id
            ):
                raise Refusal(
                    f"{stake} cannot move back: the gang it went to no longer holds it. "
                    "Transfer it on the campaign page."
                )
            lost = (
                LedgerEvent.objects.filter(
                    batch=battle.stake_transfer_mark,
                    campaign_asset=stake,
                    kind=LedgerEvent.Kind.LOST,
                )
                .select_related("gang")
                .first()
            )
            latest = (
                LedgerEvent.objects.filter(
                    campaign_asset=stake,
                    kind__in=[LedgerEvent.Kind.GAINED, LedgerEvent.Kind.LOST],
                )
                .order_by("-created", "-pk")
                .first()
            )
            if latest is None or latest.batch != battle.stake_transfer_mark:
                raise Refusal(
                    f"{stake} cannot move back: the gang it went to no longer holds it. "
                    "Transfer it on the campaign page."
                )
            if lost is None:
                self.unassign(stake, battle=battle, reverses=battle.stake_transfer_mark)
            else:
                self.transfer(
                    stake,
                    self._playing(lost.gang, stake),
                    battle=battle,
                    reverses=battle.stake_transfer_mark,
                )
        battle.stake_transfer_mark = None

    def _playing(self, gang, stake):
        from n26.core.models import CampaignMembership
        from n26.core.operations import Refusal

        membership = CampaignMembership.objects.filter(
            campaign=self.campaign, gang=gang, left__isnull=True
        ).first()
        if membership is None:
            raise Refusal(
                f"{gang.name} has left the campaign, so {stake} cannot go to "
                "them. Transfer it on the campaign page."
            )
        return membership

    def remove_battle(self, battle, *, revision):
        """Archive the occasion, retaining its records and applied gang changes."""
        from n26.core.operations import Refusal

        self._require_battle_admin()
        battle = self._locked_battle(battle, include_archived=True)
        if battle.archived:
            return battle
        if battle.revision != revision:
            raise Refusal("This battle changed. Reload it before archiving it.")
        battle.revision += 1
        battle.archive()
        self.event(CampaignEvent.Kind.BATTLE_ARCHIVED, battle=battle, note=battle.title)
        return battle

    def restore_battle(self, battle, *, revision):
        """Return an archived battle to the campaign with all records intact."""
        from n26.core.operations import Refusal

        self._require_battle_admin()
        battle = self._locked_battle(battle, include_archived=True)
        if not battle.archived:
            return battle
        if battle.revision != revision:
            raise Refusal("This battle changed. Reload it before restoring it.")
        battle.revision += 1
        battle.unarchive()
        self.event(CampaignEvent.Kind.BATTLE_RESTORED, battle=battle, note=battle.title)
        return battle

    def _require_battle_admin(self):
        from n26.core.operations import Refusal

        if self.actor is None or self.actor.pk != self.campaign.owner_id:
            raise Refusal("Only the arbitrator can archive or restore a battle.")

    def _locked_battle(self, battle, *, include_archived=False):
        from n26.core.models import Battle
        from n26.core.operations import Refusal

        # The full lock also excludes concurrent inserts naming this battle.
        try:
            found = Battle.objects.select_for_update().get(
                pk=battle.pk, campaign=self.campaign
            )
        except Battle.DoesNotExist:
            raise Refusal("This battle is no longer available.") from None
        if found.archived and not include_archived:
            raise Refusal("This battle is archived. Restore it before making changes.")
        return found

    def add_asset(self, asset, name="", *, income_override=None):
        """Add an unclaimed Holding asset eligible for this campaign.

        Possession assets belong to member gangs and cannot enter the campaign
        pool. Only the campaign log changes while the asset is unclaimed.
        """
        asset_type = asset.asset_type
        if not asset_type.is_holding:
            raise ValueError(
                f"{asset} is a {asset_type}, which every gang has its own of. "
                "Only an asset type with Transferable ownership can be added to a "
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
        # own are this campaign's to deal in — plus whatever is on a table
        # the campaign holds, wherever that is filed, which is the same rule
        # the catalogue reads (``addable_assets``).
        if asset.pack_id not in (
            self.campaign.pack_id,
            self.campaign.campaign_type.pack_id,
        ) and not _on_a_held_table(self.campaign, asset):
            raise ValueError(
                f"{asset} is in the {asset.pack} pack, which is not this "
                "campaign's own or its type's, and no table this campaign "
                "holds lists it."
            )
        campaign_asset = self._keep(asset, name, income_override=income_override)
        self.event(CampaignEvent.Kind.ASSET_ADDED, note=str(campaign_asset))
        return campaign_asset

    def add_assets(self, assets, *, name="", names=None, income=None, request_key):
        """Add a selection once, under the campaign lock.

        The request mark is recorded with the events, so a retry cannot add
        another copy even after the first holdings have moved or gone.
        """
        from n26.core.operations import Refusal

        if not isinstance(request_key, UUID):
            raise ValueError("An asset batch requires a UUID request mark.")
        assets = list(assets)
        if not assets:
            raise ValueError("An asset batch requires a selection.")
        if len(assets) > 1 and name:
            raise Refusal("Select one asset to give it a custom name in this campaign.")
        if self.campaign.events.filter(batch=request_key).exists():
            return False
        self.batch = request_key
        if len(assets) > 1 and any((names or {}).values()):
            raise Refusal("Select one asset to give it a custom name in this campaign.")
        override = None
        if income is not None:
            if not 0 <= income <= 2147483647:
                raise Refusal("Income must be between 0 and 2147483647.")
            from n26.library.authoring import (
                ef_contributes_to_counter,
                modifier,
                targets_gang_alone,
            )
            from n26.library.income import ensure_income_counter

            override = modifier(
                f"Income override {request_key}",
                targets_gang_alone(),
                ef_contributes_to_counter(ensure_income_counter(), income),
                pack=self.campaign.pack,
            )
        for asset in assets:
            self.add_asset(
                asset,
                name=(names or {}).get(str(asset.pk), "") or name,
                income_override=override,
            )
        return True

    def _keep(self, asset, name="", *, income_override=None):
        """Create an unclaimed campaign holding without recording an event.

        Manual addition and rolling each record their own event.
        """
        return CampaignAsset.objects.create(
            campaign=self.campaign,
            asset=asset,
            name=(name or "").strip(),
            income_override=income_override,
        )

    def roll_asset(
        self, table, *, membership=None, rolled=None, rng=None, avoid_duplicates=False
    ):
        """Resolve an asset-table roll and record its resulting holding.

        Pool rolls require a campaign-held table and create an unclaimed asset.
        Starting rolls require a table held by the gang and assign the asset
        with a GAINED event. With starting_from_pool, a Territory result claims
        a matching unclaimed asset instead of creating another.

        Generated rolls avoid assets already present when configured; manual
        ``rolled`` values are retained but must be valid for the die. ``rng``
        supports deterministic tests.

        Record ASSET_ROLLED once without an additional ASSET_ADDED event. Refuse
        unheld tables, tables without dice, and results without an eligible entry.
        """
        self._check_roll_table(table, membership=membership)
        entries = self._roll_entries(table)
        pool = None
        available = None
        from n26.library.territory_table import TERRITORY

        if (
            membership is not None
            and self.campaign.starting_from_pool
            and table.asset_type.label_singular == TERRITORY
        ):
            # The campaign lock protects the pool until assign takes the gang lock.
            pool = {}
            for asset in (
                self.campaign.campaign_assets.filter(
                    holder__isnull=True, asset__in=[entry.asset for entry in entries]
                )
                .select_related("asset")
                .order_by("created", "pk")
            ):
                pool.setdefault(asset.asset_id, asset)
            available = set(pool)
        elif avoid_duplicates and rolled is None:
            available = {entry.asset_id for entry in entries} - set(
                self.campaign.campaign_assets.values_list("asset_id", flat=True)
            )
        return self._roll_asset(
            table,
            entries,
            membership=membership,
            rolled=rolled,
            rng=rng,
            available=available,
            pool=pool,
        )

    def _check_roll_table(self, table, *, membership=None):
        from n26.core.operations import Refusal
        from n26.library.staged import sees_staged

        if membership is not None and (
            membership.campaign_id != self.campaign.pk or not membership.playing
        ):
            raise ValueError(f"{membership} is not playing {self.campaign}.")
        if not table.dice:
            raise Refusal(f"{table} cannot be rolled. It is a list with no dice.")
        if membership is None:
            if (
                not tables_in_play(
                    self.campaign, include_staged=sees_staged(self.actor)
                )
                .filter(pk=table.pk)
                .exists()
            ):
                raise Refusal(f"{table} is not available to {self.campaign.name}.")
        elif table.pk not in {
            held.pk
            for held in tables_held_by(
                membership.gang,
                self.campaign,
                include_staged=sees_staged(self.actor),
            )
        }:
            # A staged table the gang holds is one the roller may use only
            # if they may see staged content: the roll is where a Territory
            # is newly chosen for the campaign.
            gang = membership.gang.name
            raise Refusal(
                f"{gang} cannot roll for a {table.asset_type.label_singular.lower()} "
                f"from {table}. That table is not available to {gang}."
            )

    def _roll_entries(self, table):
        return roll_table_entries(table, self.actor)

    def _roll_asset(
        self,
        table,
        entries,
        *,
        membership=None,
        rolled=None,
        rng=None,
        available=None,
        pool=None,
    ):
        from n26.core.operations import ROLL_ENTERED, Refusal
        from n26.library.models import Dice

        dice = Dice(table.dice)
        entered = rolled is not None
        if not entered:
            if available is None:
                rolled = Dice.roll(dice, rng)
            else:
                rolled = _available_roll(table, entries, available, rng=rng, pool=pool)
        elif rolled not in Dice.rolls(dice):
            raise Refusal(f"You cannot roll {rolled} on a {dice.label}.")

        entry = table.landing(rolled, entries)
        if entry is None:
            raise Refusal(
                f"Nothing on {table} covers a roll of {rolled}. Fill that gap first."
            )
        if available is not None and entry.asset_id not in available:
            raise Refusal(
                f"No unclaimed {entry.asset} is available in the pool."
                if pool is not None
                else f"{entry.asset} is already in this campaign."
            )
        campaign_asset = (
            pool[entry.asset_id] if pool is not None else self._keep(entry.asset)
        )
        who = f" for {membership.gang.name}" if membership is not None else ""
        note = f"Rolled {rolled} from {_table_named(table)}{who}: {campaign_asset}."
        if entered:
            note = f"{note} {ROLL_ENTERED}"
        self.event(CampaignEvent.Kind.ASSET_ROLLED, note=note)
        if membership is not None:
            campaign_asset = self.assign(campaign_asset, membership)
        return AssetRoll(
            roll=rolled, dice=dice, table=table, campaign_asset=campaign_asset
        )

    def roll_assets(
        self,
        table,
        *,
        count,
        request_key,
        rolled=None,
        rng=None,
        avoid_duplicates=False,
    ):
        """Generate an unclaimed pool together and record the submission."""
        from n26.core.operations import Refusal

        if not 1 <= count <= 100:
            raise ValueError("Roll between 1 and 100 assets at a time.")
        if not isinstance(request_key, UUID):
            raise ValueError("An asset batch requires a UUID request mark.")
        if count > 1 and rolled is not None:
            raise Refusal("Set the number to 1 to use your own roll.")
        if self.campaign.events.filter(batch=request_key).exists():
            return []
        self._check_roll_table(table)
        entries = self._roll_entries(table)
        from n26.library.models import Dice

        available = None
        if avoid_duplicates and rolled is None:
            available = {entry.asset_id for entry in entries} - set(
                self.campaign.campaign_assets.values_list("asset_id", flat=True)
            )
            # Count reachable assets, not entries: bands may name the same asset.
            reachable = {
                entry.asset_id
                for roll in Dice.rolls(table.dice)
                if (entry := table.landing(roll, entries)) is not None
                and entry.asset_id in available
            }
            if count > len(reachable):
                raise Refusal(
                    f"Only {len(reachable)} different {table.asset_type.plural.lower()} "
                    "remain on this table. Reduce the number to roll or allow duplicates."
                )
        self.batch = request_key
        results = []
        for _ in range(count):
            result = self._roll_asset(
                table, entries, rolled=rolled, rng=rng, available=available
            )
            results.append(result)
            if available is not None:
                available.discard(result.campaign_asset.asset_id)
        return results

    def edit_asset(self, campaign_asset, *, name="", income=None):
        """Change one holding's name and base income under the campaign lock."""
        from n26.core.operations import Refusal
        from n26.library.authoring import (
            delete_modifier,
            ef_contributes_to_counter,
            modifier,
            targets_gang_alone,
        )
        from n26.library.income import ensure_income_counter

        if self.actor is None or self.actor.pk != self.campaign.owner_id:
            raise Refusal("Only the arbitrator can edit an asset.")
        holding = _asset_under_the_lock(campaign_asset)
        if holding is None:
            raise Refusal("This asset was removed from the campaign.")
        if holding.campaign_id != self.campaign.pk:
            raise ValueError("The asset belongs to another campaign.")
        name = (name or "").strip()
        if len(name) > 200:
            raise Refusal("The name must be at most 200 characters.")
        if income is not None and (
            not isinstance(income, int) or not 0 <= income <= 2147483647
        ):
            raise Refusal("Income must be between 0 and 2147483647.")
        previous = holding.income_override
        previous_income = (
            previous.contributes_to_counter.amount if previous is not None else None
        )
        if (holding.name, previous_income) == (name, income):
            return None

        changes = []
        was = holding.name or holding.asset.name
        now = name or holding.asset.name
        if holding.name != name:
            changes.append(f"name {was} → {now}")
        if previous_income != income:
            # Batch-added holdings can share an override. Replace the reference
            # so editing this holding cannot change another one's income.
            holding.income_override = (
                modifier(
                    f"Income override {uuid4()}",
                    targets_gang_alone(),
                    ef_contributes_to_counter(ensure_income_counter(), income),
                    pack=self.campaign.pack,
                )
                if income is not None
                else None
            )
            before = "catalogue" if previous_income is None else f"{previous_income}¢"
            after = "catalogue" if income is None else f"{income}¢"
            changes.append(f"income override {before} → {after}")
        holding.name = name
        holding.save(update_fields=["name", "income_override", "modified"])
        if (
            previous is not None
            and previous.pk != holding.income_override_id
            and not CampaignAsset.objects.filter(income_override=previous).exists()
        ):
            delete_modifier(previous)
        note = "; ".join(changes)
        if len(changes) == 1 and previous_income != income:
            note = f"{now}: {note}"
        self.event(CampaignEvent.Kind.ASSET_EDITED, note=note)
        return holding

    def remove_asset(self, campaign_asset):
        """Remove an unclaimed asset from the campaign, or return None if absent.

        Refuse held assets: unassigning first records the loss in the gang's history.
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
        override = campaign_asset.income_override
        campaign_asset.delete()
        if (
            override
            and not CampaignAsset.objects.filter(income_override=override).exists()
        ):
            from n26.library.authoring import delete_modifier

            delete_modifier(override)
        return campaign_asset

    def assign(self, campaign_asset, membership, *, battle=None, mark=None):
        """Assign an unclaimed asset to a current member gang.

        Lock campaign before gang, matching all ownership writers. Record a
        journal-only GAINED event without a ledger entry or rating. Refuse assets
        held by another gang; the same holder is a no-op.
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
        campaign_asset.ownership_revision += 1
        campaign_asset.save(update_fields=["holder", "ownership_revision", "modified"])
        with operation(membership.gang, actor=self.actor, batch=mark) as op:
            op.gain_asset(campaign_asset, battle=battle)
        return campaign_asset

    def unassign(self, campaign_asset, by_holder=None, *, battle=None, reverses=None):
        """Release a held asset and record a journal-only LOST event for its gang.

        Lock campaign before gang. Return None if already unclaimed. ``by_holder``
        revalidates the membership authorised when the command was submitted;
        arbitrator commands omit it.
        """
        from n26.core.operations import operation

        campaign_asset = _asset_under_the_lock(campaign_asset)
        if campaign_asset is None or not campaign_asset.held:
            return None
        _still_held_by(campaign_asset, by_holder)
        holder = campaign_asset.holder
        with operation(holder.gang, actor=self.actor) as op:
            op.remove_holding_picks(campaign_asset)
            campaign_asset.holder = None
            campaign_asset.ownership_revision += 1
            campaign_asset.save(
                update_fields=["holder", "ownership_revision", "modified"]
            )
            reversal = (
                LedgerEvent.objects.filter(
                    batch=reverses,
                    campaign_asset=campaign_asset,
                    gang=holder.gang,
                    kind=LedgerEvent.Kind.GAINED,
                ).first()
                if reverses
                else None
            )
            op.event(
                campaign_asset,
                LedgerEvent.Kind.LOST,
                note=str(campaign_asset),
                battle=battle,
                reversal_of=reversal,
            )
        return campaign_asset

    def transfer(
        self,
        campaign_asset,
        membership,
        by_holder=None,
        *,
        battle=None,
        mark=None,
        reverses=None,
    ):
        """Move a held asset between current member gangs and journal both sides.

        Record LOST and GAINED with one shared batch under the campaign lock.
        Refuse unclaimed assets and transfers to the existing holder.

        ``battle`` identifies the cause. ``mark`` supplies a shared batch when
        needed. ``reverses`` links each gang event to the corresponding earlier
        transfer event being undone.
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
        mark = mark or uuid4()
        undone = (
            {
                (e.gang_id, e.kind): e
                for e in LedgerEvent.objects.filter(
                    batch=reverses, campaign_asset=campaign_asset
                )
            }
            if reverses is not None
            else {}
        )
        with operation(
            loser.gang, actor=self.actor, batch=mark, also=(membership.gang,)
        ) as op:
            op.remove_holding_picks(campaign_asset)
            campaign_asset.holder = membership
            campaign_asset.ownership_revision += 1
            campaign_asset.save(
                update_fields=["holder", "ownership_revision", "modified"]
            )
            op.event(
                campaign_asset,
                LedgerEvent.Kind.LOST,
                note=str(campaign_asset),
                battle=battle,
                reversal_of=undone.get((loser.gang_id, LedgerEvent.Kind.GAINED)),
            )
        with operation(membership.gang, actor=self.actor, batch=mark) as op:
            op.gain_asset(
                campaign_asset,
                battle=battle,
                reversal_of=undone.get((membership.gang_id, LedgerEvent.Kind.LOST)),
            )
        return campaign_asset

    # --- What the arbitrator adds ------------------------------------------
    #
    # Everything below writes library content into the campaign's own pack
    # and onto its additions type, so it reaches member gangs by the path a
    # gang type's built-ins take. Nothing here touches the shared type.

    def add_asset_type(
        self, label_singular, ownership, label_plural="", display_group=""
    ):
        """Create an asset type in this campaign's additions and pack.

        Refuse labels already used by shared or campaign-owned types to prevent
        indistinguishable headings.
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
            display_group=(display_group or "").strip(),
            pack=self.campaign.pack,
        )
        self.event(CampaignEvent.Kind.ASSET_TYPE_ADDED, note=asset_type.label_singular)
        return asset_type

    def edit_asset_type(
        self, asset_type, label_singular, ownership, label_plural="", display_group=""
    ):
        """Change a campaign-owned asset type's labels or unfixed ownership.

        Reject duplicate labels and ownership changes after an asset or table exists.
        Compare against locked current values; an unchanged submission returns None.
        """
        from n26.core.operations import Refusal
        from n26.library.models import AssetType

        if asset_type.campaign_type_id != self.campaign.additions_id:
            raise ValueError(
                f"{asset_type} is not one of {self.campaign}'s own asset types."
            )
        asset_type = _asset_type_under_the_lock(asset_type)
        label_singular = (label_singular or "").strip()
        label_plural = (label_plural or "").strip()
        display_group = (display_group or "").strip()
        if not label_singular:
            raise Refusal("Give the asset type a label.")
        taken = (
            AssetType.objects.filter(
                campaign_type_id__in=(
                    self.campaign.campaign_type_id,
                    self.campaign.additions_id,
                ),
                label_singular__iexact=label_singular,
            )
            .exclude(pk=asset_type.pk)
            .exists()
        )
        if taken:
            raise Refusal(
                f"{self.campaign.name} already has an asset type called "
                f"{label_singular}."
            )
        if ownership != asset_type.ownership and (
            fixed := ownership_fixed_because(self.campaign, asset_type)
        ):
            raise Refusal(f"You cannot change the ownership now. {fixed}")
        was = asset_type.label_singular
        if (label_singular, label_plural, ownership, display_group) == (
            was,
            asset_type.label_plural,
            asset_type.ownership,
            asset_type.display_group,
        ):
            return None
        asset_type.label_singular = label_singular
        asset_type.label_plural = label_plural
        asset_type.ownership = ownership
        asset_type.display_group = display_group
        asset_type.save(
            update_fields=[
                "label_singular",
                "label_plural",
                "ownership",
                "display_group",
                "modified",
            ]
        )
        note = label_singular if was == label_singular else f"{was} → {label_singular}"
        self.event(CampaignEvent.Kind.ASSET_TYPE_EDITED, note=note)
        return asset_type

    def create_asset(self, asset_type, name, annotation="", income=0):
        """Create content in the campaign pack under a shared or owned asset type.

        Income becomes the asset's counter contribution. Possession assets are
        built into additions so future members receive them on joining and current
        members receive them through built-in propagation.
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
        asset_type = _asset_type_under_the_lock(asset_type)
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
        """Create a campaign counter and build its opening value into additions.

        Future gangs receive it on joining; current gangs receive it through
        propagation. Refuse names already used by the pack or shared counters,
        which would merge otherwise distinct table columns.
        """
        from n26.core.operations import Refusal
        from n26.library.authoring import add_built_in, create_counter
        from n26.library.models import Counter, DefaultAssignment

        name = (name or "").strip()
        archived = Counter.objects.filter(
            pack=self.campaign.pack, name__iexact=name, archived=True
        ).first()
        if archived is not None:
            raise Refusal(
                f"{self.campaign.name} has an archived counter called "
                f"{archived.name}. Unarchive it, or use another name."
            )
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
        """Create a gang-level choice and its options in the campaign pack.

        Create the slot type, qualified pickables, ordered picklist and built-in
        slot. Future and current gangs receive it through the ordinary additions
        paths. Refuse an existing question name.
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
        archived = SlotType.objects.filter(
            pack=pack, name__iexact=name, archived=True
        ).first()
        if archived is not None:
            raise Refusal(
                f"{self.campaign.name} has an archived label called "
                f"{archived.name}. Unarchive it, or use another name."
            )
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

    def archive_counter(self, member):
        """Archive an authored counter and its copies while retaining their values.

        Archive the built-in member first, then remove each current gang's copy
        under its lock in key order. Archive the content counter last. Keep
        history and record the value at removal. External library references block
        archival through _refuse_while_named.
        """
        from n26.core.models import CounterValue

        member = self._still_own(member, "counter")
        counter = member.counter
        _refuse_archiving(self.campaign, member)
        member.archive()

        def remove(op, copy):
            held = CounterValue.objects.filter(assignment=copy).first()
            value = held.value if held is not None else 0
            op.remove(copy, note=f"{ARCHIVED_COUNTER_NOTE_PREFIX}{value}")

        self._off_every_gang(member, remove)
        counter.archive()
        self.event(CampaignEvent.Kind.COUNTER_ARCHIVED, note=str(counter))
        return counter

    def archive_label(self, member):
        """Archive an authored label and each gang's slot and selection.

        Archive the member first, remove copies under each gang lock, then archive
        the slot and type. Record each removed pick for later restoration.
        External references to the label or its options block archival.
        """
        from n26.core.models import Assignment

        member = self._still_own(member, "slot")
        slot = member.slot
        _refuse_archiving(self.campaign, member)
        member.archive()

        def remove(op, copy):
            pick = Assignment.objects.filter(chosen_for=copy, archived=False).first()
            if pick is None:
                op.remove(copy)
            else:
                op.remove(copy, before_pick=pick)

        self._off_every_gang(member, remove)
        # The options and their list stay live: a clone outside the campaign
        # still carries the label, and its picker offers only live options.
        for row in (slot, slot.slot_type):
            row.archive()
        self.event(CampaignEvent.Kind.LABEL_ARCHIVED, note=slot.choice_label)
        return slot

    def _still_own(self, member, kind):
        """Reload a live authored member under lock; refuse if it was archived.

        Unrelated members remain caller errors.
        """
        from n26.core.operations import Refusal

        try:
            return own_addition(self.campaign, member.pk, kind)
        except ValueError:
            archived = (
                archived_additions(self.campaign, kind).filter(pk=member.pk).first()
            )
            if archived is None:
                raise
            name = archived.counter if kind == "counter" else archived.slot.choice_label
            raise Refusal(f"{name} was already archived.") from None

    def _off_every_gang(self, member, remove):
        """Remove each current member gang's copies under gang locks in key order.

        Visit every gang after locking it, including copies a concurrent propagation
        committed before the lock. Later propagation sees the archived member and
        creates nothing. Exclude cloned copies outside this campaign.
        """
        from n26.core.models import Assignment
        from n26.core.operations import operation

        for gang in _playing_gangs(self.campaign):
            with operation(gang, actor=self.actor, batch=self.batch) as op:
                for copy in Assignment.objects.filter(
                    materialised_from=member, archived=False, gang_root=gang
                ).order_by("pk"):
                    remove(op, copy)

    def unarchive_counter(self, member):
        """Restore an authored counter and current member gangs' archived balances.

        Restore the exact copy removed by archival. Gangs that joined during
        archival receive a new starting-value copy through filed propagation.
        """
        from n26.core.models import CounterValue
        from n26.core.propagation import file_propagation_task

        member = self._still_archived(member, "counter")
        counter = member.counter
        counter.unarchive()
        member.unarchive()

        def restore(op, copy, removal):
            held = CounterValue.objects.filter(assignment=copy).first()
            value = held.value if held is not None else 0
            op.restore(copy, note=f"{ARCHIVED_COUNTER_NOTE_PREFIX}{value}")

        self._back_on_every_gang(member, restore)
        file_propagation_task(member.default_set)
        self.event(CampaignEvent.Kind.COUNTER_UNARCHIVED, note=str(counter))
        return counter

    def unarchive_label(self, member):
        """Restore an authored label and selections removed by its archival.

        Restore only picks identified by that removal, preserving independently
        replaced selections. Previously unresolved labels remain unresolved.
        """
        from n26.core.propagation import file_propagation_task

        member = self._still_archived(member, "slot")
        slot = member.slot
        for row in (slot.slot_type, slot):
            row.unarchive()
        member.unarchive()

        def restore(op, copy, removal):
            pick = removal.before_pick
            if (
                pick is not None
                and pick.archived
                and getattr(_last_removal(pick), "batch", None) == removal.batch
            ):
                op.restore(copy, after_pick=pick)
                op.restore(pick)
            else:
                op.restore(copy)

        self._back_on_every_gang(member, restore)
        file_propagation_task(member.default_set)
        self.event(CampaignEvent.Kind.LABEL_UNARCHIVED, note=slot.choice_label)
        return slot

    def _still_archived(self, member, kind):
        """Reload an archived member under lock; refuse if already restored."""
        from n26.core.operations import Refusal

        try:
            return archived_addition(self.campaign, member.pk, kind)
        except ValueError:
            live = own_additions(self.campaign, kind).filter(pk=member.pk).first()
            if live is None:
                raise
            name = live.counter if kind == "counter" else live.slot.choice_label
            raise Refusal(f"{name} is not archived.") from None

    def _back_on_every_gang(self, member, restore):
        """Restore copies removed by archival for each gang's current membership.

        Lock gangs in key order. Ignore copies from closed memberships and those
        last removed for another reason.
        """
        from n26.core.models import Assignment
        from n26.core.operations import operation

        archives = CampaignEvent.objects.filter(
            campaign=self.campaign,
            kind__in=(
                CampaignEvent.Kind.COUNTER_ARCHIVED,
                CampaignEvent.Kind.LABEL_ARCHIVED,
            ),
        )
        memberships = (
            self.campaign.memberships.filter(
                left__isnull=True, additions_carrier__isnull=False
            )
            .select_related("gang")
            .order_by("gang_id")
        )
        for membership in memberships:
            with operation(membership.gang, actor=self.actor, batch=self.batch) as op:
                copy = Assignment.objects.filter(
                    materialised_from=member,
                    materialised_for_id=membership.additions_carrier_id,
                    archived=True,
                ).last()
                removal = _last_removal(copy) if copy is not None else None
                if removal is None or not archives.filter(batch=removal.batch).exists():
                    continue
                restore(op, copy, removal)

    def open_table(self, table):
        """Build a rollable table into campaign additions for current and future gangs.

        Require an eligible system or campaign table. Revive archived members to
        preserve existing copy provenance. Tables built into the shared type and
        tables already opened through additions are no-ops. Propagation grants
        new copies where needed.
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
                f"You cannot make {table} available here. It contains "
                f"{table.asset_type.plural.lower()}, which {self.campaign.name} "
                "does not deal in."
            )
        if (
            tables_in_play(self.campaign, include_staged=True)
            .filter(pk=table.pk)
            .exists()
        ):
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
        """Withdraw a table opened through additions without removing held copies.

        Archive its member when copies exist, otherwise delete it. Existing
        territories remain. Tables built into the shared type cannot be closed
        here.
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
                f"You cannot withdraw {table}. It is included with "
                f"{self.campaign.campaign_type}."
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
        """Create a campaign-pack table under an eligible Holding asset type.

        Build it into additions for current and future gangs. ``dice`` selects
        the die; blank means an ordered list. Refuse duplicate pack names.
        Add entries separately through add_table_entry.
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
        asset_type = _asset_type_under_the_lock(asset_type)
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
        """Add an eligible asset to a table authored in this campaign's pack.

        The authoring verb validates asset type and roll bands, including reversed
        bands and bands on unrolled tables. Surface its validation errors to forms.
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

    def add_gang(self, gang):
        """Join this non-archived campaign through Operation.join_campaign.

        The campaign lock prevents archival between validation and membership creation.
        """
        from n26.core.operations import Refusal, operation

        if self.campaign.archived:
            raise Refusal(f"{self.campaign.name} is archived, so no gang can join it.")
        with operation(gang, actor=self.actor) as op:
            return op.join_campaign(self.campaign)

    def remove_gang(self, membership):
        """End a gang's membership through Operation.leave_campaign.

        Acquire the gang lock inside the campaign lock. Return None if the
        membership has already closed.
        """
        from n26.core.models import CampaignMembership
        from n26.core.operations import operation

        if membership.campaign_id != self.campaign.pk:
            raise ValueError(f"{membership} is not in {self.campaign}.")
        membership = (
            CampaignMembership.objects.select_related("gang")
            .filter(pk=membership.pk, left__isnull=True)
            .first()
        )
        if membership is None:
            return None
        with operation(membership.gang, actor=self.actor) as op:
            return op.leave_campaign()

    def archive(self):
        """Remove every gang, archive the campaign and pack, and record the change.

        Ordinary departures release holdings and remove campaign grants. Preserve
        the campaign log and all archived history.
        """
        campaign = self.campaign
        if campaign.archived:
            return campaign
        # Each gang's line stays held until the archive commits, so they are
        # taken in key order, the order every multi-gang operation uses.
        for membership in campaign.memberships.filter(left__isnull=True).order_by(
            "gang_id"
        ):
            self.remove_gang(membership)
        campaign.archive()
        campaign.pack.archive()
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


def _available_roll(table, entries, available, *, rng=None, pool=None):
    """A roll conditioned on eligible assets, retaining each die's probability.

    Enumerating the dice avoids an unbounded re-roll loop when the table is
    exhausted or when a test generator keeps returning an excluded result.
    """
    import random

    from n26.core.operations import Refusal
    from n26.library.models import Dice

    outcomes = []
    for roll in Dice.rolls(table.dice):
        entry = table.landing(roll, entries)
        if entry is not None and entry.asset_id in available:
            weight = 6 - abs(7 - roll) if table.dice == Dice.TWO_D6 else 1
            outcomes.extend([roll] * weight)
    if not outcomes:
        label = table.asset_type.plural.lower()
        raise Refusal(
            f"No unclaimed {label} from this table are available in the pool."
            if pool is not None
            else f"No different {label} remain on this table. Allow duplicates to roll again."
        )
    return outcomes[(rng or random).randint(0, len(outcomes) - 1)]  # nosec B311


def _table_named(table):
    """A table as a sentence names it: "the Territory Selection Table",
    but "Goliath Territories". The article follows the name's own last
    word, since the name is the author's."""
    name = str(table)
    return f"the {name}" if name.lower().endswith("table") else name


def _playing_gangs(campaign):
    """The gangs playing this campaign now, in the order gang lines are
    taken."""
    from n26.core.models import Gang

    return Gang.objects.filter(
        pk__in=campaign.memberships.filter(left__isnull=True).values("gang_id")
    ).order_by("pk")


def own_additions(campaign, kind):
    """Return live counter or label members authored in this campaign's pack.

    ``kind`` is the field name ``"counter"`` or ``"slot"``. Shared campaign-type
    content and gang-owned content are excluded because the arbitrator cannot
    archive them here.
    """
    return _additions(campaign, kind, archived=False)


def archived_additions(campaign, kind):
    """Return archived counter or label additions in authored order."""
    return _additions(campaign, kind, archived=True)


def own_addition(campaign, member_pk, kind):
    """One of :func:`own_additions` by key, or ValueError. A view turns the
    ValueError into a 404."""
    return _one(own_additions(campaign, kind), campaign, member_pk, kind)


def archived_addition(campaign, member_pk, kind):
    """One of :func:`archived_additions` by key, or ValueError."""
    return _one(archived_additions(campaign, kind), campaign, member_pk, kind)


def _additions(campaign, kind, *, archived):
    from n26.library.models import DefaultAssignment

    built_ins = campaign.additions.built_ins_id
    if built_ins is None:
        return DefaultAssignment.objects.none()
    return (
        DefaultAssignment.objects.select_related(kind)
        .filter(
            default_set_id=built_ins,
            archived=archived,
            **{f"{kind}__pack_id": campaign.pack_id},
        )
        .order_by("position", "pk")
    )


def _one(members, campaign, member_pk, kind):
    from django.core.exceptions import ValidationError

    try:
        member = members.filter(pk=member_pk).first()
    except ValidationError:
        member = None
    if member is None:
        raise ValueError(f"No {kind} of {campaign}'s own has the key {member_pk}.")
    return member


def _last_removal(assignment):
    """The latest removal written for an assignment, or None."""
    return (
        LedgerEvent.objects.filter(assignment=assignment, kind=LedgerEvent.Kind.REMOVED)
        .select_related("before_pick")
        .order_by("-created", "-id")
        .first()
    )


@dataclass(frozen=True)
class UnarchiveLine:
    """One gang, as the unarchive page lists it: what it gets back, or
    what it gets for the first time."""

    gang: str
    value: str
    #: Nothing to show beyond its absence: no option picked yet.
    muted: bool


@dataclass(frozen=True)
class UnarchivePreview:
    """Per-gang restoration results using the same rules as _back_on_every_gang."""

    returning: list
    new: list


def unarchive_preview(campaign, member):
    """Preview restoration for current member gangs in a fixed query count.

    Restore archived copies with their previous values or selections. Gangs
    that joined during archival receive a new counter at its starting value
    or a new unresolved label.
    """
    from n26.core.models import Assignment

    memberships = list(
        campaign.memberships.filter(left__isnull=True, additions_carrier__isnull=False)
        .select_related("gang")
        .order_by("gang__name", "gang_id")
    )
    copies = {
        copy.materialised_for_id: copy
        for copy in Assignment.objects.filter(
            materialised_from=member,
            archived=True,
            materialised_for_id__in=[m.additions_carrier_id for m in memberships],
        )
        .select_related("counter_value")
        # The newest copy per carrier wins, as ``.last()`` picks it in the act.
        .order_by("pk")
    }
    removals = _last_removals(copies.values())
    picks = [r.before_pick for r in removals.values() if r.before_pick_id]
    pick_removals = _last_removals(picks)
    archives = set(
        campaign.events.filter(
            kind__in=(
                CampaignEvent.Kind.COUNTER_ARCHIVED,
                CampaignEvent.Kind.LABEL_ARCHIVED,
            )
        ).values_list("batch", flat=True)
    )
    returning, new = [], []
    for membership in memberships:
        name = membership.gang.name
        copy = copies.get(membership.additions_carrier_id)
        if copy is None:
            if member.counter_id:
                new.append(UnarchiveLine(name, str(member.amount), muted=False))
            else:
                new.append(UnarchiveLine(name, "Nothing picked yet", muted=True))
            continue
        removal = removals.get(copy.pk)
        if removal is None or removal.batch not in archives:
            # Removed for another reason: the act leaves it, and a copy
            # already made for this membership is never granted again.
            continue
        if member.counter_id:
            held = getattr(copy, "counter_value", None)
            value = str(held.value if held is not None else 0)
            returning.append(UnarchiveLine(name, value, muted=False))
            continue
        pick = removal.before_pick
        pick_removal = pick_removals.get(pick.pk) if pick is not None else None
        if pick is not None and pick.archived and pick_removal is not None:
            if pick_removal.batch == removal.batch:
                returning.append(UnarchiveLine(name, pick.pickable.name, muted=False))
                continue
        returning.append(UnarchiveLine(name, "Nothing picked yet", muted=True))
    return UnarchivePreview(returning=returning, new=new)


def _last_removals(assignments):
    """The latest removal of each of these assignments, by key: one query."""
    keys = [assignment.pk for assignment in assignments]
    if not keys:
        return {}
    latest = {}
    for removal in (
        LedgerEvent.objects.filter(
            assignment_id__in=keys, kind=LedgerEvent.Kind.REMOVED
        )
        .select_related("before_pick__pickable")
        .order_by("created", "id")
    ):
        latest[removal.assignment_id] = removal
    return latest


def _key(row):
    return (type(row)._meta.label_lower, row.pk)


def archive_refusal(campaign, member):
    """Return the reason an addition cannot be archived, or empty when permitted.

    Confirmation checks this before displaying the action. Execution checks
    again under the campaign lock.
    """
    from n26.core.operations import Refusal

    try:
        _refuse_archiving(campaign, member)
    except Refusal as refused:
        return str(refused)
    return ""


def _label_rows(campaign, slot):
    """What ``add_label`` wrote beside the slot: its picklist, the options
    in the campaign's pack, and the picklist's entries for them."""
    picklist = slot.picklist
    pickables = list(slot.slot_type.pickables.filter(pack_id=campaign.pack_id))
    return picklist, pickables, list(picklist.members.all())


def _refuse_archiving(campaign, member):
    """Refuse to archive an addition referenced by other library content."""
    if member.counter_id is not None:
        counter = member.counter
        _refuse_while_named(counter, [counter], own={_key(member)})
        return
    slot = member.slot
    picklist, pickables, entries = _label_rows(campaign, slot)
    own = {
        _key(row)
        for row in (member, slot, slot.slot_type, picklist, *pickables, *entries)
    }
    for things in ([slot.slot_type], [slot], [picklist], pickables):
        if things:
            _refuse_while_named(slot.choice_label, things, own=own)


def _refuse_while_named(name, things, own):
    """Refuse archival while external library content references these objects.

    ``own`` contains the addition's own supporting objects, whose references
    are permitted. Player assignments and history are handled by archival and
    do not block it. External conditions or grants must be changed first.
    """
    from n26.core.operations import Refusal
    from n26.library.references import named, references_to

    def said(row):
        # A modifier's part says what it does ("adds 2 to Faith"); the
        # rule it belongs to is what an admin would look for.
        modifier = getattr(row, "modifier", None)
        return str(modifier) if modifier is not None else named(row)

    uses = sorted(
        {
            said(reference.row)
            for reference in references_to(*things)
            if reference.row._meta.app_label == "library"
            and _key(reference.row) not in own
        }
    )
    if uses:
        raise Refusal(
            f"You cannot archive {name}. It is used by "
            f"{_and(f'“{use}”' for use in uses)}. "
            "Ask a Gyrinx admin to change that first."
        )


def _own_table(campaign, table):
    """Require a table authored in this campaign's pack before changing it."""
    if table.pack_id != campaign.pack_id:
        raise ValueError(f"{table} is not one of {campaign}'s own tables.")


def addable_assets(campaign, *, include_staged=False):
    """List visible, non-archived Holding assets eligible for manual addition.

    Include relevant asset types from the system, shared type and campaign
    packs. Also include entries of held tables regardless of pack, allowing
    those tables to extend eligibility. Exclude Possession assets, which are
    granted to member gangs. ``add_asset`` checks type and pack or held-table
    eligibility without applying these archive and staging filters.
    """
    from n26.library.models import Asset

    tabled = Asset.objects.filter(
        tabled__table__in=tables_in_play(campaign, include_staged=True)
    ).unarchived()
    if not include_staged:
        tabled = tabled.live()
    return (
        (
            (
                campaign.campaign_type.holding_assets()
                | campaign.additions.holding_assets()
            ).selectable(
                [campaign.pack_id, campaign.campaign_type.pack_id],
                include_staged=include_staged,
            )
            | tabled
        )
        .distinct()
        .select_related("asset_type")
        .order_by("asset_type__position", "asset_type__label_singular", "name")
    )


def _on_a_held_table(campaign, asset):
    """Whether a held table lists this asset, regardless of its pack."""
    from n26.library.models import AssetTableEntry

    return AssetTableEntry.objects.filter(
        table__in=tables_in_play(campaign, include_staged=True), asset=asset
    ).exists()


def roll_table_entries(table, actor):
    """The entries a new campaign roll may land on, including preview reads."""
    from n26.library.staged import sees_staged

    entries = table.entries.select_related("asset__asset_type")
    if not sees_staged(actor):
        entries = entries.live().filter(asset__staged=False)
    return list(entries)


def tables_in_play(campaign, *, include_staged=False):
    """Load live tables built into the shared type or additions in one query.

    These generate the campaign's pool. ``include_staged`` permits staged
    tables for authorised discovery or inspection of already held content.
    """
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
    tables = AssetTable.objects.filter(pk__in=members.values("asset_table_id"))
    return tables if include_staged else tables.live()


def tables_on(card, computed, withdrawn=frozenset(), *, include_staged=False):
    """Return distinct rollable tables from the gang's loaded card in card order.

    Include stored and computed tables. ``withdrawn`` identifies archived
    built-in members whose copies remain held but cannot offer new rolls.
    Exclude staged tables unless ``include_staged`` permits discovery.
    This function performs no queries.
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
    return [table for table in held.values() if include_staged or not table.staged]


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


def tables_held_by(gang, campaign, *, include_staged=False):
    """Build one gang's effective card and return its eligible campaign tables.

    For multi-gang pages, use tables_on with preloaded cards and batch
    foreign_tables instead. ``include_staged`` follows tables_on.
    """
    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute

    card = build_gang_card(gang, with_statlines=False)
    computed = compute(card, build_modifier_index(carriers(card)))
    held = tables_on(
        card, computed, withdrawn_members(card), include_staged=include_staged
    )
    foreign = foreign_tables(campaign, held)
    return [table for table in held if table.pk not in foreign]


def foreign_tables(campaign, tables):
    """Return table IDs authored in another campaign's private pack.

    Only system tables and this campaign's own tables are eligible. Use one
    query for the supplied tables, skipping it when all belong to this campaign.
    """
    from django.db.models import Q

    from n26.library.models import AssetTable

    elsewhere = {table.pk for table in tables if table.pack_id != campaign.pack_id}
    if not elsewhere:
        return frozenset()
    return frozenset(
        AssetTable.objects.filter(pk__in=elsewhere)
        .exclude(Q(pack__owner__isnull=True) | Q(pack_id=campaign.pack_id))
        .values_list("pk", flat=True)
    )


def _still_held_by(campaign_asset, membership_id):
    """Refuse a holder's command if the asset changed hands before execution.

    ``None`` bypasses the holder check for arbitrator commands.
    """
    from n26.core.operations import Refusal

    if membership_id is not None and campaign_asset.holder_id != membership_id:
        raise Refusal(
            f"{campaign_asset} is now held by {campaign_asset.holder.gang.name}, "
            "so you cannot hand it over."
        )


def ownership_fixed_because(campaign, asset_type):
    """Explain why an asset type's ownership is fixed, or return empty.

    An existing asset or table fixes ownership because it determines how those
    objects are created; only Holding types can have tables.
    """
    plural = asset_type.plural.lower()
    if asset_type.assets.exists():
        return f"{campaign.name} already has {plural}."
    if asset_type.tables.exists():
        return f"{campaign.name} already has a table of {plural}."
    return ""


def _asset_type_under_the_lock(asset_type):
    """Reload the campaign-owned asset type after acquiring the campaign lock.

    Labels or ownership may have changed since the form was loaded.
    """
    from n26.library.models import AssetType

    return AssetType.objects.get(pk=asset_type.pk)


def _asset_under_the_lock(campaign_asset):
    """Reload the asset and holder under the campaign lock, or return None.

    All ownership writers take that lock, making this state authoritative for
    a stale or concurrent submission.
    """
    return (
        CampaignAsset.objects.select_related("holder__gang", "asset__asset_type")
        .filter(pk=campaign_asset.pk)
        .first()
    )


@dataclass(frozen=True)
class BattleStake:
    """A battle's staked asset and current holder for display."""

    label: str
    name: str
    awarded_to: str
    holder: str
    #: Whether the reader is the campaign's arbitrator, who can change it.
    arbitrator: bool = False

    @property
    def outcome(self):
        if self.awarded_to:
            return f"Goes to {self.awarded_to}"
        if self.holder:
            return f"Stays with {self.holder}"
        return "Not given to any gang"

    @property
    def held_by(self):
        """Who holds it now, where the outcome does not already say so."""
        if not self.holder:
            return "Not held by any gang."
        if self.holder == (self.awarded_to or self.holder):
            return ""
        return f"Held by {self.holder}."

    @property
    def note(self):
        """The line under the stake: who holds it, and who can change it."""
        who = (
            ""
            if self.arbitrator
            else ("Only the campaign's arbitrator can change this on Edit battle.")
        )
        return " ".join(part for part in (self.held_by, who) if part)


def a_stake(label):
    """A stake's type word in a sentence: "a territory", "an asset"."""
    word = label[:1].lower() + label[1:]
    return f"{'an' if word[:1] in 'aeiou' else 'a'} {word}"


def stake_came_from(battle):
    """The gang holding the battle's stake before the battle moved it: the
    gang its transfer took it from, or the holder now where it has not
    moved. None where the battle stakes nothing or nobody holds it."""
    if battle is None or battle.stake_id is None:
        return None
    if battle.stake_transfer_mark is not None:
        lost = (
            LedgerEvent.objects.filter(
                batch=battle.stake_transfer_mark,
                campaign_asset_id=battle.stake_id,
                kind=LedgerEvent.Kind.LOST,
            )
            .select_related("gang")
            .first()
        )
        return lost.gang if lost else None
    stake = (
        CampaignAsset.objects.select_related("holder__gang")
        .filter(pk=battle.stake_id)
        .first()
    )
    return stake.holder.gang if stake is not None and stake.held else None


def battle_stake(battle, viewer=None):
    """The battle's stake as ``BattleStake``, or None where it has none.

    ``viewer`` is who is reading, so the arbitrator is not told to ask
    themselves.
    """
    if battle is None or battle.stake_id is None:
        return None
    stake = (
        CampaignAsset.objects.select_related("asset__asset_type", "holder__gang")
        .filter(pk=battle.stake_id)
        .first()
    )
    if stake is None:
        return None
    label = stake.asset.asset_type.label_singular
    awarded_to = battle.stake_awarded_to
    return BattleStake(
        label=f"{label[:1].upper()}{label[1:]} staked",
        name=f"{stake} [{str(stake.pk)[-6:]}]",
        awarded_to=awarded_to.name if awarded_to else "",
        holder=stake.holder.gang.name if stake.held else "",
        arbitrator=viewer is not None and viewer.pk == battle.campaign.owner_id,
    )


def starting_asset_types_received(campaign, memberships):
    """Asset types already received during each gang's current membership.

    A starting allocation stays complete after a holding is lost or transferred.
    An asset assigned by hand also fills that starting allocation.
    """
    from django.db.models import F

    received = {membership.pk: set() for membership in memberships}
    if not received:
        return received
    events = (
        LedgerEvent.objects.filter(
            campaign=campaign,
            gang__campaign_memberships__in=received,
            created__gte=F("gang__campaign_memberships__created"),
            kind=LedgerEvent.Kind.GAINED,
            received_asset_type__isnull=False,
        )
        .order_by()
        .values_list("gang__campaign_memberships__pk", "received_asset_type")
        .distinct()
    )
    for membership_id, asset_type_id in events:
        received[membership_id].add(asset_type_id)
    return received


def over_budget(campaign, gang):
    """Whether a pre-campaign gang's wealth exceeds the campaign's finite budget.

    Wealth includes model rating, stash rating and unspent credits. Purchases
    transfer value between these components. Active campaigns and unlimited
    budgets produce no warning.
    """
    return (
        campaign.status == Campaign.Status.PRE_CAMPAIGN
        and campaign.budget is not None
        and gang.wealth > campaign.budget
    )


def archive_gang(gang, actor=None):
    """Archive a gang after removing its current campaign membership.

    Recheck membership while locking campaign before gang, retrying if it
    changed. Joining checks gang archival under the same gang lock so a
    concurrent join cannot add the archived gang.
    """
    from n26.core.models import CampaignMembership
    from n26.core.operations import operation

    def open_membership():
        return (
            CampaignMembership.objects.filter(gang=gang, left__isnull=True)
            .select_related("campaign")
            .first()
        )

    while True:
        read = open_membership()
        with transaction.atomic():
            if read is None:
                with operation(gang, actor=actor) as op:
                    if open_membership() is not None:
                        continue
                    return op.archive_gang()
            with campaign_operation(read.campaign, actor=actor):
                with operation(gang, actor=actor) as op:
                    now = open_membership()
                    if now is None or now.pk != read.pk:
                        continue
                    op.leave_campaign()
                    return op.archive_gang()


@contextmanager
def campaign_operation(campaign, actor=None):
    """Run campaign writes atomically after locking and reloading the campaign.

    Use a no-key-update lock to serialise campaign writers while allowing
    gang events to reference the campaign. A stronger lock could deadlock
    with a gang write that holds its gang lock before inserting that reference.
    Campaign operations never change the campaign primary key.
    """
    from n26.write_pause import write_guard

    with transaction.atomic(), write_guard():
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
    """Authored setup information about a campaign type and its starting grants.

    ``kinds`` describes asset types in authored order. ``starts_with`` describes
    the built-ins, or is empty. ``rules`` describes campaign-wide modifiers.
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
    """How assets of one type behave, in one sentence: "each" rather than
    an article, so the label needs no a/an."""
    if asset_type.is_holding:
        return f"Each {asset_type.label_singular} is held by one gang at a time."
    return f"Each gang has its own {asset_type.label_singular.lower()}."


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
