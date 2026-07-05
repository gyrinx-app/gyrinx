"""Aggregated user notifications for cache reconciliation (#1826 + #721).

When we reconcile lists — a single admin action, or the estate-wide backfill
run — the people affected should hear about it. But a gamer can own many gangs,
and an arbitrator's campaigns can hold many more, so notifying *per list* would
bury them under duplicates. Instead we fan out **one notification per affected
owner** and **one per affected arbitrator**, each carrying links to every gang
that changed.

This sits on top of the #721 notification service (``notify*`` in
``models.notification``); it stays out of that generic module so the
reconcile-specific copy and grouping live with the rest of the #1826 cost code.

"Affected" means the list's cached totals actually *moved* — i.e. the number a
player sees changed. Callers pass the ids of lists whose
:class:`~gyrinx.core.cost.reconcile.ReconcileResult` reported ``moved``. That is
deliberately narrower than "a RECONCILE action was written": reconcile also
writes an action when only the *ledger head* needed aligning while the cache was
already correct — nothing a player would notice, so no notification. And it is
wider than "an action was written": a pure un-audited cache correction moves the
cache with no action at all, and the player should still be told.
"""

import logging
from collections import defaultdict

from django.urls import reverse
from django.utils.html import format_html, format_html_join

from gyrinx.core.models.list import List
from gyrinx.core.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)

__all__ = ["notify_lists_reconciled"]


def _owner_subject(n):
    return (
        "A gang of yours was recalculated"
        if n == 1
        else f"{n} of your gangs were recalculated"
    )


def _arb_subject(n):
    return (
        "A gang in your campaign was recalculated"
        if n == 1
        else f"{n} gangs in your campaigns were recalculated"
    )


def _gang_links(lists, *, with_campaign=False):
    """An HTML ``<ul>`` of links to each gang. Names are auto-escaped by
    ``format_html_join`` (they are user content), and ``safe_rich_text`` — which
    renders notification bodies — permits ``<ul>``/``<li>``/``<a href>``, so the
    links render in the inbox and nothing can inject markup."""
    items = format_html_join(
        "",
        '<li><a href="{}">{}</a>{}</li>',
        (
            (
                reverse("core:list", args=[lst.pk]),
                lst.name,
                format_html(" — {}", lst.campaign.name)
                if (with_campaign and lst.campaign_id)
                else "",
            )
            for lst in lists
        ),
    )
    return format_html("<ul>{}</ul>", items)


def _owner_content(lists):
    return format_html(
        "{}{}",
        "We corrected some out-of-date cost totals on the gang(s) below. Their "
        "ratings now reflect what their fighters and equipment actually cost — "
        "no credits were spent, and nothing was added or removed.",
        _gang_links(lists),
    )


def _arb_content(lists):
    return format_html(
        "{}{}",
        "We corrected some out-of-date cost totals on gang(s) in campaigns you "
        "run. Their ratings now reflect what their fighters and equipment "
        "actually cost — no credits or equipment changed.",
        _gang_links(lists, with_campaign=True),
    )


def notify_lists_reconciled(list_ids, *, sender=None, batch_size=500):
    """Fan out aggregated reconcile notifications for the given lists.

    Sends one notification to each affected **owner** (summarising their gangs)
    and one to each affected **arbitrator** (summarising affected gangs in
    campaigns they run, excluding gangs they own — those are already covered by
    their owner notification, mirroring ``notify_list_changed``'s de-dupe).

    Args:
        list_ids: ids of lists whose caches actually moved (see module docstring).
        sender: acting User, or ``None`` for a system/Gyrinx notification
            (the default — reconciliation is background maintenance and players
            don't need to attribute it to a particular admin).
        batch_size: bulk-create chunk size.

    Returns:
        ``(owners_notified, arbitrators_notified)``. Safe: logs and returns
        ``(0, 0)`` on error rather than raising into the reconcile flow.
    """
    list_ids = list(dict.fromkeys(list_ids))  # de-dupe, preserve order
    if not list_ids:
        return (0, 0)

    try:
        lists = list(
            List.objects.filter(pk__in=list_ids).select_related(
                "owner", "campaign", "campaign__owner"
            )
        )

        by_owner = defaultdict(list)
        owner_user = {}
        by_arb = defaultdict(list)
        arb_user = {}
        for lst in lists:
            if lst.owner_id:
                by_owner[lst.owner_id].append(lst)
                owner_user[lst.owner_id] = lst.owner
            if (
                lst.is_campaign_mode
                and lst.campaign_id
                and lst.campaign.owner_id
                and lst.campaign.owner_id != lst.owner_id
            ):
                by_arb[lst.campaign.owner_id].append(lst)
                arb_user[lst.campaign.owner_id] = lst.campaign.owner

        notifs = []
        for owner_id, olists in by_owner.items():
            notifs.append(
                Notification(
                    owner=owner_user[owner_id],
                    sender=sender,
                    subject=_owner_subject(len(olists)),
                    content=_owner_content(olists),
                    notification_type=NotificationType.LIST,
                    show_as_banner=False,
                    icon="bi-calculator",
                )
            )
        for arb_id, alists in by_arb.items():
            notifs.append(
                Notification(
                    owner=arb_user[arb_id],
                    sender=sender,
                    subject=_arb_subject(len(alists)),
                    content=_arb_content(alists),
                    notification_type=NotificationType.CAMPAIGN,
                    show_as_banner=False,
                    icon="bi-calculator",
                )
            )

        for i in range(0, len(notifs), batch_size):
            Notification.objects.bulk_create(
                notifs[i : i + batch_size], batch_size=batch_size
            )
        return (len(by_owner), len(by_arb))
    except Exception:
        logger.exception("notify_lists_reconciled failed for %s lists", len(list_ids))
        return (0, 0)
