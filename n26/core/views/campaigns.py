"""Setting a campaign up, and the arbitrator's pages for one.

Every view here is gated twice: ``requires_flag`` outside, so a reader
without the campaigns feature is told the address does not exist, and
``login_required`` inside, so the ones who do have it are still asked to
sign in. The order matters — a login redirect on a gated address would
itself say that something is there.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from n26.core.views.permissions import _own_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag

#: How many campaigns a page of the list holds. A row is a name, a budget
#: and its controls — shorter than a gang's, so a page holds more of them.
CAMPAIGNS_PER_PAGE = 25

#: How many accounts a search for somebody to invite offers at once. Enough
#: to find the person, few enough that the page is not a directory.
PEOPLE_FOUND = 10

#: How many battles the campaign's page lists, newest first. A campaign
#: played for a year has more than a page wants; the rest wait for a screen
#: of their own.
BATTLES_ON_THE_PAGE = 10

#: How many acts the campaign's own page shows before saying there are more.
#: Enough to see what happened since last time without burying the page.
LOG_ON_THE_PAGE = 10


@requires_flag(CAMPAIGNS)
@login_required
def campaigns(request):
    """Every campaign this reader arbitrates, narrowed by ``?q=``.

    Drawn by the same table the gangs list uses, so the two pages search the
    same way and count the same way. The matching is the platform's
    ``search_queryset`` for the same reason the gangs list uses it: a second
    search written here is how two lists come to disagree about what a query
    means.
    """
    # The gangs list builds the numbered links the same way, and a second
    # copy of that would be a second set of addresses to keep in step.
    from gyrinx.querysets import search_queryset
    from n26.core.models import Campaign
    from n26.core.views.gangs import _pages

    query = request.GET.get("q", "").strip()
    listed = Campaign.objects.filter(owner=request.user, archived=False).order_by(
        "name"
    )
    found = search_queryset(listed, query, ["name"])

    page = Paginator(found, CAMPAIGNS_PER_PAGE).get_page(request.GET.get("page"))
    return render(
        request,
        "n26/campaigns.html",
        {
            "invitations": invitations_for(request.user),
            "campaigns": page.object_list,
            "query": query,
            # How many rows this page carries, for a reader with no script:
            # the live count is Alpine's, and without it the number beside
            # the noun would be blank.
            "listed": len(page.object_list),
            "total": page.paginator.count,
            # Drawn only where there is more than one, so a short list is a
            # list rather than a list with a pager saying "1 of 1".
            "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
            # Kept for the pager tests, which read the page itself.
            "page": page,
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def create_campaign(request):
    """Set a campaign up. POST creates it and lands on its own page."""
    from django.db import transaction

    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import CampaignForm
    from n26.core.models import Campaign

    if request.method == "POST":
        form = CampaignForm(request.POST)
        if form.is_valid():
            # The campaign and the line that opens its log are written
            # together: a log whose first entry is missing cannot be filled
            # in afterwards, because nothing here is ever rewritten.
            with transaction.atomic():
                campaign = Campaign.objects.create(
                    name=form.cleaned_data["name"],
                    budget=form.cleaned_data["budget"],
                    summary=form.cleaned_data["summary"],
                    owner=request.user,
                )
                with campaign_operation(campaign, actor=request.user) as act:
                    act.created()
            record(
                request,
                N26Noun.CAMPAIGN,
                EventVerb.CREATE,
                campaign,
                budget=campaign.budget,
            )
            messages.success(request, f"Set up {campaign.name}.")
            return redirect("n26-campaign", pk=campaign.pk)
    else:
        form = CampaignForm()

    return render(request, "n26/create_campaign.html", {"form": form})


@requires_flag(CAMPAIGNS)
@login_required
def campaign(request, pk):
    """One campaign, as its arbitrator sees it.

    The log reads newest first and is cut to the most recent acts: the page
    is a campaign, not its history, and a log that grew without bound would
    push everything else off the bottom.
    """
    from n26.core.history import campaign_history, campaign_history_size
    from n26.core.models import CampaignMembership

    found = _own_campaign_or_404(request, pk)
    # Only the acts that will be drawn are built; how many more there are is
    # counted rather than read, so a campaign played for a year opens as
    # quickly as one set up this morning.
    recent = campaign_history(found, viewer=request.user, limit=LOG_ON_THE_PAGE)
    playing = (
        CampaignMembership.objects.filter(campaign=found, left__isnull=True)
        .select_related("gang", "gang__gang_type", "gang__owner")
        .order_by("gang__name")
    )
    battles = found.battles.prefetch_related("gangs")[:BATTLES_ON_THE_PAGE]
    return render(
        request,
        "n26/campaign.html",
        {
            "campaign": found,
            "participants": _participants(found),
            "playing": playing,
            "battles": battles,
            "acts": list(reversed(recent)),
            "more_acts": max(campaign_history_size(found) - len(recent), 0),
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def edit_campaign(request, pk):
    """The facts an arbitrator may change after setting up."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import CampaignForm

    found = _own_campaign_or_404(request, pk)

    if request.method == "POST":
        form = CampaignForm(request.POST)
        if form.is_valid():
            with campaign_operation(found, actor=request.user) as act:
                act.rename(form.cleaned_data["name"])
                act.set_budget(form.cleaned_data["budget"])
                act.edit_summary(form.cleaned_data["summary"])
            record(request, N26Noun.CAMPAIGN, EventVerb.UPDATE, found)
            messages.success(request, f"Saved {found.name}.")
            return redirect("n26-campaign", pk=found.pk)
    else:
        form = CampaignForm(
            initial={
                "name": found.name,
                "budget": found.budget,
                "summary": found.summary,
            }
        )

    return render(
        request,
        "n26/edit_campaign.html",
        {"form": form, "campaign": found},
    )


@requires_flag(CAMPAIGNS)
@login_required
def archive_campaign(request, pk):
    """The question at its own address, then the act.

    GET asks and changes nothing; the POST from that page archives. Archiving
    is the whole of it, and the word the screen uses: the campaign stops
    being listed and its pages stop opening, because every reader here asks
    for live campaigns only. Nothing is destroyed, so nothing here says
    "delete" — what a campaign recorded stays true whether or not it is
    still on show.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation

    found = _own_campaign_or_404(request, pk)

    if request.method == "POST":
        name = found.name
        with campaign_operation(found, actor=request.user) as act:
            act.archive()
        record(request, N26Noun.CAMPAIGN, EventVerb.ARCHIVE, found)
        messages.success(request, f"Archived {name}.")
        return redirect("n26-campaigns")

    return render(request, "n26/archive_campaign.html", {"campaign": found})


@requires_flag(CAMPAIGNS)
@login_required
def add_gang(request, pk):
    """Put a gang into this campaign.

    The arbitrator's act, not the gang owner's: a campaign is run by somebody,
    and it is that somebody who says who is in it. Nothing about the gang
    changes but where it plays, the gang's own history says it happened and
    who did it, and its owner may leave at any time.
    """
    from n26.core.forms import JoinCampaignForm
    from n26.core.operations import Refusal, operation

    found = _own_campaign_or_404(request, pk)

    if request.method == "POST":
        form = JoinCampaignForm(request.POST)
        if form.is_valid():
            gang = form.cleaned_data["gang"]
            try:
                with operation(gang, actor=request.user) as op:
                    op.join_campaign(found)
            except Refusal as refused:
                messages.error(request, str(refused))
            else:
                messages.success(request, f"{gang.name} joined {found.name}.")
                return redirect("n26-campaign", pk=found.pk)
    else:
        form = JoinCampaignForm()

    return render(
        request,
        "n26/add_gang_to_campaign.html",
        {"form": form, "campaign": found},
    )


@requires_flag(CAMPAIGNS)
@login_required
def remove_gang(request, pk, gang_pk):
    """The question at its own address, then the act.

    GET asks and changes nothing; the POST from that page takes the gang out.
    What the gang did while it was in the campaign stays in both histories —
    leaving closes its membership rather than unwriting anything.
    """
    from n26.core.models import CampaignMembership
    from n26.core.operations import operation

    found = _own_campaign_or_404(request, pk)
    membership = get_object_or_404(
        CampaignMembership.objects.select_related("gang"),
        campaign=found,
        gang__pk=gang_pk,
        left__isnull=True,
    )

    if request.method == "POST":
        name = membership.gang.name
        with operation(membership.gang, actor=request.user) as op:
            op.leave_campaign()
        messages.success(request, f"{name} left {found.name}.")
        return redirect("n26-campaign", pk=found.pk)

    return render(
        request,
        "n26/remove_gang_from_campaign.html",
        {"campaign": found, "gang": membership.gang},
    )


def _playing(campaign):
    """The gangs currently in this campaign, for a picker to offer."""
    from n26.core.models import Gang

    return Gang.objects.filter(
        campaign_memberships__campaign=campaign,
        campaign_memberships__left__isnull=True,
    ).order_by("name")


@requires_flag(CAMPAIGNS)
@login_required
def add_battle(request, pk):
    """Write down a battle that was fought."""
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import BattleForm

    found = _own_campaign_or_404(request, pk)
    playing = _playing(found)

    if request.method == "POST":
        form = BattleForm(request.POST, playing=playing)
        if form.is_valid():
            with campaign_operation(found, actor=request.user) as act:
                act.record_battle(form.cleaned_data["date"], form.cleaned_data["gangs"])
            messages.success(request, "Battle recorded.")
            return redirect("n26-campaign", pk=found.pk)
    else:
        form = BattleForm(playing=playing)

    return render(
        request,
        "n26/add_battle.html",
        {"form": form, "campaign": found},
    )


@requires_flag(CAMPAIGNS)
@login_required
def remove_battle(request, pk, battle_pk):
    """The question at its own address, then the act."""
    from n26.core.campaigns import campaign_operation
    from n26.core.models import Battle

    found = _own_campaign_or_404(request, pk)
    battle = get_object_or_404(Battle, pk=battle_pk, campaign=found)

    if request.method == "POST":
        with campaign_operation(found, actor=request.user) as act:
            act.remove_battle(battle)
        messages.success(request, "Battle removed.")
        return redirect("n26-campaign", pk=found.pk)

    return render(
        request,
        "n26/remove_battle.html",
        {"campaign": found, "battle": battle},
    )


def invitations_for(user):
    """The campaigns this reader has been asked into and not yet answered.

    Drawn on the campaigns list and the home page's campaigns tab, because an
    invitation nobody sees is an invitation nobody answers.
    """
    from n26.core.models import CampaignParticipant

    if not user.is_authenticated:
        return CampaignParticipant.objects.none()
    return (
        CampaignParticipant.objects.filter(
            user=user,
            state=CampaignParticipant.State.INVITED,
            campaign__archived=False,
        )
        .select_related("campaign", "campaign__owner", "invited_by")
        .order_by("campaign__name")
    )


def _person(value):
    """The active account with this id, or None.

    Ids arrive from forms and addresses, where anything can be typed. A
    primary key column refuses a value it cannot parse by raising, so asking
    for one straight from a request is a way to answer a stray character with
    a server error.
    """
    from django.contrib.auth.models import User

    try:
        return User.objects.filter(pk=int(value), is_active=True).first()
    except TypeError, ValueError:
        return None


def _participants(campaign):
    """Everybody asked into this campaign, and what they said."""
    from n26.core.models import CampaignParticipant

    return (
        CampaignParticipant.objects.filter(campaign=campaign)
        .select_related("user")
        .order_by("user__username")
    )


@requires_flag(CAMPAIGNS)
@login_required
def add_participant(request, pk):
    """Find somebody by name, and ask them into the campaign.

    The search is an ordinary ``?q=`` form, so the page works typed and
    submitted with no scripting; htmx makes the same request as you type and
    swaps the results in. Which person is being asked rides the address too,
    so the message dialog is a state the server draws rather than something
    the browser opens: a reload lands back on the same question.
    """
    from django.contrib.auth.models import User

    from n26.core.campaigns import campaign_operation
    from n26.core.operations import Refusal

    found = _own_campaign_or_404(request, pk)
    query = request.GET.get("q", "").strip()

    if request.method == "POST":
        asked = _person(request.POST.get("user"))
        if asked is None:
            messages.error(request, "That account no longer exists.")
        else:
            try:
                with campaign_operation(found, actor=request.user) as act:
                    act.invite(asked, message=request.POST.get("message", "").strip())
            except Refusal as refused:
                messages.error(request, str(refused))
            else:
                messages.success(request, f"Invited {asked.username}.")
        return redirect("n26-campaign-add-participant", pk=found.pk)

    participants = list(_participants(found))
    # Already asked, so the search offers them as asked rather than again.
    asked_already = {participant.user_id for participant in participants}
    people = []
    if query:
        people = list(
            User.objects.filter(username__icontains=query, is_active=True)
            .exclude(pk=found.owner_id)
            .order_by("username")[:PEOPLE_FOUND]
        )

    # Which person the message box is being written for, from the address.
    asking = _person(request.GET.get("invite")) if request.GET.get("invite") else None

    return render(
        request,
        "n26/add_participant.html",
        {
            "campaign": found,
            "participants": participants,
            "query": query,
            "people": people,
            "asked_already": asked_already,
            "asking": asking,
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def remove_participant(request, pk, user_pk):
    """The question at its own address, then the act."""
    from urllib.parse import quote

    from django.urls import reverse

    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignParticipant

    found = _own_campaign_or_404(request, pk)
    participant = get_object_or_404(
        CampaignParticipant.objects.select_related("user"),
        campaign=found,
        user__pk=user_pk,
    )

    if request.method == "POST":
        name = participant.user.username
        with campaign_operation(found, actor=request.user) as act:
            act.remove_participant(participant)
        messages.success(request, f"Removed {name}.")
        return redirect(
            f"{reverse('n26-campaign-add-participant', args=[found.pk])}"
            f"?q={quote(request.POST.get('q', ''))}"
        )

    return render(
        request,
        "n26/remove_participant.html",
        {"campaign": found, "participant": participant},
    )


@requires_flag(CAMPAIGNS)
@login_required
def answer_invitation(request, pk):
    """Accept or decline an invitation, as the person who was asked.

    Not owner-scoped, and deliberately: the one page in this feature acted on
    by somebody who does not own the campaign. What stands in for ownership
    is the invitation itself — no invitation, no answer, and the address says
    nothing about a campaign the reader was never asked into.
    """
    from django.core.exceptions import ValidationError
    from django.http import Http404
    from django.urls import reverse

    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignParticipant
    from n26.core.views.permissions import _safe_redirect

    if request.method != "POST":
        return redirect("n26-campaigns")

    # A malformed address is a 404, not a server error: the key column
    # refuses what it cannot parse by raising, and anybody may type anything.
    try:
        participant = get_object_or_404(
            CampaignParticipant.objects.select_related("campaign"),
            campaign__pk=pk,
            campaign__archived=False,
            user=request.user,
            state=CampaignParticipant.State.INVITED,
        )
    except ValidationError as malformed:
        raise Http404("No such campaign") from malformed
    campaign = participant.campaign
    accepted = request.POST.get("answer") == "accept"

    with campaign_operation(campaign, actor=request.user) as act:
        act.answer_invitation(request.user, accepted)

    messages.success(
        request,
        f"You joined {campaign.name}."
        if accepted
        else f"You declined {campaign.name}.",
    )
    # Answered from the campaigns list or the home page, and a reader should
    # land back where they were rather than somewhere this view chose.
    return _safe_redirect(
        request, request.POST.get("next", ""), fallback_url=reverse("n26-campaigns")
    )
