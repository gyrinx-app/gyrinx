"""Campaign CRUD views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode

from gyrinx import messages
from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.tracker import track
from n23.core.events import EventNoun
from n23.core.forms.campaign import EditCampaignForm, NewCampaignForm
from n23.core.handlers.campaign_copy import (
    apply_campaign_template,
    describe_campaign_contents,
    ensure_default_resource_type,
)
from n23.core.models.campaign import Campaign
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
    except DjangoValidationError, ValueError:
        # Not a UUID at all — a hand-edited or truncated link.
        raise Http404("No such template campaign.") from None


def _available_template_campaigns():
    """The template campaigns offered on the interstitial, in a stable order."""
    return Campaign.objects.filter(template=True, archived=False).order_by("name")


def _carried_campaign_name(raw):
    """Normalise a campaign name carried through the template-selection flow:
    strip whitespace and cap to the model field length so it can't bloat
    redirect URLs (risking 414s) or exceed what the form would accept anyway.
    """
    max_length = Campaign._meta.get_field("name").max_length
    return (raw or "").strip()[:max_length]


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
def new_campaign_template(request):
    """
    Offer the template campaigns before the new-campaign form is shown.

    Each template links straight to ``campaigns-new?template=<id>``; the
    "start from scratch" link carries ``skip_template=1``. Both bypass the
    redirect in :func:`new_campaign`, so this page never posts anything and
    needs no form of its own.

    **Context**

    ``template_campaigns``
        The :model:`core.Campaign` templates on offer, each annotated with the
        ``use_url`` that starts a campaign from it and the ``contents`` it would
        copy over.
    ``skip_url``
        Where "start from scratch" goes.
    ``name``
        A campaign name carried in from a quick-create box, threaded onto every
        outgoing link so it survives the detour.

    **Template**

    :template:`core/campaign/campaign_new_template.html`
    """
    name = _carried_campaign_name(request.GET.get("name"))
    new_url = reverse("core:campaigns-new")

    def _url(**params):
        if name:
            params["name"] = name
        return f"{new_url}?{urlencode(params)}"

    # A handful of curated templates, so the per-campaign contents summary is
    # affordable here — it is the whole reason to show this page rather than a
    # bare list of names.
    template_campaigns = list(_available_template_campaigns())
    for campaign in template_campaigns:
        campaign.use_url = _url(template=str(campaign.id))
        campaign.contents = describe_campaign_contents(campaign)

    return render(
        request,
        "core/campaign/campaign_new_template.html",
        {
            "template_campaigns": template_campaigns,
            "skip_url": _url(skip_template="1"),
            "name": name,
        },
    )


@login_required
@transaction.atomic
def new_campaign(request):
    """
    Create a new :model:`core.Campaign` owned by the current user.

    Redirects to the template interstitial first unless a template has already
    been chosen (``?template=<id>``) or declined (``?skip_template=1``).

    **Context**

    ``form``
        A NewCampaignForm for entering the name and details of the new campaign.
    ``template_campaign``
        The template :model:`core.Campaign` this one is based on, from
        ``?template=<id>``, or None. Its assets, resources, attributes and
        Content Packs are copied over once the campaign is created.
    ``change_template_url``
        Back to the interstitial, to choose a different template or none.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_new.html`
    """
    # Anyone who hasn't seen the interstitial yet gets sent there. GET only:
    # the skip branch posts back here with no query string at all, and bouncing
    # that would throw away everything they typed. And only when there is
    # something to show — with no templates the detour is a dead end.
    if (
        request.method == "GET"
        and request.GET.get("skip_template") != "1"
        and not request.GET.get("template")
        and _available_template_campaigns().exists()
    ):
        templates_url = reverse("core:campaigns-new-template")
        carried_name = _carried_campaign_name(request.GET.get("name"))
        if carried_name:
            templates_url += "?" + urlencode({"name": carried_name})
        return HttpResponseRedirect(templates_url)

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
            "change_template_url": reverse("core:campaigns-new-template"),
            # Only asked when no template is in play — that is the one branch
            # offering a way back to the interstitial.
            "has_template_campaigns": (
                template_campaign is None and _available_template_campaigns().exists()
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
