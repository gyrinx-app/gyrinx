"""Campaign setup, membership, assets and arbitrator controls.

All views require sign-in; each write checks its own campaign role.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from n26.core.listing import DANGER, LINK, SECONDARY, Action
from n26.core.views.permissions import (
    _any_campaign_or_404,
    _own_campaign_or_404,
    _recording_campaign_or_404,
)
from n26.library.scenario_tables import request_catalogue
from n26.library.staged import sees_staged

CAMPAIGNS_PER_PAGE = 25

#: Maximum account matches in an invitation search.
PEOPLE_FOUND = 10

#: Recent battles shown on the campaign page.
BATTLES_ON_THE_PAGE = 10

#: Recent acts shown before linking to the full log.
LOG_ON_THE_PAGE = 10

#: Complete acts per log page, matching gang history.
LOG_PER_PAGE = 50


@login_required
def campaigns(request):
    """List campaigns the reader owns or has joined, with shared search and paging."""
    from gyrinx.querysets import search_queryset
    from n26.core.models import Campaign
    from n26.core.views.gangs import _pages

    query = request.GET.get("q", "").strip()
    # Use the key to keep equal names stable across pages.
    listed = (
        Campaign.objects.involving(request.user)
        .filter(archived=False)
        # Load profile and grants for the arbitrator badge.
        .select_related("owner", "owner__profile", "campaign_type")
        .prefetch_related("owner__badge_grants")
        .order_by("name", "pk")
    )
    found = search_queryset(listed, query, ["name", "campaign_type__name"])

    page = Paginator(found, CAMPAIGNS_PER_PAGE).get_page(request.GET.get("page"))
    rows = campaign_rows(page.object_list)
    return render(
        request,
        "n26/campaigns.html",
        {
            "invitations": invitations_for(request.user),
            "campaigns": rows,
            "query": query,
            # Provide the count for readers without JavaScript.
            "listed": len(rows),
            "total": page.paginator.count,
            "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
            "page": page,
        },
    )


def campaign_rows(listed):
    """Build dashboard and list rows, counting memberships and battles separately."""
    from n26.core.models import Battle, CampaignMembership

    memberships = (
        CampaignMembership.objects.filter(campaign=OuterRef("pk"), left__isnull=True)
        .order_by()
        .values("campaign")
        .annotate(count=Count("pk"))
        .values("count")
    )
    battles = (
        Battle.objects.filter(campaign=OuterRef("pk"), archived=False)
        .order_by()
        .values("campaign")
        .annotate(count=Count("pk"))
        .values("count")
    )

    rows = list(
        listed.annotate(
            active_gangs=Coalesce(Subquery(memberships), 0),
            battle_count=Coalesce(Subquery(battles), 0),
        )
    )
    for row in rows:
        row.arbitrator = row.owner
    return rows


@login_required
def create_campaign(request):
    """Found a campaign, its private content and its opening log entry atomically."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import FoundCampaignForm
    from n26.core.models import Campaign

    shown = sees_staged(request.user)
    if request.method == "POST":
        form = FoundCampaignForm(request.POST, include_staged=shown)
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
        form = FoundCampaignForm(include_staged=shown)

    return render(
        request,
        "n26/create_campaign.html",
        {"form": form, "campaign_types": form.campaign_type_choices()},
    )


@login_required
def campaign(request, pk):
    """Render a campaign for any signed-in reader.

    Management controls require the arbitrator; accepted players may record
    battles and rolls. Roll dialogs can be returned without the full page.
    """
    from django.urls import reverse

    from n26.core.cycle_display import dashboard_summary
    from n26.core.models import CampaignParticipant
    from n26.core.render import CampaignPlayerLine, load_owner_badges, render_campaign
    from n26.core.views.htmx import is_htmx

    accepted = CampaignParticipant.State.ACCEPTED

    # Standalone dialogs show no owner badges, so defer those queries.
    asked_for_a_dialog = (
        request.method == "GET"
        and is_htmx(request)
        and bool(request.GET.get("roll") or request.GET.get("starting"))
    )
    found = _any_campaign_or_404(request, pk, with_owner_badge=not asked_for_a_dialog)
    reading = getattr(request.user, "id", None)
    yours = found.owner_id == reading
    sheet = render_campaign(
        found, viewer=request.user, with_owner_badges=not asked_for_a_dialog
    )
    rolling = _rolling(found, sheet, request.GET.get("roll", "")) if yours else None
    starting = (
        _starting(sheet, request.GET.get("starting", ""), request.GET.get("type", ""))
        if yours and not rolling
        else None
    )
    _fill_addresses(sheet, found, yours=yours, viewer=request.user, request=request)
    if (rolling or starting) and request.method == "GET" and is_htmx(request):
        response = render(
            request,
            "n26/includes/campaign_roll_dialogs.html",
            _roll_context(found, rolling, starting, cancel_url=sheet.table_href),
        )
        response["HX-Replace-Url"] = _table_action_href(request)
        return response
    if asked_for_a_dialog:
        # A stale dialog falls back to the full page, which needs owner badges.
        load_owner_badges(found.owner, *(line.owner for line in sheet.gangs))
    acts, more_acts = _recent_acts(found, request.user)
    battles = found.battles.filter(archived=False).prefetch_related("gangs", "winners")[
        :BATTLES_ON_THE_PAGE
    ]
    players = list(_players(found))
    player_lines = []
    for player in players:
        gangs = [
            gang
            for gang in sheet.gangs
            if gang.owner and gang.owner.pk == player.user_id
        ]
        participation = (
            ("Playing" if gangs else "No gang yet")
            if player.state == accepted
            else player.get_state_display()
        )
        player_lines.append(
            CampaignPlayerLine(player.user, player.state, gangs, participation)
        )
    player_count = sum(player.state == accepted for player in players)
    invitation_count = sum(player.waiting for player in players)
    invitations = [
        player for player in players if player.user_id == reading and player.waiting
    ]
    for invitation in invitations:
        invitation.campaign = found
    at_the_table = any(
        player.user_id == reading and player.state == accepted for player in players
    )

    from n26.core.campaign_setup import setup_checklist

    cycle_summary = dashboard_summary(found, request.user)
    return render(
        request,
        "n26/campaign.html",
        {
            "campaign": found,
            "sheet": sheet,
            "cycle_summary": cycle_summary,
            "campaign_setup": setup_checklist(
                found, sheet, players, cycle_summary, actor=request.user
            ),
            "yours": yours,
            "log_href": reverse("n26-campaign-log", args=[found.pk]),
            "more_actions": more_actions(
                found,
                yours=yours,
                playing=at_the_table,
                schedule_href=cycle_summary.schedule_href if cycle_summary else "",
            ),
            "may_add_gang": yours or at_the_table,
            "may_record": yours or at_the_table,
            "players": players,
            "player_lines": player_lines,
            "player_count": player_count,
            "invitation_count": invitation_count,
            "invitations": invitations,
            "battles": battles,
            "acts": acts,
            "more_acts": more_acts,
            **_roll_context(
                found, rolling, starting, redrawn=False, cancel_url=sheet.table_href
            ),
        },
    )


def more_actions(campaign, *, yours, playing=False, schedule_href=""):
    """Order campaign settings, destination pages and actions in separate groups."""
    actions = []
    if yours:
        edit = reverse("n26-edit-campaign", args=[campaign.pk])
        actions += [
            Action("Campaign settings", LINK, edit, SECONDARY),
            Action(
                "Counters and labels",
                LINK,
                edit + "?tab=counters-and-labels",
                SECONDARY,
            ),
            Action("Asset types", LINK, edit + "?tab=asset-types", SECONDARY),
            Action(
                "Gang grouping",
                LINK,
                reverse("n26-campaign-grouping", args=[campaign.pk]),
                SECONDARY,
            ),
        ]
    pages = []
    if schedule_href:
        pages.append(
            Action(
                "Schedule & cycles",
                LINK,
                schedule_href,
                SECONDARY,
                separator_before=bool(actions),
            )
        )
    pages += [
        Action(
            "Battles",
            LINK,
            reverse("n26-campaign-battles", args=[campaign.pk]),
            SECONDARY,
            separator_before=bool(actions) and not pages,
        ),
        Action(
            "Activity log",
            LINK,
            reverse("n26-campaign-log", args=[campaign.pk]),
            SECONDARY,
        ),
    ]
    actions += pages
    if yours:
        actions.append(
            Action(
                "Archive campaign",
                LINK,
                reverse("n26-archive-campaign", args=[campaign.pk]),
                DANGER,
                separator_before=True,
            )
        )
    if playing:
        actions.append(
            Action(
                "Leave campaign",
                LINK,
                reverse("n26-leave-campaign", args=[campaign.pk]),
                DANGER,
                separator_before=not yours,
            )
        )
    return actions


def _fill_addresses(sheet, campaign, *, yours, viewer, request=None, current_url=""):
    """Add role-specific URLs to a sheet for full-page and partial responses."""
    from django.urls import reverse

    from n26.core.owned import with_query

    here = reverse("n26-campaign", args=[campaign.pk])
    preferences = {}
    if request is not None:
        from n26.core.campaign_table import prepare_gang_table, table_query

        prepare_gang_table(sheet, request, here, current_url=current_url)
        preferences = table_query(request, current_url=sheet.table_href)
    for line in sheet.gangs:
        line.href = reverse("n26-gang", args=[line.gang_id])
        if not line.credits_unlimited and (
            line.yours or (yours and not campaign.archived)
        ):
            line.credits_href = reverse("n26-gang-credits", args=[line.gang_id])
        if yours or line.yours:
            line.remove_href = reverse(
                "n26-campaign-remove-gang", args=[campaign.pk, line.gang_id]
            )
        # Counter controls follow the same owner/arbitrator permissions as gang sheets.
        if yours or line.yours:
            for counter in line.counters:
                if counter is not None and counter.assignment_id:
                    counter.href = reverse("n26-tally", args=[counter.assignment_id])
                    counter.back = (sheet.table_href or here) + "#gangs"
                    counter.adjust_href = with_query(counter.href, back=counter.back)
    if yours:
        sheet.add_asset_type_href = reverse(
            "n26-campaign-add-asset-type", args=[campaign.pk]
        )
        sheet.add_counter_href = reverse("n26-campaign-add-counter", args=[campaign.pk])
        sheet.add_label_href = reverse("n26-campaign-add-label", args=[campaign.pk])
        sheet.tables_href = reverse("n26-campaign-tables", args=[campaign.pk])
        for line in sheet.gangs:
            for roll in line.starting_rolls:
                roll.href = with_query(
                    sheet.table_href or here,
                    starting=line.gang_id,
                    type=roll.asset_type_id,
                )
    for table in sheet.assets:
        if yours:
            table.add_href = (
                reverse("n26-campaign-add-asset", args=[campaign.pk])
                + f"?type={table.asset_type_id}"
            )
            if table.tables:
                table.roll_href = with_query(
                    sheet.table_href or here, roll=table.asset_type_id
                )
        for entry in table.entries:
            if yours:
                entry.edit_href = reverse(
                    "n26-campaign-asset-edit",
                    args=[campaign.pk, entry.campaign_asset_id],
                )
            entry.href = reverse(
                "n26-campaign-asset", args=[campaign.pk, entry.campaign_asset_id]
            )
            if entry.held:
                entry.holder_href = reverse("n26-gang", args=[entry.holder_gang_id])
            if entry.held and (yours or entry.holder_yours):
                entry.unassign_href = reverse(
                    "n26-campaign-asset-unassign",
                    args=[campaign.pk, entry.campaign_asset_id],
                )
                entry.transfer_href = reverse(
                    "n26-campaign-asset-transfer",
                    args=[campaign.pk, entry.campaign_asset_id],
                )
                entry.transfer_label = "Transfer" if yours else "Hand over"
            if not entry.held and yours:
                entry.assign_href = reverse(
                    "n26-campaign-asset-assign",
                    args=[campaign.pk, entry.campaign_asset_id],
                )
                entry.remove_href = reverse(
                    "n26-campaign-asset-remove",
                    args=[campaign.pk, entry.campaign_asset_id],
                )
            if preferences:
                for field in (
                    "href",
                    "assign_href",
                    "edit_href",
                    "unassign_href",
                    "transfer_href",
                    "remove_href",
                ):
                    href = getattr(entry, field)
                    if href:
                        setattr(entry, field, with_query(href, **preferences))


def _recent_acts(campaign, viewer):
    """Build the latest acts, return them newest first, and count the remainder."""
    from n26.core.history import (
        campaign_history,
        campaign_history_size,
        load_actor_badges,
    )

    recent = campaign_history(campaign, viewer=viewer, limit=LOG_ON_THE_PAGE)
    load_actor_badges(recent)
    more = max(campaign_history_size(campaign) - len(recent), 0)
    return list(reversed(recent)), more


def _rolling(campaign, sheet, asked):
    """Resolve ?roll= to a Holding asset type with a campaign-held rolled table."""
    from django.urls import reverse

    from n26.library.territory_table import TERRITORY

    table = next((t for t in sheet.assets if t.asset_type_id == asked), None)
    if table is None or not table.tables:
        return None
    # Territories default to three per gang; custom asset types default to one.
    label = table.plural.lower()
    lead = f"Add unclaimed {label} to the campaign pool."
    count_help = "Choose how many to add to the unclaimed pool, up to 100 at a time."
    if table.label == TERRITORY:
        if not sheet.starting_from_pool:
            lead += " Each gang's starting territory is additional."
        count_help = f"Three per gang: {sheet.territories_to_generate} unclaimed territories for this campaign."
    return {
        "kind": "pool",
        "count_help": count_help,
        "title": f"Roll {label}",
        "lead": lead,
        "action": reverse("n26-campaign-roll-asset", args=[campaign.pk]),
        "asset_type_id": asked,
        "label": label,
        "default_count": max(sheet.territories_to_generate, 1)
        if table.label == TERRITORY
        else 1,
        "tables": table.tables,
        "only": table.tables[0] if len(table.tables) == 1 else None,
    }


def _starting(sheet, gang_id, asked):
    """Resolve ?starting= to an active gang and an asset type it can roll for."""
    from django.urls import reverse

    from n26.library.territory_table import TERRITORY

    line = next((g for g in sheet.gangs if g.gang_id == gang_id), None)
    if line is None:
        return None
    roll = next((r for r in line.starting_rolls if r.asset_type_id == asked), None)
    if roll is None:
        return None
    column = next(
        column for column in sheet.asset_types if column.asset_type_id == asked
    )
    label = column.label.lower()
    allocating = sheet.starting_from_pool and column.label == TERRITORY
    return {
        "plural": column.plural.lower(),
        "allocating": allocating,
        "kind": "starting",
        "title": f"{'Allocate' if allocating else 'Roll'} starting {label} for {line.name}",
        "lead": (
            f"Allocate an unclaimed {label} from the pool to {line.name}."
            if allocating
            else f"Roll an additional {label} for this gang, separate from the unclaimed pool."
        ),
        "action": reverse(
            "n26-campaign-roll-starting", args=[sheet.campaign_id, gang_id]
        ),
        "gang_id": gang_id,
        "gang_name": line.name,
        "asset_type_id": asked,
        "label": label,
        "tables": roll.tables,
        "only": roll.tables[0] if len(roll.tables) == 1 else None,
    }


def _island_field(bound):
    """Serialise a roll form field with its label, value, help and errors."""
    value = bound.value()
    return {
        "label": bound.label,
        "helpText": bound.help_text,
        "value": "" if value is None else str(value),
        "errors": list(bound.errors),
    }


def _roll_context(
    campaign, rolling, starting, form=None, *, redrawn=True, cancel_url=""
):
    """Build roll-dialog props from a fresh or refused form.

    An invalid table selection falls back to the first offered table so the
    picker always names an available table.
    """
    from n26.core.forms import PoolRollForm, RollAssetForm
    from n26.library.models import AssetTable

    question = rolling or starting
    if question is not None:
        tables = question["tables"]
        if form is None:
            form_class = PoolRollForm if rolling else RollAssetForm
            form = form_class(
                initial={"count": question.get("default_count", 1)},
                tables=AssetTable.objects.filter(pk__in=[t.table_id for t in tables]),
            )
        if rolling:
            form.fields["count"].help_text = question["count_help"]
        form.fields[
            "avoid_duplicates"
        ].label = f"Avoid duplicate {question.get('plural', question['label'])}"
        chosen = str(form["table"].value() or "")
        if chosen not in {table.table_id for table in tables}:
            chosen = tables[0].table_id
        question["choices"] = [(table, table.table_id == chosen) for table in tables]
        island_tables = {
            "table": chosen,
            "tableErrors": list(form["table"].errors),
            "tables": [
                {
                    "value": table.table_id,
                    "label": table.name,
                    "die": table.die,
                    "lowest": table.lowest,
                    "highest": table.highest,
                }
                for table in tables
            ],
        }
        duplicate_field = {
            "label": form["avoid_duplicates"].label,
            "helpText": form["avoid_duplicates"].help_text,
            "checked": bool(form["avoid_duplicates"].value()),
        }
        if question.get("allocating"):
            from collections import Counter, defaultdict

            from n26.core.models import CampaignAsset
            from n26.library.models import AssetTableEntry, Dice

            pool_counts = Counter(
                CampaignAsset.objects.filter(
                    campaign=campaign, holder__isnull=True
                ).values_list("asset_id", flat=True)
            )
            entries = AssetTableEntry.objects.all()
            if not sees_staged(campaign.owner):
                entries = entries.live().filter(asset__staged=False)
            by_table = defaultdict(list)
            for entry in entries.filter(
                table_id__in=[table.table_id for table in tables]
            ).select_related("table"):
                by_table[str(entry.table_id)].append(entry)
            matching = Counter()
            for table in tables:
                bands = by_table[table.table_id]
                if not bands:
                    continue
                # Count only assets reachable by the selected table's die.
                reachable = {
                    entry.asset_id
                    for roll in Dice.rolls(table.dice)
                    if (entry := bands[0].table.landing(roll, bands)) is not None
                }
                matching[table.table_id] = sum(pool_counts[pk] for pk in reachable)
            for table in island_tables["tables"]:
                table["availableCount"] = matching[table["value"]]
        if rolling:
            question["pool_fields"] = {
                "avoidDuplicates": duplicate_field,
                "count": _island_field(form["count"]),
                "rolled": _island_field(form["rolled"]),
                "previewUrl": reverse(
                    "n26-campaign-preview-pool-roll", args=[campaign.pk]
                ),
                "assetType": question["asset_type_id"],
                **island_tables,
            }
        else:
            question["roll_fields"] = {
                "allocating": question.get("allocating", False),
                "avoidDuplicates": None
                if question.get("allocating")
                else duplicate_field,
                "rolled": _island_field(form["rolled"]),
                "inputId": f"{question['kind']}-roll",
                "cancelUrl": cancel_url or _campaign_page(campaign),
                **island_tables,
            }

    return {
        "campaign": campaign,
        "rolling": rolling,
        "starting": starting,
        "form": form,
        "redrawn": redrawn,
        "cancel_url": cancel_url or _campaign_page(campaign),
        # Replace the refused dialog while keeping it open.
        "reopened": redrawn and form is not None and form.is_bound,
    }


def _roll_dialog(request, campaign, rolling, starting, form, *, cancel_url=""):
    """Return an open roll dialog carrying the bound form and its refusal."""
    return render(
        request,
        "n26/includes/campaign_roll_dialogs.html",
        _roll_context(campaign, rolling, starting, form, cancel_url=cancel_url),
    )


def _campaign_update(request, campaign):
    """Redraw campaign sections and close the dialog after a roll.

    Keep table sorting and grouping in the URL and deliver queued messages
    as toasts.
    """
    from n26.core.render import render_campaign
    from n26.core.views.htmx import with_toasts

    sheet = render_campaign(campaign, viewer=request.user)
    _fill_addresses(
        sheet,
        campaign,
        yours=campaign.owner_id == request.user.pk,
        viewer=request.user,
        request=request,
    )
    acts, more_acts = _recent_acts(campaign, request.user)
    guidance = None
    if campaign.owner_id == request.user.pk:
        from n26.core.campaign_setup import setup_checklist
        from n26.core.cycle_display import dashboard_summary

        guidance = setup_checklist(
            campaign,
            sheet,
            campaign.participants.only("state", "campaign_id"),
            dashboard_summary(campaign, request.user),
            actor=request.user,
        )
    response = render(
        request,
        "n26/includes/campaign_update.html",
        {
            "campaign": campaign,
            "sheet": sheet,
            "acts": acts,
            "more_acts": more_acts,
            "campaign_setup": guidance,
        },
    )
    response["HX-Replace-Url"] = sheet.table_href or _campaign_page(campaign)
    return with_toasts(request, response)


@login_required
def roll_asset(request, pk):
    """Roll campaign-held tables to add unclaimed assets.

    HTMX receives a dialog refusal or updated sections; ordinary requests
    redirect to the campaign page.
    """
    from n26.core.campaigns import campaign_operation, tables_in_play
    from n26.core.forms import PoolRollForm
    from n26.core.operations import Refusal

    found = _own_campaign_or_404(request, pk, with_owner_badge=False)
    asked = request.POST.get("type", "") or request.GET.get("type", "")
    asset_type = _asset_type_asked_for(found, asked)
    again = _campaign_page(found) + (f"?roll={asset_type.pk}" if asset_type else "")
    if request.method != "POST" or asset_type is None:
        return _back_to_the_page(request, again)
    tables = (
        tables_in_play(found, include_staged=sees_staged(request.user))
        .filter(asset_type=asset_type)
        .exclude(dice="")
    )
    form = PoolRollForm(request.POST, tables=tables)
    rolls = None
    if form.is_valid():
        try:
            with campaign_operation(found, actor=request.user) as act:
                rolls = act.roll_assets(
                    form.cleaned_data["table"],
                    count=form.cleaned_data["count"],
                    avoid_duplicates=form.cleaned_data["avoid_duplicates"],
                    request_key=form.cleaned_data["request_key"],
                    rolled=form.cleaned_data["rolled"],
                )
        except Refusal as refused:
            form.add_error(None, str(refused))
    if rolls is None:
        return _roll_refused(
            request,
            found,
            form,
            again,
            lambda sheet: _rolling(found, sheet, str(asset_type.pk)),
        )
    if not rolls:
        messages.info(request, "That selection was already rolled.")
    elif len(rolls) == 1:
        roll = rolls[0]
        messages.success(
            request,
            f"Rolled {roll.roll}: {roll.campaign_asset} added to the campaign, unclaimed.",
        )
    else:
        messages.success(
            request,
            f"Rolled {len(rolls)} {asset_type.plural.lower()}, added to the campaign unclaimed.",
        )
    return _roll_made(request, found)


def _back_to_the_page(request, again):
    """Redirect normally or use HX-Redirect when hx-swap="none" would discard it."""
    from n26.core.views.htmx import is_htmx

    if not is_htmx(request):
        return redirect(again)
    response = HttpResponse(status=204)
    response["HX-Redirect"] = again
    return response


def _roll_refused(request, campaign, form, again, question):
    """Redisplay a refused roll against a fresh sheet.

    HTMX replaces the dialog only; ordinary requests queue the error and
    redirect to the page with the dialog open.
    """
    from n26.core.campaign_table import prepare_gang_table
    from n26.core.render import render_campaign
    from n26.core.views.htmx import is_htmx

    if not is_htmx(request):
        messages.error(request, _first_error(form))
        return redirect(again)
    sheet = render_campaign(campaign, viewer=request.user, with_owner_badges=False)
    prepare_gang_table(sheet, request, _campaign_page(campaign))
    asked = question(sheet)
    if asked is None:
        # The table was withdrawn, so return to the page instead.
        response = HttpResponse(status=204)
        response["HX-Redirect"] = _campaign_page(campaign)
        return response
    if "gang_id" in asked:
        return _roll_dialog(
            request, campaign, None, asked, form=form, cancel_url=sheet.table_href
        )
    return _roll_dialog(
        request, campaign, asked, None, form=form, cancel_url=sheet.table_href
    )


def _roll_made(request, campaign):
    """Update the campaign over HTMX or redirect to show the queued message."""
    from n26.core.views.htmx import is_htmx

    if is_htmx(request):
        return _campaign_update(request, campaign)
    return redirect(_campaign_page(campaign))


@login_required
def roll_starting_asset(request, pk, gang_pk):
    """Roll a gang-held table and assign its starting asset to that gang."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.core.campaigns import (
        campaign_operation,
        starting_asset_types_received,
        tables_held_by,
    )
    from n26.core.forms import RollAssetForm
    from n26.core.models import CampaignMembership
    from n26.core.operations import Refusal
    from n26.library.models import AssetTable

    found = _own_campaign_or_404(request, pk, with_owner_badge=False)
    try:
        membership = (
            CampaignMembership.objects.filter(
                campaign=found, gang_id=gang_pk, left__isnull=True
            )
            .select_related("gang")
            .first()
        )
    except ValidationError:
        raise Http404("No such gang in this campaign") from None
    if membership is None:
        raise Http404("No such gang in this campaign")
    asked = request.POST.get("type", "") or request.GET.get("type", "")
    asset_type = _asset_type_asked_for(found, asked)
    again = _campaign_page(found) + (
        f"?starting={gang_pk}&type={asset_type.pk}" if asset_type else ""
    )
    if request.method != "POST" or asset_type is None:
        return _back_to_the_page(request, again)
    held = [
        table.pk
        for table in tables_held_by(
            membership.gang, found, include_staged=sees_staged(request.user)
        )
        if table.dice and table.asset_type_id == asset_type.pk
    ]
    form = RollAssetForm(request.POST, tables=AssetTable.objects.filter(pk__in=held))
    roll = None
    if form.is_valid():
        try:
            with campaign_operation(found, actor=request.user) as act:
                received = starting_asset_types_received(found, [membership])
                if asset_type.pk in received[membership.pk]:
                    messages.info(
                        request,
                        f"{membership.gang.name} has already received its starting "
                        f"{asset_type.label_singular.lower()}.",
                    )
                    return _roll_made(request, found)
                roll = act.roll_asset(
                    form.cleaned_data["table"],
                    membership=membership,
                    rolled=form.cleaned_data["rolled"],
                    avoid_duplicates=form.cleaned_data["avoid_duplicates"],
                )
        except Refusal as refused:
            form.add_error(None, str(refused))
    if roll is None:
        return _roll_refused(
            request,
            found,
            form,
            again,
            lambda sheet: _starting(sheet, str(gang_pk), str(asset_type.pk)),
        )
    messages.success(
        request,
        f"Rolled {roll.roll}: {roll.campaign_asset} assigned to {membership.gang.name}.",
    )
    return _roll_made(request, found)


def _campaign_page(campaign):
    from django.urls import reverse

    return reverse("n26-campaign", args=[campaign.pk])


def _badge_a_redrawn_page(request, campaign):
    """Load the arbitrator badge when a POST must redisplay its page.

    GET lookups already include it; successful POSTs redirect without it.
    """
    from n26.core.render import load_owner_badges

    if request.method == "POST":
        load_owner_badges(campaign.owner)


def _first_error(form):
    """Return the first form error for a queued message."""
    for errors in form.errors.values():
        for error in errors:
            return str(error)
    return "Check the form and try again."


@login_required
def campaign_log(request, pk):
    """Filter and page complete campaign acts, newest first.

    Build acts before paging because one act may combine several ledger rows.
    Only the displayed page needs actor badge data.
    """
    from n26.core.campaign_permissions import may_record_campaign
    from n26.core.history import campaign_history, load_actor_badges
    from n26.core.views.gangs import _pages
    from n26.core.views.history import by_day, filter_campaign_acts

    found = _any_campaign_or_404(request, pk, with_owner_badge=True)
    acts = campaign_history(found, viewer=request.user)
    total = len(acts)
    filters, acts, narrowed = filter_campaign_acts(request, acts)
    # Sort newest first before paging.
    page = Paginator(list(reversed(acts)), LOG_PER_PAGE).get_page(
        request.GET.get("page")
    )
    # Load actor badges only for the displayed page.
    load_actor_badges(page.object_list)

    return render(
        request,
        "n26/campaign_log.html",
        {
            "campaign": found,
            "may_record": may_record_campaign(found, request.user),
            "days": by_day(page.object_list),
            "filters": filters,
            "narrowed": narrowed,
            "matched": len(acts),
            "total": total,
            "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
        },
    )


@login_required
def scenario_generator(request, pk):
    """Generate a scenario with its complete state in the query string.

    Generation redirects to fixed rolls and preserves explicit picks, making
    results reloadable and shareable. Readers with recording permission can
    save the scenario or use it for a battle.
    """
    from urllib.parse import urlencode

    from n26.core.campaign_permissions import may_record_campaign
    from n26.core.forms import ScenarioGeneratorForm
    from n26.core.scenarios import parse, rolls_of
    from n26.core.views.scenario_props import scenario_picks_props
    from n26.core.views.scenarios import reroll_dialog, side_job_changes

    found = _any_campaign_or_404(request, pk, with_owner_badge=True)
    here = reverse("n26-scenario-generator", args=[found.pk])
    form = ScenarioGeneratorForm(request.GET, catalogue=request_catalogue(request))
    changed = side_job_changes(request, form, here)
    if changed:
        return changed
    valid = form.is_valid()

    if "generate" in request.GET and valid:
        query = {**form.chosen_picks(), **form.generate()}
        return redirect(f"{here}?{urlencode(query)}#scenario")

    scenario, wrong = parse(request.GET, request_catalogue(request))
    if wrong:
        scenario = []
    rolls = rolls_of(scenario)
    reroll, reroll_links = reroll_dialog(request, here, rolls)
    record_href = save_href = ""
    if scenario and may_record_campaign(found, request.user):
        record_href = (
            f"{reverse('n26-campaign-add-battle', args=[found.pk])}?{urlencode(rolls)}"
        )
        query = {**(form.chosen_picks() if valid else {}), **rolls}
        save_href = (
            f"{reverse('n26-save-scenario', args=[found.pk])}?{urlencode(query)}"
        )
    return render(
        request,
        "n26/scenario_generator.html",
        {
            "campaign": found,
            "form": form,
            "scenario_picks": scenario_picks_props(form),
            "scenario": scenario,
            "rolls": rolls,
            "wrong": wrong,
            "share_url": request.get_full_path(),
            "scenario_reroll": reroll,
            "reroll_links": reroll_links,
            "record_href": record_href,
            "save_href": save_href,
            # Printing requires read access rather than recording permission.
            "print_url": (
                f"{reverse('n26-campaign-scenario-print', args=[found.pk])}"
                f"?{urlencode({**(form.chosen_picks() if valid else {}), **rolls})}"
            ),
        },
    )


@login_required
def save_scenario(request, pk):
    """Save a named scenario to the log for an arbitrator or accepted player.

    Carry scenario components in hidden fields and preserve them on errors.
    """
    from urllib.parse import urlencode

    from n26.core.campaigns import campaign_operation
    from n26.core.forms import SaveScenarioForm, ScenarioGeneratorForm
    from n26.core.operations import Refusal
    from n26.core.scenarios import parse, rolls_of

    found = _recording_campaign_or_404(
        request, pk, with_owner_badge=request.method == "GET"
    )
    data = request.POST if request.method == "POST" else request.GET
    scenario, wrong = parse(data, request_catalogue(request))
    if wrong:
        scenario = []
    generator = reverse("n26-scenario-generator", args=[found.pk])
    picks_form = ScenarioGeneratorForm(
        request.GET, catalogue=request_catalogue(request)
    )
    picks = picks_form.chosen_picks() if picks_form.is_valid() else {}
    action_url = reverse("n26-save-scenario", args=[found.pk])
    if picks:
        action_url += f"?{urlencode(picks)}"

    if request.method == "POST":
        form = SaveScenarioForm(request.POST, catalogue=request_catalogue(request))
        if form.is_valid():
            try:
                with campaign_operation(found, actor=request.user) as act:
                    act.save_scenario(
                        form.cleaned_data["scenario_rolls"],
                        name=form.cleaned_data["name"],
                    )
            except Refusal as refused:
                form.add_error(None, str(refused))
            else:
                messages.success(request, "Scenario saved to the campaign log.")
                query = {**picks, **form.cleaned_data["scenario_rolls"]}
                return redirect(f"{generator}?{urlencode(query)}#scenario")
    else:
        form = SaveScenarioForm(
            initial=rolls_of(scenario), catalogue=request_catalogue(request)
        )

    _badge_a_redrawn_page(request, found)
    return render(
        request,
        "n26/save_scenario.html",
        {
            "campaign": found,
            "form": form,
            "scenario": scenario,
            "scenario_wrong": bool(wrong),
            "action_url": action_url,
            "cancel_url": (
                f"{generator}?{urlencode({**picks, **rolls_of(scenario)})}#scenario"
            ),
        },
    )


@login_required
def edit_campaign(request, pk):
    """Edit campaign settings, custom asset types, counters and labels."""
    from django.db.models import Q
    from django.urls import reverse

    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import archived_additions, campaign_operation
    from n26.core.forms import EditCampaignForm
    from n26.library.models import DefaultAssignment

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    tab = request.GET.get("tab", "general")
    if tab not in ("counters-and-labels", "asset-types") or request.method == "POST":
        tab = "general"
    edit_url = reverse("n26-edit-campaign", args=[found.pk])
    counters = []
    labels = []
    asset_types = []
    shared_asset_types = ""
    shared_definitions = ""
    archived_counters = []
    archived_labels = []

    if request.method == "POST":
        form = EditCampaignForm(request.POST)
        if form.is_valid():
            with campaign_operation(found, actor=request.user) as act:
                act.rename(form.cleaned_data["name"])
                act.set_budget(form.cleaned_data["budget"])
                act.edit_summary(form.cleaned_data["summary"])
                act.set_starting_from_pool(form.cleaned_data["starting_from_pool"])
                if form.cleaned_data["status"]:
                    act.set_status(form.cleaned_data["status"])
            record(request, N26Noun.CAMPAIGN, EventVerb.UPDATE, found)
            messages.success(request, f"Saved {found.name}.")
            return redirect("n26-campaign", pk=found.pk)
    elif tab == "general":
        form = EditCampaignForm(
            initial={
                "name": found.name,
                "budget": found.budget,
                "summary": found.summary,
                "status": found.status,
                "starting_from_pool": found.starting_from_pool,
            }
        )

    elif tab == "asset-types":
        form = None
        own, shared = [], []
        for asset_type in _campaign_asset_types(found):
            if asset_type.campaign_type_id != found.additions_id:
                shared.append(asset_type.plural)
                continue
            own.append(
                {
                    "label": asset_type.label_singular,
                    "plural": asset_type.plural,
                    "ownership": asset_type.get_ownership_display(),
                    "href": reverse(
                        "n26-campaign-edit-asset-type", args=[found.pk, asset_type.pk]
                    ),
                }
            )
        asset_types = own
        if shared:
            names = (
                shared[0]
                if len(shared) == 1
                else f"{', '.join(shared[:-1])} and {shared[-1]}"
            )
            shared_asset_types = (
                f"{names} come with {found.campaign_type}. You cannot edit them here."
            )

    else:
        form = None
        members = (
            DefaultAssignment.objects.filter(
                default_set_id__in=(
                    found.campaign_type.built_ins_id,
                    found.additions.built_ins_id,
                ),
                archived=False,
            )
            .filter(Q(counter__isnull=False) | Q(slot__isnull=False))
            .select_related("counter", "slot")
            .order_by("position", "pk")
        )
        shared = []
        for member in members:
            if member.counter_id:
                item = {"name": str(member.counter), "opening": member.amount}
                counters.append(item)
                thing, route = member.counter, "n26-campaign-archive-counter"
            else:
                item = {"name": member.slot.choice_label}
                labels.append(item)
                thing, route = member.slot, "n26-campaign-archive-label"
            # Archive only campaign additions; shared definitions remain read-only.
            if (
                member.default_set_id == found.additions.built_ins_id
                and thing.pack_id == found.pack_id
            ):
                item["archive_href"] = reverse(route, args=[found.pk, member.pk])
            else:
                shared.append(item["name"])
        if len(shared) == 1:
            shared_definitions = (
                f"{shared[0]} comes with {found.campaign_type}. "
                "You cannot archive it here."
            )
        elif shared:
            names = f"{', '.join(shared[:-1])} and {shared[-1]}"
            shared_definitions = (
                f"{names} come with {found.campaign_type}. "
                "You cannot archive them here."
            )
        archived_counters = [
            {
                "name": str(member.counter),
                "unarchive_href": reverse(
                    "n26-campaign-unarchive-counter", args=[found.pk, member.pk]
                ),
            }
            for member in archived_additions(found, "counter")
        ]
        archived_labels = [
            {
                "name": member.slot.choice_label,
                "unarchive_href": reverse(
                    "n26-campaign-unarchive-label", args=[found.pk, member.pk]
                ),
            }
            for member in archived_additions(found, "slot")
        ]

    _badge_a_redrawn_page(request, found)
    return render(
        request,
        "n26/edit_campaign.html",
        {
            "form": form,
            "campaign": found,
            "tab": tab,
            "edit_tabs": [
                {"label": "General", "href": edit_url, "current": tab == "general"},
                {
                    "label": "Counters and labels",
                    "href": f"{edit_url}?tab=counters-and-labels",
                    "current": tab == "counters-and-labels",
                },
                {
                    "label": "Asset types",
                    "href": f"{edit_url}?tab=asset-types",
                    "current": tab == "asset-types",
                },
            ],
            "counters": counters,
            "labels": labels,
            "asset_types": asset_types,
            "shared_asset_types": shared_asset_types,
            "shared_definitions": shared_definitions,
            "archived_counters": archived_counters,
            "archived_labels": archived_labels,
        },
    )


@login_required
def archive_campaign(request, pk):
    """Confirm on GET and archive on POST, preserving the campaign records."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")

    if request.method == "POST":
        name = found.name
        with campaign_operation(found, actor=request.user) as act:
            act.archive()
        record(request, N26Noun.CAMPAIGN, EventVerb.ARCHIVE, found)
        messages.success(request, f"Archived {name}.")
        return redirect("n26-campaigns")

    return render(request, "n26/archive_campaign.html", {"campaign": found})


def _addable_gangs(campaign, reader, arbitrating):
    """Offer active gangs owned by the reader, or by accepted players to an arbitrator.

    Order by each gang's latest ledger event, with untouched gangs last.
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
            # A correlated subquery reads one latest event per gang without grouping
            # all joined events.
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


@login_required
def add_gang(request, pk):
    """Add a gang selected from the reader's permitted owners.

    Validate POST against the same list shown by the picker. The operation
    adds campaign grants and records the membership change.
    """
    from django.http import Http404

    from n26.core.campaigns import campaign_operation, over_budget
    from n26.core.forms import BringGangForm
    from n26.core.operations import Refusal
    from n26.core.people import person_link

    found = _any_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    arbitrating = found.owner_id == getattr(request.user, "id", None)
    if not arbitrating and not _plays_in(found, request.user):
        raise Http404("No such campaign")

    offering = _addable_gangs(found, request.user, arbitrating)

    if request.method == "POST":
        form = BringGangForm(request.POST, gangs=offering)
        if form.is_valid():
            gang = form.cleaned_data["gang"]
            try:
                with campaign_operation(found, actor=request.user) as act:
                    act.add_gang(gang)
            except Refusal as refused:
                messages.error(request, str(refused))
            else:
                messages.success(request, f"{gang.name} joined {found.name}.")
                gang.refresh_from_db()
                if gang.credits_unlimited:
                    messages.warning(
                        request,
                        f"{gang.name} uses unlimited credits. Its credit balance "
                        "is not tracked. The gang owner can set a credits "
                        "budget on the gang's Edit page.",
                    )
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
    _badge_a_redrawn_page(request, found)

    # Render gang wealth in bulk to avoid a query per picker row.
    drawn = offering
    if arbitrating:
        # Preload owner badge data for the arbitrator's gang picker.
        drawn = offering.select_related("owner__profile").prefetch_related(
            "owner__badge_grants"
        )
    gangs = [
        {
            "pk": str(row.pk),
            "name": row.name,
            "href": reverse("n26-gang", args=[row.pk]),
            "unlimited": row.credits_unlimited,
            "budget_href": reverse("n26-edit-gang", args=[row.pk]) + "#starting-credits"
            if row.credits_unlimited and row.owner_id == request.user.pk
            else "",
            "owner": row.owner.username,
            "owned_by": row.owner,
            "wealth": row.wealth,
            # Search owner names because they are visible in the arbitrator's picker.
            "search": f"{row.name} {row.owner.username}".lower(),
            "playing": row.playing_now,
        }
        for row in drawn
    ]
    players = sorted({row["owner"] for row in gangs})
    badges = {}
    picker = {
        "gangs": [
            {
                "pk": row["pk"],
                "name": row["name"],
                "href": row["href"],
                "unlimited": row["unlimited"],
                "budgetHref": row["budget_href"],
                "owner": row["owner"],
                "ownerLink": person_link(row["owned_by"], badges)
                if arbitrating
                else None,
                "wealth": row["wealth"],
                "search": row["search"],
                "playing": row["playing"],
            }
            for row in gangs
        ],
        # Deduplicate badge artwork across gangs with the same owner.
        "badges": badges,
        "playerOptions": [{"value": name, "label": name} for name in players]
        if len(players) > 1
        else [],
        "wealthCeiling": max((row["wealth"] for row in gangs), default=0),
    }
    return render(
        request,
        "n26/add_gang_to_campaign.html",
        {
            "form": form,
            "campaign": found,
            "arbitrating": arbitrating,
            "gangs": gangs,
            "picker": picker,
            "nothing_to_offer": not gangs,
        },
    )


@login_required
def remove_gang(request, pk, gang_pk):
    """Confirm and remove a gang, showing campaign grants and holdings it loses.

    The arbitrator may remove any active gang; its owner may remove their own.
    """
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignMembership

    found = _any_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    try:
        membership = get_object_or_404(
            CampaignMembership.objects.select_related("gang"),
            campaign=found,
            gang__pk=gang_pk,
            left__isnull=True,
        )
    except ValidationError:
        raise Http404("No such gang in this campaign") from None
    if not may_remove_gang(found, membership.gang, request.user):
        raise Http404("No such gang in this campaign")
    gang = membership.gang
    from n26.core.campaign_table import table_view_href

    back = table_view_href(request, _campaign_page(found))

    if request.method == "POST":
        with campaign_operation(found, actor=request.user) as act:
            removed = act.remove_gang(membership)
        if removed is None:
            messages.error(request, f"{gang.name} is not in {found.name}.")
        else:
            messages.success(request, f"Removed {gang.name} from {found.name}.")
        # Return to the page top so the queued message is visible.
        return redirect(back)

    losing, returning = _what_the_gang_loses(found, gang)
    return render(
        request,
        "n26/remove_gang_from_campaign.html",
        {
            "campaign": found,
            "gang": gang,
            "losing": losing,
            "returning": returning,
            "back": back + "#gangs",
        },
    )


def may_remove_gang(campaign, gang, user):
    """Allow the campaign arbitrator or the gang owner to remove the gang."""
    reading = getattr(user, "id", None)
    return reading is not None and reading in (campaign.owner_id, gang.owner_id)


def _what_the_gang_loses(campaign, gang):
    """Read lost grants and returned holdings from the gang's campaign-sheet row."""
    from n26.core.render import render_campaign

    sheet = render_campaign(campaign, with_owner_badges=False)
    line = next(line for line in sheet.gangs if line.gang_id == str(gang.pk))
    return _what_the_line_loses(sheet, line)


def _what_the_line_loses(sheet, line):
    """Extract lost grants and returned holdings from an existing sheet row."""
    losing = []
    returning = []
    for column, names in zip(sheet.asset_types, line.assets, strict=True):
        for name in names:
            (returning if column.holding else losing).append((column.label, name))
    for name, counter in zip(sheet.counter_columns, line.counters, strict=True):
        if counter is not None:
            losing.append((name, counter.value))
    for name, pick in zip(sheet.label_columns, line.labels, strict=True):
        if pick:
            losing.append((name, pick))
    return losing, returning


def _playing(campaign):
    """Offer the campaign's active gangs, ordered by name."""
    from n26.core.models import Gang

    return Gang.objects.filter(
        campaign_memberships__campaign=campaign,
        campaign_memberships__left__isnull=True,
    ).order_by("name")


@login_required
def add_battle(request, pk):
    """Accepted players and the arbitrator record a battle."""
    from n26.core.views.battle_editing import editor

    return editor(request, pk)


@login_required
def remove_battle(request, pk, battle_pk):
    """Confirm on GET and remove the battle at the submitted revision on POST."""
    from n26.core.campaigns import campaign_operation
    from n26.core.operations import Refusal
    from n26.core.views.battles import battle_or_404

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    battle = battle_or_404(found, battle_pk)

    if request.method == "POST":
        try:
            revision = int(request.POST.get("revision", ""))
        except TypeError, ValueError:
            messages.error(
                request,
                "The battle version is missing or invalid. Reload it before archiving it.",
            )
            return redirect("n26-battle", pk=found.pk, battle_pk=battle.pk)
        try:
            with campaign_operation(found, actor=request.user) as act:
                act.remove_battle(battle, revision=revision)
        except Refusal as exc:
            messages.error(request, str(exc))
            return redirect("n26-battle", pk=found.pk, battle_pk=battle.pk)
        else:
            messages.success(request, "Battle archived.")
            return redirect("n26-campaign", pk=found.pk)

    return render(
        request,
        "n26/remove_battle.html",
        {
            "campaign": found,
            "battle": battle,
        },
    )


def _holding_assets(campaign, *, include_staged=False):
    """Return the catalogue assets allowed by the campaign's add-asset policy."""
    from n26.core.campaigns import addable_assets

    return addable_assets(campaign, include_staged=include_staged)


def _assets_anchor(campaign):
    """Link to the campaign's assets section."""
    from django.urls import reverse

    return reverse("n26-campaign", args=[campaign.pk]) + "#assets"


def _table_action_href(request, here=""):
    """Carry the visible table's state into a dialog opened from an older link."""
    from urllib.parse import parse_qsl, urlencode, urlsplit

    from n26.core.campaign_table import CAMPAIGN_VIEW_KEYS, table_query
    from n26.core.views.htmx import is_htmx

    query = table_query(request)
    url = urlsplit(here or request.get_full_path())
    parameters = dict(parse_qsl(url.query, keep_blank_values=True))
    if is_htmx(request) and request.headers.get("HX-Current-URL"):
        for key in CAMPAIGN_VIEW_KEYS:
            parameters.pop(key, None)
    parameters.update({key: query[key] for key in CAMPAIGN_VIEW_KEYS if key in query})
    return url.path + ("?" + urlencode(parameters) if parameters else "")


def _gangs_anchor(campaign):
    """Link to the campaign's gangs table."""
    from django.urls import reverse

    return reverse("n26-campaign", args=[campaign.pk]) + "#gangs"


def _campaign_asset_or_404(campaign, asset_pk):
    """Load a campaign asset with its library definition and holder; reject bad keys."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.core.models import CampaignAsset

    try:
        return get_object_or_404(
            CampaignAsset.objects.select_related(
                "asset__asset_type",
                "asset__base_income_modifier__contributes_to_counter__counter",
                "holder__gang",
                "income_override__contributes_to_counter",
            ),
            pk=asset_pk,
            campaign=campaign,
        )
    except ValidationError:
        raise Http404("No such asset in this campaign") from None


def _asset_back(request, campaign, holding):
    from django.urls import reverse

    from n26.core.campaign_table import table_view_href

    if request.GET.get("from") == "detail":
        return table_view_href(
            request, reverse("n26-campaign-asset", args=[campaign.pk, holding.pk])
        )

    return table_view_href(request, _campaign_page(campaign)) + "#assets"


def _asset_update(request, campaign, holding):
    if request.GET.get("from") == "detail":
        from n26.core.views.campaign_assets import _asset_detail_update

        return _asset_detail_update(request, campaign.pk, holding.pk)
    return _campaign_update(request, campaign)


def _holding_owner(campaign_asset, user):
    """Check ownership of the gang currently holding this asset."""
    return campaign_asset.held and campaign_asset.holder.gang.owner_id == getattr(
        user, "id", None
    )


def _asset_type_asked_for(campaign, value):
    """Resolve ?type= to a campaign Holding type, or leave the picker unfiltered."""
    from django.core.exceptions import ValidationError

    from n26.library.models import AssetType

    if not value:
        return None
    try:
        return AssetType.objects.filter(
            pk=value,
            ownership=AssetType.Ownership.HOLDING,
            campaign_type_id__in=(campaign.campaign_type_id, campaign.additions_id),
        ).first()
    except ValidationError, ValueError:
        return None


@login_required
def add_asset(request, pk):
    """Add unclaimed catalogue assets, optionally filtered by ?type=."""
    if request.GET.get("source") == "custom":
        return new_asset(request, pk)

    from django.urls import reverse

    from n26.core.campaigns import campaign_operation
    from n26.core.forms import AddAssetForm
    from n26.library.income import income_of, with_income
    from n26.library.models import AssetType

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    from n26.core.campaign_table import table_view_href

    back = table_view_href(request, _campaign_page(found)) + "#assets"
    asset_type = _asset_type_asked_for(found, request.GET.get("type"))
    offered = _holding_assets(found, include_staged=sees_staged(request.user))
    if asset_type is not None:
        offered = offered.filter(asset_type=asset_type)

    if request.method == "POST":
        form = AddAssetForm(request.POST, offered=offered)
        if form.is_valid():
            with campaign_operation(found, actor=request.user) as act:
                made = act.add_assets(
                    form.cleaned_data["asset"],
                    name=form.cleaned_data["name"],
                    names=form.cleaned_data["names"],
                    income=form.cleaned_data["income"],
                    request_key=form.cleaned_data["request_key"],
                )
            if not made:
                messages.info(request, "That selection was already added.")
            elif len(form.cleaned_data["asset"]) == 1:
                chosen = form.cleaned_data["asset"][0]
                messages.success(
                    request,
                    f"Added {form.cleaned_data['names'].get(str(chosen.pk)) or form.cleaned_data['name'] or str(chosen)}.",
                )
            else:
                label = asset_type.plural.lower() if asset_type else "assets"
                messages.success(
                    request, f"Added {len(form.cleaned_data['asset'])} {label}."
                )
            return redirect(back)
    else:
        form = AddAssetForm(offered=offered)

    submitted = set(form["asset"].value() or [])

    def card(asset):
        income = income_of(asset)
        description = ", ".join(
            part
            for part in (
                str(asset.asset_type) if asset_type is None else "",
                f"Income {income}¢" if income else "",
            )
            if part
        )
        return {
            "value": str(asset.pk),
            "label": str(asset),
            "description": description,
            "checked": str(asset.pk) in submitted,
            "name": form[f"name_{asset.pk}"].value() or ""
            if f"name_{asset.pk}" in form.fields
            else "",
            "nameErrors": list(form[f"name_{asset.pk}"].errors)
            if f"name_{asset.pk}" in form.fields
            else [],
        }

    noun = asset_type.plural.lower() if asset_type else "assets"
    assets = [card(asset) for asset in with_income(offered)]
    has_holding_type = (
        asset_type is not None
        or bool(assets)
        or _campaign_asset_types(found)
        .filter(ownership=AssetType.Ownership.HOLDING)
        .exists()
    )
    custom_href = (
        request.path
        + "?source=custom"
        + (f"&type={asset_type.pk}" if asset_type else "")
        if has_holding_type
        else ""
    )
    if custom_href:
        custom_href = _table_action_href(request, custom_href)
    empty_next_href = custom_href or reverse(
        "n26-campaign-add-asset-type", args=[found.pk]
    )
    _badge_a_redrawn_page(request, found)
    return render(
        request,
        "n26/add_asset.html",
        {
            "form": form,
            "campaign": found,
            "asset_type": asset_type,
            "adding": noun,
            "catalogue_href": _table_action_href(
                request, request.path + (f"?type={asset_type.pk}" if asset_type else "")
            ),
            "custom_href": custom_href,
            "custom_label": asset_type.label_singular.lower()
            if asset_type
            else "asset",
            "back": back,
            "assets": assets,
            "fallback_options": [
                {
                    "key": asset["value"],
                    "name": asset["label"],
                    "detail": asset["description"],
                    "is_current": asset["checked"],
                }
                for asset in assets
            ],
            "selection": {
                "label": f"Select {noun}",
                "invalid": bool(form["asset"].errors),
                "options": assets,
                "selected": list(submitted),
            },
            "empty_next_href": empty_next_href,
            "empty_next_label": "Create asset"
            if has_holding_type
            else "Add an asset type",
        },
    )


@login_required
def assign_asset(request, pk, asset_pk):
    """Assign a campaign asset to a selected active gang."""
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import AssignAssetForm
    from n26.core.models import CampaignMembership
    from n26.core.operations import Refusal
    from n26.core.views.htmx import is_htmx

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    campaign_asset = _campaign_asset_or_404(found, asset_pk)
    playing = (
        CampaignMembership.objects.filter(campaign=found, left__isnull=True)
        .select_related("gang", "gang__gang_type", "gang__owner")
        .order_by("gang__name")
    )

    if request.method == "POST":
        form = AssignAssetForm(request.POST, playing=playing)
        if form.is_valid():
            membership = form.cleaned_data["membership"]
            try:
                with campaign_operation(found, actor=request.user) as act:
                    assigned = act.assign(campaign_asset, membership)
            except Refusal as refused:
                messages.error(request, str(refused))
            else:
                if assigned is None:
                    messages.error(request, f"{campaign_asset} was already removed.")
                else:
                    messages.success(
                        request, f"Assigned {campaign_asset} to {membership.gang.name}."
                    )
            if is_htmx(request):
                return _asset_update(request, found, campaign_asset)
            return redirect(_asset_back(request, found, campaign_asset))
    else:
        form = AssignAssetForm(playing=playing)

    _badge_a_redrawn_page(request, found)
    response = render(
        request,
        "n26/includes/campaign_assign_dialog.html"
        if is_htmx(request)
        else "n26/assign_asset.html",
        {
            "form": form,
            "campaign": found,
            "campaign_asset": campaign_asset,
            "choices": [
                (membership, str(membership.pk) == str(form["membership"].value()))
                for membership in playing
            ],
            "back": _asset_back(request, found, campaign_asset),
            "action": _table_action_href(request),
            "redrawn": is_htmx(request),
            "reopened": is_htmx(request) and request.method == "POST",
        },
    )

    if is_htmx(request):
        response["HX-Replace-Url"] = _table_action_href(request)
    return response


@login_required
def unassign_asset(request, pk, asset_pk):
    """Confirm and return a held asset to the unclaimed pool.

    Allow the arbitrator or the holding gang's owner.
    """
    from django.http import Http404

    from n26.core.campaigns import campaign_operation
    from n26.core.operations import Refusal
    from n26.core.views.htmx import is_htmx

    found = _any_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    campaign_asset = _campaign_asset_or_404(found, asset_pk)
    reading = getattr(request.user, "id", None)
    arbitrating = found.owner_id == reading
    if not arbitrating and not _holding_owner(campaign_asset, request.user):
        raise Http404("No such asset in this campaign")
    if not campaign_asset.held:
        messages.error(request, f"{campaign_asset} is not held by any gang.")
        if is_htmx(request):
            return _asset_update(request, found, campaign_asset)
        return redirect(_asset_back(request, found, campaign_asset))

    if request.method == "POST":
        holder = campaign_asset.holder.gang.name
        # The holding owner must still hold this asset; the arbitrator may act
        # regardless of its current holder.
        try:
            with campaign_operation(found, actor=request.user) as act:
                unassigned = act.unassign(
                    campaign_asset,
                    by_holder=None if arbitrating else campaign_asset.holder_id,
                )
        except Refusal as refused:
            messages.error(request, str(refused))
        else:
            if unassigned is None:
                messages.error(request, f"{campaign_asset} is not held by any gang.")
            else:
                messages.success(request, f"Unassigned {campaign_asset} from {holder}.")
        if is_htmx(request):
            return _asset_update(request, found, campaign_asset)
        return redirect(_asset_back(request, found, campaign_asset))

    response = render(
        request,
        "n26/includes/campaign_unassign_dialog.html"
        if is_htmx(request)
        else "n26/unassign_asset.html",
        {
            "campaign": found,
            "campaign_asset": campaign_asset,
            "back": _asset_back(request, found, campaign_asset),
            "action": _table_action_href(request),
        },
    )

    if is_htmx(request):
        response["HX-Replace-Url"] = _table_action_href(request)
    return response


@login_required
def transfer_asset(request, pk, asset_pk):
    """Transfer a held asset to another active gang.

    Allow the arbitrator or the holding gang's owner; validate the recipient
    against the same list shown by the form.
    """
    from django.http import Http404

    from n26.core.campaigns import campaign_operation
    from n26.core.forms import AssignAssetForm
    from n26.core.models import CampaignMembership
    from n26.core.operations import Refusal
    from n26.core.views.htmx import is_htmx

    found = _any_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    campaign_asset = _campaign_asset_or_404(found, asset_pk)
    reading = getattr(request.user, "id", None)
    arbitrating = found.owner_id == reading
    if not arbitrating and not _holding_owner(campaign_asset, request.user):
        raise Http404("No such asset in this campaign")
    if not campaign_asset.held:
        messages.error(request, f"{campaign_asset} is not held by any gang.")
        if is_htmx(request):
            return _asset_update(request, found, campaign_asset)
        return redirect(_asset_back(request, found, campaign_asset))
    receiving = (
        CampaignMembership.objects.filter(campaign=found, left__isnull=True)
        .exclude(pk=campaign_asset.holder_id)
        .select_related("gang", "gang__gang_type", "gang__owner")
        .order_by("gang__name")
    )

    if request.method == "POST":
        form = AssignAssetForm(request.POST, playing=receiving)
        if form.is_valid():
            membership = form.cleaned_data["membership"]
            holder = campaign_asset.holder.gang.name
            try:
                with campaign_operation(found, actor=request.user) as act:
                    moved = act.transfer(
                        campaign_asset,
                        membership,
                        by_holder=None if arbitrating else campaign_asset.holder_id,
                    )
            except Refusal as refused:
                messages.error(request, str(refused))
            else:
                if moved is None:
                    messages.error(request, f"{campaign_asset} was already removed.")
                else:
                    messages.success(
                        request,
                        f"{campaign_asset} went from {holder} to {membership.gang.name}.",
                    )
            if is_htmx(request):
                return _asset_update(request, found, campaign_asset)
            return redirect(_asset_back(request, found, campaign_asset))
    else:
        form = AssignAssetForm(playing=receiving)

    _badge_a_redrawn_page(request, found)
    response = render(
        request,
        "n26/includes/campaign_transfer_dialog.html"
        if is_htmx(request)
        else "n26/transfer_asset.html",
        {
            "form": form,
            "campaign": found,
            "campaign_asset": campaign_asset,
            "choices": [
                (membership, str(membership.pk) == str(form["membership"].value()))
                for membership in receiving
            ],
            "redrawn": is_htmx(request),
            "reopened": is_htmx(request) and request.method == "POST",
            "verb": "Transfer" if arbitrating else "Hand over",
            "back": _asset_back(request, found, campaign_asset),
            "action": _table_action_href(request),
        },
    )

    if is_htmx(request):
        response["HX-Replace-Url"] = _table_action_href(request)
    return response


@login_required
def remove_asset(request, pk, asset_pk):
    """Confirm on GET and remove a campaign asset on POST."""
    from n26.core.campaign_table import table_view_href
    from n26.core.campaigns import campaign_operation
    from n26.core.operations import Refusal

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    campaign_asset = _campaign_asset_or_404(found, asset_pk)
    back = table_view_href(request, _campaign_page(found)) + "#assets"

    if request.method == "POST":
        name = str(campaign_asset)
        try:
            with campaign_operation(found, actor=request.user) as act:
                removed = act.remove_asset(campaign_asset)
        except Refusal as refused:
            messages.error(request, str(refused))
        else:
            if removed is None:
                messages.error(request, f"{name} was already removed.")
            else:
                messages.success(request, f"Removed {name}.")
        return redirect(back)

    return render(
        request,
        "n26/remove_asset.html",
        {
            "campaign": found,
            "campaign_asset": campaign_asset,
            "back": back,
        },
    )


def _campaign_asset_types(campaign):
    """List shared asset types before campaign additions, in authored order."""
    from django.db.models import Case, IntegerField, When

    from n26.library.models import AssetType

    return (
        AssetType.objects.filter(
            campaign_type_id__in=(campaign.campaign_type_id, campaign.additions_id)
        )
        .annotate(
            own=Case(
                When(campaign_type_id=campaign.campaign_type_id, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("own", "position", "label_singular")
    )


def _addition_page(request, campaign, form, template, act, back, **context):
    """Validate and run a campaign-addition form through campaign_operation.

    Attach operation refusals to the form; redirect successful writes to back.
    """
    from n26.core.campaigns import campaign_operation
    from n26.core.operations import Refusal

    if request.method == "POST" and form.is_valid():
        try:
            with campaign_operation(campaign, actor=request.user) as op:
                said = act(op, form.cleaned_data)
        except Refusal as refused:
            form.add_error(None, str(refused))
        else:
            messages.success(request, said)
            return redirect(back)
    _badge_a_redrawn_page(request, campaign)
    return render(
        request,
        template,
        {
            "form": form,
            "campaign": campaign,
            "back": back,
            **context,
        },
    )


@login_required
def add_asset_type(request, pk):
    """Declare a new asset type for this campaign alone."""
    from n26.core.forms import AddAssetTypeForm

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    form = AddAssetTypeForm(request.POST or None)

    def act(op, data):
        asset_type = op.add_asset_type(
            data["label_singular"],
            data["ownership"],
            label_plural=data["label_plural"],
            display_group=data["display_group"],
        )
        return f"Added the asset type {asset_type.label_singular}."

    return _addition_page(
        request,
        found,
        form,
        "n26/add_asset_type.html",
        act,
        _assets_anchor(found),
        ownerships=_ownership_cards(str(form["ownership"].value() or "")),
    )


def _ownership_cards(chosen):
    """Build Holding and Possession radio cards with the selected value."""
    from n26.library.models import AssetType

    return [
        {
            "value": ownership.value,
            "label": ownership.label,
            "description": description,
            "checked": ownership.value == chosen,
        }
        for ownership, description in (
            (
                AssetType.Ownership.HOLDING,
                "One gang holds it at a time, and it can change hands.",
            ),
            (
                AssetType.Ownership.POSSESSION,
                "Each gang that receives an asset owns its own.",
            ),
        )
    ]


@login_required
def new_asset(request, pk):
    """Create an asset under a campaign type and add Holdings to the unclaimed pool.

    The unified custom picker accepts ?type= to restrict the offered type.
    """
    from n26.core.campaign_table import table_view_href
    from n26.core.forms import NewAssetForm

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    from n26.library.models import AssetType

    unified = request.GET.get("source") == "custom"
    offered_types = _campaign_asset_types(found)
    asset_type = (
        _asset_type_asked_for(found, request.GET.get("type")) if unified else None
    )
    if unified:
        offered_types = offered_types.filter(ownership=AssetType.Ownership.HOLDING)
        if asset_type:
            offered_types = offered_types.filter(pk=asset_type.pk)
    asset_types = list(offered_types)
    if unified and not asset_types:
        return redirect("n26-campaign-add-asset-type", pk=found.pk)
    form = NewAssetForm(request.POST or None, asset_types=offered_types)
    if asset_type and request.method == "GET":
        form.initial["asset_type"] = asset_type.pk

    def act(op, data):
        asset = op.create_asset(
            data["asset_type"],
            data["name"],
            annotation=data["annotation"],
            income=data["income"],
        )
        if asset.asset_type.is_holding:
            op.add_asset(asset)
        return f"Created {asset}."

    picked = str(form["asset_type"].value() or request.GET.get("type", ""))
    return _addition_page(
        request,
        found,
        form,
        "n26/new_asset.html",
        act,
        table_view_href(request, _campaign_page(found)) + "#assets",
        asset_types=[
            {
                "value": str(asset_type.pk),
                "label": asset_type.label_singular,
                "description": (
                    "Owned by one gang at a time and can be transferred."
                    if asset_type.is_holding
                    else f"Each gang has its own {asset_type.label_singular.lower()}."
                ),
                "checked": str(asset_type.pk) == picked,
            }
            for asset_type in asset_types
        ],
        adding=asset_type.plural.lower() if asset_type else "assets",
        unified=unified,
        custom_label=asset_type.label_singular.lower() if asset_type else "asset",
        custom_href=request.get_full_path(),
        catalogue_href=_table_action_href(
            request,
            reverse("n26-campaign-add-asset", args=[found.pk])
            + (f"?type={asset_type.pk}" if asset_type else ""),
        ),
    )


def _campaign_settings_url(campaign):
    from django.urls import reverse

    return reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=counters-and-labels"


@login_required
def add_counter(request, pk):
    """Give every gang in the campaign a counter, opening at a value."""
    from n26.core.forms import AddCounterForm

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    form = AddCounterForm(request.POST or None)

    def act(op, data):
        counter = op.add_counter(data["name"], opening=data["opening"])
        return f"Added the counter {counter}. Every gang starts at {data['opening']}."

    return _addition_page(
        request, found, form, "n26/add_counter.html", act, _campaign_settings_url(found)
    )


@login_required
def add_label(request, pk):
    """Add a fixed-option label to every gang in the campaign."""
    from n26.core.forms import AddLabelForm

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    form = AddLabelForm(request.POST or None)

    def act(op, data):
        slot = op.add_label(data["name"], data["options"])
        return f"Added the label {slot.choice_label}. Every gang picks one option."

    return _addition_page(
        request, found, form, "n26/add_label.html", act, _campaign_settings_url(found)
    )


@login_required
def archive_addition(request, pk, member_pk, kind):
    """Confirm and archive a campaign-added counter or label.

    Only the campaign's own additions are reachable. Show affected gang values
    and any refusal caused by rules that still reference the addition.
    """
    from django.http import Http404

    from n26.core.campaigns import archive_refusal, campaign_operation, own_addition
    from n26.core.operations import Refusal

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    field = "counter" if kind == "counter" else "slot"
    try:
        member = own_addition(found, member_pk, field)
    except ValueError:
        raise Http404(f"No such {kind} in this campaign") from None
    name = str(member.counter) if member.counter_id else member.slot.choice_label
    back = _campaign_settings_url(found)

    if request.method == "POST":
        try:
            with campaign_operation(found, actor=request.user) as act:
                if member.counter_id:
                    act.archive_counter(member)
                else:
                    act.archive_label(member)
        except Refusal as refused:
            messages.error(request, str(refused))
        else:
            messages.success(request, f"Archived the {kind} {name}.")
        return redirect(back)

    kept = (
        f"every change to {name} and the value it ended on"
        if member.counter_id
        else f"the gang's pick for {name}"
    )
    _badge_a_redrawn_page(request, found)
    return render(
        request,
        "n26/archive_campaign_addition.html",
        {
            "campaign": found,
            "kind": kind,
            "name": name,
            "action": request.path,
            "back": back,
            "heading": f"Archiving removes {name} from every gang in {found.name}",
            "consequences": (
                f"Gangs that join later will not get it. "
                f"Each gang's history keeps {kept}. "
                f"You can unarchive it later to give each gang still in "
                f"{found.name} what it had."
            ),
            "gangs": _what_each_gang_has(found, member),
            "refusal": archive_refusal(found, member),
        },
    )


def _what_each_gang_has(campaign, member):
    """List active gangs carrying an addition with its counter value or label pick.

    Load counter values with assignments; label picks use one extra query.
    """
    from n26.core.models import Assignment

    copies = list(
        Assignment.objects.filter(
            materialised_from=member,
            archived=False,
            gang_root__campaign_memberships__campaign=campaign,
            gang_root__campaign_memberships__left__isnull=True,
        )
        .select_related("gang_root", "counter_value")
        .order_by("gang_root__name", "pk")
    )
    if member.counter_id:
        # Match the gang sheet's zero value for an uninitialised counter.
        values = [getattr(copy, "counter_value", None) for copy in copies]
        return [
            {
                "gang": copy.gang_root.name,
                "value": str(held.value if held is not None else 0),
                "muted": False,
            }
            for copy, held in zip(copies, values, strict=True)
        ]
    picks = {
        pick.chosen_for_id: pick.pickable.name
        for pick in Assignment.objects.filter(
            chosen_for__in=copies, archived=False
        ).select_related("pickable")
    }
    return [
        {
            "gang": copy.gang_root.name,
            "value": picks.get(copy.pk, "Nothing picked yet"),
            "muted": copy.pk not in picks,
        }
        for copy in copies
    ]


@login_required
def unarchive_addition(request, pk, member_pk, kind):
    """Confirm and restore a campaign-added counter or label.

    Preview returning values separately from defaults for gangs that joined later.
    """
    from django.http import Http404

    from n26.core.campaigns import (
        archived_addition,
        campaign_operation,
        unarchive_preview,
    )
    from n26.core.operations import Refusal

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    field = "counter" if kind == "counter" else "slot"
    try:
        member = archived_addition(found, member_pk, field)
    except ValueError:
        raise Http404(f"No such archived {kind} in this campaign") from None
    name = str(member.counter) if member.counter_id else member.slot.choice_label
    back = _campaign_settings_url(found)

    if request.method == "POST":
        try:
            with campaign_operation(found, actor=request.user) as act:
                if member.counter_id:
                    act.unarchive_counter(member)
                else:
                    act.unarchive_label(member)
        except Refusal as refused:
            messages.error(request, str(refused))
        else:
            messages.success(request, f"Unarchived the {kind} {name}.")
        return redirect(back)

    preview = unarchive_preview(found, member)
    _badge_a_redrawn_page(request, found)
    return render(
        request,
        "n26/unarchive_campaign_addition.html",
        {
            "campaign": found,
            "kind": kind,
            "name": name,
            "action": request.path,
            "back": back,
            "returning": preview.returning,
            "new": preview.new,
            "new_heading": (
                f"Gangs that get {name} at its starting value"
                if member.counter_id
                else f"Gangs that get {name} with nothing picked"
            ),
        },
    )


def _tables_offered(campaign, *, include_staged=False):
    """Offer unarchived tables from system packs or this campaign's pack.

    Limit them to the campaign's asset types and the reader's staged-content access.
    """
    from django.db.models import Q

    from n26.library.models import AssetTable

    offered = (
        AssetTable.objects.filter(
            asset_type__campaign_type_id__in=(
                campaign.campaign_type_id,
                campaign.additions_id,
            )
        )
        .filter(Q(pack__owner__isnull=True) | Q(pack=campaign.pack))
        .unarchived()
        .annotate(entry_count=Count("entries"))
        .select_related("asset_type")
        .order_by("asset_type__position", "name")
    )
    return offered if include_staged else offered.live()


def _given_tables(campaign):
    """Return tables granted by the shared campaign type, which cannot be closed here."""
    from n26.library.models import DefaultAssignment

    return set(
        DefaultAssignment.objects.filter(
            default_set_id=campaign.campaign_type.built_ins_id,
            archived=False,
            asset_table__isnull=False,
        ).values_list("asset_table_id", flat=True)
    )


def _open_tables(campaign):
    """Return tables granted by this campaign's active built-in additions."""
    from n26.library.models import DefaultAssignment

    return set(
        DefaultAssignment.objects.filter(
            default_set_id=campaign.additions.built_ins_id,
            archived=False,
            asset_table__isnull=False,
        ).values_list("asset_table_id", flat=True)
    )


def _table_said(table):
    """Summarise a table's die and entry count using its asset type's labels."""
    asset_type = table.asset_type
    count = table.entry_count
    if count == 0:
        contains = f"no {asset_type.plural.lower()} yet"
    elif count == 1:
        contains = f"1 {asset_type.label_singular.lower()}"
    else:
        contains = f"{count} {asset_type.plural.lower()}"
    if table.dice:
        return f"{table.get_dice_display()} · {contains}"
    return contains


def _tables_lead(asset_types):
    """Use Territory wording for a single Territory type, or generic asset wording."""
    from n26.library.territory_table import TERRITORY

    holding = [t for t in asset_types if t.is_holding]
    if len(holding) == 1 and holding[0].label_singular == TERRITORY:
        return "These are roll options. Generate the unclaimed pool separately with Roll territories."
    return "These are roll options. Generate unclaimed assets separately on the campaign page."


@login_required
def campaign_tables(request, pk):
    """Open or close tables for every gang, grouped by Holding asset type.

    Shared built-in tables remain read-only. Apply changes only where the
    submitted selection differs from the campaign's current additions.
    """
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import OpenTablesForm
    from n26.core.operations import Refusal

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    offered = _tables_offered(found, include_staged=sees_staged(request.user))
    given = _given_tables(found)
    was_open = _open_tables(found)
    openable = offered.exclude(pk__in=given)

    if request.method == "POST":
        form = OpenTablesForm(request.POST, tables=openable)
        if form.is_valid():
            wanted = {table.pk: table for table in form.cleaned_data["open"]}
            by_pk = {table.pk: table for table in openable}
            opened, closed = [], []
            try:
                with campaign_operation(found, actor=request.user) as act:
                    for table_pk, table in wanted.items():
                        if table_pk not in was_open and act.open_table(table):
                            opened.append(str(table))
                    for table_pk in was_open - set(wanted):
                        table = by_pk.get(table_pk)
                        if table is not None and act.close_table(table):
                            closed.append(str(table))
            except Refusal as refused:
                messages.error(request, str(refused))
            else:
                said = []
                if opened:
                    said.append(f"Made {', '.join(opened)} available to every gang.")
                if closed:
                    said.append(f"Withdrew {', '.join(closed)}.")
                messages.success(request, " ".join(said) or "Nothing changed.")
            return redirect("n26-campaign-tables", pk=found.pk)
        messages.error(request, _first_error(form))
        return redirect("n26-campaign-tables", pk=found.pk)

    asset_types = list(_campaign_asset_types(found))
    sections = []
    for asset_type in asset_types:
        if not asset_type.is_holding:
            continue
        tables = [t for t in offered if t.asset_type_id == asset_type.pk]
        label = asset_type.label_singular.lower()
        plural = asset_type.plural.lower()
        sections.append(
            {
                "asset_type": asset_type,
                "label": label,
                "plural": plural,
                "intro": (
                    f"Use these tables for starting rolls or to generate unclaimed {plural}."
                ),
                "ticks_help": (
                    "Tick a table to make it available to every gang. Untick to "
                    f"withdraw it. {asset_type.plural} already rolled stay in the "
                    "campaign."
                ),
                "empty": (
                    f"No tables of {plural} yet. Create one and add {plural} to it."
                ),
                "given": [
                    {
                        "name": str(t),
                        "said": _table_said(t),
                        "href": _table_href(found, t),
                    }
                    for t in tables
                    if t.pk in given
                ],
                "offered": [
                    {
                        "value": str(t.pk),
                        "name": str(t),
                        "said": _table_said(t),
                        "checked": t.pk in was_open,
                        "href": _table_href(found, t),
                    }
                    for t in tables
                    if t.pk not in given
                ],
            }
        )
    from django.urls import reverse

    return render(
        request,
        "n26/campaign_tables.html",
        {
            "campaign": found,
            "sections": sections,
            "lead": _tables_lead(asset_types),
            "tables_title": "Available territory tables"
            if [t.label_singular for t in asset_types if t.is_holding] == ["Territory"]
            else "Available tables",
            "back": _assets_anchor(found),
            "new_href": reverse("n26-campaign-new-table", args=[found.pk]),
        },
    )


def _table_href(campaign, table):
    """Link to editable campaign-owned tables; shared tables have no page here."""
    from django.urls import reverse

    if table.pack_id != campaign.pack_id:
        return ""
    return reverse("n26-campaign-table", args=[campaign.pk, table.pk])


@login_required
def new_table(request, pk):
    """Create a campaign table and redirect to its entry editor."""
    from django.urls import reverse

    from n26.core.campaigns import campaign_operation
    from n26.core.forms import NewTableForm
    from n26.core.operations import Refusal
    from n26.library.models import AssetType

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    asset_types = _campaign_asset_types(found).filter(
        ownership=AssetType.Ownership.HOLDING
    )
    form = NewTableForm(request.POST or None, asset_types=asset_types)
    if request.method == "POST" and form.is_valid():
        try:
            with campaign_operation(found, actor=request.user) as act:
                table = act.create_table(
                    form.cleaned_data["asset_type"],
                    form.cleaned_data["name"],
                    dice=form.cleaned_data["dice"],
                )
        except Refusal as refused:
            form.add_error(None, str(refused))
        else:
            messages.success(
                request,
                f"Created the table {table}. Add "
                f"{table.asset_type.plural.lower()} to it next.",
            )
            return redirect("n26-campaign-table", pk=found.pk, table_pk=table.pk)

    picked = str(form["asset_type"].value() or request.GET.get("type", ""))
    chosen = str(form["dice"].value() or "")
    _badge_a_redrawn_page(request, found)
    return render(
        request,
        "n26/new_table.html",
        {
            "form": form,
            "campaign": found,
            "back": reverse("n26-campaign-tables", args=[found.pk]),
            "asset_types": [
                {
                    "value": str(asset_type.pk),
                    "label": asset_type.label_singular,
                    "description": f"A table of {asset_type.plural.lower()}.",
                    "checked": str(asset_type.pk) == picked,
                }
                for asset_type in asset_types
            ],
            "dice": [
                {"value": value, "label": label, "checked": value == chosen}
                for value, label in form.fields["dice"].choices
            ],
        },
    )


def _own_table_or_404(campaign, table_pk):
    """Load a table from this campaign's pack with its asset type; reject bad keys."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.library.models import AssetTable

    try:
        return get_object_or_404(
            AssetTable.objects.select_related("asset_type"),
            pk=table_pk,
            pack=campaign.pack,
        )
    except ValidationError:
        raise Http404("No such table in this campaign") from None


@login_required
def campaign_table(request, pk, table_pk):
    """Edit a campaign table and display its die coverage.

    Offer only addable assets of the table's type and display entry validation
    errors on the form.
    """
    from django.core.exceptions import ValidationError
    from django.db.models import F
    from django.urls import reverse

    from n26.core.campaigns import campaign_operation
    from n26.core.forms import TableEntryForm
    from n26.library.views import _coverage_context

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    table = _own_table_or_404(found, table_pk)
    offered = _holding_assets(found, include_staged=sees_staged(request.user)).filter(
        asset_type=table.asset_type
    )
    form = TableEntryForm(request.POST or None, offered=offered, table=table)
    if request.method == "POST" and form.is_valid():
        try:
            with campaign_operation(found, actor=request.user) as act:
                entry = act.add_table_entry(
                    table,
                    form.cleaned_data["asset"],
                    roll_low=form.cleaned_data["roll_low"],
                    roll_high=form.cleaned_data["roll_high"],
                )
        except ValidationError as refused:
            for message in refused.messages:
                form.add_error(None, message)
        else:
            messages.success(request, f"Added {entry.label} to {table}.")
            return redirect("n26-campaign-table", pk=found.pk, table_pk=table.pk)

    entries = list(
        table.entries.select_related("asset").order_by(
            F("roll_low").asc(nulls_last=True), "position", "asset__name"
        )
    )
    coverage = (
        _coverage_context(table.coverage(entries), lambda entry: entry.label)
        if table.dice
        else None
    )
    submitted = str(form["asset"].value() or "")
    _badge_a_redrawn_page(request, found)
    return render(
        request,
        "n26/campaign_table.html",
        {
            "form": form,
            "campaign": found,
            "table": table,
            "entries": [
                {
                    "band": entry.band,
                    "label": entry.label,
                    "remove_href": reverse(
                        "n26-campaign-table-entry-remove",
                        args=[found.pk, table.pk, entry.pk],
                    ),
                }
                for entry in entries
            ],
            "coverage": coverage,
            "assets": [
                {
                    "value": str(asset.pk),
                    "label": asset.name,
                    "checked": str(asset.pk) == submitted,
                }
                for asset in offered
            ],
            "label": table.asset_type.label_singular.lower(),
            "plural": table.asset_type.plural.lower(),
            "back": reverse("n26-campaign-tables", args=[found.pk]),
        },
    )


@login_required
def remove_table_entry(request, pk, table_pk, entry_pk):
    """Remove a campaign table entry on POST; redirect GET without changing it."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.core.campaigns import campaign_operation
    from n26.library.models import AssetTableEntry

    found = _own_campaign_or_404(request, pk, with_owner_badge=False)
    table = _own_table_or_404(found, table_pk)
    if request.method == "POST":
        try:
            entry = get_object_or_404(
                AssetTableEntry.objects.select_related("asset"),
                pk=entry_pk,
                table=table,
            )
        except ValidationError:
            raise Http404("No such entry on this table") from None
        label = entry.label
        with campaign_operation(found, actor=request.user) as act:
            act.remove_table_entry(entry)
        messages.success(request, f"Removed {label} from {table}.")
    return redirect("n26-campaign-table", pk=found.pk, table_pk=table.pk)


def invitations_for(user):
    """Return unanswered invitations to active campaigns with arbitrator badge data."""
    from n26.core.models import CampaignParticipant

    if not user.is_authenticated:
        return CampaignParticipant.objects.none()
    return (
        CampaignParticipant.objects.filter(
            user=user,
            state=CampaignParticipant.State.INVITED,
            campaign__archived=False,
        )
        # Preload arbitrator profile and grants for invitation badges.
        .select_related(
            "campaign", "campaign__owner", "campaign__owner__profile", "invited_by"
        )
        .prefetch_related("campaign__owner__badge_grants")
        .order_by("campaign__name")
    )


def _person(value):
    """Return an active account for a numeric id, or None for invalid input."""
    from django.contrib.auth.models import User

    try:
        return User.objects.filter(pk=int(value), is_active=True).first()
    except TypeError, ValueError:
        return None


def _plays_in(campaign, user):
    """Check accepted participation, excluding pending or declined invitations.

    Arbitrators are authorised separately from this player check.
    """
    from n26.core.models import CampaignParticipant

    if not user.is_authenticated:
        return False
    return CampaignParticipant.objects.filter(
        campaign=campaign,
        user=user,
        state=CampaignParticipant.State.ACCEPTED,
    ).exists()


def _players(campaign):
    """Load campaign participants and their states with user badge data."""
    from n26.core.models import CampaignParticipant

    return (
        CampaignParticipant.objects.filter(campaign=campaign)
        # Preload profile and grants for participant badges.
        .select_related("user", "user__profile")
        .prefetch_related("user__badge_grants")
        .order_by("user__username")
    )


@login_required
def add_player(request, pk):
    """Search active accounts and invite a selected person.

    Keep search and the selected invitation dialog in the URL for reloads.
    """
    from django.contrib.auth.models import User

    from n26.core.campaigns import campaign_operation
    from n26.core.operations import Refusal

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
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
        return redirect("n26-campaign-add-player", pk=found.pk)

    players = list(_players(found))
    # Mark existing participants in the search results.
    asked_already = {player.user_id for player in players}
    people = []
    if query:
        people = list(
            User.objects.filter(username__icontains=query, is_active=True)
            .exclude(pk=found.owner_id)
            # Preload profile and grants for search-result badges.
            .select_related("profile")
            .prefetch_related("badge_grants")
            .order_by("username")[:PEOPLE_FOUND]
        )

    asking = _person(request.GET.get("invite")) if request.GET.get("invite") else None

    return render(
        request,
        "n26/add_player.html",
        {
            "campaign": found,
            "players": players,
            "query": query,
            "people": people,
            "asked_already": asked_already,
            "asking": asking,
        },
    )


@login_required
def remove_player(request, pk, user_pk):
    """Confirm removal of a player, optionally removing their gangs too."""
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignParticipant

    found = _own_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    players = CampaignParticipant.objects.select_related("user")
    if request.method != "POST":
        # Load player badges only for the confirmation page.
        players = players.select_related("user__profile").prefetch_related(
            "user__badge_grants"
        )
    player = get_object_or_404(players, campaign=found, user__pk=user_pk)

    if request.method == "POST":
        name = player.user.username
        # Remove gangs only when explicitly requested.
        with_gangs = request.POST.get("gangs") == "remove"
        with campaign_operation(found, actor=request.user) as act:
            removed = act.remove_player(player, with_gangs=with_gangs)
        if removed is None:
            messages.info(request, f"{name} is no longer in {found.name}.")
        elif removed:
            gangs = "gangs" if len(removed) > 1 else "gang"
            messages.success(
                request, f"Removed {name} and their {gangs} from {found.name}."
            )
        else:
            messages.success(request, f"Removed {name}.")
        return redirect("n26-campaign-add-player", pk=found.pk)

    return render(
        request,
        "n26/remove_player.html",
        {
            "campaign": found,
            "player": player,
            "gangs": list(_gangs_of(found, player.user)),
        },
    )


@login_required
def leave_campaign(request, pk):
    """Confirm an accepted player's departure and remove their active gangs.

    Preview each gang's losses and unfinished battles; unfinished work does not
    block departure.
    """
    from django.http import Http404

    from n26.core.campaigns import campaign_operation
    from n26.core.render import render_campaign

    found = _any_campaign_or_404(request, pk, with_owner_badge=request.method == "GET")
    if not _plays_in(found, request.user):
        raise Http404("You are not a player in this campaign")
    back = _campaign_page(found)

    if request.method == "POST":
        with campaign_operation(found, actor=request.user) as act:
            left = act.leave()
        if left is None:
            messages.info(request, f"You are no longer a player in {found.name}.")
        elif left:
            gangs = "gangs" if len(left) > 1 else "gang"
            messages.success(request, f"You and your {gangs} left {found.name}.")
        else:
            messages.success(request, f"You left {found.name}.")
        # Return to the page top so the queued message is visible.
        return redirect(back)

    sheet = render_campaign(found, with_owner_badges=False)
    lines = [
        line
        for line in sheet.gangs
        if line.owner is not None and line.owner.pk == request.user.pk
    ]
    losses = [
        GangLosses(line.name, *_what_the_line_loses(sheet, line)) for line in lines
    ]
    drafts, unrecorded = _unfinished_battles(found, [line.gang_id for line in lines])
    return render(
        request,
        "n26/leave_campaign.html",
        {
            "campaign": found,
            "losses": losses,
            "drafts": drafts,
            "unrecorded": unrecorded,
            "back": back,
        },
    )


def _gangs_of(campaign, user):
    """List a player's active gangs in this campaign, ordered by name."""
    from n26.core.models import Gang

    return Gang.objects.filter(
        owner=user,
        campaign_memberships__campaign=campaign,
        campaign_memberships__left__isnull=True,
    ).order_by("name")


@dataclass(frozen=True)
class GangLosses:
    """One departing gang's lost grants and returned holdings, as (column, value) pairs."""

    name: str
    losing: list
    returning: list


@dataclass(frozen=True)
class UnfinishedBattle:
    """A label and URL for unfinished work on the leave page."""

    label: str
    href: str


def _unfinished_battles(campaign, gang_ids):
    """List draft reports and unrecorded battles involving the departing gangs."""
    from n26.core.models import Battle, PostBattleReport

    if not gang_ids:
        return [], []
    drafts = [
        UnfinishedBattle(
            f"{report.gang.name}: {report.battle.title}",
            reverse("n26-post-battle-editor", args=[report.pk]),
        )
        for report in PostBattleReport.objects.filter(
            gang__in=gang_ids,
            battle__campaign=campaign,
            battle__archived=False,
            state=PostBattleReport.State.DRAFT,
        )
        .select_related("gang", "battle")
        .order_by("battle__date", "gang__name")
    ]
    unrecorded = [
        UnfinishedBattle(
            battle.title,
            reverse("n26-battle", args=[campaign.pk, battle.pk]),
        )
        for battle in campaign.battles.filter(
            gangs__in=gang_ids, result=Battle.Result.NOT_RECORDED, archived=False
        )
        .distinct()
        .order_by("date")
    ]
    return drafts, unrecorded


@login_required
def answer_invitation(request, pk):
    """Accept or decline the signed-in reader's own campaign invitation.

    Read its stored state under the campaign lock before choosing the response.
    """
    from django.core.exceptions import ValidationError
    from django.http import Http404
    from django.urls import reverse

    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignParticipant
    from n26.core.views.permissions import _safe_redirect

    if request.method != "POST":
        return redirect("n26-campaigns")

    try:
        player = get_object_or_404(
            CampaignParticipant.objects.select_related("campaign"),
            campaign__pk=pk,
            campaign__archived=False,
            user=request.user,
        )
    except ValidationError as malformed:
        raise Http404("No such campaign") from malformed
    campaign = player.campaign
    answer = request.POST.get("answer")
    if answer not in ("accept", "decline"):
        messages.error(request, "Say whether you are accepting or declining.")
        return _safe_redirect(
            request, request.POST.get("next", ""), fallback_url=reverse("n26-campaigns")
        )

    accepted = answer == "accept"
    with campaign_operation(campaign, actor=request.user) as act:
        answered = act.answer_invitation(request.user, accepted)
        # Read invitation state while the campaign lock prevents concurrent removal.
        state = (
            CampaignParticipant.objects.filter(pk=player.pk)
            .values_list("state", flat=True)
            .first()
        )
    if state is None:
        messages.info(request, "This invitation is no longer available.")
        return redirect("n26-campaigns")
    if state == CampaignParticipant.State.ACCEPTED:
        messages.success(
            request,
            f"You joined {campaign.name}."
            if answered
            else f"You have already joined {campaign.name}.",
        )
        return redirect("n26-campaign", pk=campaign.pk)
    messages.info(
        request,
        f"You declined {campaign.name}."
        if answered
        else f"You have already declined {campaign.name}.",
    )
    return _safe_redirect(
        request, request.POST.get("next", ""), fallback_url=reverse("n26-campaigns")
    )


@login_required
def campaign_grouping(request, pk):
    """Only the arbitrator sets shared grouping and colours."""
    from n26.core.campaign_table import label_options
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import CampaignGroupingForm
    from n26.core.operations import Refusal
    from n26.core.render import _arbitrators_additions

    found = _own_campaign_or_404(request, pk, with_owner_badge=False)
    _, slots = _arbitrators_additions(found)
    form = CampaignGroupingForm(
        request.POST or None,
        campaign=found,
        slots=slots,
        options=label_options(found, slots),
    )
    if request.method == "POST" and form.is_valid():
        try:
            with campaign_operation(found, actor=request.user) as op:
                op.set_gang_grouping(form.cleaned_data["grouping"], form.colours())
        except Refusal as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Gang grouping saved.")
            return redirect(reverse("n26-campaign", args=[found.pk]) + "#gangs")
    return render(
        request,
        "n26/campaign_grouping.html",
        {
            "campaign": found,
            "form": form,
            "groups": form.groups,
            "back": reverse("n26-campaign", args=[found.pk]) + "#gangs",
        },
    )
