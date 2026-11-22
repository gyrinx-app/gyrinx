"""Campaign feeds — one section of a campaign, readable from another website.

A feed lets the arbitrator show one section of a campaign (its gangs, its
battles, or one type of asset such as Territories) on a site outside
Gyrinx, starting with Google Sites. The other site frames the feed's page
and loads it afresh on every visit, so what it shows is always current.

Visitors to that site are not signed in to Gyrinx, so the feed's page asks
for no sign-in. Its address carries ``token`` instead, which is long and
random so that it cannot be guessed. Google Sites strips query strings from
an embedded address, so the token sits in the path. Turning a feed off
archives it, and an archived feed's page returns 404 at once.

A feed is display state, like ``PrintConfig``: it records nothing that
happened in the campaign, so it is saved directly rather than through a
campaign operation.
"""

import secrets

from django.db import models

from n26.core.models.abstract import Archived, Base


def new_feed_token():
    """Return 128 bits of randomness, URL-safe. Never derived from the id,
    which is a ULID and so partly predictable from its creation time."""
    return secrets.token_urlsafe(16)


class CampaignFeed(Base, Archived):
    class Section(models.TextChoices):
        GANGS = "gangs", "Gangs"
        BATTLES = "battles", "Battles"
        ASSETS = "assets", "Assets"

    #: Where the arbitrator will show the feed. Website builders frame the
    #: feed's page; Facebook, Discord and Slack allow no frames and draw a
    #: link as a preview card instead; an RSS reader follows the battles as
    #: a news feed. ``n26.core.feeds`` says what each one is given to copy.
    class Target(models.TextChoices):
        GOOGLE_SITES = "google_sites", "Google Sites"
        SQUARESPACE = "squarespace", "Squarespace"
        WORDPRESS = "wordpress", "WordPress"
        WIX = "wix", "Wix"
        LINK_CARD = "link_card", "Facebook, Discord or Slack"
        RSS = "rss", "RSS reader"

    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="feeds"
    )
    section = models.CharField(max_length=20, choices=Section)
    #: Which asset type an Assets feed shows. Asset types differ from one
    #: campaign type to another, so a feed names one rather than a fixed
    #: section such as Territories.
    asset_type = models.ForeignKey(
        "library.AssetType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    target = models.CharField(max_length=20, choices=Target)
    token = models.CharField(
        max_length=32,
        unique=True,
        default=new_feed_token,
        editable=False,
        help_text="The random part of the feed's address.",
    )

    class Meta:
        ordering = ["created"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(section="assets", asset_type__isnull=False)
                    | (~models.Q(section="assets") & models.Q(asset_type__isnull=True))
                ),
                name="campaign_feed_asset_type_iff_assets",
            ),
            # An RSS item is an event, and only battles are a list of
            # events; a table of gangs or territories has no items to follow.
            models.CheckConstraint(
                condition=~models.Q(target="rss") | models.Q(section="battles"),
                name="campaign_feed_rss_only_for_battles",
            ),
        ]

    def __str__(self):
        return f"{self.campaign} — {self.section_label} on {self.get_target_display()}"

    @property
    def section_label(self):
        """The section as a person names it: an Assets feed goes by its
        asset type's plural, such as Territories."""
        if self.section == self.Section.ASSETS and self.asset_type is not None:
            return self.asset_type.plural
        return self.get_section_display()
