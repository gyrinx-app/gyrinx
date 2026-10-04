"""Public account destinations and a route into the existing invitation flow."""

from dataclasses import dataclass

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.models import Campaign, CampaignParticipant, Gang
from n26.core.operations import Refusal
from n26.flags import CAMPAIGNS, enabled, requires_flag


@dataclass(frozen=True)
class PublicGang:
    name: str
    gang_type: str
    href: str


def _person(username):
    return get_object_or_404(
        User.objects.all(),
        username__iexact=username,
        is_active=True,
    )


def _owned_campaigns(user, person):
    state = CampaignParticipant.objects.filter(
        campaign=OuterRef("pk"), user=person
    ).values("state")[:1]
    return (
        Campaign.objects.filter(owner=user, archived=False)
        .annotate(invitation_state=Subquery(state))
        .order_by("name", "pk")
    )


def user_profile(request, username):
    """Public username and gang links; account details and campaigns stay private."""
    person = _person(username)
    gangs = [
        PublicGang(name=name, gang_type=kind, href=reverse("n26-gang", args=[pk]))
        for pk, name, kind in Gang.objects.filter(owner=person, archived=False)
        .order_by("name", "pk")
        .values_list("pk", "name", "gang_type__name")
    ]
    may_invite = (
        request.user.is_authenticated
        and request.user.pk != person.pk
        and enabled(CAMPAIGNS, request.user)
        and _owned_campaigns(request.user, person).exists()
    )
    return render(
        request,
        "n26/user_profile.html",
        {"person": person, "gangs": gangs, "may_invite": may_invite},
    )


class InviteCampaignForm(forms.Form):
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.none(),
        label="Campaign",
        error_messages={"invalid_choice": "Select one of your available campaigns."},
    )

    message = forms.CharField(
        required=False,
        label="Message",
        help_text="Optional. Sent with the invitation.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, campaigns, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campaign"].queryset = campaigns


@requires_flag(CAMPAIGNS)
@login_required
def invite_user(request, username):
    """Send a campaign invitation and its optional message from one form."""
    person = _person(username)
    if person.pk == request.user.pk:
        return redirect("n26-user-profile", username=person.username)
    campaigns = _owned_campaigns(request.user, person)
    eligible = campaigns.filter(
        Q(invitation_state__isnull=True)
        | Q(invitation_state=CampaignParticipant.State.DECLINED)
    )
    form = InviteCampaignForm(
        eligible, request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        campaign = form.cleaned_data["campaign"]
        try:
            with campaign_operation(campaign, actor=request.user) as op:
                op.invite(person, message=form.cleaned_data["message"])
        except Refusal as refused:
            form.add_error(None, str(refused))
        else:
            messages.success(request, f"Invited {person.username}.")
            return redirect("n26-campaign", pk=campaign.pk)
    options = [
        {
            "value": str(campaign.pk),
            "label": campaign.name,
            "selected": str(campaign.pk) == str(form["campaign"].value() or ""),
        }
        for campaign in eligible
    ]
    existing = [
        {
            "name": campaign.name,
            "href": reverse("n26-campaign", args=[campaign.pk]),
            "status": "Invitation pending"
            if campaign.invitation_state == CampaignParticipant.State.INVITED
            else "Already playing",
        }
        for campaign in campaigns
        if campaign.invitation_state
        in {CampaignParticipant.State.INVITED, CampaignParticipant.State.ACCEPTED}
    ]
    return render(
        request,
        "n26/invite_user.html",
        {"person": person, "form": form, "options": options, "existing": existing},
    )
