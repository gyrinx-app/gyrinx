"""List attribute views."""

import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.attribute import ListAttributeForm
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def manage_list_attributes(request: HttpRequest, id: uuid.UUID):
    """
    Show all attributes for a list, allowing the user to manage them.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    context = {
        "list": lst,
    }

    return render(request, "core/list_attributes_manage.html", context)


@login_required
def edit_list_attribute(request: HttpRequest, id: uuid.UUID, attribute_id: uuid.UUID):
    """
    Edit attributes for a list.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)

    # Check if list is archived
    if lst.archived:
        messages.error(request, "Cannot modify attributes for an archived list.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Get the attribute
    from gyrinx.content.models import ContentAttribute

    attribute = get_object_or_404(ContentAttribute, id=attribute_id)

    # Check if attribute is available to this house
    if (
        attribute.restricted_to.exists()
        and lst.content_house not in attribute.restricted_to.all()
    ):
        messages.error(
            request, f"{attribute.name} is not available to {lst.content_house.name}."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = ListAttributeForm(
            request.POST, list_obj=lst, attribute=attribute, request=request
        )
        if form.is_valid():
            form.save()

            # Log the attribute update
            log_event(
                user=request.user,
                noun=EventNoun.LIST,
                verb=EventVerb.UPDATE,
                object=lst,
                request=request,
                list_id=str(lst.id),
                list_name=lst.name,
                action="attribute_updated",
                attribute_name=attribute.name,
            )

            messages.success(request, f"{attribute.name} updated successfully.")
            default_url = reverse("core:list", args=(lst.id,))
            return safe_redirect(
                request, get_return_url(request, default_url), fallback_url=default_url
            )
    else:
        form = ListAttributeForm(list_obj=lst, attribute=attribute, request=request)

    return_url = get_return_url(request, "")

    context = {
        "list": lst,
        "attribute": attribute,
        "form": form,
        "return_url": return_url,
    }

    return render(request, "core/list_attribute_edit.html", context)
