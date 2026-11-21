"""What the Feeds tab gives the arbitrator for each place a feed can go.

Every feed has one public page. Where it is shown decides how that page is
reached, which is one of three kinds:

- ``EMBED``: website builders frame the page, so the arbitrator copies an
  iframe that names it. Live: the page loads afresh on every visit.
- ``LINK``: Facebook, Discord and Slack allow no frames. A pasted link is
  drawn as a preview card from the page's Open Graph tags, which those
  sites read once and keep, so the card is a snapshot that opens the live
  page.
- ``RSS``: a feed reader polls a list of battles at its own pace.

Plain data, so the tab and its tests read the same steps.
"""

from dataclasses import dataclass

from django.urls import reverse
from django.utils.html import escape

EMBED = "embed"
LINK = "link"
RSS = "rss"

#: Frame heights that fit each section's first few lines without a gap.
#: The other site's editor can resize the frame afterwards.
EMBED_HEIGHTS = {"gangs": 320, "battles": 360, "assets": 360}


@dataclass(frozen=True)
class Placement:
    kind: str
    #: What the copy box is called, for screen readers and its label.
    copy_label: str
    steps: str


PLACEMENTS = {
    "google_sites": Placement(
        EMBED,
        "Embed code",
        "In Google Sites, choose Insert, then Embed, then Embed code. "
        "Paste the code, then choose Next and Insert.",
    ),
    "squarespace": Placement(
        EMBED,
        "Embed code",
        "Edit the page, add a Code block and paste the code. "
        "Squarespace allows Code blocks on the Core plan and above.",
    ),
    "wordpress": Placement(
        EMBED,
        "Embed code",
        "Edit the page, add a Custom HTML block and paste the code. "
        "WordPress.com allows this on the Business plan and above.",
    ),
    "wix": Placement(
        EMBED,
        "Embed code",
        "In the Wix editor, choose Add Elements, then Embed Code, then "
        "Embed HTML. Paste the code into the box.",
    ),
    "link_card": Placement(
        LINK,
        "Link",
        "Paste the link into a post or message. It shows as a card that "
        "opens the live feed. The card itself keeps what the feed showed "
        "when the link was first posted.",
    ),
    "rss": Placement(
        RSS,
        "RSS link",
        "Paste the link into a feed reader, the WordPress RSS block, "
        "Slack's RSS app or a Discord RSS bot.",
    ),
}


def page_url(request, feed):
    return request.build_absolute_uri(reverse("n26-campaign-feed", args=[feed.token]))


def rss_url(request, feed):
    return request.build_absolute_uri(
        reverse("n26-campaign-feed-rss", args=[feed.token])
    )


def copy_text(request, feed):
    """What the arbitrator pastes into the other site."""
    placement = PLACEMENTS[feed.target]
    if placement.kind == RSS:
        return rss_url(request, feed)
    if placement.kind == LINK:
        return page_url(request, feed)
    height = EMBED_HEIGHTS[feed.section]
    title = escape(f"{feed.section_label} – {feed.campaign.name}")
    return (
        f'<iframe src="{page_url(request, feed)}" title="{title}" '
        f'style="width:100%;height:{height}px;border:0"></iframe>'
    )
