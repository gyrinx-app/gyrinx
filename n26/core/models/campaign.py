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
            "What a gang founded for this campaign has to spend on models and "
            "gear. Whatever is left goes to its stash, so this is what a gang "
            "is worth on the day it starts. Null means the campaign sets none."
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

    #: Long enough for a rename, which holds two campaign names and the mark
    #: between them. Nothing here is ever rewritten, so a note cut short stays
    #: cut short, and a reader is left with half a name for good.
    NOTE_LENGTH = 512

    class Kind(models.TextChoices):
        CREATED = "created", "Set up"
        RENAMED = "renamed", "Renamed"
        BUDGET_SET = "budget_set", "Budget set"
        SUMMARY_EDITED = "summary_edited", "Summary edited"
        ARCHIVED = "archived", "Archived"
        BATTLE_RECORDED = "battle_recorded", "Battle recorded"
        BATTLE_REMOVED = "battle_removed", "Battle removed"
        INVITED = "invited", "Invited somebody"
        INVITE_ACCEPTED = "invite_accepted", "Invitation accepted"
        INVITE_DECLINED = "invite_declined", "Invitation declined"
        PARTICIPANT_REMOVED = "participant_removed", "Participant removed"

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
    #: The person an act was about, where it was about one. Kept as a plain
    #: link: the name a line reads is looked up when the page is drawn, as
    #: every other name here is.
    about_user = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: The battle an act was about, where it was about one. Set to nothing if
    #: the battle goes, which leaves the line saying a battle was recorded
    #: without offering a page that is not there.
    battle = models.ForeignKey(
        "n26.Battle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: What changed, where the kind alone cannot say it: "1000 → 1200" for a
    #: budget, the two names for a rename. Figures are stored bare and given
    #: their mark when the page is drawn. Never the summary's own words — the
    #: log is a list of acts, not a copy of the arbitrator's prose.
    note = models.CharField(max_length=NOTE_LENGTH, blank=True)
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


class CampaignMembership(Base):
    """One gang's place in one campaign, for as long as it lasts.

    A gang is in at most one campaign at a time, and the database holds it to
    that: only one membership per gang may be open. Leaving closes the one it
    has rather than deleting it, so a gang that plays a campaign, leaves, and
    joins another still says what it did and when.

    ``created`` is when the gang joined; ``left`` is when it stopped, and is
    unset while it is still playing. A campaign never writes to a gang, so
    this row is the whole of what being in one means.
    """

    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    gang = models.ForeignKey(
        "n26.Gang",
        on_delete=models.CASCADE,
        related_name="campaign_memberships",
    )
    #: When the gang stopped playing. Unset while it still is, which is what
    #: the one-at-a-time constraint counts.
    left = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "campaign membership"
        verbose_name_plural = "campaign memberships"
        ordering = ["created"]
        constraints = [
            models.UniqueConstraint(
                fields=["gang"],
                condition=models.Q(left__isnull=True),
                name="campaign_membership_one_open_per_gang",
            ),
        ]
        indexes = [
            models.Index(
                fields=["campaign", "left"], name="campaign_membership_roll_idx"
            ),
        ]

    def __str__(self):
        return f"{self.gang} in {self.campaign}"

    @property
    def playing(self):
        """Whether the gang is still in the campaign."""
        return self.left is None


class Battle(Base):
    """One battle fought in a campaign: when, and who was in it.

    Deliberately little. What a battle *did* — who won, what it dealt out,
    what changed hands — is recorded against the gangs it happened to, in
    their own ledgers, each event naming this battle. The row itself is only
    the occasion those records hang from, so nothing here has to be kept in
    step with them.

    A gang in the fight need not still be in the campaign: a battle is a thing
    that happened, and stays true after a gang leaves.
    """

    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.CASCADE,
        related_name="battles",
    )
    #: When it was fought, which is the players' own date rather than when
    #: somebody got round to writing it down.
    date = models.DateField()
    gangs = models.ManyToManyField(
        "n26.Gang",
        related_name="battles",
        blank=True,
    )

    class Meta:
        verbose_name = "battle"
        verbose_name_plural = "battles"
        ordering = ["-date", "-created"]
        indexes = [
            models.Index(fields=["campaign", "-date"], name="battle_by_date_idx"),
        ]

    def __str__(self):
        return f"Battle on {self.date} in {self.campaign}"


class CampaignParticipant(Base):
    """One person the arbitrator has asked into a campaign, and their answer.

    Being a participant is about the *person*, not their gangs: an invitation
    says somebody is at this table, and which gangs they bring is a separate
    question the campaign answers elsewhere. So there is one row per person
    per campaign, and inviting somebody who has already declined asks the same
    row again rather than starting a second conversation.

    The arbitrator owns the campaign and is not a participant of it. Being
    one grants membership and nothing else: what a participant may do is a
    question their campaign's own screens answer.
    """

    class State(models.TextChoices):
        INVITED = "invited", "Invited"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="n26_campaign_participations",
    )
    state = models.CharField(max_length=20, choices=State, default=State.INVITED)
    #: What the arbitrator said when they asked. Theirs, not ours: shown to
    #: the person invited and never rewritten.
    message = models.TextField(blank=True, default="")
    #: Who asked. Kept when the account goes, because the invitation is a
    #: record of what happened rather than of who is still here.
    invited_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: When they answered, either way. Unset while the question stands.
    answered = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "campaign participant"
        verbose_name_plural = "campaign participants"
        ordering = ["created"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "user"],
                name="campaign_participant_one_per_person",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "state"], name="campaign_participant_inbox_idx"
            ),
        ]

    def __str__(self):
        return f"{self.user} in {self.campaign}"

    @property
    def waiting(self):
        """Whether the question still stands."""
        return self.state == self.State.INVITED

    def get_absolute_url(self):
        """The campaign this invitation is to.

        What a notification about it points at, because the campaign is what
        somebody asked into one wants to look at. Who may open that page is
        the campaign's own question, answered by its views.
        """
        from django.urls import reverse

        return reverse("n26-campaign", args=[self.campaign_id])
