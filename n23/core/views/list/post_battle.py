"""Bulk post-battle updates editor for a list (campaign mode)."""

import uuid
from dataclasses import dataclass, field

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from gyrinx import messages
from gyrinx.analytics.models import EventNoun, EventVerb, log_event
from n23.content.models import ContentInjury
from n23.core.forms.post_battle import PostBattleUpdatesForm
from n23.core.handlers.fighter import (
    handle_fighter_add_injury,
    handle_fighter_add_xp,
    handle_fighter_adjust_counter,
)
from n23.core.handlers.fighter.capture import handle_fighter_capture
from n23.core.handlers.fighter.kill import handle_fighter_kill
from n23.core.handlers.list import handle_credits_modification
from n23.core.models.battle import Battle
from n23.core.models.campaign import (
    CampaignAction,
    CampaignAsset,
    CampaignListResource,
)
from n23.core.models.list import List, ListFighter
from n23.core.views.fighter.permissions import get_list_for_edit


@dataclass
class _ApplySummary:
    """Tally of what a post-battle submit changed, for the flash message."""

    credits: int = 0
    resources: int = 0
    assets: int = 0
    xp: int = 0
    injuries: int = 0
    kills: int = 0
    counters: int = 0
    states: int = 0
    captured: int = 0
    killed_names: list = field(default_factory=list)
    capture_skipped_names: list = field(default_factory=list)

    @property
    def changed(self):
        return bool(
            self.credits
            or self.resources
            or self.assets
            or self.xp
            or self.injuries
            or self.counters
            or self.states
            or self.captured
        )

    @property
    def message(self):
        parts = []
        if self.credits:
            parts.append(f"{self.credits}¢ gained")
        if self.resources:
            parts.append(f"{self.resources} resource update{_s(self.resources)}")
        if self.assets:
            parts.append(f"{self.assets} asset{_s(self.assets)} claimed")
        if self.xp:
            parts.append(f"XP for {self.xp} fighter{_s(self.xp)}")
        if self.injuries:
            parts.append(f"{self.injuries} injur{'ies' if self.injuries != 1 else 'y'}")
        if self.counters:
            parts.append(f"{self.counters} counter update{_s(self.counters)}")
        if self.states:
            parts.append(f"{self.states} state change{_s(self.states)}")
        if self.captured:
            parts.append(f"{self.captured} fighter{_s(self.captured)} captured")
        summary = "Post-battle updates applied: " + ", ".join(parts) + "."
        if self.killed_names:
            names = ", ".join(self.killed_names)
            summary += (
                f" {names} died — any equipment they carried was returned to"
                " the gang's stash."
            )
        if self.capture_skipped_names:
            names = ", ".join(self.capture_skipped_names)
            summary += f" The capture of {names} was therefore not applied."
        return summary


def _s(n):
    return "" if n == 1 else "s"


class _ResourceApplyError(Exception):
    """A resource delta failed at apply time (e.g. a concurrent change pushed
    the resource below zero after the form validated). Carries the field name
    so the view can surface it as a field error instead of a 500."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def _post_battle_fighters(lst):
    """Active roster fighters for the grid: no stash, no archived; vehicles,
    crew and dead fighters are included (post-battle needs them). Counters and
    capture state are prefetched so the grid doesn't go N+1."""
    return list(
        lst.fighters()
        .exclude(content_fighter__is_stash=True)
        .select_related("capture_info")
        .prefetch_related("content_fighter__counters", "counters")
    )


def _selectable_battles(lst):
    """Non-archived battles in this list's campaign that the list fought in,
    for linking the logged actions to a specific battle."""
    if not lst.campaign_id:
        return Battle.objects.none()
    return (
        lst.campaign.battles.filter(archived=False, participants=lst)
        .distinct()
        .select_related("campaign")
    )


def _capture_lists(lst):
    """Other campaign-mode gangs in the campaign that could hold a captive."""
    if not lst.campaign_id:
        return List.objects.none()
    return (
        lst.campaign.campaign_lists.filter(status=List.CAMPAIGN_MODE)
        .exclude(id=lst.id)
        .order_by("name")
    )


def _gang_resources(lst):
    """This gang's campaign resources, for the ± delta fields."""
    if not lst.campaign_id:
        return []
    return list(
        CampaignListResource.objects.filter(
            campaign=lst.campaign, list=lst
        ).select_related("resource_type")
    )


def _claimable_assets(lst):
    """Campaign assets this gang doesn't already hold. Ordered by asset type
    (the model Meta), so the grouped select renders one optgroup per type."""
    if not lst.campaign_id:
        return CampaignAsset.objects.none()
    return (
        CampaignAsset.objects.filter(asset_type__campaign=lst.campaign)
        .exclude(holder=lst)
        .select_related("asset_type", "holder")
    )


def _apply(request, lst, fighters, resources, form):
    """Apply only the fields that were filled in, gang gains then per fighter."""
    user = request.user
    cd = form.cleaned_data
    battle = cd.get("battle")
    summary = _ApplySummary()

    with transaction.atomic():
        credits = cd.get("credits_gained")
        if credits:
            result = handle_credits_modification(
                user=user,
                lst=lst,
                operation="add",
                amount=credits,
                description="Post-battle winnings",
                battle=battle,
            )
            log_event(
                user=user,
                noun=EventNoun.LIST,
                verb=EventVerb.UPDATE,
                object=lst,
                request=request,
                list_name=lst.name,
                credit_operation="add",
                amount=credits,
                credits_current=result.credits_after,
                credits_earned=result.credits_earned_after,
                description="Post-battle winnings",
            )
            summary.credits = credits

        for resource in resources:
            delta = cd.get(f"resource_{resource.pk}")
            if delta:
                try:
                    resource.modify_amount(delta, user=user, battle=battle)
                except ValueError as e:
                    # The form validated against the amount loaded at bind
                    # time; a concurrent change can still push the resource
                    # below zero here. Roll the whole submit back and let the
                    # view re-render with a field error.
                    raise _ResourceApplyError(f"resource_{resource.pk}", str(e)) from e
                log_event(
                    user=user,
                    noun=EventNoun.CAMPAIGN_RESOURCE,
                    verb=EventVerb.UPDATE,
                    object=resource,
                    request=request,
                    campaign_id=str(lst.campaign_id),
                    campaign_name=lst.campaign.name,
                    resource_type=resource.resource_type.name,
                    list_name=lst.name,
                    modification=delta,
                    new_amount=resource.amount,
                )
                summary.resources += 1

        # dict.fromkeys: the repeated select preserves duplicates for injuries,
        # but claiming the same asset twice is meaningless.
        for asset in dict.fromkeys(cd.get("assets_captured") or ()):
            old_holder = asset.holder
            asset.transfer_to(lst, user=user, battle=battle)
            log_event(
                user=user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.UPDATE,
                object=asset,
                request=request,
                campaign_id=str(lst.campaign_id),
                campaign_name=lst.campaign.name,
                asset_name=asset.name,
                transfer_from=old_holder.name if old_holder else "Unassigned",
                transfer_to=lst.name,
                action="transfer",
            )
            summary.assets += 1

        for fighter in fighters:
            # Cache the parent so the handlers don't re-query fighter.list.
            fighter.list = lst
            pk = fighter.pk

            xp = cd.get(f"xp_{pk}")
            if xp:
                handle_fighter_add_xp(
                    user=user, fighter=fighter, amount=xp, battle=battle
                )
                summary.xp += 1

            for entry in fighter.applicable_counters:
                delta = cd.get(f"counter_{pk}_{entry.counter.pk}")
                if delta and handle_fighter_adjust_counter(
                    user=user,
                    fighter=fighter,
                    counter=entry.counter,
                    delta=delta,
                    battle=battle,
                ):
                    summary.counters += 1

            killed_now = False
            for injury in cd.get(f"injury_{pk}") or ():
                result = handle_fighter_add_injury(
                    user=user,
                    fighter=fighter,
                    injury=injury,
                    battle=battle,
                )
                # The handler stays HTTP-free; the view owns event logging.
                log_event(
                    user=user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.UPDATE,
                    object=fighter,
                    request=request,
                    action="injury_added",
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    injury_name=injury.name,
                    injury_state=result.outcome_state,
                )
                summary.injuries += 1
                if result.killed:
                    summary.kills += 1
                    summary.killed_names.append(fighter.name)
                    killed_now = True
                    # A dead fighter can't take further injuries.
                    break

            # An explicit state choice is applied after injuries, so it wins
            # over an injury's default outcome — unless the fighter just died.
            new_state = cd.get(f"state_{pk}")
            if new_state and not killed_now and new_state != fighter.injury_state:
                if new_state == ListFighter.DEAD:
                    # Full kill logic: equipment -> stash, cost 0, rating
                    # propagation — same as a fatal injury.
                    handle_fighter_kill(
                        user=user, lst=lst, fighter=fighter, battle=battle
                    )
                    log_event(
                        user=user,
                        noun=EventNoun.LIST_FIGHTER,
                        verb=EventVerb.DELETE,
                        object=fighter,
                        request=request,
                        fighter_name=fighter.name,
                        list_id=str(lst.id),
                        list_name=lst.name,
                        action="killed",
                    )
                    summary.kills += 1
                    summary.killed_names.append(fighter.name)
                    killed_now = True
                else:
                    old_state = fighter.get_injury_state_display()
                    fighter.injury_state = new_state
                    fighter.save_with_user(user=user)
                    new_state_display = dict(ListFighter.INJURY_STATE_CHOICES)[
                        new_state
                    ]
                    CampaignAction.objects.create(
                        user=user,
                        owner=user,
                        campaign=lst.campaign,
                        list=lst,
                        battle=battle,
                        description=(
                            f"State Change: {fighter.name} changed from"
                            f" {old_state} to {new_state_display}"
                        ),
                        outcome=f"{fighter.name} is now {new_state_display}",
                    )
                    log_event(
                        user=user,
                        noun=EventNoun.LIST_FIGHTER,
                        verb=EventVerb.UPDATE,
                        object=fighter,
                        request=request,
                        action="state_changed",
                        fighter_name=fighter.name,
                        list_id=str(lst.id),
                        list_name=lst.name,
                        injury_state=new_state,
                    )
                summary.states += 1

            capturing_list = cd.get(f"captured_by_{pk}")
            if capturing_list:
                if killed_now:
                    # A fatal injury in the same submit wins over the capture.
                    summary.capture_skipped_names.append(fighter.name)
                else:
                    handle_fighter_capture(
                        user=user,
                        fighter=fighter,
                        capturing_list=capturing_list,
                        battle=battle,
                    )
                    log_event(
                        user=user,
                        noun=EventNoun.LIST_FIGHTER,
                        verb=EventVerb.UPDATE,
                        object=fighter,
                        request=request,
                        action="captured",
                        fighter_name=fighter.name,
                        list_id=str(lst.id),
                        list_name=lst.name,
                        capturing_list_name=capturing_list.name,
                        capturing_list_id=str(capturing_list.id),
                    )
                    summary.captured += 1

    return summary


@login_required
def post_battle_updates(request, id):
    """
    Bulk-edit a whole gang's post-battle results in one grid: record gang
    gains (credits, resources, assets), add XP, adjust counters, apply
    injuries, and mark fighters captured. Campaign mode only; open to the
    list owner and the campaign arbitrator.

    **Context**

    ``list``
        The :model:`core.List` being updated.
    ``form``
        A :class:`PostBattleUpdatesForm` bound to the list's fighters.
    ``rows``
        Per-fighter rows pairing each fighter with its bound form fields.
    ``resource_fields``
        Per-resource entries pairing each campaign resource with its field.

    **Template**

    :template:`core/list_post_battle_updates.html`
    """
    lst, _perms = get_list_for_edit(request, id)

    default_url = reverse("core:list", args=(lst.id,))

    if not lst.is_campaign_mode:
        messages.error(
            request, "Post-battle updates are only available in campaign mode."
        )
        return HttpResponseRedirect(default_url)

    fighters = _post_battle_fighters(lst)
    battles = _selectable_battles(lst)
    capture_lists = _capture_lists(lst)
    resources = _gang_resources(lst)
    assets = _claimable_assets(lst)

    form_kwargs = {
        "fighters": fighters,
        "battles": battles,
        "capture_lists": capture_lists,
        "resources": resources,
        "assets": assets,
    }

    if request.method == "POST":
        form = PostBattleUpdatesForm(request.POST, **form_kwargs)
        if form.is_valid():
            try:
                summary = _apply(request, lst, fighters, resources, form)
            except _ResourceApplyError as e:
                # Everything rolled back; fall through and re-render.
                form.add_error(e.field, str(e))
            else:
                if summary.changed:
                    messages.success(request, summary.message)
                else:
                    messages.info(request, "No post-battle changes were entered.")
                return HttpResponseRedirect(default_url)
    else:
        # A ?battle=<id> query param preselects that battle (only if the list
        # actually fought in it — otherwise it's ignored). Validate the UUID
        # first so a malformed value is ignored rather than 500ing the lookup.
        initial = {}
        battle_param = request.GET.get("battle")
        if battle_param:
            try:
                uuid.UUID(str(battle_param))
            except ValueError, TypeError:
                battle_param = None
        if battle_param and battles.filter(pk=battle_param).exists():
            initial["battle"] = battle_param
        form = PostBattleUpdatesForm(initial=initial, **form_kwargs)

    rows = _build_rows(fighters, form)
    resource_fields = [
        {"resource": resource, "field": form[f"resource_{resource.pk}"]}
        for resource in resources
    ]
    # Injury id -> default outcome, for the JS that mirrors the single-fighter
    # add-injury screen: picking an injury pre-fills the row's state select.
    injury_phases = {
        str(pk): phase for pk, phase in ContentInjury.objects.values_list("id", "phase")
    }
    return render(
        request,
        "core/list_post_battle_updates.html",
        {
            "list": lst,
            "form": form,
            "rows": rows,
            "has_battles": battles.exists(),
            "resource_fields": resource_fields,
            "has_assets": assets.exists(),
            "injury_phases": injury_phases,
        },
    )


def _build_rows(fighters, form):
    """Pair each fighter with its bound fields so the template can render the
    grid without dynamic field-name lookups."""
    rows = []
    for fighter in fighters:
        pk = fighter.pk
        counters = [
            {
                "counter": entry.counter,
                "value": entry.value,
                "warn": entry.warn,
                "field": form[f"counter_{pk}_{entry.counter.pk}"],
            }
            for entry in fighter.applicable_counters
        ]
        captured_by_name = f"captured_by_{pk}"
        state_name = f"state_{pk}"
        injury_name = f"injury_{pk}"
        rows.append(
            {
                "fighter": fighter,
                "xp": form[f"xp_{pk}"],
                "injury": form[injury_name] if injury_name in form.fields else None,
                "counters": counters,
                "state": form[state_name] if state_name in form.fields else None,
                "captured_by": (
                    form[captured_by_name] if captured_by_name in form.fields else None
                ),
            }
        )
    return rows
