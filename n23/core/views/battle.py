from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.http import get_return_url, safe_redirect
from gyrinx.state_machine import InvalidStateTransition
from n23.core.events import EventNoun
from n23.core.forms.battle import (
    BattleEndForm,
    BattleForm,
    BattleNoteForm,
    BattleRolesForm,
)
from n23.core.handlers.battle import (
    battle_not_ready_gangs,
    battle_start_crew_rows,
    battle_timeline,
    charge_crew_spending,
    handle_battle_end,
    notify_battle_participants,
)
from n23.core.handlers.crew import crew_spread_rating, crew_stash_totals
from n23.core.models import Battle, Campaign, CampaignAction
from n23.core.models.crew import Crew


def _top_rating(values):
    """The highest rating in ``values`` when at least two are known, else None —
    a gap only means something when there is something to compare against."""
    known = [v for v in values if v is not None]
    return max(known) if len(known) >= 2 else None


def _delta(top, rating):
    """How far ``rating`` sits below ``top``, or None when there is nothing to
    say (no top to compare against, no rating, or this side *is* the top)."""
    if top is None or rating is None or rating >= top:
        return None
    return top - rating


class BattleDetailView(generic.DetailView):
    """
    Display a single :model:`core.Battle` object.

    **Context**

    ``battle``
        The requested :model:`core.Battle` object.
    ``can_edit``
        Whether the current user can edit this battle.
    ``can_add_notes``
        Whether the current user can add notes to this battle.
    ``notes``
        All notes for this battle.
    ``user_note``
        The current user's note if they have one.
    ``participant_groups``
        Participants grouped by role option for display.
    ``state_display``
        Human-readable label for the current battle state.
    ``can_start`` / ``can_end``
        Whether the current user can start or end the battle (managers only).

    **Template**

    :template:`core/battle/battle.html`
    """

    template_name = "core/battle/battle.html"
    context_object_name = "battle"

    def get_object(self):
        """Retrieve the Battle by its id."""
        battle = get_object_or_404(
            Battle.objects.select_related("campaign", "owner").prefetch_related(
                "winners",
                "notes__owner",
            ),
            id=self.kwargs["id"],
        )
        return battle

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        battle = self.object
        user = self.request.user

        if user.is_authenticated:
            context["can_edit"] = battle.can_edit(user)
            context["can_manage"] = battle.can_manage(user)
            context["can_unarchive"] = battle.can_unarchive(user)
            context["can_add_notes"] = battle.can_add_notes(user)
            # Check if user already has a note
            context["user_note"] = battle.notes.filter(owner=user).first()
        else:
            context["can_edit"] = False
            context["can_manage"] = False
            context["can_unarchive"] = False
            context["can_add_notes"] = False
            context["user_note"] = None

        # Battle state, plus the start/end actions for people who can manage it.
        context["state_display"] = battle.states.display
        context["state_current"] = battle.states.current
        context["can_start"] = context["can_manage"] and battle.can_start()
        context["can_end"] = context["can_manage"] and battle.can_end()

        # How the battle finished. An ended battle with no recorded result is
        # not a draw — battles ended before results were captured look exactly
        # like this, and must not be labelled as draws.
        ended = battle.states.current == Battle.POST_BATTLE
        context["show_draw_note"] = ended and battle.is_draw
        context["show_no_result_note"] = ended and not battle.result_recorded

        # Get all notes ordered by creation date
        context["notes"] = battle.notes.select_related("owner").order_by("created")

        # Get associated campaign actions with related data
        context["actions"] = battle.get_actions().select_related("user", "list")

        # Where the battle has got to, as ordered steps. Read-only.
        context["timeline"] = battle_timeline(battle)

        # Participants grouped by role, each gang carrying its rating and its
        # crew (battle flow step 3: a virtual sub-gang per participating gang).
        self._add_participant_context(context, battle, user)

        return context

    def _add_participant_context(self, context, battle, user):
        """Build the participants table: gangs grouped by role, each carrying its
        rating and its crew inlined as a sub-row (or an 'add crew' affordance).
        """
        # One crew summary per gang that has a live one, keyed by gang id.
        # Archived crews are withdrawn records — excluded here so the gang shows
        # the "add crew" affordance again rather than a stale crew sub-row.
        crews = list(
            battle.crews.filter(archived=False)
            # ``battle`` for readiness_open: it reads the battle's state, and
            # this loop asks every crew.
            .select_related("list", "battle")
            .prefetch_related("members", "line_items")
        )
        # Every crew's brought-stash total in one load. Left to themselves the
        # crews would each pay a full equipment prefetch chain — a dozen queries
        # or more apiece, on a page that shows one crew per gang.
        stash_totals = crew_stash_totals(crews)
        # Crews whose gang can no longer cover what they are spending. Marking
        # ready is guarded, but a gang can spend elsewhere afterwards, so a crew
        # can sit "ready" and unaffordable. Warning beats silently un-readying
        # them: the money is safe either way (the charge floors at zero and
        # records the shortfall), it is the arbitrator who needs to know.
        overspending = []
        crew_by_gang = {}
        for crew in crews:
            if crew.readiness_open:
                blocker = crew.ready_blocker()
                if blocker:
                    overspending.append({"crew": crew, **blocker})
            # The one definition of what a crew is worth right now (pending draw
            # → unknown; whole-gang draft → forecast; else its live/played
            # rating), shared with the crew-page spread so the two can't drift.
            # A forecast is flagged provisional; a pending draw returns no rating.
            rating, is_forecast = crew_spread_rating(crew, stash_totals.get(crew.id, 0))
            # Balancing sits outside that rating by design, so the table can show
            # the gap the allowance was granted for and the gap that remains once
            # it is spent. A crew with no allowance has identical figures either
            # side, which is the honest answer rather than a missing one.
            balancing = crew.balancing_total()
            pending = crew.pending_roll
            # The rating shown is what the gang would field now, or, once the
            # battle has ended, what it did field. Either way, flag when that
            # isn't the number the crew was picked at — the arbitrator needs to
            # see the crew has changed since selection. A forecast or a pending
            # draw has nothing to compare against: the crew hasn't been picked,
            # or its draw hasn't resolved.
            note = None if (pending or is_forecast) else crew.rating_note()
            crew_by_gang[crew.list_id] = {
                "crew": crew,
                "method_label": crew.method_label(),
                "rating": rating,
                "balancing": balancing,
                "rating_after": None if rating is None else rating + balancing,
                "pending_roll": pending,
                "is_forecast": is_forecast,
                "is_ready": crew.is_ready,
                "show_rating_note": bool(note and note["differs"]),
                "rating_note": note,
            }

        is_over = battle.states.current == Battle.POST_BATTLE

        # Whether this user may add a crew to a gang that hasn't got one yet.
        # The outer guard is a fast-path so anon/archived skip the per-gang
        # work; once the battle is over there is no crew left to pick.
        can_add_any = (
            user.is_authenticated
            and not is_over
            and not (battle.archived or battle.campaign.archived)
        )

        # Whether this user may record post-battle results for a gang — an
        # affordance under the gang's name once the battle is over.
        can_record_any = (
            user.is_authenticated
            and is_over
            and not (battle.archived or battle.campaign.archived)
        )
        is_admin = can_record_any and battle.campaign.is_admin(user)

        # winners is prefetched in get_object(); read the cache, not a new query.
        winner_ids = {w.id for w in battle.winners.all()}

        # Every gang's rating, and every crew's (None for a gang with no crew or
        # a crew still mid-draw), collected as the loop runs so the top of each
        # can be found for the inline deltas below — no extra query.
        gang_ratings = []
        crew_ratings = []
        crew_ratings_after = []

        groups = []
        for group in battle.participants_grouped_by_role():
            rows = []
            for entry in group["participants"]:
                gang = entry.list
                crew = crew_by_gang.get(gang.id)
                gang_ratings.append(gang.rating_current)
                crew_ratings.append(crew["rating"] if crew is not None else None)
                crew_ratings_after.append(
                    crew["rating_after"] if crew is not None else None
                )
                rows.append(
                    {
                        "list": gang,
                        "is_winner": gang.id in winner_ids,
                        "rating": gang.rating_current,
                        "crew": crew,
                        "can_add_crew": (
                            crew is None
                            and can_add_any
                            and Crew.can_manage_new(user, battle, gang)
                        ),
                        "can_record_post_battle": (
                            can_record_any
                            # Only gangs the post-battle editor will accept.
                            and gang.is_campaign_mode
                            and not gang.archived
                            and (is_admin or gang.owner_id == user.id)
                        ),
                    }
                )
            groups.append({"role_option": group["role_option"], "participants": rows})
        context["overspending_crews"] = overspending
        context["participant_groups"] = groups
        # Hide the "No role" group header when nobody has a role assigned — with
        # no roles in play it is just noise above a single list of gangs.
        context["roles_in_use"] = any(g["role_option"] for g in groups)

        # Rating deltas shown inline next to each rating: how far each gang (and
        # each crew) sits below the highest. Numbers only — the players decide
        # what a gap means for their scenario. Built from figures already in
        # hand, so no extra query. A delta needs at least two known ratings to
        # mean anything; the top side (and any side with no known rating) shows
        # none.
        #
        # Crews get the comparison twice: once on the pre-balancing ratings (the
        # gap that earns an allowance) and once on the post-balancing ones (the
        # gap left after it is spent). Each is measured against the top of its
        # own column — spending an allowance can change *which* crew is top, so
        # reusing the pre-balancing leader would misreport the remaining gap.
        top_gang = _top_rating(gang_ratings)
        top_crew = _top_rating(crew_ratings)
        top_crew_after = _top_rating(crew_ratings_after)
        for group in groups:
            for row in group["participants"]:
                row["rating_delta"] = _delta(top_gang, row["rating"])
                if row["crew"] is not None:
                    row["crew"]["rating_delta"] = _delta(
                        top_crew, row["crew"]["rating"]
                    )
                    row["crew"]["rating_delta_after"] = _delta(
                        top_crew_after, row["crew"]["rating_after"]
                    )


@login_required
@transaction.atomic
def new_battle(request, campaign_id):
    """Create a new battle for a campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id)

    # Check permissions - a campaign admin (arbitrator), or any player with a
    # gang in the campaign, can create battles.
    is_arbitrator = campaign.is_admin(request.user)
    has_gang = campaign.lists.filter(owner=request.user).exists()
    if not (is_arbitrator or has_gang):
        messages.error(
            request,
            "Only the campaign arbitrator or players with a gang in the campaign can create battles.",
        )
        return HttpResponseRedirect(reverse("core:campaign", args=[campaign.id]))

    # Check campaign is in progress
    if not campaign.is_in_progress:
        messages.error(
            request, "Battles can only be created for campaigns in progress."
        )
        return HttpResponseRedirect(reverse("core:campaign", args=[campaign.id]))

    if request.method == "POST":
        form = BattleForm(request.POST, campaign=campaign)
        if form.is_valid():
            battle = form.save(commit=False)
            battle.campaign = campaign
            battle.owner = request.user
            battle.save()
            battle.set_participants(form.cleaned_data["participants"])

            # Log the battle creation event
            log_event(
                user=request.user,
                noun=EventNoun.BATTLE,
                verb=EventVerb.CREATE,
                object=battle,
                request=request,
                battle_name=battle.name,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
            )

            # Create a campaign action for the battle. The battle has not been
            # fought yet, so record it as created rather than claiming a result.
            participants_names = ", ".join(
                sorted(p.name for p in battle.participants.all())
            )
            description = f"Battle created: {battle.mission}"
            if battle.date:
                description += f" on {battle.date}"
            if participants_names:
                description += f". Gangs: {participants_names}."

            CampaignAction.objects.create(
                campaign=campaign,
                user=request.user,
                battle=battle,
                description=description,
                owner=request.user,
            )

            # Tell the owners of the other participating gangs their gang is in
            # a battle. Every participant is newly added here, so pass them all;
            # the handler skips the acting user's own gangs.
            notify_battle_participants(
                user=request.user,
                battle=battle,
                added_lists=form.cleaned_data["participants"],
            )

            messages.success(request, f"Battle '{battle.name}' created successfully!")
            return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))
    else:
        form = BattleForm(campaign=campaign)

    return render(
        request,
        "core/battle/battle_new.html",
        {"form": form, "campaign": campaign},
    )


@login_required
@transaction.atomic
def edit_battle(request, id):
    """Edit an existing battle."""
    battle = get_object_or_404(Battle.objects.select_related("campaign"), id=id)

    # Check permissions
    if not battle.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this battle.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if request.method == "POST":
        form = BattleForm(
            request.POST,
            instance=battle,
            campaign=battle.campaign,
            include_winners=True,
        )
        if form.is_valid():
            if "result" in form.cleaned_data:
                battle.result = form.cleaned_data["result"]
            # Capture the current participants before syncing so we can notify
            # only the gangs newly added by this edit (removals get nothing).
            existing_participant_ids = set(
                battle.participants.values_list("pk", flat=True)
            )
            form.save()
            battle.set_participants(form.cleaned_data["participants"])
            battle.winners.set(form.cleaned_data.get("winners") or [])

            newly_added = [
                lst
                for lst in form.cleaned_data["participants"]
                if lst.pk not in existing_participant_ids
            ]
            notify_battle_participants(
                user=request.user,
                battle=battle,
                added_lists=newly_added,
            )

            # Log the battle update event
            log_event(
                user=request.user,
                noun=EventNoun.BATTLE,
                verb=EventVerb.UPDATE,
                object=battle,
                request=request,
                battle_name=battle.name,
                campaign_id=str(battle.campaign.id),
                campaign_name=battle.campaign.name,
            )

            messages.success(request, "Battle updated successfully!")
            return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))
    else:
        form = BattleForm(
            instance=battle, campaign=battle.campaign, include_winners=True
        )

    return render(
        request,
        "core/battle/battle_edit.html",
        {"form": form, "battle": battle},
    )


def _transition_battle(request, battle, new_status, invalid_message):
    """Apply a forward state transition, then log and flash the result."""
    try:
        battle.states.transition_to(new_status)
    except InvalidStateTransition:
        messages.error(request, invalid_message)
    else:
        log_event(
            user=request.user,
            noun=EventNoun.BATTLE,
            verb=EventVerb.UPDATE,
            object=battle,
            request=request,
            action="state_changed",
            battle_state=new_status,
            battle_name=battle.name,
            campaign_id=str(battle.campaign.id),
            campaign_name=battle.campaign.name,
        )
        messages.success(request, f"Battle moved to {battle.states.display}.")
    return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))


@login_required
def start_battle(request, id):
    """Move a battle from pre-battle to in-progress, via a confirmation page."""
    battle = get_object_or_404(Battle.objects.select_related("campaign"), id=id)

    if not battle.can_manage(request.user):
        messages.error(request, "You don't have permission to manage this battle.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if request.method == "POST":
        # Starting and charging are one unit of work. Charging in its own
        # transaction and then transitioning would take a gang's credits for a
        # battle that never started — and worse, credits_charged_at would be
        # set, so the retry that did start it would charge nobody.
        #
        # The transition goes first inside the block so an invalid state returns
        # before any credits move; a failure in the charge rolls the transition
        # back with it.
        try:
            with transaction.atomic():
                battle.states.transition_to(Battle.IN_PROGRESS)
                charges = charge_crew_spending(user=request.user, battle=battle)
        except InvalidStateTransition:
            messages.error(request, "This battle cannot be started.")
            return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

        log_event(
            user=request.user,
            noun=EventNoun.BATTLE,
            verb=EventVerb.UPDATE,
            object=battle,
            request=request,
            action="state_changed",
            battle_state=Battle.IN_PROGRESS,
            battle_name=battle.name,
            campaign_id=str(battle.campaign.id),
            campaign_name=battle.campaign.name,
        )
        messages.success(request, f"Battle moved to {battle.states.display}.")
        for result in charges:
            if result.shortfall:
                messages.warning(
                    request,
                    f"{result.crew.list.name} could only cover {result.charged}¢ of "
                    f"{result.owed}¢ — {result.shortfall}¢ is unpaid.",
                )
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if not battle.can_start():
        messages.error(request, "This battle cannot be started.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    return render(
        request,
        "core/battle/battle_start.html",
        {
            "battle": battle,
            "crew_rows": battle_start_crew_rows(battle),
            "not_ready": battle_not_ready_gangs(battle),
        },
    )


@login_required
def end_battle(request, id):
    """End a battle, recording who won (or that it was a draw)."""
    battle = get_object_or_404(Battle.objects.select_related("campaign"), id=id)

    if not battle.can_manage(request.user):
        messages.error(request, "You don't have permission to manage this battle.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    # Guarded before the POST branch so re-submitting an already-ended battle
    # short-circuits rather than doing form work first.
    if not battle.can_end():
        if battle.states.current == Battle.POST_BATTLE:
            messages.error(request, "This battle has already been ended.")
        else:
            messages.error(request, "This battle cannot be ended.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if request.method == "POST":
        form = BattleEndForm(request.POST, battle=battle)
        if form.is_valid():
            is_draw = form.cleaned_data["result"] == Battle.RESULT_DRAW
            try:
                handle_battle_end(
                    user=request.user,
                    battle=battle,
                    winners=form.cleaned_data.get("winners") or [],
                    is_draw=is_draw,
                )
            except ValidationError as e:
                messages.error(request, e.messages[0])
                return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

            log_event(
                user=request.user,
                noun=EventNoun.BATTLE,
                verb=EventVerb.UPDATE,
                object=battle,
                request=request,
                action="state_changed",
                battle_state=Battle.POST_BATTLE,
                battle_result=Battle.RESULT_DRAW if is_draw else Battle.RESULT_WINNERS,
                battle_name=battle.name,
                campaign_id=str(battle.campaign.id),
                campaign_name=battle.campaign.name,
            )

            messages.success(request, "Battle ended and result recorded.")
            return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))
    else:
        form = BattleEndForm(battle=battle)

    return render(
        request,
        "core/battle/battle_end.html",
        {
            "battle": battle,
            "form": form,
            "has_participants": battle.participants.exists(),
            # The template's script compares against this rather than
            # hardcoding the stored value.
            "draw_value": Battle.RESULT_DRAW,
        },
    )


@login_required
@transaction.atomic
def edit_battle_roles(request, id):
    """Assign roles (e.g. Attacker/Defender) to a battle's participants."""
    battle = get_object_or_404(Battle.objects.select_related("campaign"), id=id)

    if not battle.can_manage(request.user):
        messages.error(request, "You don't have permission to manage this battle.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if not battle.participant_entries.exists():
        messages.info(request, "Add participants before assigning roles.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if request.method == "POST":
        form = BattleRolesForm(request.POST, battle=battle)
        if form.is_valid():
            form.save()

            log_event(
                user=request.user,
                noun=EventNoun.BATTLE,
                verb=EventVerb.UPDATE,
                object=battle,
                request=request,
                action="roles_updated",
                battle_name=battle.name,
                campaign_id=str(battle.campaign.id),
                campaign_name=battle.campaign.name,
            )

            messages.success(request, "Participant roles updated.")
            return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))
    else:
        form = BattleRolesForm(battle=battle)

    return render(
        request,
        "core/battle/battle_roles.html",
        {"form": form, "battle": battle},
    )


@login_required
@transaction.atomic
def archive_battle(request, id):
    """Archive or unarchive a battle.

    Archiving hides the battle from the campaign's battle lists and blocks
    further edits until it is unarchived. Only the battle owner or campaign
    owner can archive or unarchive.
    """
    battle = get_object_or_404(Battle.objects.select_related("campaign"), id=id)

    if not (battle.can_edit(request.user) or battle.can_unarchive(request.user)):
        messages.error(request, "You don't have permission to archive this battle.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if request.method == "POST":
        if request.POST.get("archive") == "1" and battle.can_edit(request.user):
            battle.archive()
            log_event(
                user=request.user,
                noun=EventNoun.BATTLE,
                verb=EventVerb.ARCHIVE,
                object=battle,
                request=request,
                battle_name=battle.name,
                campaign_id=str(battle.campaign.id),
                campaign_name=battle.campaign.name,
            )
            messages.success(request, f"Battle '{battle.name}' archived.")
        elif battle.can_unarchive(request.user):
            battle.unarchive()
            log_event(
                user=request.user,
                noun=EventNoun.BATTLE,
                verb=EventVerb.RESTORE,
                object=battle,
                request=request,
                battle_name=battle.name,
                campaign_id=str(battle.campaign.id),
                campaign_name=battle.campaign.name,
            )
            messages.success(request, f"Battle '{battle.name}' unarchived.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    return render(
        request,
        "core/battle/battle_archive.html",
        {"battle": battle},
    )


@login_required
def add_battle_note(request, battle_id):
    """Add a note to a battle."""
    battle = get_object_or_404(Battle, id=battle_id)

    # Check permissions
    if not battle.can_add_notes(request.user):
        messages.error(
            request, "You don't have permission to add notes to this battle."
        )
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    # Get the return URL from query params, with fallback to default
    default_url = reverse("core:battle", args=[battle.id])
    return_url = get_return_url(request, default_url)

    # Check if user already has a note
    existing_note = battle.notes.filter(owner=request.user).first()

    if request.method == "POST":
        if existing_note:
            form = BattleNoteForm(request.POST, instance=existing_note)
        else:
            form = BattleNoteForm(request.POST)

        if form.is_valid():
            note = form.save(commit=False)
            note.battle = battle
            note.owner = request.user
            is_new_note = note.pk is None
            note.save()

            # Log the note creation/update event
            log_event(
                user=request.user,
                noun=EventNoun.BATTLE,
                verb=EventVerb.CREATE if is_new_note else EventVerb.UPDATE,
                object=battle,
                request=request,
                action="note_added" if is_new_note else "note_updated",
                battle_name=battle.name,
                campaign_id=str(battle.campaign.id),
                campaign_name=battle.campaign.name,
            )

            messages.success(request, "Battle report saved.")
            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        if existing_note:
            form = BattleNoteForm(instance=existing_note)
        else:
            form = BattleNoteForm()

    return render(
        request,
        "core/battle/battle_note_add.html",
        {
            "form": form,
            "battle": battle,
            "existing_note": existing_note,
            "return_url": return_url,
        },
    )
