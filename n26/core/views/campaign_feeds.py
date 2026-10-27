"""Campaign feeds: the public page another website frames, and the
arbitrator's controls for making and turning off feeds.

The feed's page is the one N26 page anybody may read without signing in,
and the one page another site may frame. Both follow from where it is
shown: a Google Site's visitors are not Gyrinx users, and a browser blocks
the cookies a sign-in would need inside a frame on another site. The token
in the address is the whole of the permission, so the page shows one
section and offers no control that changes anything.
"""

from datetime import UTC, datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.syndication.views import Feed
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST

from n26.core.views.permissions import _own_campaign_or_404
from n26.flags import CAMPAIGN_FEEDS, requires_flag, switched_on

#: How long a browser or cache may reuse a feed's page. Short, so a battle
#: recorded on Gyrinx reaches the other site within a minute.
FEED_MAX_AGE_SECONDS = 60


def feed_choices(campaign):
    """What a feed can show: Gangs, Battles, then one entry per
    transferable asset type, such as Territories. Each is ``(value, label)``;
    an asset type's value is ``assets:<asset type id>``."""
    from n26.core.views.campaigns import _campaign_asset_types
    from n26.library.models import AssetType

    choices = [("gangs", "Gangs"), ("battles", "Battles")]
    for asset_type in _campaign_asset_types(campaign).filter(
        ownership=AssetType.Ownership.HOLDING, archived=False
    ):
        choices.append((f"assets:{asset_type.pk}", asset_type.plural))
    return choices


def feed_rows(campaign, request):
    """The campaign's live feeds as the Feeds tab lists them: what to copy
    for the place each one is shown, and the steps for that place."""
    from n26.core.feeds import PLACEMENTS, copy_text, page_url
    from n26.core.models import CampaignFeed

    rows = []
    for feed in CampaignFeed.objects.filter(
        campaign=campaign, archived=False
    ).select_related("campaign", "asset_type"):
        placement = PLACEMENTS[feed.target]
        rows.append(
            {
                "section": feed.section_label,
                "target": feed.get_target_display(),
                "copy_label": placement.copy_label,
                "copy_text": copy_text(request, feed),
                "multiline": placement.kind == "embed",
                "steps": placement.steps,
                "preview_url": page_url(request, feed),
                "turn_off_href": reverse(
                    "n26-campaign-turn-off-feed", args=[campaign.pk, feed.pk]
                ),
            }
        )
    return rows


@requires_flag(CAMPAIGN_FEEDS)
@login_required
@require_POST
def add_campaign_feed(request, pk):
    """Make a feed of one section, then return to the Feeds tab."""
    from n26.core.models import CampaignFeed

    found = _own_campaign_or_404(request, pk, with_owner_badge=False)
    feeds_url = reverse("n26-edit-campaign", args=[found.pk]) + "?tab=feeds"

    shown = dict(feed_choices(found))
    chosen = request.POST.get("section", "")
    target = request.POST.get("target", "")
    if chosen not in shown or target not in CampaignFeed.Target.values:
        messages.error(request, "Choose a section and where to show it.")
        return redirect(feeds_url)

    section, _, asset_type_id = chosen.partition(":")
    if target == CampaignFeed.Target.RSS and section != CampaignFeed.Section.BATTLES:
        messages.error(
            request,
            "An RSS feed can only follow Battles. Choose Battles, or show "
            f"{shown[chosen]} somewhere else.",
        )
        return redirect(feeds_url)
    CampaignFeed.objects.create(
        campaign=found,
        section=section,
        asset_type_id=asset_type_id or None,
        target=target,
    )
    messages.success(request, f"Made a feed of {shown[chosen]}.")
    return redirect(feeds_url)


@requires_flag(CAMPAIGN_FEEDS)
@login_required
@require_POST
def turn_off_campaign_feed(request, pk, feed_pk):
    """Archive a feed. Its address stops working at once."""
    from n26.core.models import CampaignFeed

    found = _own_campaign_or_404(request, pk, with_owner_badge=False)
    feed = get_object_or_404(CampaignFeed, pk=feed_pk, campaign=found, archived=False)
    feed.archive()
    messages.success(request, f"Turned off the {feed.section_label} feed.")
    return redirect(reverse("n26-edit-campaign", args=[found.pk]) + "?tab=feeds")


def _live_feed_or_404(token):
    """A feed that is switched on, in a campaign that is still running.

    Not ``requires_flag``: that asks about the signed-in reader, and a
    feed's readers are never signed in. It asks whether the feature is
    switched on at all instead.
    """
    from n26.core.models import CampaignFeed

    if not switched_on(CAMPAIGN_FEEDS):
        raise Http404("Campaign feeds are not switched on")
    return get_object_or_404(
        CampaignFeed.objects.select_related("campaign", "asset_type"),
        token=token,
        archived=False,
        campaign__archived=False,
    )


def _recent_battles(campaign):
    """The newest battles as the campaign's Battles page reads them: each
    gang with its type and starting crew, and the stake. Player names are
    left out of every feed, because a feed is public."""
    from n26.core.views.battles import _battle_lines
    from n26.core.views.campaigns import BATTLES_ON_THE_PAGE

    return _battle_lines(campaign, limit=BATTLES_ON_THE_PAGE)


def battle_summary(line):
    """One battle in a sentence, for RSS items: result, gangs, stake."""
    gangs = ", ".join(
        f"{entry.gang.name} ({entry.gang.gang_type.name}"
        + (f", {entry.starting} starting" if entry.starting is not None else "")
        + ")"
        for entry in line.gangs
    )
    summary = f"{line.battle.result_label}. Gangs: {gangs or 'none named'}."
    if line.stake:
        summary += (
            f" Stake: {line.stake} ({line.stake.asset.asset_type.label_singular})"
        )
        if line.battle.stake_awarded_to:
            summary += f", to {line.battle.stake_awarded_to.name}"
        summary += "."
    return summary


@xframe_options_exempt
def campaign_feed(request, token):
    """One section of a campaign, for another website to frame, or for a
    social site to draw as a link card from its Open Graph tags."""
    from n26.core.feeds import PLACEMENTS, RSS, page_url, rss_url
    from n26.core.models import CampaignFeed
    from n26.core.render import render_campaign

    feed = _live_feed_or_404(token)
    campaign = feed.campaign

    context = {
        "feed": feed,
        "campaign": campaign,
        "page_url": page_url(request, feed),
        "rss_url": rss_url(request, feed)
        if PLACEMENTS[feed.target].kind == RSS
        else "",
    }
    if feed.section == CampaignFeed.Section.BATTLES:
        lines = _recent_battles(campaign)
        context["lines"] = lines
        recorded = campaign.battles.filter(archived=False).count()
        summary = f"{recorded} battle{'s' if recorded != 1 else ''} recorded."
        if lines:
            latest = lines[0].battle
            summary += f" Latest: {latest.title}, {latest.result_label}."
    else:
        sheet = render_campaign(campaign, viewer=None, with_owner_badges=False)
        if feed.section == CampaignFeed.Section.GANGS:
            context["sheet"] = sheet
            names = [gang.name for gang in sheet.gangs]
            summary = (
                f"{len(names)} gang{'s' if len(names) != 1 else ''}: "
                + ", ".join(names)
                + "."
                if names
                else "No gangs yet."
            )
        else:
            table = next(
                (
                    table
                    for table in sheet.assets
                    if table.asset_type_id == str(feed.asset_type_id)
                ),
                None,
            )
            context["table"] = table
            summary = (
                f"{table.held} of {len(table.entries)} {feed.section_label.lower()} held."
                if table and table.entries
                else f"No {feed.section_label.lower()} yet."
            )
    context["summary"] = summary

    response = render(request, "n26/campaign_feed.html", context)
    response["Cache-Control"] = f"public, max-age={FEED_MAX_AGE_SECONDS}"
    # Browsers that honour CSP check this instead of X-Frame-Options. Any
    # site may frame the page: a Google Site on its own domain puts that
    # domain at the top of the frame chain, so no fixed list would do.
    response["Content-Security-Policy"] = "frame-ancestors *"
    return response


class BattlesRss(Feed):
    """A battles feed as RSS 2.0: one item per recorded battle, newest
    first. Only feeds made for an RSS reader are served here.

    Holds the request it serves, so ``campaign_feed_rss`` makes one per
    request rather than sharing one between threads.
    """

    def get_object(self, request, token):
        from n26.core.models import CampaignFeed

        feed = _live_feed_or_404(token)
        if feed.target != CampaignFeed.Target.RSS:
            raise Http404("This feed is not an RSS feed")
        self.request, self.feed = request, feed
        return feed

    language = "en-gb"

    def title(self, feed):
        return f"Battles – {feed.campaign.name}"

    def feed_url(self, feed):
        # The request's own address, so the self link names the host the
        # reader used rather than the one the Sites framework is set to.
        from n26.core.feeds import rss_url

        return rss_url(self.request, feed)

    def link(self, feed):
        from n26.core.feeds import page_url

        return page_url(self.request, feed)

    def description(self, feed):
        return f"Battles recorded in {feed.campaign.name} on Gyrinx."

    def items(self, feed):
        return _recent_battles(feed.campaign)

    def item_title(self, line):
        return line.battle.title

    def item_description(self, line):
        return battle_summary(line)

    def item_link(self, line):
        # Battle pages need a sign-in, so every item opens the feed's page.
        return self.link(self.feed) + f"#battle-{line.battle.pk}"

    def item_guid(self, line):
        return str(line.battle.pk)

    item_guid_is_permalink = False

    def item_pubdate(self, line):
        return datetime.combine(line.battle.date, time(12), tzinfo=UTC)

    def item_updateddate(self, line):
        return line.battle.modified

    def __call__(self, request, *args, **kwargs):
        response = super().__call__(request, *args, **kwargs)
        response["Cache-Control"] = f"public, max-age={FEED_MAX_AGE_SECONDS}"
        return response


def campaign_feed_rss(request, token):
    return BattlesRss()(request, token=token)
