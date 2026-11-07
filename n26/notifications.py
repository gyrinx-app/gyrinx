"""Send N26 campaign notifications through the shared platform inbox. The campaign log
records the operation independently of notification delivery.
"""

from gyrinx.site.models import NotificationType, notify

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
