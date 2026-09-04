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

from n26.core.views.permissions import _any_campaign_or_404, _own_campaign_or_404
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
    """Every campaign this reader is in, narrowed by ``?q=``.

    Both kinds together: the campaigns they arbitrate and the ones they
    were asked into and accepted. Somebody looking for a campaign does not
    first decide which sort it was, and a page that held only one sort
    would leave the other reachable by nothing but the invitation that has
    already been answered.

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
    # Ordered by name and then by key: two campaigns may share a name now
    # that the list holds other people's, and tied rows under a name-only
    # sort are free to swap places from one page to the next.
    listed = (
        Campaign.objects.involving(request.user)
        .filter(archived=False)
        .select_related("owner")
        .order_by("name", "pk")
    )
    found = search_queryset(listed, query, ["name"])

    page = Paginator(found, CAMPAIGNS_PER_PAGE).get_page(request.GET.get("page"))
    rows = campaign_rows(page.object_list, request.user)
    return render(
        request,
        "n26/campaigns.html",
        {
            "invitations": invitations_for(request.user),
            "campaigns": rows,
            "query": query,
            # How many rows this page carries, for a reader with no script:
            # the live count is Alpine's, and without it the number beside
            # the noun would be blank.
            "listed": len(rows),
            "total": page.paginator.count,
            # Drawn only where there is more than one, so a short list is a
            # list rather than a list with a pager saying "1 of 1".
            "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
            # Kept for the pager tests, which read the page itself.
            "page": page,
        },
    )


def campaign_rows(listed, user):
    """The listed campaigns, each carrying what its row has to draw.

    A list holding both the campaigns somebody runs and the ones they play
    in has to say which is which: what an arbitrator may do to a campaign
    is not what somebody playing in it may. The answer is settled here, as
    the words the row draws rather than a flag it has to interpret, so the
    campaigns list and the home page's tab cannot come to disagree about
    what either sort of row looks like.

    A campaign the reader runs names nobody — they know who runs it — and
    offers the way in to change it. One they only play in names its
    arbitrator and offers nothing: the whole row already opens it, and
    there is nothing on the far side for them to change.
    """
    rows = list(listed)
    for row in rows:
        arbitrated = row.owner_id == getattr(user, "id", None)
        row.owner_name = "" if arbitrated else row.owner.username
        row.action_label = "Edit" if arbitrated else ""
    return rows


@requires_flag(CAMPAIGNS)
@login_required
def create_campaign(request):
    """Set a campaign up on a type. POST founds it and lands on its page.

    Founding writes the campaign, its own pack and additions type, and the
    line that opens its log in one operation: a log whose first entry is
    missing cannot be filled in afterwards, because nothing here is ever
    rewritten.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import FoundCampaignForm
    from n26.core.models import Campaign

    if request.method == "POST":
        form = FoundCampaignForm(request.POST)
        if form.is_valid():
            campaign = Campaign(
                name=form.cleaned_data["name"],
                budget=form.cleaned_data["budget"],
                summary=form.cleaned_data["summary"],
                owner=request.user,
            )
            with campaign_operation(campaign, actor=request.user) as act:
                act.found(form.cleaned_data["campaign_type"])
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
        form = FoundCampaignForm()

    return render(
        request,
        "n26/create_campaign.html",
        {"form": form, "campaign_types": form.campaign_type_choices()},
    )


@requires_flag(CAMPAIGNS)
@login_required
def campaign(request, pk):
    """One campaign, whoever is reading it.

    An arbitrator can send the address round the table, and everybody who
    opens it reads the same campaign — the same facts, the same gangs, the
    same battles, the same log. What the page withholds from a reader who
    does not arbitrate it is every control, and not a disabled one either:
    the acts belong to the arbitrator, so for anybody else they are simply
    not there.

    Who the address reaches is the decorators' answer rather than this
    one's: signed in, and inside the campaigns feature. A reader outside
    either is told there is nothing here.

    The log reads newest first and is cut to the most recent acts: the page
    is a campaign, not its history, and a log that grew without bound would
    push everything else off the bottom.
    """
    from n26.core.campaigns import over_budget
    from n26.core.history import campaign_history, campaign_history_size
    from n26.core.models import CampaignMembership, CampaignParticipant

    accepted = CampaignParticipant.State.ACCEPTED

    found = _any_campaign_or_404(pk)
    reading = getattr(request.user, "id", None)
    yours = found.owner_id == reading
    # Only the acts that will be drawn are built; how many more there are is
    # counted rather than read, so a campaign played for a year opens as
    # quickly as one set up this morning.
    recent = campaign_history(found, viewer=request.user, limit=LOG_ON_THE_PAGE)
    playing = list(
        CampaignMembership.objects.filter(campaign=found, left__isnull=True)
        .select_related("gang", "gang__gang_type", "gang__owner", "gang__stash")
        .order_by("gang__name")
    )
    # Read now rather than at the moment of joining: a gang that has grown
    # past the campaign's ceiling since is as much worth saying as one that
    # arrived over it, and neither is anything the page stops.
    for membership in playing:
        membership.wealth = membership.gang.wealth
        membership.over_budget = over_budget(found, membership.gang)
    battles = found.battles.prefetch_related("gangs")[:BATTLES_ON_THE_PAGE]
    # Read once and asked twice: the page draws the participants, and
    # whether this reader is one of them decides what it offers them.
    participants = list(_participants(found))
    at_the_table = any(
        participant.user_id == reading and participant.state == accepted
        for participant in participants
    )

    return render(
        request,
        "n26/campaign.html",
        {
            "campaign": found,
            "yours": yours,
            # A player at the table brings their own gangs; the arbitrator
            # brings anybody's. Both reach the same screen.
            "may_add_gang": yours or at_the_table,
            "participants": participants,
            "playing": playing,
            "battles": battles,
            "acts": list(reversed(recent)),
            "more_acts": max(campaign_history_size(found) - len(recent), 0),
            # What the arbitrator has added on top of the shared type, by
            # name. Empty for a campaign nothing has been added to, which is
            # every campaign at founding.
            "additions": _additions_of(found),
        },
    )


def _additions_of(campaign):
    """The names of what this campaign's additions type gives every member
    gang — its built-in members, in their order."""
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

    built_ins = campaign.additions.built_ins
    if built_ins is None:
        return []
    members = (
        built_ins.members.filter(archived=False)
        .select_related(*DEFAULT_ASSIGNABLE_FIELDS)
        .order_by("position")
    )
    return [str(member.assignable) for member in members]


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


def _addable_gangs(campaign, reader, arbitrating):
    """The gangs this reader may put into this campaign, newest first.

    The arbitrator draws on everybody at the table — the people who have
    accepted a place, and themselves — because a campaign's gangs come
    from its players and asking for an address is asking somebody to
    fetch one. A player draws on their own and nobody else's.

    Ordered by the last thing that happened to each, which is the ledger's
    to answer: the gang somebody is picking is nearly always the one they
    were last working on. A gang nothing has happened to yet sorts last
    rather than first, where a null would put it.
    """
    from django.db.models import Exists, F, OuterRef, Subquery

    from n26.core.models import (
        CampaignMembership,
        CampaignParticipant,
        Gang,
        LedgerEvent,
    )

    if arbitrating:
        owners = set(
            CampaignParticipant.objects.filter(
                campaign=campaign, state=CampaignParticipant.State.ACCEPTED
            ).values_list("user_id", flat=True)
        )
        owners.add(campaign.owner_id)
    else:
        owners = {reader.pk}

    return (
        Gang.objects.filter(owner_id__in=owners, archived=False)
        .select_related("owner", "stash")
        .annotate(
            # The newest event of this gang's own, read one at a time rather
            # than aggregated: a Max over the join groups every event
            # belonging to every gang on the page to produce one sort key
            # each, where this seeks the gang's own newest and stops.
            last_touched=Subquery(
                LedgerEvent.objects.filter(gang=OuterRef("pk"))
                .order_by("-created")
                .values("created")[:1]
            ),
            playing_now=Exists(
                CampaignMembership.objects.filter(
                    gang=OuterRef("pk"), left__isnull=True
                )
            ),
        )
        .order_by(F("last_touched").desc(nulls_last=True), "name")
    )


@requires_flag(CAMPAIGNS)
@login_required
def add_gang(request, pk):
    """Put a gang into this campaign, chosen from the ones at its table.

    The arbitrator sees every gang belonging to somebody who has accepted
    a place, and their own; a player sees their own. Both pick from a list
    rather than naming an address, and the same list decides what the POST
    will accept — a gang the screen would not offer is not one it takes.

    Nothing about the gang changes but where it plays, and the gang's own
    history says it happened and who did it.
    """
    from django.http import Http404

    from n26.core.campaigns import over_budget
    from n26.core.forms import BringGangForm
    from n26.core.operations import Refusal, operation

    found = _any_campaign_or_404(pk)
    arbitrating = found.owner_id == getattr(request.user, "id", None)
    if not arbitrating and not _plays_in(found, request.user):
        raise Http404("No such campaign")

    offering = _addable_gangs(found, request.user, arbitrating)

    if request.method == "POST":
        form = BringGangForm(request.POST, gangs=offering)
        if form.is_valid():
            gang = form.cleaned_data["gang"]
            try:
                with operation(gang, actor=request.user) as op:
                    op.join_campaign(found)
            except Refusal as refused:
                messages.error(request, str(refused))
            else:
                messages.success(request, f"{gang.name} joined {found.name}.")
                # Said after the fact, because the budget stops nobody. The
                # sum is spelled out: a reader comparing this against their
                # gang sheet should not have to work out which figures it
                # added together.
                gang.refresh_from_db()
                if over_budget(found, gang):
                    messages.warning(
                        request,
                        f"{gang.name} is over the budget. Its rating "
                        f"{gang.rating:,}¢, stash {gang.stash_rating:,}¢ and "
                        f"credits {gang.credits:,}¢ add up to "
                        f"{gang.wealth:,}¢. The budget is {found.budget:,}¢.",
                    )
                return redirect("n26-campaign", pk=found.pk)
    else:
        form = BringGangForm(gangs=offering)

    # Drawn here rather than in the template, which cannot ask a gang what
    # it is worth without a query per row.
    gangs = [
        {
            "pk": str(row.pk),
            "name": row.name,
            "owner": row.owner.username,
            "wealth": row.wealth,
            # The arbitrator's rows draw the owner, so a search that did not
            # reach it would find nothing for a name the reader can see.
            "search": f"{row.name} {row.owner.username}".lower(),
            "playing": row.playing_now,
        }
        for row in offering
    ]
    # Only where there is somebody to tell apart: a list of one person's
    # gangs is not narrowed by asking which person.
    players = sorted({row["owner"] for row in gangs})
    return render(
        request,
        "n26/add_gang_to_campaign.html",
        {
            "form": form,
            "campaign": found,
            "arbitrating": arbitrating,
            "gangs": gangs,
            "player_options": [{"value": name, "label": name} for name in players]
            if len(players) > 1
            else [],
            # The ends of the wealth filter, which are also its off positions.
            "wealth_ceiling": max((row["wealth"] for row in gangs), default=0),
            "nothing_to_offer": not gangs,
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def remove_gang(request, pk, gang_pk):
    """Taking a gang out of a campaign, which is not offered.

    A gang that joins is given the campaign's types and everything they
    bring, so leaving has to return all of it — the carriers, the
    Settlement, the counters, every token the gang holds — and until it
    does, a gang that left would keep what the campaign gave it. Nothing
    on the campaign's page leads here, and a reader who reaches the address
    anyway is told the same thing in words and sent back.

    The 404 rules are the ones the act will have: the gang must be playing
    this campaign, and the reader must arbitrate it or own the gang. A gang
    key that is not a key at all is a bad link, not a server error.
    """
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.core.models import CampaignMembership

    found = _any_campaign_or_404(pk)
    try:
        membership = get_object_or_404(
            CampaignMembership.objects.select_related("gang"),
            campaign=found,
            gang__pk=gang_pk,
            left__isnull=True,
        )
    except ValidationError:
        raise Http404("No such gang in this campaign") from None
    reading = getattr(request.user, "id", None)
    if found.owner_id != reading and membership.gang.owner_id != reading:
        raise Http404("No such gang in this campaign")

    messages.error(
        request,
        f"{membership.gang.name} cannot leave {found.name}. Taking a gang "
        "out of a campaign is not available yet.",
    )
    return redirect("n26-campaign", pk=found.pk)


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


def _plays_in(campaign, user):
    """Whether this reader has a place at this campaign's table.

    Accepted and nothing else: an invitation still waiting has not been
    answered, and a declined one is over. Somebody who arbitrates the
    campaign is not a participant of it, so callers asking "may this reader
    act here" have to ask both questions.
    """
    from n26.core.models import CampaignParticipant

    if not user.is_authenticated:
        return False
    return CampaignParticipant.objects.filter(
        campaign=campaign,
        user=user,
        state=CampaignParticipant.State.ACCEPTED,
    ).exists()


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
        return redirect("n26-campaign-add-participant", pk=found.pk)

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
    answer = request.POST.get("answer")
    if answer not in ("accept", "decline"):
        messages.error(request, "Say whether you are accepting or declining.")
        return _safe_redirect(
            request, request.POST.get("next", ""), fallback_url=reverse("n26-campaigns")
        )

    accepted = answer == "accept"
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
