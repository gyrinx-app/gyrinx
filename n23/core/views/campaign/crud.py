"""Campaign CRUD views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from n23.core.forms.campaign import EditCampaignForm, NewCampaignForm
from n23.core.handlers.campaign_copy import (
    apply_campaign_template,
    describe_campaign_contents,
    ensure_default_resource_type,
)
from n23.core.models.campaign import Campaign
from gyrinx.analytics.models import EventNoun, EventVerb, log_event
from gyrinx.tracker import track
from n23.core.views.campaign.common import get_campaign_admin_or_404


def _get_template_campaign(request):
    """Resolve the ``?template=<id>`` campaign this new campaign is based on.

    Returns None when no template was requested. Template campaigns are offered
    to everyone regardless of who owns them, which is the point of marking one
    as a template.
    """
    template_id = request.GET.get("template")
    if not template_id:
        return None

    try:
        return get_object_or_404(
            Campaign.objects.filter(template=True, archived=False),
            id=template_id,
        )
    except (DjangoValidationError, ValueError):
        # Not a UUID at all — a hand-edited or truncated link.
        raise Http404("No such template campaign.")


def _resolve_template_campaign(request):
    """Resolve the requested template, tolerating one that vanished mid-form.

    Returns ``(template_campaign, missing)``. A bad template is a 404 on GET,
    but on POST the user has already typed a name, summary and narrative — so
    if the template was archived or un-flagged in the meantime we report it and
    re-render rather than throwing their work away with an error page.
    """
    try:
        return _get_template_campaign(request), False
    except Http404:
        if request.method != "POST":
            raise
        return None, True


@login_required
@transaction.atomic
def new_campaign(request):
    """
    Create a new :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A NewCampaignForm for entering the name and details of the new campaign.
    ``template_campaign``
        The template :model:`core.Campaign` this one is based on, from
        ``?template=<id>``, or None. Its assets, resources, attributes and
        Content Packs are copied over once the campaign is created.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_new.html`
    """
    template_campaign, template_missing = _resolve_template_campaign(request)
    error_message = None
    if request.method == "POST":
        form = NewCampaignForm(request.POST)
        if template_missing:
            messages.error(
                request,
                "That template is no longer available, so nothing has been "
                "copied. Create the Campaign as it stands, or start again from "
                "another template.",
            )
        elif form.is_valid():
            campaign = form.save(commit=False)
            campaign.owner = request.user
            campaign.save()

            applied = None
            if template_campaign:
                applied = apply_campaign_template(
                    template_campaign=template_campaign,
                    campaign=campaign,
                    user=request.user,
                )

            # Every campaign gets a Reputation resource type, unless the template
            # already supplied one of its own.
            ensure_default_resource_type(campaign=campaign, user=request.user)

            # Log the campaign creation event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.CREATE,
                object=campaign,
                request=request,
                campaign_name=campaign.name,
                public=campaign.public,
                template_campaign_id=(
                    str(template_campaign.id) if template_campaign else None
                ),
                template_campaign_name=(
                    template_campaign.name if template_campaign else None
                ),
            )

            track(
                "campaign_created",
                campaign_id=str(campaign.id),
                template_campaign_id=(
                    str(template_campaign.id) if template_campaign else None
                ),
            )

            if applied:
                messages.success(
                    request,
                    f"Created from the {template_campaign.name} template. "
                    f"{applied.action.outcome}.",
                )

            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        initial = {"name": request.GET.get("name", "")}
        if template_campaign:
            initial["budget"] = template_campaign.budget
        form = NewCampaignForm(initial=initial)

    return render(
        request,
        "core/campaign/campaign_new.html",
        {
            "form": form,
            "error_message": error_message,
            "template_campaign": template_campaign,
            "template_contents": (
                describe_campaign_contents(template_campaign)
                if template_campaign
                else []
            ),
        },
    )


@login_required
def edit_campaign(request, id):
    """
    Edit an existing :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A EditCampaignForm for editing the campaign's details.
    ``campaign``
        The :model:`core.Campaign` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_edit.html`
    """
    campaign = get_campaign_admin_or_404(request, id)

    error_message = None
    if request.method == "POST":
        form = EditCampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            # Pass user to save() for phase change logging
            updated_campaign = form.save(user=request.user)

            # Log the campaign update event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.UPDATE,
                object=updated_campaign,
                request=request,
                campaign_name=updated_campaign.name,
            )

            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        form = EditCampaignForm(instance=campaign)

    return render(
        request,
        "core/campaign/campaign_edit.html",
        {"form": form, "campaign": campaign, "error_message": error_message},
    )
