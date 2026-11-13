"""Version arbitrator messages and update tag assignments under the campaign lock."""

from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from n26.core import toolkit
from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignParticipant, LedgerEvent
from n26.core.models.toolkit import (
    CampaignTag,
    InterventionReceipt,
    ToolkitCommand,
    ToolkitCommunicationRevision,
    ToolkitDelivery,
)
from n26.core.operations import Refusal, operation
from n26.rich_text import authored_html


class EditConflict(Refusal):
    revision_conflict = True


def signed_state(kind, subject, actor, state):
    return signing.dumps(
        {"kind": kind, "subject": str(subject.pk), "actor": actor.pk, "state": state},
        salt="n26-toolkit-edit",
    )


def check_state(payload, kind, subject, actor, state, unchanged=False):
    try:
        value = signing.loads(payload.get("snapshot", ""), salt="n26-toolkit-edit")
    except signing.BadSignature, TypeError, ValueError:
        raise Refusal("Reload this edit form before saving.") from None
    if not isinstance(value, dict) or any(
        value.get(k) != v
        for k, v in {
            "kind": kind,
            "subject": str(subject.pk),
            "actor": actor.pk,
        }.items()
    ):
        raise Refusal("Reload this edit form before saving.")
    if not unchanged and value.get("state") != state:
        raise EditConflict(
            "This content has changed. Review the current version before saving."
        )


def communication_values(command):
    revisions = list(command.communication_revisions.all())
    current = revisions[0] if revisions else None
    return {
        "title": current.title if current else command.payload["title"],
        "body": current.body if current else command.payload["body"],
        "revision": str(current.pk) if current else "original",
    }


def edit_communication(campaign, actor, payload):
    command = (
        ToolkitCommand.objects.filter(
            pk=payload.get("communication"), campaign=campaign, action="communication"
        )
        .prefetch_related("communication_revisions")
        .first()
    )
    if command is None:
        raise Refusal("That message does not belong to this campaign.")
    title, body = payload.get("title"), payload.get("body")
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title) > 200
        or not isinstance(body, str)
        or len(body) > 10000
        or not (
            strip_tags(authored_html(body)).strip() or "<img " in authored_html(body)
        )
    ):
        raise Refusal(
            "Enter a title of up to 200 characters and a message of up to 10000 characters."
        )
    current = communication_values(command)
    unchanged = title.strip() == current["title"] and body == current["body"]
    check_state(
        payload, "communication", command, actor, current["revision"], unchanged
    )
    if not unchanged:
        ToolkitCommunicationRevision.objects.create(
            communication=command, actor=actor, title=title.strip(), body=body
        )
        from n26.notifications import enqueue_toolkit_delivery

        for delivery in ToolkitDelivery.objects.select_for_update().filter(
            campaign=campaign, identity=f"communication:{command.request_key}"
        ):
            if delivery.edited_at is None:
                delivery.original_subject, delivery.original_content = (
                    delivery.subject,
                    delivery.content,
                )
            delivery.subject = f"{campaign.name}: {title.strip()}"[:255]
            delivery.content = toolkit.content_for(campaign, "", body)
            delivery.edited_at = timezone.now()
            delivery.needs_sync = True
            delivery.save(
                update_fields=[
                    "subject",
                    "content",
                    "original_subject",
                    "original_content",
                    "edited_at",
                    "needs_sync",
                    "modified",
                ]
            )
            transaction.on_commit(
                lambda pk=str(delivery.pk): enqueue_toolkit_delivery(pk)
            )
    return toolkit.toolkit_href(campaign) + "?tab=communications"


def tag_state(tags):
    return [
        [str(t.pk), t.modified.isoformat()]
        for t in sorted(tags, key=lambda t: str(t.pk))
    ]


def record_tag(tag, actor, *, remove=False, changed=False):
    if remove:
        tag.removed_at = timezone.now()
    if tag.gang_id:
        with operation(tag.gang, actor=actor) as op:
            if tag._state.adding:
                from n26.core.models import CampaignMembership

                tag.gang.refresh_from_db(fields=["owner", "archived"])
                if (
                    tag.gang.archived
                    or not CampaignMembership.objects.filter(
                        campaign=tag.campaign, gang=tag.gang, left__isnull=True
                    ).exists()
                ):
                    raise Refusal("This gang is no longer active in the campaign.")
            tag.save()
            op.event(
                None,
                LedgerEvent.Kind.TOOLKIT_TAG,
                note=f"{'Removed' if remove else 'Updated' if changed else 'Assigned'} {tag.name}",
            )
    else:
        with campaign_operation(tag.campaign, actor=actor) as act:
            tag.save()
            act.event(
                "player_tagged",
                note=f"{'Removed' if remove else 'Updated' if changed else 'Assigned'} {tag.name}",
                about_user=tag.player,
            )


def edit_tag(campaign, actor, payload):
    anchor = (
        CampaignTag.objects.select_related("receipt__intervention")
        .filter(campaign=campaign, pk=payload.get("tag"))
        .first()
    )
    if anchor is None:
        raise Refusal("That tag does not belong to this campaign.")
    rewards = toolkit.rewards_from(payload.get("rewards"), campaign)
    if len(rewards) != 1 or rewards[0]["kind"] != "tag":
        raise Refusal("Assign one tag at a time.")
    reward = rewards[0]
    player_target = anchor.player_id is not None
    if payload.get("target", "gangs") != ("players" if player_target else "gangs"):
        raise Refusal("Keep the existing player or gang target when editing a tag.")
    if player_target:
        participants = campaign.participants.filter(
            state=CampaignParticipant.State.ACCEPTED
        ).select_related("user")
        targets = [p.user for p in participants]
        if payload.get("recipients_mode") != "all":
            ids = payload.get("players", [])
            if not isinstance(ids, list) or any(type(i) is not str for i in ids):
                raise Refusal("Select players from this campaign.")
            targets = [p for p in targets if str(p.pk) in ids]
            if len(targets) != len(set(ids)):
                raise Refusal("Select players from this campaign.")
    else:
        targets = toolkit.recipients_from(payload, campaign)
    if not targets:
        raise Refusal("Select at least one recipient.")
    tags = list(
        CampaignTag.objects.filter(
            campaign=campaign,
            assignment_key=anchor.assignment_key,
            removed_at__isnull=True,
        ).select_related("gang", "player", "campaign")
    )
    wanted = {p.pk: p for p in targets}
    held = {t.player_id if player_target else t.gang_id: t for t in tags}
    definition_changed = any(
        (t.name, t.icon, t.info) != (reward["name"], reward["icon"], reward["info"])
        for t in tags
    )
    unchanged = set(held) == set(wanted) and not definition_changed
    check_state(payload, "tag", anchor, actor, tag_state(tags), unchanged)
    if unchanged:
        return toolkit.toolkit_href(campaign) + "?tab=tags"
    for key, tag in held.items():
        if key not in wanted:
            record_tag(tag, actor, remove=True)
        elif (tag.name, tag.icon, tag.info) != (
            reward["name"],
            reward["icon"],
            reward["info"],
        ):
            tag.name, tag.icon, tag.info = (
                reward["name"],
                reward["icon"],
                reward["info"],
            )
            record_tag(tag, actor, changed=True)
    for key, target in wanted.items():
        if key in held:
            continue
        receipt, _ = InterventionReceipt.objects.get_or_create(
            intervention=anchor.receipt.intervention,
            **({"player": target} if player_target else {"gang": target}),
            defaults={"selected": [], "resolved_at": timezone.now()},
        )
        tag = CampaignTag(
            campaign=campaign,
            receipt=receipt,
            assignment_key=anchor.assignment_key,
            name=reward["name"],
            icon=reward["icon"],
            info=reward["info"],
            **({"player": target} if player_target else {"gang": target}),
        )
        record_tag(tag, actor)
        toolkit.queue(
            campaign,
            [target.pk if player_target else target.owner_id],
            identity=f"tag-added:{payload['_key']}:{key}",
            title=f"Tag: {tag.name}",
            text=f"{target.username if player_target else target.name} received {tag.name}. {tag.info}",
            sender=actor,
        )
    return toolkit.toolkit_href(campaign) + "?tab=tags"
