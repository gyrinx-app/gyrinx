"""Who may act on what — the guards every player-facing view starts with.

Most scope to the owner and answer a stranger with 404 rather than 403:
which gangs and fighters exist is not something to be probed for. The
exceptions are the two read guards, ``_any_gang_or_404`` and
``_any_campaign_or_404``: a roster and a campaign are things players
send each other, so owner-scoping is the rule for acting on one and not
for reading it. Those two also record whose content the page is showing
(``n26.impersonation.note_page_subject``), because they are exactly the
pages that open for somebody other than the owner — an admin reading one
is offered a way straight into that account. All of them catch the
ULIDField refusal, because a pk that is not a ULID is only ever a bad link
and a 500 is the wrong answer to one.
"""

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme

from n26.impersonation import note_page_subject


def _safe_redirect(request, url, fallback_url="/"):
    """Redirect only to this request's host."""
    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return HttpResponseRedirect(url)
    return HttpResponseRedirect(fallback_url)


def trade_points_href(gang, user):
    """Where the Trade Points figure leads, or nowhere for a reader who
    cannot change it.

    A roster opens for whoever holds its address, so the figure strip is
    drawn for people with no business on the gang's edit screens. A
    number they cannot act on is a number, not a link: offering the door
    and refusing them at it is worse than never offering.
    """
    from django.urls import reverse

    if user is None or not user.is_authenticated or gang.owner_id != user.pk:
        return ""
    return reverse("n26-gang-trade-points", args=[gang.pk])


def link_campaign(block, user):
    """Point a gang sheet's campaign block at the campaign's own pages,
    or at nothing for a reader who cannot open them.

    A roster opens for whoever holds its address, and the campaign pages
    behind these two links are signed-in-only and inside the campaigns
    feature. A name somebody cannot open is a name, not a link: offering
    the door and refusing them at it is worse than never offering.

    One query, and only for a gang playing a campaign.
    """
    from django.urls import reverse

    from n26.flags import CAMPAIGNS, enabled

    if block is None:
        return
    if user is None or not user.is_authenticated or not enabled(CAMPAIGNS, user):
        return
    block.href = reverse("n26-campaign", args=[block.campaign_id])
    block.assets_href = block.href + "#assets"


def may_see_founding(gang, user):
    """Whether the reader is shown the founding Trade Point budgets.

    The figures on the model cards, the allowance block on the equip
    screen and the terms that make list lines count Trade Points are one
    feature, and while it is being tested it reaches the same readers as
    the Actions square that completes the founding: staff who own the
    gang. Everyone else is read exactly as before budgets existed. The
    two gates lift together.
    """
    return may_see_actions_square(gang, user)


def may_see_actions_square(gang, user):
    """Whether the gang page draws its Actions square for this reader.

    The square is shown to staff who own the gang while the actions it
    holds are still being built out. Everyone else reads the gang page
    as it was before the square existed: the Trading Post visit line
    stays on the stash card for every owner.
    """
    return bool(
        user is not None
        and user.is_authenticated
        and user.is_staff
        and gang.owner_id == user.pk
    )


def _own_gang_or_404(request, pk):
    """The gang, if it is the viewer's to act on.

    A pk that is not a ULID reaches ``to_python`` and raises
    ``ValidationError`` — a 500 for what is only ever a bad URL, so it is
    caught here. Well-formed-but-absent already 404s on its own.

    What the gang's open Visit Trading Post action brought comes with the
    row: every screen holding the figure strip draws it, and a page that
    only draws it should not pay a query to find out.
    """
    from n26.core.models import Gang
    from n26.core.models.gang import open_visit_points

    try:
        return get_object_or_404(
            Gang.objects.select_related("gang_type", "owner", "stash").annotate(
                open_visit_points=open_visit_points()
            ),
            pk=pk,
            owner=request.user,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such gang") from None


def _any_gang_or_404(request, pk):
    """The gang, whoever owns it — a roster anybody may read.

    A gang sheet is shareable: the address one player sends another shows
    the same roster to whoever opens it. What differs is what the page
    lets them *do*, which the sheet decides by asking whether the reader
    owns it — never by hiding the gang.

    Archived rosters stay out: a gang its owner has put away is not
    something a link should keep alive. A pk that is not a ULID is a bad
    URL rather than a server error, as above.

    The open visit's figure rides along, as above: a sheet draws it
    whoever is reading.
    """
    from n26.core.models import Gang
    from n26.core.models.gang import open_visit_points

    try:
        gang = get_object_or_404(
            Gang.objects.select_related("gang_type", "owner", "stash").annotate(
                open_visit_points=open_visit_points()
            ),
            pk=pk,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such gang") from None
    note_page_subject(request, gang.owner)
    return gang


def _any_campaign_or_404(request, pk):
    """The campaign, whoever arbitrates it — a table its players may read.

    Not owner-scoped: the address an arbitrator sends round shows the same
    campaign to everybody it reaches, and what differs is what the page
    lets them *do*. Every control on it is the arbitrator's, and the page
    decides that by asking who is reading, never by hiding the campaign.

    How far the address reaches is decided above this, not here: the view
    is gated on the campaigns feature and on being signed in, so a reader
    outside either gets a 404 whatever this returns. A roster reaches
    further — anybody at all may read one — and the difference is the
    gate, not the guard.

    Archived campaigns stay out, as archived rosters do: one its arbitrator
    has put away is not something a link should keep alive. A pk that is
    not a ULID is a bad URL rather than a server error.
    """
    from n26.core.models import Campaign

    try:
        campaign = get_object_or_404(
            Campaign.objects.select_related(
                "owner", "campaign_type", "additions__built_ins"
            ),
            pk=pk,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such campaign") from None
    note_page_subject(request, campaign.owner)
    return campaign


def _own_campaign_or_404(request, pk):
    """The campaign, if the viewer is its arbitrator.

    Owner-scoped where the page itself is not: reading a campaign is one
    question and changing it is another, so the screens that set a campaign
    up ask for its arbitrator by name rather than gating a control on a
    page anybody may open.
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


def _campaign_counter_or_404(request, pk):
    """A campaign's counter on a gang playing a campaign this reader
    arbitrates, live and in a live gang — or one of the reader's own
    assignments, as ``_own_assignment_or_404`` finds it.

    The one place somebody other than a gang's owner may change the
    gang: the arbitrator moving a campaign counter — Reputation, Meat —
    on any gang at their table. A counter is the campaign's where the
    gang's carrier of the campaign's type or its additions caused it, and
    only while that membership is open; the arbitrator has no say over
    what a gang tracks for itself, nor over a gang that has left.
    """
    from django.db.models import Q

    from n26.core.models import Assignment

    try:
        return _own_assignment_or_404(request, pk)
    except Http404:
        pass
    carried = Q(
        caused_by__type_carrier_of__campaign__owner=request.user,
        caused_by__type_carrier_of__left__isnull=True,
    ) | Q(
        caused_by__additions_carrier_of__campaign__owner=request.user,
        caused_by__additions_carrier_of__left__isnull=True,
    )
    try:
        return get_object_or_404(
            Assignment.objects.select_related(
                "ledger_entry",
                "gang_root__owner",
                "gang_root__stash",
                "miniature_root",
            ).filter(carried),
            pk=pk,
            counter__isnull=False,
            gang_root__archived=False,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such assignment") from None


def _own_assignment_or_404(request, pk):
    """One of the viewer's own assignments, live and in a live gang.

    Scoped by ``gang_root``, which every assignment carries whatever it
    hangs off — so a weapon on a fighter, a sight on that weapon and a
    crate in the stash are all reached the same way, and none of them by
    somebody else. Archived assignments are out: a thing already sold is not
    something to sell again. That is a courtesy to a stale button, not
    what keeps the gang from being charged twice — this runs before the
    operation holds the gang's line, so two clicks can both pass it. The
    operation reads the row again under the lock and stands down if it
    has gone (``n26.core.operations._under_the_lock``).
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
    from n26.core.models.gang import open_visit_points

    try:
        miniature = get_object_or_404(
            Miniature.objects.select_related(
                "membership__gang__gang_type",
                "membership__gang__owner",
                "membership__gang__stash",
                # The profile's rank rides along: every fighter screen
                # names the model, and the header says the rank beside it.
                "membership__profile__category",
            ).annotate(open_visit_points=open_visit_points("membership__gang")),
            pk=pk,
            membership__gang__owner=request.user,
            membership__gang__archived=False,
            membership__archived=False,
        )
    except ValidationError:
        raise Http404("No such fighter") from None
    # Asked for on the gang's behalf — a fighter's screens draw the
    # gang's figures — so it is handed over to the gang that draws it.
    miniature.gang.hold_open_visit(miniature.open_visit_points)
    return miniature
