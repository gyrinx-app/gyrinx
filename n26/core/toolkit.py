"""Validate campaign toolkit commands and apply rewards through gang operations."""

from uuid import uuid5

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, strip_tags

from n26.core.campaigns import campaign_operation
from n26.core.models import (
    Assignment,
    Campaign,
    CampaignMembership,
    CampaignParticipant,
    Gang,
    LedgerEvent,
    Reason,
)
from n26.core.models.toolkit import (
    TAG_ICONS,
    CampaignTag,
    Intervention,
    InterventionReceipt,
    ToolkitCommand,
    ToolkitDelivery,
)
from n26.core.operations import Refusal, operation
from n26.library.models import Counter, Profile, Wargear, Weapon
from n26.rich_text import authored_html, plain_html
from n26.write_pause import write_guard

REWARD_MODELS = {
    "weapon": Weapon,
    "equipment": Wargear,
    "profile": Profile,
    "resource": Counter,
}


def campaign_href(campaign):
    return reverse("n26-campaign", args=[campaign.pk])


def toolkit_href(campaign):
    return reverse("n26-toolkit", args=[campaign.pk])


def content_for(campaign, text, message=""):
    return str(
        format_html(
            '<p><a href="{}">{}</a></p>{}{}',
            campaign_href(campaign),
            campaign.name,
            plain_html(text),
            authored_html(message),
        )
    )


def queue(
    campaign, recipients, *, identity, title, text, sender, href=None, message=""
):
    from n26.notifications import enqueue_toolkit_delivery

    for recipient in sorted({x for x in recipients if x is not None}):
        delivery, created = ToolkitDelivery.objects.get_or_create(
            identity=identity,
            recipient_id=recipient,
            defaults={
                "campaign": campaign,
                "sender": sender,
                "subject": f"{campaign.name}: {title}"[:255],
                "content": content_for(campaign, text, message),
                "href": href or campaign_href(campaign),
            },
        )
        if created:
            transaction.on_commit(
                lambda pk=str(delivery.pk): enqueue_toolkit_delivery(pk)
            )


def audience(campaign):
    return (
        set(
            CampaignParticipant.objects.filter(
                campaign=campaign, state=CampaignParticipant.State.ACCEPTED
            ).values_list("user_id", flat=True)
        )
        | set(
            campaign.memberships.filter(left__isnull=True).values_list(
                "gang__owner_id", flat=True
            )
        )
        | {campaign.owner_id}
    )


def selectable(model, campaign):
    return model.objects.selectable(packs=[campaign.pack_id])


def catalogue(campaign):
    result = []
    for kind, model in REWARD_MODELS.items():
        found = selectable(model, campaign)
        if kind == "profile":
            found = found.select_related("profile_type", "gang_type")
        for obj in found.order_by("name"):
            result.append(
                {
                    "id": str(obj.pk),
                    "kind": kind,
                    "name": obj.name,
                    "detail": (
                        f"{obj.profile_type.name} · {obj.gang_type.name}"
                        if kind == "profile"
                        else kind.title()
                    ),
                    "rating": getattr(obj, "price", 0),
                }
            )
    return result


def positive(value, label, maximum=1000000):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise Refusal(f"Enter {label} between 1 and {maximum}.")
    return value


def rewards_from(data, campaign):
    if not isinstance(data, list) or not 1 <= len(data) <= 30:
        raise Refusal("Add between 1 and 30 rewards.")
    result = []
    for entry in data:
        if not isinstance(entry, dict):
            raise Refusal("Check each reward.")
        kind = entry.get("kind")
        if not isinstance(kind, str):
            raise Refusal("Select a reward type.")
        amount = positive(
            entry.get("amount", 1),
            "an amount",
            1000000 if kind in {"credits", "resource"} else 20,
        )
        reward = {"kind": kind, "amount": amount}
        if kind == "credits":
            reward["label"] = f"{amount}¢"
        elif kind == "tag":
            name = entry.get("name", "")
            info = entry.get("info", "")
            if (
                not isinstance(name, str)
                or not name.strip()
                or len(name) > 80
                or not isinstance(info, str)
                or len(info) > 1000
                or entry.get("icon") not in TAG_ICONS
            ):
                raise Refusal(
                    "Give the tag a name, an allowed icon and up to 1000 characters of information."
                )
            reward.update(
                name=name.strip(),
                info=info,
                icon=entry["icon"],
                label=name.strip(),
                amount=1,
            )
        elif kind in REWARD_MODELS:
            ident = entry.get("id", "")
            # Match against the picker queryset, including its content visibility rules.
            obj = next(
                iter(selectable(REWARD_MODELS[kind], campaign).filter(pk=ident)), None
            )
            if obj is None:
                raise Refusal("That reward is no longer available in this campaign.")
            reward.update(
                id=str(obj.pk),
                label=f"{amount} × {obj.name}",
                rating=getattr(obj, "price", 0),
            )
        else:
            raise Refusal("Select a reward type.")
        result.append(reward)
    return result


def recipients_from(payload, campaign):
    if payload.get("recipients_mode") not in {"all", "selected"}:
        raise Refusal("Choose selected gangs or all gangs.")
    found = Gang.objects.filter(
        campaign_memberships__campaign=campaign,
        campaign_memberships__left__isnull=True,
        archived=False,
    ).order_by("pk")
    if payload.get("recipients_mode") != "all":
        ids = payload.get("gangs", [])
        if (
            not isinstance(ids, list)
            or not ids
            or any(not isinstance(x, str) for x in ids)
            or len(ids) != len(set(ids))
        ):
            raise Refusal("Select at least one gang.")
        found = found.filter(pk__in=ids)
        result = list(found)
        if len(result) != len(ids):
            raise Refusal("Select active gangs from this campaign.")
    else:
        result = list(found)
    if not result:
        raise Refusal("This campaign has no active gangs to receive this.")
    return result


def apply_rewards(receipt, indices, actor):
    intervention = receipt.intervention
    gang = receipt.gang
    if receipt.player_id:
        if not CampaignParticipant.objects.filter(
            campaign=intervention.campaign,
            user_id=receipt.player_id,
            state=CampaignParticipant.State.ACCEPTED,
        ).exists():
            raise Refusal("This player is no longer in the campaign.")
        for index in indices:
            reward = intervention.rewards[index]
            if reward["kind"] != "tag":
                raise Refusal("Only tags can be assigned directly to players.")
            CampaignTag.objects.create(
                campaign=intervention.campaign,
                player_id=receipt.player_id,
                receipt=receipt,
                name=reward["name"],
                icon=reward["icon"],
                info=reward["info"],
                assignment_key=uuid5(intervention.pk.to_uuid(), f"tag:{index}"),
            )
            with campaign_operation(intervention.campaign, actor=actor) as act:
                act.event(
                    "player_tagged",
                    note=f"Assigned {reward['name']} to {receipt.player.username}",
                    about_user=receipt.player,
                )
        receipt.selected = indices
        receipt.resolved_at = timezone.now()
        receipt.save(update_fields=["selected", "resolved_at", "modified"])
        return
    with operation(gang, actor=actor) as op:
        gang.refresh_from_db(fields=["owner", "archived"])
        if (
            gang.archived
            or not CampaignMembership.objects.filter(
                campaign=intervention.campaign, gang=gang, left__isnull=True
            ).exists()
        ):
            raise Refusal("This gang is no longer active in the campaign.")
        for index in indices:
            reward = intervention.rewards[index]
            kind = reward["kind"]
            note = f"{intervention.title}: {strip_tags(intervention.narrative)}"[:255]
            if kind == "credits":
                op.adjust_credits(reward["amount"], note)
            elif kind == "tag":
                CampaignTag.objects.create(
                    campaign=intervention.campaign,
                    gang=gang,
                    receipt=receipt,
                    name=reward["name"],
                    icon=reward["icon"],
                    info=reward["info"],
                    assignment_key=uuid5(intervention.pk.to_uuid(), f"tag:{index}"),
                )
                op.event(
                    None,
                    LedgerEvent.Kind.TOOLKIT_TAG,
                    note=f"Assigned {reward['name']}: {reward['info']}"[:255],
                )
            else:
                obj = REWARD_MODELS[kind].objects.get(pk=reward["id"])
                if kind == "resource":
                    held = Assignment.objects.filter(
                        gang=gang, counter=obj, archived=False, removes=False
                    ).first()
                    if held is None:
                        held = op.assign(
                            obj, gang=gang, reason=Reason.REWARD, note=note
                        )
                    op.tally(held, reward["amount"], note=note)
                else:
                    for _ in range(reward["amount"]):
                        if kind == "profile":
                            op.hire(
                                obj,
                                obj.name,
                                paid=0,
                                list_price=reward["rating"],
                                discount=reward["rating"],
                                rating=reward["rating"],
                                reason=Reason.REWARD,
                                note=note,
                            )
                        else:
                            op.reward_to_stash(obj, rating=reward["rating"], note=note)
        receipt.selected = indices
        receipt.resolved_at = timezone.now()
        receipt.save(update_fields=["selected", "resolved_at", "modified"])


def summary(rewards):
    return ", ".join(r["label"] for r in rewards)


def send_intervention(campaign, actor, payload):
    title = payload.get("title", "")
    narrative = payload.get("narrative", "")
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title) > 200
        or not isinstance(narrative, str)
        or len(narrative) > 10000
    ):
        raise Refusal("Enter a title and up to 10000 characters of accompanying text.")
    mode = payload.get("mode")
    if not isinstance(mode, str) or mode not in {"bundle", "choice"}:
        raise Refusal("Select all rewards or a choice of rewards.")
    rewards = rewards_from(payload.get("rewards"), campaign)
    choices = (
        positive(payload.get("choices", 1), "a choice limit", len(rewards))
        if mode == "choice"
        else len(rewards)
    )
    player_target = payload.get("target") == "players"
    if player_target:
        if any(r["kind"] != "tag" for r in rewards):
            raise Refusal("Only tags can be assigned directly to players.")
        gangs = list(
            get_user_model()
            .objects.filter(
                n26_campaign_participations__campaign=campaign,
                n26_campaign_participations__state=CampaignParticipant.State.ACCEPTED,
            )
            .order_by("pk")
        )
        if payload.get("recipients_mode") != "all":
            ids = payload.get("players", [])
            if (
                not isinstance(ids, list)
                or not ids
                or any(type(x) is not str for x in ids)
            ):
                raise Refusal("Select at least one player.")
            gangs = [p for p in gangs if str(p.pk) in ids]
            if len(gangs) != len(set(ids)):
                raise Refusal("Select players from this campaign.")
        if not gangs:
            raise Refusal("Select at least one player.")
    else:
        gangs = recipients_from(payload, campaign)
    intervention = Intervention.objects.create(
        campaign=campaign,
        actor=actor,
        purpose=payload.get("_purpose", "intervention"),
        title=title.strip(),
        narrative=narrative,
        mode=mode,
        choices=choices,
        rewards=rewards,
        inform_all=payload.get("inform_all") is True,
    )
    for gang in gangs:
        receipt = InterventionReceipt.objects.create(
            intervention=intervention,
            **({"player": gang} if player_target else {"gang": gang}),
        )
        if mode == "bundle":
            apply_rewards(receipt, list(range(len(rewards))), actor)
        recipient_name = gang.username if player_target else gang.name
        recipient_id = gang.pk if player_target else gang.owner_id
        wording = (
            f"{recipient_name}: "
            + (
                f"Choose exactly {choices} {'reward' if choices == 1 else 'rewards'} from "
                if mode == "choice"
                else "Received "
            )
            + summary(rewards)
            + "."
        )
        queue(
            campaign,
            [recipient_id],
            identity=f"offer:{receipt.pk}",
            title=intervention.title,
            text=wording,
            message=narrative,
            sender=actor,
            href=intervention.get_absolute_url(),
        )
    if intervention.inform_all:
        queue(
            campaign,
            audience(campaign),
            identity=f"announce:{intervention.pk}",
            title=intervention.title,
            text=f"{', '.join(g.username if player_target else g.name for g in gangs)} "
            + (
                f"were offered a choice of {choices} {'reward' if choices == 1 else 'rewards'} from "
                if mode == "choice"
                else "received "
            )
            + summary(rewards)
            + ".",
            message=narrative,
            sender=actor,
        )
    return intervention.get_absolute_url()


def choose(campaign, actor, payload):
    receipt = (
        InterventionReceipt.objects.select_for_update(of=("self",))
        .select_related("gang", "player", "intervention")
        .filter(
            Q(gang__owner=actor) | Q(player=actor),
            pk=payload.get("receipt"),
            intervention__campaign=campaign,
        )
        .first()
    )
    if receipt is None:
        raise Refusal("You cannot choose rewards for this gang.")
    intervention = receipt.intervention
    selected = payload.get("selected")
    if (
        intervention.mode != "choice"
        or not isinstance(selected, list)
        or len(selected) != intervention.choices
        or any(
            type(i) is not int or not 0 <= i < len(intervention.rewards)
            for i in selected
        )
        or len(set(selected)) != len(selected)
    ):
        raise Refusal(
            f"Choose exactly {intervention.choices} {'reward' if intervention.choices == 1 else 'different rewards'}."
        )
    selected = sorted(selected)
    if receipt.resolved_at:
        if receipt.selected != selected:
            raise Refusal("This gang has already confirmed different rewards.")
        return intervention.get_absolute_url()
    # Gang ownership can change while a submitted choice waits for its lock.
    if receipt.gang_id:
        with operation(receipt.gang, actor=actor):
            receipt.gang.refresh_from_db(fields=["owner"])
            if receipt.gang.owner_id != actor.pk:
                raise Refusal("You no longer own this gang.")
            apply_rewards(receipt, selected, actor)
    else:
        apply_rewards(receipt, selected, actor)
    recipient_name = receipt.gang.name if receipt.gang_id else receipt.player.username
    recipient_id = receipt.gang.owner_id if receipt.gang_id else receipt.player_id
    text = f"{recipient_name} chose {summary([intervention.rewards[i] for i in selected])}."
    queue(
        campaign,
        [recipient_id],
        identity=f"chosen:{receipt.pk}",
        title=intervention.title,
        text=text,
        message=intervention.narrative,
        sender=intervention.actor,
    )
    alert_event(
        campaign, "offer_selected", identity=str(receipt.pk), text=text, actor=actor
    )
    return intervention.get_absolute_url()


def run_command(campaign, actor, action, payload):
    if action == "choose":
        return choose(campaign, actor, payload)
    if campaign.owner_id != actor.pk:
        raise Refusal("Only the campaign arbitrator can use these tools.")
    if action == "edit_communication":
        from n26.core.toolkit_edit import edit_communication

        return edit_communication(campaign, actor, payload)
    if action == "edit_tag":
        from n26.core.toolkit_edit import edit_tag

        return edit_tag(campaign, actor, payload)
    if action == "intervention":
        return send_intervention(campaign, actor, payload)
    if action == "tags":
        if (
            not isinstance(payload.get("rewards"), list)
            or len(payload["rewards"]) != 1
            or any(
                not isinstance(r, dict) or r.get("kind") != "tag"
                for r in payload["rewards"]
            )
        ):
            raise Refusal("Assign one tag at a time.")
        send_intervention(
            campaign,
            actor,
            {
                **payload,
                "title": "Tags: "
                + ", ".join(str(r.get("name", "")) for r in payload["rewards"])[:190],
                "narrative": "",
                "mode": "bundle",
                "inform_all": False,
                "_purpose": "tags",
            },
        )
        return toolkit_href(campaign) + "?tab=tags"
    if action == "communication":
        gangs = recipients_from(payload, campaign)
        title = payload.get("title", "")
        body = payload.get("body", "")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title) > 200
            or not isinstance(body, str)
            or len(body) > 10000
            or not (
                strip_tags(authored_html(body)).strip()
                or "<img " in authored_html(body)
            )
        ):
            raise Refusal("Enter a title and message of up to 10000 characters.")
        identity = f"communication:{payload['_key']}"
        queue(
            campaign,
            [g.owner_id for g in gangs],
            identity=identity,
            title=title.strip(),
            text="",
            message=body,
            sender=actor,
        )
        return toolkit_href(campaign) + "?tab=communications"
    if action == "alerts":
        from n26.core.toolkit_alerts import configure

        configure(campaign, payload)
        return toolkit_href(campaign) + "?tab=alerts"
    if action == "remove_tag":
        tag = (
            CampaignTag.objects.select_related("gang")
            .filter(pk=payload.get("tag"), campaign=campaign)
            .first()
        )
        if tag is None:
            raise Refusal("That tag does not belong to this campaign.")
        if tag.removed_at is None:
            tag.removed_at = timezone.now()
            if tag.gang_id:
                with operation(tag.gang, actor=actor) as op:
                    tag.save(update_fields=["removed_at", "modified"])
                    op.event(
                        None, LedgerEvent.Kind.TOOLKIT_TAG, note=f"Removed {tag.name}"
                    )
            else:
                with campaign_operation(campaign, actor=actor) as act:
                    tag.save(update_fields=["removed_at", "modified"])
                    act.event(
                        "player_tagged",
                        note=f"Removed {tag.name} from {tag.player.username}",
                        about_user=tag.player,
                    )
        return toolkit_href(campaign) + "?tab=tags"
    raise Refusal("Select a toolkit action.")


class CommandForm(forms.Form):
    request_key = forms.UUIDField()
    payload = forms.JSONField()


def change(campaign, actor, action, data):
    form = CommandForm(data)
    if not form.is_valid():
        return form, None
    payload = form.cleaned_data["payload"]
    if not isinstance(payload, dict):
        form.add_error("payload", "Check the form values.")
        return form, None
    key = form.cleaned_data["request_key"]
    try:
        with transaction.atomic(), write_guard():
            campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
            if campaign.archived:
                raise Refusal("This campaign is archived.")
            if action != "choose" and campaign.owner_id != actor.pk:
                raise Refusal("Only the campaign arbitrator can use these tools.")
            previous = ToolkitCommand.objects.filter(
                campaign=campaign, actor=actor, request_key=key
            ).first()
            if previous:
                if previous.action != action or previous.payload != payload:
                    raise Refusal(
                        "Different values were already saved from this form. Reload the page."
                    )
                if (
                    action == "choose"
                    and not InterventionReceipt.objects.filter(
                        Q(gang__owner=actor) | Q(player=actor),
                        pk=payload.get("receipt"),
                        intervention__campaign=campaign,
                    ).exists()
                ):
                    raise Refusal("You no longer own this gang.")
                return form, previous.next_url
            clean_payload = {**payload, "_key": str(key)}
            destination = run_command(campaign, actor, action, clean_payload)
            ToolkitCommand.objects.create(
                campaign=campaign,
                actor=actor,
                request_key=key,
                action=action,
                payload=payload,
                next_url=destination,
            )
            return form, destination
    except Refusal as exc:
        form.conflicted = getattr(exc, "revision_conflict", False)
        form.add_error(None, exc.public_message)
    except ValidationError:
        form.add_error("payload", "Check the selected gangs and rewards.")
    return form, None


def alert_event(campaign, event, *, identity, text, actor=None):
    from n26.core.toolkit_alerts import capture

    return capture(campaign, event, identity=identity, text=text, actor=actor)
