"""Telling somebody something happened, through the site's own inbox.

The single-file seam onto the platform's notifications, and the only file in
this edition that imports them. It works the way ``n26/analytics.py`` does,
and for the same reason: an inbox is the site's, not an edition's. A person
has one inbox and reads it in one place, whichever game the thing that filled
it came from, and a second store here would give them two.

What crosses is one call. The words are ours — an edition knows what happened
and how to say it — and the delivery is the platform's.

Failure is not this caller's business: the platform's ``notify`` logs and
returns ``None`` rather than raising, so an invitation is still written when
the inbox is having a bad day. A notification is how somebody hears about an
act, never the record that it happened; that is the campaign's log.
"""

from gyrinx.site.models import NotificationType, notify


def tell(recipient, subject, content="", sender=None):
    """Put one notification in somebody's inbox, about a campaign.

    No ``target`` or ``scope``. The platform stores those as generic links
    whose key column is a UUID, and this edition's rows are keyed by ULID —
    handing one over raises, and the notification is lost. What a reader needs
    is in the words, so the words carry it.

    **Call this after the transaction that recorded the act, never inside
    it.** ``notify`` catches its own errors, but a database error inside an
    atomic block has already poisoned it: the block rolls back on the way out
    and takes the act with it, while the caller sees nothing wrong.
    ``deliver`` does the waiting.
    """
    return notify(
        recipient=recipient,
        subject=subject,
        content=content,
        notification_type=NotificationType.CAMPAIGN,
        sender=sender,
    )


def deliver(recipient, subject, content="", sender=None):
    """Tell somebody once the act that prompted it is safely written.

    Telling is not the record — the campaign's log is — so it waits for the
    commit and never stands between the act and the database.
    """
    from django.db import transaction

    transaction.on_commit(
        lambda: tell(recipient, subject, content=content, sender=sender)
    )
