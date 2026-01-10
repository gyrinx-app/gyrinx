"""Fighter narrative and info editing views."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.core.forms.list import EditListFighterInfoForm, EditListFighterNarrativeForm
from gyrinx.core.models.events import EventField, EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def edit_list_fighter_narrative(request, id, fighter_id):
    """
    Edit the narrative of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterNarrativeForm for editing fighter narrative.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_narrative_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get the return URL from query params or POST data, with fallback to default
    default_url = (
        reverse("core:list-about", args=(lst.id,)) + f"#about-{str(fighter.id)}"
    )
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = EditListFighterNarrativeForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()

            # Log the narrative update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                field="narrative",
                narrative_length=len(fighter.narrative) if fighter.narrative else 0,
            )

            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = EditListFighterNarrativeForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_narrative_edit.html",
        {
            "form": form,
            "list": lst,
            "error_message": error_message,
            "return_url": return_url,
        },
    )


@login_required
def edit_list_fighter_info(request, id, fighter_id):
    """
    Edit the info section (image, save, notes) of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterInfoForm for editing fighter info.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_info_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get the return URL from query params or POST data, with fallback to default
    default_url = (
        reverse("core:list-about", args=(lst.id,)) + f"#about-{str(fighter.id)}"
    )
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = EditListFighterInfoForm(request.POST, request.FILES, instance=fighter)
        if form.is_valid():
            form.save()

            # Log the info update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                field=EventField.INFO,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                has_image=bool(fighter.image),
                image_url=fighter.image.url if fighter.image else None,
                has_save=bool(fighter.save_roll),
                has_private_notes=bool(fighter.private_notes),
            )

            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = EditListFighterInfoForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_info_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
            "error_message": error_message,
            "return_url": return_url,
        },
    )
