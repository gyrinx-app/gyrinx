from django.db import models

from n26.core.models.abstract import Archived, Base, Owned


class Campaign(Base, Owned, Archived):
    """A run of linked battles, and the gangs playing them.

    The owner is the arbitrator: the person who sets the campaign up, says
    who is in it, and settles what the book leaves to a table. Owning a
    campaign is not owning the gangs in it — each of those stays its own
    player's, and a campaign never writes to one.

    Deliberately not ``Rated``. A campaign holds no assignments, so there is
    nothing for a rating to sum; what it is worth is not a question anybody
    asks of it.
    """

    #: Named here rather than taken from ``Owned`` because the other edition
    #: has a Campaign too, and two models of the same name would claim the
    #: same reverse accessor on the user.
    owner = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        null=True,
        blank=False,
        db_index=True,
        related_name="n26_campaigns",
    )
    name = models.CharField(max_length=200)
    budget = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "What a gang may spend to join, where the campaign says. Null "
            "means no ceiling — gangs enter at whatever they are worth."
        ),
    )
    #: The arbitrator's own words: what this campaign is, and whatever the
    #: table has agreed. Editor HTML, stored as written and sanitised on the
    #: way out (n26.core.templatetags.richtext), so a tightened allowlist
    #: reaches what was already saved.
    summary = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "campaign"
        verbose_name_plural = "campaigns"
        ordering = ["name"]

    def __str__(self):
        return self.name
