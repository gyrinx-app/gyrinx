"""Bulk post-battle updates editor for a list (campaign mode)."""

import uuid
from dataclasses import dataclass, field

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.post_battle import PostBattleUpdatesForm
from gyrinx.core.handlers.fighter import (
    handle_fighter_add_injury,
    handle_fighter_add_xp,
    handle_fighter_adjust_counter,
)
from gyrinx.core.models.battle import Battle
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.views.fighter.permissions import get_list_for_edit


@dataclass
class _ApplySummary:
    """Tally of what a post-battle submit changed, for the flash message."""

    xp: int = 0
    injuries: int = 0
    kills: int = 0
    counters: int = 0
    notes: int = 0
    killed_names: list = field(default_factory=list)

    @property
    def changed(self):
        return bool(self.xp or self.injuries or self.counters or self.notes)

    @property
    def message(self):
        parts = []
        if self.xp:
            parts.append(f"XP for {self.xp} fighter{_s(self.xp)}")
        if self.injuries:
            parts.append(f"{self.injuries} injur{'ies' if self.injuries != 1 else 'y'}")
        if self.counters:
            parts.append(f"{self.counters} counter update{_s(self.counters)}")
        if self.notes:
            parts.append(f"notes for {self.notes} fighter{_s(self.notes)}")
        summary = "Post-battle updates applied: " + ", ".join(parts) + "."
        if self.killed_names:
            summary += (
                f" {', '.join(self.killed_names)} died — their equipment moved to"
                " the stash."
            )
        return summary


def _s(n):
    return "" if n == 1 else "s"


def _post_battle_fighters(lst):
    """Active roster fighters for the grid: no stash, no archived; vehicles,
    crew and dead fighters are included (post-battle needs them). Counters are
    prefetched so ``applicable_counters`` doesn't go N+1 across the grid."""
    return list(
        lst.fighters()
        .exclude(content_fighter__is_stash=True)
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


def _apply(request, lst, fighters, form):
    """Apply only the fields that were filled in or changed, per fighter."""
    user = request.user
    cd = form.cleaned_data
    battle = cd.get("battle")
    summary = _ApplySummary()

    with transaction.atomic():
        for fighter in fighters:
            # Cache the parent so the handlers don't re-query fighter.list.
            fighter.list = lst
            pk = fighter.pk

            # Notes first: a fatal injury (below) calls the kill handler, which
            # mutates and saves the fighter — we don't want a later notes save
            # on a now-stale instance to clobber that.
            new_private = cd.get(f"private_notes_{pk}", "") or ""
            if new_private != fighter.private_notes:
                fighter.private_notes = new_private
                fighter.save_with_user(user=user)
                log_event(
                    user=user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.UPDATE,
                    object=fighter,
                    request=request,
                    action="notes_updated",
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                )
                summary.notes += 1

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

            injury = cd.get(f"injury_{pk}")
            if injury:
                result = handle_fighter_add_injury(
                    user=user,
                    fighter=fighter,
                    injury=injury,
                    notes=(cd.get(f"injury_reason_{pk}") or "").strip(),
                    request=request,
                    battle=battle,
                )
                summary.injuries += 1
                if result.killed:
                    summary.kills += 1
                    summary.killed_names.append(fighter.name)

    return summary


@login_required
def post_battle_updates(request, id):
    """
    Bulk-edit a whole gang's post-battle results in one grid: add XP, adjust
    counters, apply injuries, and edit notes. Campaign mode only; open to the
    list owner and the campaign arbitrator.

    **Context**

    ``list``
        The :model:`core.List` being updated.
    ``form``
        A :class:`PostBattleUpdatesForm` bound to the list's fighters.
    ``rows``
        Per-fighter rows pairing each fighter with its bound form fields.

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

    if request.method == "POST":
        form = PostBattleUpdatesForm(request.POST, fighters=fighters, battles=battles)
        if form.is_valid():
            summary = _apply(request, lst, fighters, form)
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
            except (ValueError, TypeError):
                battle_param = None
        if battle_param and battles.filter(pk=battle_param).exists():
            initial["battle"] = battle_param
        form = PostBattleUpdatesForm(
            fighters=fighters, battles=battles, initial=initial
        )

    rows = _build_rows(fighters, form)
    return render(
        request,
        "core/list_post_battle_updates.html",
        {"list": lst, "form": form, "rows": rows, "has_battles": battles.exists()},
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
        rows.append(
            {
                "fighter": fighter,
                "xp": form[f"xp_{pk}"],
                "injury": form[f"injury_{pk}"],
                "injury_reason": form[f"injury_reason_{pk}"],
                "counters": counters,
                "private_notes": form[f"private_notes_{pk}"],
            }
        )
    return rows
