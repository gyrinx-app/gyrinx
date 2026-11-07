"""Resolve player resources with ownership, archive and identifier checks.

Write guards normally require the gang owner and return 404 for absent or
unauthorised resources. Shareable gang and campaign reads resolve any owner;
views apply their own authentication and action permissions.

Shared read guards record the page subject for impersonation controls.
Convert malformed ULID validation errors into 404 responses. Load relations
needed by common headers and figure strips with the guarded resource.
"""

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme

from n26.impersonation import note_page_subject


def own_address(request, url):
    """Accept a return URL only when it matches this request's host and HTTPS requirement."""
    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url
    return ""


def _safe_redirect(request, url, fallback_url="/"):
    """Redirect to a validated same-host URL, otherwise use the fallback."""
    return HttpResponseRedirect(own_address(request, url) or fallback_url)


def may_mark_status(gang, user):
    """Allow manual model status controls only for the signed-in gang owner."""
    return user is not None and user.is_authenticated and gang.owner_id == user.pk


def link_model_cards(gang, cards, user):
    """Owner-only card management links."""
    from django.urls import reverse

    available = user is not None and user.is_authenticated and gang.owner_id == user.pk
    if available:
        for card in cards:
            card.model_cards_href = reverse("n26-model-cards", args=[gang.pk, card.id])
    return available


def status_href(gang, miniature, user=None, *, back="", ransom=True):
    """Link to status editing or ransom payment when status controls are available.

    ``ransom=False`` always selects status editing. ``back`` identifies the return
    surface. Passing a non-owner user returns no link.
    """
    from django.urls import reverse

    from n26.core.status import Status

    if user is not None and not may_mark_status(gang, user):
        return ""
    sheet = reverse("n26-gang", args=[gang.pk])
    kind = "ransom" if ransom and miniature.status == Status.RANSOMED else "status"
    tail = f"&back={back}" if back else ""
    return f"{sheet}?{kind}={miniature.pk}{tail}"


def trade_points_href(gang, user):
    """Link owners to relevant Trade Point controls; other readers receive no link."""
    from django.urls import reverse

    if user is None or not user.is_authenticated or gang.owner_id != user.pk:
        return ""
    from n26.core.built_in_actions import trading_post_visit_relevant

    if not trading_post_visit_relevant(gang) and not gang.visiting_trading_post:
        return ""
    return reverse("n26-gang-trade-points", args=[gang.pk])


def credits_campaign(gang, user):
    """Find an active campaign whose arbitrator may change this gang's credits.

    Return ``None`` for the gang owner because their access does not require a
    campaign. Apply the campaign recording policy after resolving membership.
    """
    from n26.core.battle_permissions import may_record_gang
    from n26.core.models import CampaignMembership

    if user is None or not user.is_authenticated or gang.owner_id == user.pk:
        return None
    membership = (
        CampaignMembership.objects.filter(
            gang=gang, left__isnull=True, campaign__owner=user
        )
        .select_related("campaign")
        .first()
    )
    if membership is None:
        return None
    campaign = membership.campaign
    if not may_record_gang(
        gang=gang, actor=user, campaign=campaign, active_gang_ids={gang.pk}
    ):
        return None
    return campaign


def credits_href(gang, user):
    """Link the owner to credit editing only when the gang tracks credits."""
    from django.urls import reverse

    if gang.credits_unlimited:
        return ""
    if user is None or not user.is_authenticated or gang.owner_id != user.pk:
        return ""
    return reverse("n26-gang-credits", args=[gang.pk])


def link_campaign(block, user):
    """Add campaign and asset links only for authenticated gang-sheet viewers."""
    from django.urls import reverse

    if block is None:
        return
    if user is None or not user.is_authenticated:
        return
    block.href = reverse("n26-campaign", args=[block.campaign_id])
    block.assets_href = block.href + "#assets"


def may_see_founding(gang, user):
    """Allow founding controls and budgets only for the gang owner."""
    return user is not None and user.is_authenticated and gang.owner_id == user.pk


def _own_gang_or_404(request, pk):
    """Resolve a live gang owned by the viewer and convert invalid identifiers to 404.

    Load the owner, type and stash and annotate open-visit points for figure strips.
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
    """Resolve any live gang for shareable reading and record its owner as page subject.

    Annotate open-visit points and load common header relations. Invalid identifiers
    return 404; available controls are determined separately.
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


def _any_campaign_or_404(request, pk, *, with_owner_badge=True):
    """Resolve any live campaign and record its owner as page subject.

    Views enforce authentication. Load header relations and optionally prefetch
    owner badge grants; command and dialog callers can disable that prefetch.
    Invalid identifiers return 404.
    """
    from n26.core.models import Campaign

    try:
        campaigns = Campaign.objects.select_related(
            "owner", "owner__profile", "campaign_type", "additions__built_ins"
        )
        if with_owner_badge:
            campaigns = campaigns.prefetch_related("owner__badge_grants")
        campaign = get_object_or_404(campaigns, pk=pk, archived=False)
    except ValidationError:
        raise Http404("No such campaign") from None
    note_page_subject(request, campaign.owner)
    return campaign


def _own_campaign_or_404(request, pk, *, with_owner_badge=True):
    """Resolve a live campaign owned by the viewer, returning 404 for invalid identifiers.

    Load the owner's profile and optionally prefetch badge grants for the header.
    """
    from n26.core.models import Campaign

    try:
        campaigns = Campaign.objects.select_related("owner", "owner__profile")
        if with_owner_badge:
            campaigns = campaigns.prefetch_related("owner__badge_grants")
        return get_object_or_404(
            campaigns,
            pk=pk,
            owner=request.user,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such campaign") from None


def _campaign_counter_or_404(request, pk):
    """Resolve an owned assignment or a live counter caused by the viewer's campaign.

    Arbitrator access requires an active membership whose campaign type or additions
    caused the assignment. Exclude archived assignments and gangs.
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
    """Resolve a live assignment through its gang_root ownership.

    This pre-operation check does not guarantee idempotency. Operations must reload
    under the gang lock because concurrent submissions can both pass this guard.
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
    """Resolve a model in the viewer's live gang with a live membership.

    Load header and pet-owner relations and open-visit points; return 404 for
    invalid identifiers.
    """
    from n26.core.models import Miniature
    from n26.core.models.gang import open_visit_points

    try:
        miniature = get_object_or_404(
            Miniature.objects.select_related(
                "membership__gang__gang_type",
                "membership__gang__owner",
                "membership__gang__stash",
                # Load the profile category used to display rank in model headers.
                "membership__profile__category",
                # Load the model whose acquisition caused this pet for its owner display.
                "membership__caused_by__miniature_root",
            ).annotate(open_visit_points=open_visit_points("membership__gang")),
            pk=pk,
            membership__gang__owner=request.user,
            membership__gang__archived=False,
            membership__archived=False,
        )
    except ValidationError:
        raise Http404("No such fighter") from None
    # Cache the annotated open-visit points on the gang whose figures are rendered.
    miniature.gang.hold_open_visit(miniature.open_visit_points)
    return miniature


def _recording_campaign_or_404(request, pk, *, with_owner_badge=True):
    from n26.core.campaign_permissions import may_record_campaign

    campaign = _any_campaign_or_404(request, pk, with_owner_badge=with_owner_badge)
    if not may_record_campaign(campaign, request.user):
        raise Http404("No such campaign")
    return campaign
