"""Fighter stats editing views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.core.forms.list import EditListFighterStatsForm
from gyrinx.core.models.events import EventField, EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter, ListFighterStatOverride
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
@transaction.atomic
def list_fighter_stats_edit(request, id, fighter_id):
    """
    Edit the stat overrides of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterStatsForm for editing fighter stats.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_stats_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get the return URL from query params or POST data, with fallback to default
    default_url = reverse("core:list-fighter-edit", args=(lst.id, fighter.id))
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = EditListFighterStatsForm(request.POST, fighter=fighter)
        if form.is_valid():
            # Check if the fighter has a custom statline
            has_custom_statline = hasattr(fighter.content_fighter, "custom_statline")

            if has_custom_statline:
                # Handle custom statline overrides
                statline = fighter.content_fighter.custom_statline

                # Delete existing overrides
                fighter.stat_overrides.all().delete()

                # Create new overrides
                for field_name, value in form.cleaned_data.items():
                    if field_name.startswith("stat_") and value:
                        stat_id = field_name.replace("stat_", "")
                        # Find the stat definition
                        stat_def = statline.statline_type.stats.get(id=stat_id)

                        # Create the override
                        ListFighterStatOverride.objects.create(
                            list_fighter=fighter,
                            content_stat=stat_def,
                            value=value,
                            owner=request.user,
                        )
            else:
                # Handle legacy overrides
                for field_name, value in form.cleaned_data.items():
                    if field_name.endswith("_override"):
                        setattr(fighter, field_name, value or None)

                fighter.save()

            # Log the stat update event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                field=EventField.STATS,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                has_custom_statline=has_custom_statline,
            )

            # Use safe redirect with fallback
            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = EditListFighterStatsForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_stats_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
            "error_message": error_message,
            "return_url": return_url,
        },
    )
