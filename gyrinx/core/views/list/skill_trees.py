"""List gang-wide skill-tree views."""

import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.skill_tree import ListSkillTreeForm
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def manage_list_skill_trees(request: HttpRequest, id: uuid.UUID):
    """
    Show the gang's ranked skill-tree picks (gang-wide skills).
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    if not lst.content_house.gang_wide_skills:
        messages.error(
            request, f"{lst.content_house.name} does not use gang-wide skill trees."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    context = {
        "list": lst,
        "assignments": lst.active_skill_trees_cached,
    }

    return render(request, "core/list_skill_trees_manage.html", context)


@login_required
def edit_list_skill_trees(request: HttpRequest, id: uuid.UUID):
    """
    Edit the gang's ranked skill-tree picks (gang-wide skills).
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    if not lst.content_house.gang_wide_skills:
        messages.error(
            request, f"{lst.content_house.name} does not use gang-wide skill trees."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if lst.archived:
        messages.error(request, "Cannot modify skill trees for an archived list.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    include_restricted = request.GET.get("include_restricted") == "1"

    if request.method == "POST":
        form = ListSkillTreeForm(
            request.POST,
            list_obj=lst,
            request=request,
            include_restricted=include_restricted,
        )
        if form.is_valid():
            form.save()

            log_event(
                user=request.user,
                noun=EventNoun.LIST,
                verb=EventVerb.UPDATE,
                object=lst,
                request=request,
                list_id=str(lst.id),
                list_name=lst.name,
                action="skill_trees_updated",
            )

            messages.success(request, "Gang skill trees updated.")
            default_url = reverse("core:list", args=(lst.id,))
            return safe_redirect(
                request, get_return_url(request, default_url), fallback_url=default_url
            )
    else:
        form = ListSkillTreeForm(
            list_obj=lst, request=request, include_restricted=include_restricted
        )

    return_url = get_return_url(request, "")

    context = {
        "list": lst,
        "form": form,
        "include_restricted": include_restricted,
        "return_url": return_url,
    }

    return render(request, "core/list_skill_trees_edit.html", context)
