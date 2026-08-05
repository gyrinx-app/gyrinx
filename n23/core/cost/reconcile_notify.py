"""Aggregated user notifications for cache reconciliation (#1826 + #721).

When we reconcile lists — a single admin action, or the estate-wide backfill
run — the people affected should hear about it. But a gamer can own many gangs,
and an arbitrator's campaigns can hold many more, so notifying *per list* would
bury them under duplicates. Instead we fan out **one notification per affected
owner** and **one per affected arbitrator**, each carrying links to every gang
that changed.

This sits on top of the #721 notification service (``notify*`` in
``gyrinx.site.models``); it stays out of that generic module so the
reconcile-specific copy and grouping live with the rest of the #1826 cost code.

"Affected" means the list's cached totals actually *moved* — i.e. the number a
player sees changed. Callers pass the ids of lists whose
:class:`~n23.core.cost.reconcile.ReconcileResult` reported ``moved``. That is
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

from n23.core.models.list import List
from gyrinx.site.models import Notification, NotificationType
from n23.models import format_cost_display

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


def _change_summary(deltas, lst):
    """A ' (rating +N¢, stash +M¢)' suffix summarising what moved for a gang,
    including only the parts that actually changed. Empty if nothing did.

    ``deltas`` is keyed by ``str(list_id)`` with ``[rating_delta, stash_delta]``
    values. Mirrors the wording of the RECONCILE ledger action's description."""
    rating_delta, stash_delta = deltas.get(str(lst.pk), (0, 0))
    parts = []
    if rating_delta:
        parts.append(f"rating {format_cost_display(rating_delta, show_sign=True)}")
    if stash_delta:
        parts.append(f"stash {format_cost_display(stash_delta, show_sign=True)}")
    if not parts:
        return ""
    return format_html(" ({})", ", ".join(parts))


def _gang_links(lists, deltas, *, with_campaign=False):
    """An HTML ``<ul>`` of links to each gang, each annotated with a summary of
    what changed (rating and/or stash). Names are auto-escaped by
    ``format_html_join`` (they are user content), and ``safe_rich_text`` — which
    renders notification bodies — permits ``<ul>``/``<li>``/``<a href>``, so the
    links render in the inbox and nothing can inject markup."""
    items = format_html_join(
        "",
        '<li><a href="{}">{}</a>{}{}</li>',
        (
            (
                reverse("core:list", args=[lst.pk]),
                lst.name,
                format_html(" — {}", lst.campaign.name)
                if (with_campaign and lst.campaign_id)
                else "",
                _change_summary(deltas, lst),
            )
            for lst in lists
        ),
    )
    return format_html("<ul>{}</ul>", items)


def _owner_content(lists, deltas):
    return format_html(
        "{}{}",
        "We corrected some out-of-date cost totals on the gang(s) below. Their "
        "ratings now reflect what their fighters and equipment actually cost — "
        "no credits were spent, and nothing was added or removed.",
        _gang_links(lists, deltas),
    )


def _arb_content(lists, deltas):
    return format_html(
        "{}{}",
        "We corrected some out-of-date cost totals on gang(s) in campaigns you "
        "run. Their ratings now reflect what their fighters and equipment "
        "actually cost — no credits or equipment changed.",
        _gang_links(lists, deltas, with_campaign=True),
    )


def notify_lists_reconciled(deltas, *, sender=None, batch_size=500):
    """Fan out aggregated reconcile notifications for the given lists.

    Sends one notification to each affected **owner** (summarising their gangs)
    and one to each affected **arbitrator** (summarising affected gangs in
    campaigns they run, excluding gangs they own — those are already covered by
    their owner notification, mirroring ``notify_list_changed``'s de-dupe). Each
    gang link is annotated with a summary of what moved (rating and/or stash).

    Args:
        deltas: a mapping ``{list_id: [rating_delta, stash_delta]}`` for the
            lists whose caches actually moved (see module docstring). Keys may be
            ``str`` or ``UUID``; each delta is ``after - before`` (negative means
            the shown value went down). Only the non-zero parts are surfaced, so
            a rating-only move shows just the rating, a stash-only move just the
            stash.
        sender: acting User, or ``None`` for a system/Gyrinx notification
            (the default — reconciliation is background maintenance and players
            don't need to attribute it to a particular admin).
        batch_size: bulk-create chunk size.

    Returns:
        ``(owners_notified, arbitrators_notified)``. Safe: logs and returns
        ``(0, 0)`` on error rather than raising into the reconcile flow.
    """
    # Normalise keys to str so lookups work whether callers pass UUIDs (admin
    # path) or strings (task kwargs, which must be JSON-serialisable).
    deltas = {str(k): v for k, v in dict(deltas).items()}
    list_ids = list(deltas)
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
        # These are background-maintenance notices (no human sender), so they
        # use the SYSTEM type — and its default gear icon — rather than the
        # LIST/CAMPAIGN types a user-driven change would carry.
        for owner_id, olists in by_owner.items():
            notifs.append(
                Notification(
                    owner=owner_user[owner_id],
                    sender=sender,
                    subject=_owner_subject(len(olists)),
                    content=_owner_content(olists, deltas),
                    notification_type=NotificationType.SYSTEM,
                    show_as_banner=False,
                )
            )
        for arb_id, alists in by_arb.items():
            notifs.append(
                Notification(
                    owner=arb_user[arb_id],
                    sender=sender,
                    subject=_arb_subject(len(alists)),
                    content=_arb_content(alists, deltas),
                    notification_type=NotificationType.SYSTEM,
                    show_as_banner=False,
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
