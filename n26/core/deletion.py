"""Permanently delete gangs and campaigns selected for content cleanup.

Player-facing gang deletion archives data. Author-created test gangs can
still protect staged content after archival, so library deletion may need
to destroy them and their dependants.

``n26.library.deletion`` decides which objects qualify. These functions
perform database cascades; tests build representative complete graphs and
verify dependent table counts.
"""


def destroy_gang(gang):
    """Delete the gang and its dependent player data through database cascades.

    Includes assignments, roster models, stash, activities, ledger, print layouts,
    memberships and battle entries. Other gangs' payments retain their events
    with the deleted counterpart cleared.
    """
    from django.db import transaction

    from n26.core.models import Miniature
    from n26.write_pause import write_guard

    models_in = list(
        Miniature.objects.filter(membership__gang_root=gang).values_list(
            "pk", flat=True
        )
    )
    with transaction.atomic(), write_guard():
        gang.delete()
        # Roster models must cascade with their memberships; unreachable survivors
        # would prevent complete cleanup.
        left = Miniature.objects.filter(pk__in=models_in).count()
        if left:
            raise RuntimeError(f"{left} models survived deleting {gang.name}")


def destroy_campaign(campaign):
    """Delete a campaign and its memberships, events, assets, battles and invitations.

    Its additions type and pack remain library content for the caller to
    delete after their campaign protection is removed.
    """
    from django.db import transaction

    from n26.write_pause import write_guard

    with transaction.atomic(), write_guard():
        campaign.delete()
