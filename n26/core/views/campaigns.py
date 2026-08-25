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


@requires_flag(CAMPAIGNS)
@login_required
def campaigns(request):
    """Every campaign this reader arbitrates."""
    # The gangs list builds the numbered links the same way, and a second
    # copy of that would be a second set of addresses to keep in step.
    from n26.core.models import Campaign
    from n26.core.views.gangs import _pages

    rows = Campaign.objects.filter(owner=request.user, archived=False)
    page = Paginator(rows, CAMPAIGNS_PER_PAGE).get_page(request.GET.get("page"))
    return render(
        request,
        "n26/campaigns.html",
        {
            "page": page,
            # Drawn only where there is more than one, so a short list is a
            # list rather than a list with a pager saying "1 of 1".
            "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def create_campaign(request):
    """Set a campaign up. POST creates it and lands on its own page."""
    from n26.analytics import EventVerb, N26Noun, record
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
    """One campaign, as its arbitrator sees it."""
    return render(
        request,
        "n26/campaign.html",
        {"campaign": _own_campaign_or_404(request, pk)},
    )


@requires_flag(CAMPAIGNS)
@login_required
def edit_campaign(request, pk):
    """The facts an arbitrator may change after setting up."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import CampaignForm

    found = _own_campaign_or_404(request, pk)

    if request.method == "POST":
        form = CampaignForm(request.POST)
        if form.is_valid():
            found.name = form.cleaned_data["name"]
            found.budget = form.cleaned_data["budget"]
            found.summary = form.cleaned_data["summary"]
            found.save()
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
def delete_campaign(request, pk):
    """The question at its own address, then the act.

    GET asks and changes nothing; the POST from that page archives.
    Archiving is the whole of it: the campaign stops being listed and its
    pages stop opening, because every reader here asks for live campaigns
    only.
    """
    from n26.analytics import EventVerb, N26Noun, record

    found = _own_campaign_or_404(request, pk)

    if request.method == "POST":
        name = found.name
        found.archive()
        record(request, N26Noun.CAMPAIGN, EventVerb.DELETE, found)
        messages.success(request, f"Deleted {name}.")
        return redirect("n26-campaigns")

    return render(request, "n26/delete_campaign.html", {"campaign": found})
