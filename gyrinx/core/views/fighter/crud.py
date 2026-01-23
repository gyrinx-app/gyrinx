"""Fighter CRUD views (create, read, update, delete, archive, restore, kill, resurrect)."""

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic
from django.views.decorators.clickjacking import xframe_options_exempt

from gyrinx import messages
from gyrinx.core.forms.list import CloneListFighterForm, ListFighterForm
from gyrinx.core.handlers.fighter import (
    FighterCloneParams,
    handle_fighter_archive_toggle,
    handle_fighter_clone,
    handle_fighter_deletion,
    handle_fighter_edit,
    handle_fighter_hire,
    handle_fighter_kill,
    handle_fighter_resurrect,
)
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def new_list_fighter(request, id):
    """
    Add a new :model:`core.ListFighter` to an existing :model:`core.List`.

    **Context**

    ``form``
        A ListFighterForm for adding a new fighter.
    ``list``
        The :model:`core.List` to which this fighter will be added.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_new.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = ListFighter(list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            fighter = form.save(commit=False)
            fighter.list = lst
            fighter.owner = lst.owner

            # Call handler to handle business logic
            try:
                result = handle_fighter_hire(
                    user=request.user,
                    lst=lst,
                    fighter=fighter,
                )
            except DjangoValidationError as e:
                error_message = messages.validation(request, e)
                form = ListFighterForm(request.POST, instance=fighter)
                return render(
                    request,
                    "core/list_fighter_new.html",
                    {"form": form, "list": lst, "error_message": error_message},
                )

            # Log the fighter creation event (HTTP-specific)
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.CREATE,
                object=result.fighter,
                request=request,
                fighter_name=result.fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
            )

            # Redirect with flash parameter (HTTP-specific)
            query_params = urlencode(dict(flash=result.fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(result.fighter.id)}"
            )

    else:
        form = ListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_new.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter(request, id, fighter_id):
    """
    Edit an existing :model:`core.ListFighter` within a :model:`core.List`.

    **Context**

    ``form``
        A ListFighterForm for editing fighter details.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    error_message = None
    if request.method == "POST":
        # Capture old values before form.is_valid() modifies the instance
        old_name = fighter.name
        old_content_fighter = fighter.content_fighter
        old_legacy_content_fighter = fighter.legacy_content_fighter
        old_category_override = fighter.category_override
        old_cost_override = fighter.cost_override

        form = ListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            # Form's is_valid() already applied new values to fighter
            # Call handler to save and track changes via ListAction
            handle_fighter_edit(
                user=request.user,
                fighter=fighter,
                old_name=old_name,
                old_content_fighter=old_content_fighter,
                old_legacy_content_fighter=old_legacy_content_fighter,
                old_category_override=old_category_override,
                old_cost_override=old_cost_override,
            )

            # Log the fighter update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
            )

            query_params = urlencode(dict(flash=fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )
    else:
        form = ListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def clone_list_fighter(request: HttpRequest, id, fighter_id):
    """
    Clone an existing :model:`core.ListFighter` to the same or another :model:`core.List`.

    **Context**

    ``form``
        A CloneListFighterForm for entering the name and details of the new fighter.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to be cloned.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_clone.html`
    """
    lst = get_clean_list_or_404(List, id=id)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
    )

    error_message = None
    if request.method == "POST":
        form = CloneListFighterForm(request.POST, fighter=fighter, user=request.user)
        if form.is_valid():
            try:
                # Prepare clone params
                # Handle category_override based on checkbox
                # If fighter has an override and checkbox is checked, preserve it
                # Otherwise, clear it
                category_override = None
                if fighter.category_override and form.cleaned_data.get(
                    "clone_category_override", False
                ):
                    category_override = fighter.category_override

                clone_params = FighterCloneParams(
                    name=form.cleaned_data["name"],
                    content_fighter=form.cleaned_data["content_fighter"],
                    target_list=form.cleaned_data["list"],
                    category_override=category_override,
                )

                # Handle the clone operation (clones fighter, creates ListAction, handles credits)
                result = handle_fighter_clone(
                    user=request.user,
                    source_fighter=fighter,
                    clone_params=clone_params,
                )

                # Log the fighter clone event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.CLONE,
                    object=result.fighter,
                    request=request,
                    fighter_name=result.fighter.name,
                    list_id=str(result.fighter.list.id),
                    list_name=result.fighter.list.name,
                    source_fighter_id=str(fighter.id),
                    source_fighter_name=fighter.name,
                )

                query_params = urlencode(dict(flash=result.fighter.id))
                return HttpResponseRedirect(
                    reverse("core:list", args=(result.fighter.list.id,))
                    + f"?{query_params}"
                    + f"#{str(result.fighter.id)}"
                )
            except DjangoValidationError as e:
                error_message = str(e)
    else:
        form = CloneListFighterForm(
            fighter=fighter,
            initial={
                "name": f"{fighter.name} (Clone)",
                "content_fighter": fighter.content_fighter,
                "list": fighter.list,
            },
            user=request.user,
        )

    return render(
        request,
        "core/list_fighter_clone.html",
        {"form": form, "list": lst, "fighter": fighter, "error_message": error_message},
    )


@login_required
def archive_list_fighter(request, id, fighter_id):
    """
    Archive or unarchive a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be archived or unarchived.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_archive.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    if request.method == "POST":
        # Determine archive/unarchive based on POST data
        archive = request.POST.get("archive") == "1"

        # Only process if archiving or if fighter is currently archived (for unarchive)
        if archive or fighter.archived:
            # Call handler to perform business logic
            result = handle_fighter_archive_toggle(
                user=request.user,
                lst=lst,
                fighter=fighter,
                archive=archive,
                request_refund=request.POST.get("refund") == "on",
            )

            # Log the event based on operation
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.ARCHIVE if result.archived else EventVerb.RESTORE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
            )

        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    # Calculate fighter cost for template
    fighter_cost = fighter.cost_int()

    return render(
        request,
        "core/list_fighter_archive.html",
        {"fighter": fighter, "list": lst, "fighter_cost": fighter_cost},
    )


@login_required
def restore_list_fighter(request, id, fighter_id):
    """
    Restore an archived :model:`core.ListFighter`.

    Shows a confirmation page on GET, performs the restore on POST.

    **Context**

    ``fighter``
        The archived :model:`core.ListFighter` to be restored.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter_cost``
        The cost of the fighter in credits.

    **Template**

    :template:`core/list_fighter_restore_confirm.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
        archived=True,  # Only allow restoring archived fighters
    )

    if request.method == "POST":
        # Call handler to perform business logic (unarchive)
        handle_fighter_archive_toggle(
            user=request.user,
            lst=lst,
            fighter=fighter,
            archive=False,  # Unarchive/restore
            request_refund=False,
        )

        # Log the restore event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.RESTORE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
        )

        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    # Calculate fighter cost for template
    fighter_cost = fighter.cost_int()

    return render(
        request,
        "core/list_fighter_restore_confirm.html",
        {"fighter": fighter, "list": lst, "fighter_cost": fighter_cost},
    )


@login_required
def kill_list_fighter(request, id, fighter_id):
    """
    Mark a :model:`core.ListFighter` as dead in campaign mode.
    This transfers all equipment to the stash and sets cost to 0.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be marked as dead.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_kill.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Only allow killing fighters in campaign mode
    if not lst.is_campaign_mode:
        messages.error(request, "Fighters can only be killed in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Don't allow killing stash fighters
    if fighter.is_stash:
        messages.error(request, "Cannot kill the stash.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        # Handle fighter death (transfers equipment, creates ListAction and CampaignAction)
        result = handle_fighter_kill(
            user=request.user,
            lst=lst,
            fighter=fighter,
        )

        # Log the fighter kill event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.DELETE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="killed",
        )

        messages.success(request, result.description)
        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    return render(
        request,
        "core/list_fighter_kill.html",
        {"fighter": fighter, "list": lst},
    )


@login_required
def resurrect_list_fighter(request, id, fighter_id):
    """
    Change the status of a :model:`core.ListFighter` from dead to alive in campaign mode.
    This sets cost to the original value of the fighter, but does not
    restore equipment transferred to the stash when the fighter was killed.

    **Context**

    ``fighter``
        The dead :model:`core.ListFighter` to be marked as alive.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_resurrect.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    if not lst.is_campaign_mode:
        messages.error(request, "Fighters can only be resurrected in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Don't resurrect stash fighters - just in case
    if fighter.is_stash:
        messages.error(request, "Cannot resurrect the stash.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        if fighter.injury_state != ListFighter.DEAD:
            messages.error(request, "Only dead fighters can be resurrected.")
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

        # Handle resurrection (restores cost, creates ListAction and CampaignAction)
        handle_fighter_resurrect(
            user=request.user,
            fighter=fighter,
        )

        # Log the resurrection event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.ACTIVATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="resurrected",
        )

        messages.success(
            request,
            f"{fighter.name} has been resurrected. They can now be re-equipped from the stash.",
        )

        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    return render(
        request, "core/list_fighter_resurrect.html", {"fighter": fighter, "list": lst}
    )


@login_required
def delete_list_fighter(request, id, fighter_id):
    """
    Delete a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be deleted.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_delete.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    if request.method == "POST":
        # Store fighter name for logging before handler deletes it
        fighter_name = fighter.name

        # Log the fighter delete event before deletion
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.DELETE,
            object=fighter,
            request=request,
            fighter_name=fighter_name,
            list_id=str(lst.id),
            list_name=lst.name,
        )

        # Call handler to perform business logic
        handle_fighter_deletion(
            user=request.user,
            lst=lst,
            fighter=fighter,
            request_refund=request.POST.get("refund") == "on",
        )

        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Calculate fighter cost for template
    fighter_cost = fighter.cost_int()

    return render(
        request,
        "core/list_fighter_delete.html",
        {"fighter": fighter, "list": lst, "fighter_cost": fighter_cost},
    )


@xframe_options_exempt
def embed_list_fighter(request, id, fighter_id):
    """
    Display a single :model:`core.ListFighter` object in an embedded view.

    **Context**

    ``fighter``
        The requested :model:`core.ListFighter` object.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_embed.html`
    """
    lst = get_clean_list_or_404(List, id=id)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Log the embed view event
    log_event(
        user=request.user
        if hasattr(request, "user") and request.user.is_authenticated
        else None,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.VIEW,
        object=fighter,
        request=request,
        list_id=str(lst.id),
        list_name=lst.name,
        fighter_id=str(fighter.id),
        fighter_name=fighter.name,
        embed=True,
    )

    return render(
        request,
        "core/list_fighter_embed.html",
        {"fighter": fighter, "list": lst},
    )


class ListArchivedFightersView(LoginRequiredMixin, generic.ListView):
    """
    Display a page with archived :model:`core.ListFighter` objects within a given :model:`core.List`.

    **Context**

    ``list``
        The requested :model:`core.List` object (retrieved by ID).

    **Template**

    :template:`core/list_archived_fighters.html`
    """

    template_name = "core/list_archived_fighters.html"
    context_object_name = "list"

    def get_queryset(self):
        """
        Retrieve the :model:`core.List` by its `id`, ensuring it's owned by the current user.
        """
        return get_object_or_404(List, id=self.kwargs["id"], owner=self.request.user)
