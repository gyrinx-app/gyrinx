from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.core.forms.battle import BattleForm, BattleNoteForm
from gyrinx.core.models import Battle, Campaign, CampaignAction
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import safe_redirect


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

    **Template**

    :template:`core/battle/battle.html`
    """

    template_name = "core/battle/battle.html"
    context_object_name = "battle"

    def get_object(self):
        """Retrieve the Battle by its id."""
        battle = get_object_or_404(
            Battle.objects.select_related("campaign", "owner").prefetch_related(
                "participants",
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
            context["can_add_notes"] = battle.can_add_notes(user)
            # Check if user already has a note
            context["user_note"] = battle.notes.filter(owner=user).first()
        else:
            context["can_edit"] = False
            context["can_add_notes"] = False
            context["user_note"] = None

        # Get all notes ordered by creation date
        context["notes"] = battle.notes.select_related("owner").order_by("created")

        # Get associated campaign actions with related data
        context["actions"] = battle.get_actions().select_related("user", "list")

        return context


@login_required
def new_battle(request, campaign_id):
    """Create a new battle for a campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id)

    # Check permissions - only users with a list in the campaign can create battles
    if not campaign.lists.filter(owner=request.user).exists():
        messages.error(
            request, "Only players with a gang in the campaign can create battles."
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
            form.save_m2m()  # Save many-to-many relationships

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

            # Create a campaign action for the battle
            participants_names = ", ".join([p.name for p in battle.participants.all()])
            winners_names = ", ".join([w.name for w in battle.winners.all()])

            description = f"Battle Report created: {battle.mission} on {battle.date}. {participants_names} participated."
            outcome = f"Winners: {winners_names}" if winners_names else "Draw"

            CampaignAction.objects.create(
                campaign=campaign,
                user=request.user,
                battle=battle,
                description=description,
                outcome=outcome,
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
def edit_battle(request, id):
    """Edit an existing battle."""
    battle = get_object_or_404(Battle.objects.select_related("campaign"), id=id)

    # Check permissions
    if not battle.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this battle.")
        return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))

    if request.method == "POST":
        form = BattleForm(request.POST, instance=battle, campaign=battle.campaign)
        if form.is_valid():
            form.save()

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
        form = BattleForm(instance=battle, campaign=battle.campaign)

    return render(
        request,
        "core/battle/battle_edit.html",
        {"form": form, "battle": battle},
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
    return_url = request.GET.get("return_url", default_url)

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
            # Get return URL from POST data (in case it was in the form)
            post_return_url = request.POST.get("return_url", return_url)
            # Use safe redirect with fallback
            return safe_redirect(request, post_return_url, fallback_url=default_url)
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
