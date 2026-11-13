"""Capture selected campaign actions and deliver fixed-window wrap-up reports."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from n26.core.models.toolkit import (
    ALERT_EVENTS,
    ToolkitAlert,
    ToolkitAlertEvent,
    ToolkitAlertSettings,
)
from n26.core.operations import Refusal
from n26.write_pause import write_guard


def preferences(campaign):
    settings = ToolkitAlertSettings.objects.filter(campaign=campaign).first()
    return {
        "immediate": settings.immediate if settings else True,
        "report_enabled": bool(settings and settings.report_days),
        "report_days": settings.report_days if settings and settings.report_days else 7,
        "next_report_at": settings.next_report_at.isoformat()
        if settings and settings.next_report_at
        else None,
    }


def configure(campaign, payload):
    events = payload.get("events", [])
    immediate = payload.get("immediate", True)
    report_enabled = payload.get("report_enabled", False)
    days = payload.get("report_days", 7)
    if not isinstance(events, list) or any(
        not isinstance(e, str) or e not in dict(ALERT_EVENTS) for e in events
    ):
        raise Refusal("Select events from this campaign's alert list.")
    if type(immediate) is not bool or type(report_enabled) is not bool:
        raise Refusal("Choose how your alerts should arrive.")
    if report_enabled and (type(days) is not int or not 1 <= days <= 365):
        raise Refusal("Enter a report interval between 1 and 365 days.")
    settings, _ = ToolkitAlertSettings.objects.get_or_create(campaign=campaign)
    settings = ToolkitAlertSettings.objects.select_for_update().get(pk=settings.pk)
    settings.immediate = immediate
    if report_enabled:
        if settings.report_days is None:
            settings.window_start = timezone.now()
        settings.report_days = days
        settings.next_report_at = settings.window_start + timedelta(days=days)
    else:
        settings.report_days = None
        settings.window_start = None
        settings.next_report_at = None
    settings.save()
    ToolkitAlert.objects.filter(campaign=campaign).exclude(event__in=events).delete()
    for event in set(events):
        ToolkitAlert.objects.get_or_create(campaign=campaign, event=event)
    return settings


def capture(campaign, event, *, identity, text, actor=None):
    from n26.core.toolkit import queue

    if event not in dict(ALERT_EVENTS):
        raise ValueError(f"Unknown toolkit alert event: {event}")
    # The settings lock also orders events against a report's closing boundary.
    with transaction.atomic(), write_guard():
        if not ToolkitAlert.objects.filter(campaign=campaign, event=event).exists():
            return None
        settings, _ = ToolkitAlertSettings.objects.get_or_create(campaign=campaign)
        settings = ToolkitAlertSettings.objects.select_for_update().get(pk=settings.pk)
        if not ToolkitAlert.objects.filter(campaign=campaign, event=event).exists():
            return None
        captured, created = ToolkitAlertEvent.objects.get_or_create(
            campaign=campaign,
            event=event,
            identity=identity,
            defaults={"text": text, "actor": actor, "occurred_at": timezone.now()},
        )
        if created and settings.immediate:
            queue(
                campaign,
                [campaign.owner_id],
                identity=f"alert:{event}:{identity}",
                title=dict(ALERT_EVENTS)[event],
                text=text,
                sender=actor,
            )
        return captured


def period(start, end):
    return f"from {start.strftime('%d %b %Y, %H:%M UTC')} to {end.strftime('%d %b %Y, %H:%M UTC')}"


def report_content(start, end, events):
    events = list(events)
    if not events:
        return f"None of the selected actions took place {period(start, end)}.", ""
    sections = []
    for event, label in ALERT_EVENTS:
        entries = [e for e in events if e.event == event]
        if entries:
            items = format_html_join("", "<li>{}</li>", ((e.text,) for e in entries))
            sections.append(format_html("<h3>{}</h3><ul>{}</ul>", label, items))
    return f"Selected actions {period(start, end)}:", str(
        format_html_join("", "{}", ((s,) for s in sections))
    )


def deliver_due_reports(*, now=None):
    from n26.core.toolkit import queue

    now = now or timezone.now()
    due = list(
        ToolkitAlertSettings.objects.filter(
            next_report_at__lte=now, campaign__archived=False
        )
        .order_by("next_report_at")
        .values_list("pk", flat=True)[:100]
    )
    sent = 0
    for settings_pk in due:
        # Bound one delayed run; the next tick continues any remaining windows.
        for _ in range(32):
            with transaction.atomic(), write_guard():
                settings = (
                    ToolkitAlertSettings.objects.select_for_update(of=("self",))
                    .select_related("campaign")
                    .get(pk=settings_pk)
                )
                if (
                    not settings.report_days
                    or not settings.next_report_at
                    or settings.next_report_at > now
                    or settings.campaign.archived
                ):
                    break
                start, end = settings.window_start, settings.next_report_at
                events = list(
                    ToolkitAlertEvent.objects.filter(
                        campaign=settings.campaign,
                        occurred_at__gte=start,
                        occurred_at__lt=end,
                    ).order_by("occurred_at", "pk")
                )
                text, message = report_content(start, end, events)
                queue(
                    settings.campaign,
                    [settings.campaign.owner_id],
                    identity=f"report:{settings.pk}:{end.isoformat()}",
                    title="Campaign wrap-up",
                    text=text,
                    message=message,
                    sender=None,
                )
                settings.window_start = end
                settings.next_report_at = end + timedelta(days=settings.report_days)
                settings.save(
                    update_fields=["window_start", "next_report_at", "modified"]
                )
                sent += 1
    return sent
