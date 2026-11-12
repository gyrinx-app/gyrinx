"""Send N26 campaign notifications through the shared platform inbox. The campaign log
records the operation independently of notification delivery.
"""

import logging

from django.db import transaction
from django.tasks import task
from django.utils import timezone

from gyrinx.site.models import NotificationType, notify
from gyrinx.tasks import TaskRoute

logger = logging.getLogger(__name__)

#: Truncate combined campaign and account names to the notification subject column's
#: limit.
SUBJECT_LENGTH = 255


def tell(recipient, subject, content="", sender=None, about=None):
    """Send a campaign notification, truncating its subject to the platform limit. about
    supplies the related object and its get_absolute_url link.

    Call only after the domain transaction commits: a caught database error can still
    invalidate an enclosing transaction. Use deliver to schedule that ordering.
    """
    return notify(
        recipient=recipient,
        subject=subject[:SUBJECT_LENGTH],
        content=content,
        notification_type=NotificationType.CAMPAIGN,
        sender=sender,
        target=about,
    )


def deliver(recipient, subject, content="", sender=None, about=None):
    """Schedule tell with transaction.on_commit so inbox failures cannot roll back the
    domain operation.
    """
    from django.db import transaction

    transaction.on_commit(
        lambda: tell(recipient, subject, content=content, sender=sender, about=about)
    )


def record_cycle_deliveries(transition):
    """Commit recipient obligations with the transition, then request delivery.

    A later flag change or campaign departure does not retract a committed
    notification. Pending records also survive a failed publish after commit.
    """
    from n26.core.models import CampaignCycleDelivery, CampaignParticipant

    receipt = transition.receipt
    campaign = receipt["campaign"]
    current = receipt["current_cycle"]
    if transition.kind == "phase_changed":
        phase = receipt["current_phase"]["name"]
        subject = f"{campaign}: {phase}"
        content = f"{current} now uses {phase}. Read the phase rules."
    elif transition.kind == "finished":
        subject = f"{campaign}: campaign finished"
        content = f"{current} ended. Complete the post-cycle actions for {current}."
    else:
        subject = f"{campaign}: {current} has begun"
        parts = [f"{current} has begun."]
        if receipt["previous_cycle"]:
            ended = receipt["previous_cycle"]
            parts.append(f"{ended} ended. Complete the post-cycle actions for {ended}.")
        if receipt["enters_phase"]:
            phase = receipt["current_phase"]["name"]
            parts.append(f"The campaign has entered {phase}. Read the phase rules.")
        content = " ".join(parts)
    recipients = list(
        CampaignParticipant.objects.filter(
            campaign_id=transition.campaign_id,
            state=CampaignParticipant.State.ACCEPTED,
        ).values_list("user_id", flat=True)
    )
    CampaignCycleDelivery.objects.bulk_create(
        [
            CampaignCycleDelivery(
                transition=transition,
                recipient_id=recipient,
                subject=subject[:SUBJECT_LENGTH],
                content=content,
            )
            for recipient in recipients
        ]
    )
    if recipients:
        transaction.on_commit(lambda: enqueue_cycle_transition(str(transition.pk)))


def enqueue_cycle_transition(transition_id):
    try:
        deliver_cycle_transition.enqueue(transition_id)
    except Exception:
        logger.exception("Cycle notification publish failed: %s", transition_id)


def _deliver_cycle(delivery_id):
    from n26.core.models import CampaignCycleDelivery
    from n26.write_pause import write_guard

    with transaction.atomic(), write_guard():
        delivery = (
            CampaignCycleDelivery.objects.select_for_update(of=("self",))
            .select_related(
                "recipient", "transition__actor", "transition__current_cycle"
            )
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None or delivery.delivered_at is not None:
            return False
        notification = tell(
            delivery.recipient,
            delivery.subject,
            delivery.content,
            sender=delivery.transition.actor,
            about=delivery.transition.current_cycle,
        )
        if notification is None:
            raise RuntimeError("Cycle notification creation failed.")
        delivery.notification_id = notification.pk
        delivery.delivered_at = timezone.now()
        delivery.save(update_fields=["notification_id", "delivered_at", "modified"])
        return True


@task
def deliver_cycle_transition(transition_id: str):
    """Create each inbox record and acknowledge its obligation atomically."""
    from n26.core.models import CampaignCycleDelivery

    pending = CampaignCycleDelivery.objects.filter(
        transition_id=transition_id, delivered_at__isnull=True
    )
    identities = list(pending.order_by("id").values_list("pk", flat=True)[:100])
    delivered = sum(_deliver_cycle(identity) for identity in identities)
    if pending.exists():
        enqueue_cycle_transition(transition_id)
    return delivered


@task
def retry_pending_cycle_notifications():
    """Recover committed deliveries whose immediate publish or worker failed."""
    from n26.core.models import CampaignCycleDelivery

    transitions = list(
        CampaignCycleDelivery.objects.filter(delivered_at__isnull=True)
        .order_by("transition_id")
        .values_list("transition_id", flat=True)
        .distinct()[:100]
    )
    for transition_id in transitions:
        deliver_cycle_transition.func(str(transition_id))
    return len(transitions)


task_routes = [
    TaskRoute(deliver_cycle_transition, write_scope="n26"),
    TaskRoute(
        retry_pending_cycle_notifications, schedule="*/5 * * * *", write_scope="n26"
    ),
]


def enqueue_toolkit_delivery(delivery_id):
    try:
        deliver_toolkit_notification.func(delivery_id)
    except Exception:
        logger.exception("Toolkit notification delivery pending: %s", delivery_id)


@task
def deliver_toolkit_notification(delivery_id: str):
    from n26.core.models.toolkit import ToolkitDelivery
    from n26.write_pause import write_guard

    with transaction.atomic(), write_guard():
        delivery = (
            ToolkitDelivery.objects.select_for_update(of=("self",))
            .select_related("recipient", "sender")
            .filter(pk=delivery_id, delivered_at__isnull=True)
            .first()
        )
        if delivery is None:
            return False
        notification = tell(
            delivery.recipient,
            delivery.subject,
            delivery.content,
            sender=delivery.sender,
            about=delivery,
        )
        if notification is None:
            raise RuntimeError("Toolkit notification creation failed.")
        delivery.delivered_at = timezone.now()
        delivery.save(update_fields=["delivered_at", "modified"])
        return True


@task
def retry_toolkit_notifications():
    from n26.core.models.toolkit import ToolkitDelivery

    for pk in (
        ToolkitDelivery.objects.filter(delivered_at__isnull=True)
        .order_by("created")
        .values_list("pk", flat=True)[:100]
    ):
        enqueue_toolkit_delivery(str(pk))


task_routes += [
    TaskRoute(deliver_toolkit_notification, write_scope="n26"),
    TaskRoute(retry_toolkit_notifications, schedule="*/5 * * * *", write_scope="n26"),
]
