from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.core.forms.battle import (
    BattleEndForm,
    BattleForm,
    BattleNoteForm,
    BattleRolesForm,
)
from gyrinx.core.handlers.battle import handle_battle_end
from gyrinx.core.handlers.crew import crew_whole_gang_projection
from gyrinx.core.models import Battle, Campaign, CampaignAction
from gyrinx.core.models.crew import Crew
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.state_machine import InvalidStateTransition
from gyrinx.core.utils import get_return_url, safe_redirect


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
            .select_related("list")
            .prefetch_related("members")
        )
        crew_by_gang = {}
        for crew in crews:
            # Only the rating and pending-roll flag are needed here, so skip the
            # full receipt() (which also builds the extras breakdown). A pending
            # draw leaves the rating unknown, so don't compute it at all.
            pending = crew.pending_roll
            # A whole-gang crew enrols nobody until it is confirmed, so its own
            # rating would read 0¢ here — "no fighters" rather than "the whole
            # gang attends". Forecast it the same way the crew page does.
            forecast = (
                not crew.is_locked and crew.is_whole_gang and not crew.members.all()
            )
            if pending:
                rating = None
            elif forecast:
                rating = crew_whole_gang_projection(crew)["total"]
            else:
                rating = crew.rating()
            # The rating shown is what the gang would field now, or, once the
            # battle has ended, what it did field. Either way, flag when that
            # isn't the number the crew was picked at — the arbitrator needs to
            # see the crew has changed since selection. A forecast has nothing
            # to compare against: the crew hasn't been picked yet.
            note = None if (pending or forecast) else crew.rating_note()
            crew_by_gang[crew.list_id] = {
                "crew": crew,
                "method_label": crew.method_label(),
                "rating": rating,
                "pending_roll": pending,
                "is_forecast": forecast,
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

        groups = []
        for group in battle.participants_grouped_by_role():
            rows = []
            for entry in group["participants"]:
                gang = entry.list
                crew = crew_by_gang.get(gang.id)
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
        context["participant_groups"] = groups


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
            form.save()
            battle.set_participants(form.cleaned_data["participants"])
            battle.winners.set(form.cleaned_data.get("winners") or [])

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
        return _transition_battle(
            request, battle, Battle.IN_PROGRESS, "This battle cannot be started."
        )

    if not battle.can_start():
        messages.error(request, "This battle cannot be started.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    return render(request, "core/battle/battle_start.html", {"battle": battle})


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

            messages.success(request, "Note saved successfully!")
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
