"""Fighter stats editing views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.analytics.models import EventField, EventNoun, EventVerb, log_event
from gyrinx.http import get_return_url, safe_redirect
from n23.core.forms.list import EditListFighterStatsForm
from n23.core.models.list import List, ListFighter, ListFighterStatOverride
from n23.core.views.list.common import get_clean_list_or_404


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
            statline = getattr(fighter.content_fighter, "custom_statline", None)

            # Reconcile stat by stat, rather than clearing every override and
            # rebuilding from the submission. Wholesale rewriting means any
            # POST that omits a field silently drops that stat's override —
            # a stale page or a partial request would take the rest of the
            # fighter's stats with it. A field that was submitted blank is a
            # real instruction to clear that one.
            if statline is not None:
                for field_name, field in form.fields.items():
                    if field_name not in request.POST:
                        continue

                    stat_def = getattr(field, "stat_def", None)
                    if stat_def is None:
                        continue

                    value = form.cleaned_data.get(field_name)
                    if value:
                        ListFighterStatOverride.objects.update_or_create(
                            list_fighter=fighter,
                            content_stat=stat_def,
                            defaults={
                                "value": value,
                                "owner": request.user,
                                # An override cleared earlier and set again is
                                # the same row; leaving it archived would store
                                # the value without applying it.
                                "archived": False,
                                "archived_at": None,
                            },
                        )
                    else:
                        fighter.stat_overrides.filter(content_stat=stat_def).delete()

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
                has_custom_statline=statline is not None,
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
