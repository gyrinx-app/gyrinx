"""Deleting a gang or a campaign for good.

Nowhere else in this edition deletes player data: a player's Delete
gang archives, because a gang somebody played is history, and history
stays true whether or not the roster is on show. The one gang that is
not history is the one an author founded to check content that was not
yet live — hired from, equipped, and then archived, still holding every
row it touched and so still protecting them. Deleting that content means
deleting the gang, and this is where that happens.

Both verbs are plain deletes that rely on what the database already
cascades, and they exist so the one place that decides *which* gangs may
go (``n26.library.deletion``) is not the place that knows what hangs off
one. What hangs off a gang is proved rather than listed: a test builds
the fullest gang the verbs can and asserts every table returns to its
prior count.
"""


def destroy_gang(gang):
    """Delete a gang and everything that is only there because of it.

    The database cascades the lot: every assignment rooted on the gang,
    the models those brought in (a model's membership is one such
    assignment), the stash, the actions, the ledger, the saved print
    layouts, the campaign memberships and the battle lines naming it.
    A payment another gang made to this one keeps its line with the
    counterpart emptied, which is what that column says it does.
    """
    from n26.core.models import Miniature

    models_in = list(
        Miniature.objects.filter(membership__gang_root=gang).values_list(
            "pk", flat=True
        )
    )
    gang.delete()
    # A model lives only through its membership, so none can survive the
    # gang. Checked because a model nothing reaches would be a row
    # nobody could ever delete.
    left = Miniature.objects.filter(pk__in=models_in).count()
    if left:
        raise RuntimeError(f"{left} models survived deleting {gang.name}")


def destroy_campaign(campaign):
    """Delete a campaign. The memberships, log, assets, battles and
    invitations cascade with it.

    What the campaign owned — its additions type, its pack and whatever
    the arbitrator created in that pack — is library content, and stays
    for the caller to delete once the campaign no longer protects it.
    """
    campaign.delete()
