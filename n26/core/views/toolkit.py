"""Arbitrator-only toolkit pages and recipient-owned intervention choices."""

import json
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26.core import toolkit
from n26.core.fields import to_ulid
from n26.core.models import CampaignParticipant, Gang
from n26.core.models.toolkit import (
    ALERT_EVENTS,
    TAG_ICONS,
    CampaignTag,
    Intervention,
    InterventionReceipt,
    ToolkitCommand,
)
from n26.core.toolkit_edit import communication_values, signed_state, tag_state
from n26.core.views.permissions import _any_campaign_or_404, _own_campaign_or_404
from n26.rich_text import rich_text_nodes


def identifier(value):
    try:
        return to_ulid(value)
    except ValueError, TypeError:
        raise Http404("No such toolkit record") from None


def common(request, campaign):
    return {
        "campaignName": campaign.name,
        "campaignHref": toolkit.campaign_href(campaign),
        "toolkitHref": toolkit.toolkit_href(campaign),
        "isArbitrator": campaign.owner_id == request.user.pk,
    }


@login_required
@never_cache
def toolkit_home(request, pk):
    campaign = _own_campaign_or_404(request, pk)
    from n26.core.toolkit_alerts import preferences

    tab = request.GET.get("tab", "interventions")
    if tab not in {"interventions", "communications", "alerts", "tags"}:
        tab = "interventions"
    interventions = list(
        campaign.interventions.filter(purpose="intervention")
        .order_by("-created")
        .prefetch_related("receipts__gang")[:100]
    )
    communications = (
        ToolkitCommand.objects.filter(campaign=campaign, action="communication")
        .select_related("actor")
        .prefetch_related("communication_revisions")
        .order_by("-created")[:100]
    )
    props = {
        **common(request, campaign),
        "screen": "home",
        "tab": tab,
        "interventions": [
            {
                "id": str(i.pk),
                "title": i.title,
                "href": i.get_absolute_url(),
                "mode": i.mode,
                "summary": toolkit.summary(i.rewards),
                "date": i.created.isoformat(),
                "recipients": len(i.receipts.all()),
                "pending": sum(r.resolved_at is None for r in i.receipts.all()),
            }
            for i in interventions
        ],
        "communications": [
            {
                "id": str(c.pk),
                "title": communication_values(c)["title"],
                "body": communication_values(c)["body"],
                "bodyNodes": rich_text_nodes(communication_values(c)["body"]),
                "editHref": reverse(
                    "n26-toolkit-form", args=[campaign.pk, "edit_communication"]
                )
                + f"?communication={c.pk}",
                "date": c.created.isoformat(),
            }
            for c in communications
        ],
        "alerts": [{"value": key, "label": label} for key, label in ALERT_EVENTS],
        "enabledAlerts": list(campaign.toolkit_alerts.values_list("event", flat=True)),
        "tags": [
            {
                "id": str(t.pk),
                "name": t.name,
                "icon": t.icon,
                "info": t.info,
                "recipient": t.gang.name if t.gang_id else t.player.username,
                "target": "gangs" if t.gang_id else "players",
                "assignmentKey": str(t.assignment_key),
                "editHref": reverse("n26-toolkit-form", args=[campaign.pk, "edit_tag"])
                + f"?tag={t.pk}",
                "removeHref": reverse(
                    "n26-toolkit-form", args=[campaign.pk, "remove_tag"]
                )
                + f"?tag={t.pk}",
            }
            for t in campaign.gang_tags.filter(removed_at__isnull=True)
            .select_related("gang", "player")
            .order_by("gang__name", "name")
        ],
        "newIntervention": reverse(
            "n26-toolkit-form", args=[campaign.pk, "intervention"]
        ),
        "newCommunication": reverse(
            "n26-toolkit-form", args=[campaign.pk, "communication"]
        ),
        "newTags": reverse("n26-toolkit-form", args=[campaign.pk, "tags"]),
        "alertTiming": preferences(campaign),
        "editAlerts": reverse("n26-toolkit-form", args=[campaign.pk, "alerts"]),
    }
    return render(
        request, "n26/toolkit.html", {"campaign": campaign, "toolkit_props": props}
    )


def access(request, pk, action):
    if action == "choose":
        return _any_campaign_or_404(request, pk)
    return _own_campaign_or_404(request, pk)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def toolkit_form(request, pk, action):
    if action not in {
        "intervention",
        "tags",
        "communication",
        "alerts",
        "choose",
        "remove_tag",
        "edit_communication",
        "edit_tag",
    }:
        raise Http404
    campaign = access(request, pk, action)
    initial = {
        "title": "",
        "narrative": "",
        "body": "",
        "mode": "bundle",
        "choices": 1,
        "rewards": [{"kind": "credits", "amount": 30}],
        "recipients_mode": "selected",
        "gangs": [],
        "inform_all": False,
    }
    if action == "intervention":
        initial.update(mode="", recipients_mode="", rewards=[{"kind": "", "amount": 1}])
    props = {
        **common(request, campaign),
        "screen": "form",
        "actionKind": action,
        "icons": list(TAG_ICONS),
        "alertEvents": [{"value": key, "label": label} for key, label in ALERT_EVENTS],
        "catalogue": [],
        "gangs": [],
        "receipt": None,
        "tag": None,
    }
    if action in {"tags", "edit_tag"}:
        initial.update(
            target="gangs",
            rewards=[
                {
                    "kind": "tag",
                    "amount": 1,
                    "icon": "crosshair",
                    "name": "",
                    "info": "",
                }
            ],
        )
    if action in {"intervention", "communication", "tags", "edit_tag"}:
        props["gangs"] = [
            {
                "id": str(g.pk),
                "name": g.name,
                "owner": g.owner.username if g.owner else "",
            }
            for g in Gang.objects.filter(
                campaign_memberships__campaign=campaign,
                campaign_memberships__left__isnull=True,
                archived=False,
            )
            .select_related("owner")
            .order_by("name")
        ]
        props["players"] = [
            {"id": str(p.user_id), "name": p.user.username, "owner": "Player"}
            for p in campaign.participants.filter(
                state=CampaignParticipant.State.ACCEPTED
            )
            .select_related("user")
            .order_by("user__username")
        ]
        if action == "intervention":
            props["catalogue"] = toolkit.catalogue(campaign)
    if action == "alerts":
        from n26.core.toolkit_alerts import preferences

        initial = {
            "events": list(campaign.toolkit_alerts.values_list("event", flat=True)),
            **preferences(campaign),
        }
    if action == "choose":
        receipt = (
            InterventionReceipt.objects.select_related("intervention", "gang", "player")
            .filter(
                Q(gang__owner=request.user) | Q(player=request.user),
                pk=identifier(request.GET.get("receipt")),
                intervention__campaign=campaign,
            )
            .first()
        )
        if receipt is None:
            raise Http404
        if receipt.resolved_at:
            return redirect(receipt.intervention.get_absolute_url())
        initial = {"receipt": str(receipt.pk), "selected": []}
        props["receipt"] = {
            "title": receipt.intervention.title,
            "gang": receipt.gang.name if receipt.gang_id else receipt.player.username,
            "choices": receipt.intervention.choices,
            "rewards": receipt.intervention.rewards,
            "narrative": receipt.intervention.narrative,
            "narrativeNodes": rich_text_nodes(receipt.intervention.narrative),
        }
    if action == "remove_tag":
        tag = (
            campaign.gang_tags.select_related("gang", "player")
            .filter(pk=identifier(request.GET.get("tag")), removed_at__isnull=True)
            .first()
        )
        if tag is None:
            raise Http404
        initial = {"tag": str(tag.pk)}
        props["tag"] = {
            "name": tag.name,
            "gang": tag.gang.name if tag.gang_id else tag.player.username,
        }
    if action == "edit_communication":
        communication = (
            ToolkitCommand.objects.filter(
                campaign=campaign,
                action="communication",
                pk=identifier(request.GET.get("communication")),
            )
            .prefetch_related("communication_revisions")
            .first()
        )
        if communication is None:
            raise Http404
        current = communication_values(communication)
        initial = {
            "communication": str(communication.pk),
            "title": current["title"],
            "body": current["body"],
            "snapshot": signed_state(
                "communication", communication, request.user, current["revision"]
            ),
        }
        props["recipientNames"] = list(
            campaign.toolkitdelivery_set.filter(
                identity=f"communication:{communication.request_key}"
            ).values_list("recipient__username", flat=True)
        )
    if action == "edit_tag":
        anchor = CampaignTag.objects.filter(
            campaign=campaign, pk=identifier(request.GET.get("tag"))
        ).first()
        if anchor is None:
            raise Http404
        tags = list(
            CampaignTag.objects.filter(
                campaign=campaign,
                assignment_key=anchor.assignment_key,
                removed_at__isnull=True,
            )
        )
        if not tags:
            raise Http404
        current = tags[0]
        initial = {
            "tag": str(anchor.pk),
            "target": "players" if anchor.player_id else "gangs",
            "recipients_mode": "selected",
            "players": [str(t.player_id) for t in tags if t.player_id],
            "gangs": [str(t.gang_id) for t in tags if t.gang_id],
            "rewards": [
                {
                    "kind": "tag",
                    "amount": 1,
                    "name": current.name,
                    "icon": current.icon,
                    "info": current.info,
                }
            ],
            "snapshot": signed_state("tag", anchor, request.user, tag_state(tags)),
        }
    if action in {"edit_tag", "edit_communication"}:
        props["reviewHref"] = request.get_full_path()
    if action in {"intervention", "communication", "edit_communication"}:
        from n26.core.widgets import campaign_editor_props

        props["editor"] = campaign_editor_props()
    form = toolkit.CommandForm(initial={"request_key": uuid4(), "payload": initial})
    if request.method == "POST":
        form, destination = toolkit.change(campaign, request.user, action, request.POST)
        if destination:
            return redirect(destination)
    props.update(
        {
            "values": {
                "request_key": str(form["request_key"].value() or uuid4()),
                "payload": json.dumps(initial)
                if not form.is_bound
                else form["payload"].value(),
            },
            "errors": dict(form.errors),
            "conflicted": getattr(form, "conflicted", False),
            "csrfToken": get_token(request),
            "commandHref": reverse("n26-toolkit-command", args=[campaign.pk, action]),
            "recoveryKey": f"toolkit:{request.user.pk}:{campaign.pk}:{action}:{initial.get('receipt', initial.get('tag', initial.get('communication', '')))}",
        }
    )
    return render(
        request, "n26/toolkit.html", {"campaign": campaign, "toolkit_props": props}
    )


@require_POST
def toolkit_command(request, pk, action):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this change."}, status=401)
    campaign = access(request, pk, action)
    form, destination = toolkit.change(campaign, request.user, action, request.POST)
    if destination:
        return JsonResponse({"nextUrl": destination})
    return JsonResponse(
        {
            "errors": dict(form.errors),
            "code": "revision_conflict"
            if getattr(form, "conflicted", False)
            else "invalid",
        },
        status=409 if getattr(form, "conflicted", False) else 422,
    )


@login_required
@never_cache
def intervention_detail(request, pk, intervention_pk):
    campaign = _any_campaign_or_404(request, pk)
    intervention = Intervention.objects.filter(
        campaign=campaign, pk=identifier(intervention_pk)
    ).first()
    if intervention is None:
        raise Http404
    receipts = intervention.receipts.select_related(
        "gang", "gang__owner", "player"
    ).order_by("gang__name")
    if campaign.owner_id != request.user.pk:
        receipts = receipts.filter(Q(gang__owner=request.user) | Q(player=request.user))
        if not receipts.exists():
            raise Http404
    props = {
        **common(request, campaign),
        "screen": "detail",
        "title": intervention.title,
        "narrative": intervention.narrative,
        "narrativeNodes": rich_text_nodes(intervention.narrative),
        "mode": intervention.mode,
        "choices": intervention.choices,
        "rewards": intervention.rewards,
        "informAll": intervention.inform_all,
        "receipts": [
            {
                "id": str(r.pk),
                "gang": r.gang.name if r.gang_id else r.player.username,
                "gangHref": reverse("n26-gang", args=[r.gang_id])
                if r.gang_id
                else toolkit.campaign_href(campaign) + "#players",
                "resolved": r.resolved_at is not None,
                "selected": r.selected,
                "chooseHref": reverse("n26-toolkit-form", args=[campaign.pk, "choose"])
                + f"?receipt={r.pk}"
                if r.resolved_at is None
                and (
                    (r.gang_id and r.gang.owner_id == request.user.pk)
                    or r.player_id == request.user.pk
                )
                else "",
            }
            for r in receipts
        ],
    }
    return render(
        request, "n26/toolkit.html", {"campaign": campaign, "toolkit_props": props}
    )
