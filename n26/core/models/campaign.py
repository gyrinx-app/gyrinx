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


class CampaignEvent(Base):
    """One append-only record of a change to the campaign, with who made it.

    The campaign's own acts and no others: set up, renamed, its budget
    changed, its summary edited, archived. What happens to a *gang* in a
    campaign belongs to that gang's ledger instead, so one question decides
    where anything is written — did a gang change? Nothing is recorded twice,
    and the campaign's log is read from both.

    No sentence is stored. What a reader sees is built when the page is drawn,
    from the kind and the note, so the wording stays something we can change
    and the log stays something that can be filtered by what happened rather
    than by what it happened to say.
    """

    class Kind(models.TextChoices):
        CREATED = "created", "Set up"
        RENAMED = "renamed", "Renamed"
        BUDGET_SET = "budget_set", "Budget set"
        SUMMARY_EDITED = "summary_edited", "Summary edited"
        ARCHIVED = "archived", "Archived"

    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.CASCADE,
        related_name="events",
    )
    kind = models.CharField(max_length=20, choices=Kind)
    #: Who did this. Kept when the account goes, because the campaign's log is
    #: a record of what happened to it rather than of who is still here.
    actor = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: What changed, where the kind alone cannot say it: "1000 → 1200" for a
    #: budget, the two names for a rename. Figures are stored bare and given
    #: their mark when the page is drawn. Never the summary's own words — the
    #: log is a list of acts, not a copy of the arbitrator's prose.
    note = models.CharField(max_length=255, blank=True)
    #: One mark per act, shared by every event that act wrote. Events sharing
    #: a mark were written together — three fields changed on one submit — so
    #: what was one act stays recognisable as one.
    batch = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "campaign event"
        verbose_name_plural = "campaign events"
        ordering = ["created"]
        indexes = [
            models.Index(fields=["campaign", "created"], name="campaign_event_log_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.campaign}"
