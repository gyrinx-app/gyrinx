from django.db import models
from django.utils.dateformat import format as format_date

from n26.core.models.abstract import Archived, Base, Owned


class CampaignQuerySet(models.QuerySet):
    def involving(self, user):
        """Every campaign this person arbitrates or has accepted an invitation to.

        Pending invitations are excluded. Archived campaigns are included;
        callers that want them hidden must filter ``archived=False``.
        """
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(
            models.Q(owner=user)
            | models.Q(
                participants__user=user,
                participants__state=CampaignParticipant.State.ACCEPTED,
            )
        ).distinct()


class Campaign(Base, Owned, Archived):
    """A run of linked battles, and the gangs playing them.

    The owner is the arbitrator, who sets the campaign up, decides who is in
    it, and rules on what the rulebook leaves to the players. Owning a
    campaign does not make the arbitrator the owner of the gangs in it:
    each gang stays its player's.

    Not ``Rated``: a campaign holds no assignments, so it has no rating to
    sum.

    A campaign is founded on a **campaign type** from the system pack. At
    founding it also gets a **pack** the arbitrator owns and an empty
    **additions** type in that pack. A joining gang is assigned both types,
    so the shared type's built-ins and the arbitrator's additions reach the
    gang the same way a gang type's built-ins do
    (design/campaign-assets.md). The additions type is internal: no page
    names it, and authoring lists exclude it.
    """

    class Status(models.TextChoices):
        PRE_CAMPAIGN = "pre_campaign", "Pre-campaign"
        IN_PROGRESS = "in_progress", "In progress"
        POST_CAMPAIGN = "post_campaign", "Post-campaign"

    status = models.CharField(
        max_length=20,
        choices=Status,
        default=Status.PRE_CAMPAIGN,
        help_text="The campaign's current status, set by its arbitrator.",
    )

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
    #: What the campaign was founded on. Shared with every other campaign of
    #: the type and edited by staff, so a fix to it reaches running campaigns.
    campaign_type = models.ForeignKey(
        "library.CampaignType",
        on_delete=models.PROTECT,
        related_name="campaigns",
        help_text=(
            "The campaign type this campaign was founded on. Every gang that "
            "joins is assigned this type and is given its built-ins."
        ),
    )
    #: The arbitrator's own pack, created at founding. Holds the additions
    #: type and everything the arbitrator creates for this campaign. Pack
    #: pickers offer the system pack alone, so nothing here is ever offered
    #: to another campaign or gang. Neither the pack nor the campaign can be
    #: deleted while the other stands.
    pack = models.OneToOneField(
        "library.ContentPack",
        on_delete=models.PROTECT,
        related_name="campaign",
        help_text="The pack holding what the arbitrator creates for this campaign.",
    )
    #: A second campaign type, created empty in the pack at founding and
    #: assigned to every member gang beside the shared one. What the
    #: arbitrator adds lands here, never on the shared type.
    additions = models.OneToOneField(
        "library.CampaignType",
        on_delete=models.PROTECT,
        related_name="additions_to",
        help_text=(
            "This campaign's own campaign type, holding what the arbitrator "
            "adds on top of the type the campaign was founded on."
        ),
    )
    gang_grouping = models.ForeignKey(
        "library.Slot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grouped_campaigns",
        help_text="The campaign label used to group gangs by default.",
    )
    group_colours = models.JSONField(default=dict, blank=True)
    budget = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "What a gang should be worth to join, counting its rating, stash "
            "and unspent credits. A gang worth more than this can still join. "
            "Over-budget warnings appear only while the campaign status is "
            "Pre-campaign. Leave blank for no budget."
        ),
    )
    #: The arbitrator's own words: what this campaign is, and whatever the
    #: table has agreed. Editor HTML, stored as written and sanitised on the
    #: way out (n26.core.templatetags.richtext), so a tightened allowlist
    #: reaches what was already saved.
    summary = models.TextField(blank=True, default="")
    starting_from_pool = models.BooleanField(
        default=False,
        help_text="Allocate starting territories from the existing unclaimed pool.",
    )

    objects = CampaignQuerySet.as_manager()

    class Meta:
        verbose_name = "campaign"
        verbose_name_plural = "campaigns"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CampaignEvent(Base):
    """An append-only record of one change to the campaign, and who made it.

    Only changes to the campaign itself are recorded here: setup, renames,
    budget, summary, archiving and so on. A change to a gang in the
    campaign is that gang's ledger event instead, so nothing is recorded
    twice. The campaign's log reads both.

    No display sentence is stored. The page builds the wording from the
    kind and the note, so the wording can change and the log can be
    filtered by kind.
    """

    #: Long enough for a rename: two campaign names and the arrow between
    #: them. Events are never rewritten, so a truncated note stays truncated.
    NOTE_LENGTH = 512

    class Kind(models.TextChoices):
        CREATED = "created", "Set up"
        RENAMED = "renamed", "Renamed"
        BUDGET_SET = "budget_set", "Budget set"
        SUMMARY_EDITED = "summary_edited", "Summary edited"
        STARTING_MODE_SET = "starting_mode_set", "Starting territories changed"
        STATUS_CHANGED = "status_changed", "Status changed"
        GROUPING_CHANGED = "grouping_changed", "Gang grouping changed"
        ARCHIVED = "archived", "Archived"
        DICE_ROLLED = "dice_rolled", "Dice rolled"
        DICE_ROLL_NOTED = "dice_roll_noted", "Dice roll noted"
        BATTLE_RECORDED = "battle_recorded", "Battle recorded"
        BATTLE_EDITED = "battle_edited", "Battle edited"
        BATTLE_REMOVED = "battle_removed", "Battle removed"
        BATTLE_ARCHIVED = "battle_archived", "Battle archived"
        BATTLE_RESTORED = "battle_restored", "Battle restored"
        INVITED = "invited", "Invited a player"
        INVITE_ACCEPTED = "invite_accepted", "Invitation accepted"
        INVITE_DECLINED = "invite_declined", "Invitation declined"
        PLAYER_REMOVED = "player_removed", "Player removed"
        PLAYER_LEFT = "player_left", "Player left"
        # The campaign's assets changing with no gang touched. An asset
        # assigned to a gang or unassigned from one changes the gang, and
        # is that gang's ledger event instead.
        ASSET_ADDED = "asset_added", "Asset added"
        ASSET_EDITED = "asset_edited", "Asset edited"
        ASSET_REMOVED = "asset_removed", "Asset removed"
        # A roll for an asset table. The note names the asset it adds, so no
        # separate ASSET_ADDED is written. A roll for a gang also assigns
        # the asset, which is recorded as that gang's ledger event.
        ASSET_ROLLED = "asset_rolled", "Rolled"
        # Content the arbitrator wrote into the campaign's own pack and
        # onto its additions type. What a member gang then receives is
        # that gang's ledger event, as every built-in is.
        ASSET_TYPE_ADDED = "asset_type_added", "Asset type added"
        ASSET_TYPE_EDITED = "asset_type_edited", "Asset type edited"
        ASSET_CREATED = "asset_created", "Asset created"
        COUNTER_ADDED = "counter_added", "Counter added"
        LABEL_ADDED = "label_added", "Label added"
        # A counter or label the arbitrator added, taken off every gang.
        # Each gang's removal is that gang's ledger event, written under
        # the same mark, so the log shows the archive as this one line.
        COUNTER_ARCHIVED = "counter_archived", "Counter archived"
        LABEL_ARCHIVED = "label_archived", "Label archived"
        # The same counter or label given back to every gang still in the
        # campaign, each gang's restoration written under the same mark.
        COUNTER_UNARCHIVED = "counter_unarchived", "Counter unarchived"
        LABEL_UNARCHIVED = "label_unarchived", "Label unarchived"
        # Changes to the asset tables available to every gang in the
        # campaign beyond its type's own: a table added to the campaign's
        # additions, removed from them, or created for this campaign.
        TABLE_OPENED = "table_opened", "Table opened"
        TABLE_CLOSED = "table_closed", "Table closed"
        TABLE_CREATED = "table_created", "Table created"
        # The note stores the scenario name and component values.
        # Recording a battle with a scenario is BATTLE_RECORDED.
        SCENARIO_SAVED = "scenario_saved", "Scenario saved"

    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.CASCADE,
        related_name="events",
    )
    kind = models.CharField(max_length=20, choices=Kind)
    #: Who made the change. SET_NULL so deleting an account keeps the
    #: campaign's history.
    actor = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: The person the change was about, if any. Only the link is stored; the
    #: page looks up the name when it renders, as for every name in the log.
    about_user = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: The battle the change was about, if any. SET_NULL: if the battle is
    #: deleted, the line still says a battle was recorded but links nowhere.
    battle = models.ForeignKey(
        "n26.Battle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    roll = models.ForeignKey(
        "n26.CampaignRoll",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    #: Detail the kind cannot carry: "1000 → 1200" for a budget, both names
    #: for a rename. Figures are stored bare and formatted when the page
    #: renders. A summary edit does not store the summary's text.
    note = models.CharField(max_length=NOTE_LENGTH, blank=True)
    #: Shared by every event one change wrote, such as three fields saved in
    #: one submit, so the log can show them as one change.
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
    """One gang's time in one campaign.

    A database constraint allows one open membership per gang, so a gang is
    in at most one campaign at a time. Leaving sets ``left`` instead of
    deleting the membership, so the gang keeps a record of past campaigns.

    ``created`` is when the gang joined; ``left`` is when it left, and is
    null while it is still playing.

    Joining assigns the campaign's two types to the gang, and the two
    **carriers** point at those assignments, as ``Gang.founding`` points at
    the founding assignment. Everything the gang has from the campaign, such
    as its Settlement or Reputation counter, is caused by one of them. The
    card can then show where each came from, and leaving removes them all
    at once.
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
    #: When the gang left. Null while it is still playing; the one-open
    #: constraint counts only null rows.
    left = models.DateTimeField(null=True, blank=True)
    #: The gang-hosted assignment naming the campaign's shared type.
    #: What the type gives every member gang is caused by it.
    type_carrier = models.OneToOneField(
        "n26.Assignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="type_carrier_of",
        help_text=(
            "The gang's assignment of the campaign's type. The type's "
            "built-ins on this gang are caused by it."
        ),
    )
    #: The gang-hosted assignment naming the campaign's additions type.
    #: What the arbitrator adds is caused by it.
    additions_carrier = models.OneToOneField(
        "n26.Assignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="additions_carrier_of",
        help_text=(
            "The gang's assignment of the campaign's own campaign type. What "
            "the arbitrator adds to this campaign is caused by it."
        ),
    )

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
        return self.left is None


class CampaignAsset(Base):
    """One of a campaign's assets, and the gang that holds it.

    Only assets of a Holding asset type are recorded here. A **holding**
    belongs to the campaign; a gang only holds it, and ``holder`` says
    which. The holding itself is not assigned to the gang, and the gang's
    rating never counts it. Assigning, unassigning and handing over change
    ``holder`` under the campaign's lock and write an event on each gang
    involved (design/campaign-assets.md). Gaining a holding can also fill
    its required slots with default picks
    (``Operation._default_holding_picks``), which are ordinary assignments.

    ``holder`` is a membership, not a gang, so an asset cannot point at a
    gang that has left the campaign. ``name`` optionally renames the asset
    in this campaign ("the Old Ruins by the sump") and is shown instead of
    the library asset's name.

    While held, a holding adds computed effects to its holder's card,
    credited to this asset. What a stored effect does on assignment is
    decided by the code that makes assignments.
    """

    #: Where the effects engine finds a campaign asset's modifiers: on the
    #: library asset it stands for, supplemented by an optional income override.
    carries_modifiers_of = "asset"

    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.CASCADE,
        related_name="campaign_assets",
    )
    asset = models.ForeignKey(
        "library.Asset",
        on_delete=models.PROTECT,
        related_name="campaign_assets",
        help_text="Which asset in the library this is.",
    )
    #: SET_NULL when the membership is deleted. Apart from unassigning, that
    #: is the only way ``holder`` becomes null.
    holder = models.ForeignKey(
        "n26.CampaignMembership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="held",
        help_text="The gang holding this asset. Blank when nobody holds it.",
    )
    ownership_revision = models.PositiveIntegerField(default=0)
    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "A name for this asset in this campaign. Leave blank to use the "
            "asset's own name."
        ),
    )

    income_override = models.ForeignKey(
        "library.Modifier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="The income contribution used for this holding instead of its catalogue income.",
    )

    class Meta:
        verbose_name = "campaign asset"
        verbose_name_plural = "campaign assets"
        ordering = ["asset__asset_type__position", "asset__name", "name", "created"]
        indexes = [
            models.Index(
                fields=["campaign", "holder"], name="campaign_asset_holder_idx"
            ),
        ]

    def __str__(self):
        return self.name or str(self.asset)

    @property
    def held(self):
        """Whether a gang still playing holds this asset."""
        return self.holder is not None and self.holder.playing

    @property
    def type_label(self):
        return self.asset.asset_type.label_singular.lower()


class Battle(Base, Archived):
    """A campaign battle and its result, separate from changes to the gangs."""

    class Result(models.TextChoices):
        NOT_RECORDED = "not_recorded", "Not recorded"
        DRAW = "draw", "Draw"
        WINNERS = "winners", "Winner or winners"

    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.CASCADE,
        related_name="battles",
    )
    #: The date the battle was played, as the players enter it, not when it
    #: was recorded.
    date = models.DateField()
    # An unnamed record is valid; entry forms require a scenario name.
    scenario = models.CharField(max_length=200, blank=True, default="")
    #: What each scenario generator table landed on, as ``{key: roll}``,
    #: for the tables the battle was played with. Empty when the scenario
    #: was not generated. Only the rolls are stored; the battle's page
    #: looks each entry up through ``n26.core.scenarios``.
    scenario_rolls = models.JSONField(default=dict, blank=True)
    result = models.CharField(
        max_length=20, choices=Result, default=Result.NOT_RECORDED
    )
    revision = models.PositiveIntegerField(default=0)
    gangs = models.ManyToManyField(
        "n26.Gang",
        related_name="battles",
        blank=True,
    )
    winners = models.ManyToManyField("n26.Gang", related_name="battles_won", blank=True)

    class Meta:
        verbose_name = "battle"
        verbose_name_plural = "battles"
        ordering = ["-date", "-created"]
        indexes = [
            models.Index(fields=["campaign", "-date"], name="battle_by_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(result__in=["not_recorded", "draw", "winners"]),
                name="battle_result_is_known",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def title(self):
        return self.scenario or f"Battle on {format_date(self.date, 'j M Y')}"

    @property
    def gang_outcomes(self):
        """Each participant with whether it won, by name.

        Reads ``gangs`` and ``winners`` through ``.all()`` so a list that
        prefetched both asks nothing more per battle.
        """
        won = {gang.pk for gang in self.winners.all()}
        return [
            (gang, gang.pk in won)
            for gang in sorted(self.gangs.all(), key=lambda gang: gang.name.lower())
        ]

    @property
    def result_label(self):
        if self.result == self.Result.WINNERS:
            return "Won by " + ", ".join(gang.name for gang in self.winners.all())
        return self.get_result_display()

    @classmethod
    def validate_outcome(cls, *, result, gangs, winners):
        from django.core.exceptions import ValidationError

        if result not in cls.Result.values:
            raise ValidationError({"result": "Select an outcome."})
        if result == cls.Result.WINNERS and not winners:
            raise ValidationError({"winners": "Select at least one winning gang."})
        if result != cls.Result.WINNERS and winners:
            raise ValidationError(
                {
                    "winners": "Clear the winners for a draw or an outcome not yet recorded."
                }
            )
        if {gang.pk for gang in winners} - {gang.pk for gang in gangs}:
            raise ValidationError({"winners": "Every winner must be a participant."})


class BattleStake(Base):
    """A campaign asset staked in a battle, and the gang it goes to.

    A battle can stake several assets, and each goes to its own gang. Only
    the arbitrator sets them, and the holder is always read from the asset.
    """

    battle = models.ForeignKey(
        "n26.Battle",
        on_delete=models.CASCADE,
        related_name="stakes",
    )
    asset = models.ForeignKey(
        "n26.CampaignAsset",
        on_delete=models.CASCADE,
        related_name="battle_stakes",
    )
    #: The participant the asset goes to. Blank leaves it with its holder
    #: or in the unclaimed pool.
    awarded_to = models.ForeignKey(
        "n26.Gang",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stakes_awarded",
    )
    #: The ledger batch recording this award. An unclaimed asset has only a
    #: GAINED event. When set, the asset has moved, so saving again does not
    #: move it twice; a correction reverses the transfer first.
    transfer_mark = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "battle stake"
        verbose_name_plural = "battle stakes"
        ordering = ["created", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "asset"],
                name="battle_stake_one_per_asset",
            ),
        ]

    def __str__(self):
        return str(self.asset)


class CampaignParticipant(Base):
    """A person the arbitrator has invited to a campaign, and their response.

    A participant is a person, not a gang. Which gangs they bring is
    recorded separately (``CampaignMembership``). There is one participant
    per person per campaign, so re-inviting someone who declined reuses the
    same participant.

    The arbitrator owns the campaign and is not a participant. An accepted
    participant is a member of the campaign and nothing more; invited and
    declined participants are not members. The campaign's views decide
    what a member may do.
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
    #: The arbitrator's invitation message, shown to the invitee and never
    #: rewritten.
    message = models.TextField(blank=True, default="")
    #: Who sent the invitation. SET_NULL keeps the invitation when that
    #: account is deleted.
    invited_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: When the invitee accepted or declined. Null while the invitation is
    #: pending.
    answered = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "player"
        verbose_name_plural = "players"
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
        return self.state == self.State.INVITED

    def get_absolute_url(self):
        """The invited campaign's page, which notifications about this
        invitation link to. The campaign's views decide who may open it.
        """
        from django.urls import reverse

        return reverse("n26-campaign", args=[self.campaign_id])
