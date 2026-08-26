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
from django.shortcuts import redirect, render

from n26.core.views.permissions import _own_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag

#: How many campaigns a page of the list holds. A row is a name, a budget
#: and its controls — shorter than a gang's, so a page holds more of them.
CAMPAIGNS_PER_PAGE = 25

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
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import CampaignForm
    from n26.core.models import Campaign

    if request.method == "POST":
        form = CampaignForm(request.POST)
        if form.is_valid():
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
    from n26.core.history import campaign_history

    found = _own_campaign_or_404(request, pk)
    told = campaign_history(found, viewer=request.user)
    return render(
        request,
        "n26/campaign.html",
        {
            "campaign": found,
            "acts": list(reversed(told))[:LOG_ON_THE_PAGE],
            "more_acts": max(len(told) - LOG_ON_THE_PAGE, 0),
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
