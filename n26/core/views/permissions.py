"""Who may act on what — the guards every player-facing view starts with.

Most scope to the owner and answer a stranger with 404 rather than 403:
which gangs and fighters exist is not something to be probed for. The
exception is ``_any_gang_or_404``, which scopes to nobody, because a
roster is a thing players send each other — owner-scoping is the rule
for acting on a gang, not for reading one. All of them catch the
ULIDField refusal, because a pk that is not a ULID is only ever a bad
link and a 500 is the wrong answer to one.
"""

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme


def _safe_redirect(request, url, fallback_url="/"):
    """Redirect only to this request's host."""
    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return HttpResponseRedirect(url)
    return HttpResponseRedirect(fallback_url)


def _own_gang_or_404(request, pk):
    """The gang, if it is the viewer's to act on.

    A pk that is not a ULID reaches ``to_python`` and raises
    ``ValidationError`` — a 500 for what is only ever a bad URL, so it is
    caught here. Well-formed-but-absent already 404s on its own.
    """
    from n26.core.models import Gang

    try:
        return get_object_or_404(
            Gang.objects.select_related("gang_type", "owner", "stash"),
            pk=pk,
            owner=request.user,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such gang") from None


def _any_gang_or_404(pk):
    """The gang, whoever owns it — a roster anybody may read.

    A gang sheet is shareable: the address one player sends another shows
    the same roster to whoever opens it. What differs is what the page
    lets them *do*, which the sheet decides by asking whether the reader
    owns it — never by hiding the gang.

    Archived rosters stay out: a gang its owner has put away is not
    something a link should keep alive. A pk that is not a ULID is a bad
    URL rather than a server error, as above.
    """
    from n26.core.models import Gang

    try:
        return get_object_or_404(
            Gang.objects.select_related("gang_type", "owner", "stash"),
            pk=pk,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such gang") from None


def _own_campaign_or_404(request, pk):
    """The campaign, if the viewer is its arbitrator.

    Owner-scoped where a gang sheet is not: a roster is a thing players
    send each other, while a campaign's own pages are where its arbitrator
    sets it up. What a player in a campaign gets to see is a different
    question, answered by a different view when there are players to ask
    about.
    """
    from n26.core.models import Campaign

    try:
        return get_object_or_404(
            Campaign.objects.select_related("owner"),
            pk=pk,
            owner=request.user,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such campaign") from None


def _own_assignment_or_404(request, pk):
    """One of the viewer's own assignments, live and in a live gang.

    Scoped by ``gang_root``, which every assignment carries whatever it
    hangs off — so a weapon on a fighter, a sight on that weapon and a
    crate in the stash are all reached the same way, and none of them by
    somebody else. Archived assignments are out: a thing already sold is not
    something to sell again, and a second click of a stale button must
    find nothing rather than charge the gang twice.
    """
    from n26.core.models import Assignment

    try:
        return get_object_or_404(
            Assignment.objects.select_related(
                "ledger_entry",
                "gang_root__owner",
                "gang_root__stash",
                "miniature_root",
            ),
            pk=pk,
            gang_root__owner=request.user,
            gang_root__archived=False,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such assignment") from None


def _own_miniature_or_404(request, pk):
    """The fighter, if theirs to act on — the miniature-shaped twin of
    ``_own_gang_or_404``, with the same bad-ULID guard. Archived
    memberships and archived gangs are out: a dead fighter's Equip link
    should go the way the fighter did."""
    from n26.core.models import Miniature

    try:
        return get_object_or_404(
            Miniature.objects.select_related(
                "membership__gang__gang_type",
                "membership__gang__owner",
                "membership__gang__stash",
                # The profile's rank rides along: every fighter screen
                # names the model, and the header says the rank beside it.
                "membership__profile__category",
            ),
            pk=pk,
            membership__gang__owner=request.user,
            membership__gang__archived=False,
            membership__archived=False,
        )
    except ValidationError:
        raise Http404("No such fighter") from None
