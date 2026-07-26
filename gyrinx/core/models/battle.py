from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase
from gyrinx.core.models.state_machine import StateMachine

User = get_user_model()


class Battle(AppBase):
    """
    Battle model to track battles that occur within a campaign.

    A battle moves through a simple lifecycle (pre-battle -> in-progress ->
    post-battle) so the app can guide players through setup and resolution. The
    state machine is forward-only.
    """

    # Convenience constants for the state machine values.
    PRE_BATTLE = "pre_battle"
    IN_PROGRESS = "in_progress"
    POST_BATTLE = "post_battle"

    # How the battle finished. Blank is a distinct third state from "draw":
    # it means nobody recorded a result, which is what every battle ended
    # before this field existed looks like. Without it, an empty ``winners``
    # would be indistinguishable from a genuine draw.
    RESULT_UNRECORDED = ""
    RESULT_WINNERS = "winners"
    RESULT_DRAW = "draw"
    RESULT_CHOICES = [
        (RESULT_WINNERS, "Win"),
        (RESULT_DRAW, "Draw"),
    ]

    states = StateMachine(
        states=[
            (PRE_BATTLE, "Pre-battle"),
            (IN_PROGRESS, "In progress"),
            (POST_BATTLE, "Post-battle"),
        ],
        initial=PRE_BATTLE,
        transitions={
            PRE_BATTLE: [IN_PROGRESS],
            IN_PROGRESS: [POST_BATTLE],
            POST_BATTLE: [],
        },
    )

    campaign = models.ForeignKey(
        "core.Campaign",
        on_delete=models.CASCADE,
        related_name="battles",
        help_text="The campaign this battle belongs to",
        db_index=True,
    )
    date = models.DateField(
        null=True,
        blank=True,
        help_text="The date of the battle (leave blank until it is scheduled or played)",
        db_index=True,
    )
    mission = models.CharField(
        max_length=200,
        help_text="The mission name or type",
    )
    participants = models.ManyToManyField(
        "core.List",
        through="core.BattleParticipant",
        related_name="battles_participated",
        help_text="Gangs taking part in the battle",
    )
    winners = models.ManyToManyField(
        "core.List",
        related_name="battles_won",
        blank=True,
        help_text="Gangs that won the battle (leave empty for a draw)",
    )
    result = models.CharField(
        max_length=20,
        blank=True,
        default=RESULT_UNRECORDED,
        choices=RESULT_CHOICES,
        help_text="How the battle finished. Blank means no result was recorded.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date", "-created"]
        indexes = [
            models.Index(fields=["campaign", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return self.name

    @cached_property
    def name(self):
        """Computed display name: the mission and date, with a disambiguating
        ordinal only when it is needed.

        The ordinal used to be a campaign-wide sequence, so "Border Dispute
        2026-07-19 #7" meant "the campaign's 7th battle" but read as "the 7th
        Border Dispute". It now counts only within the group it disambiguates
        — battles of the same mission on the same date in the same campaign —
        and is left off entirely when the mission and date are already unique.
        """
        base = f"{self.mission} {self.date}" if self.date is not None else self.mission

        if self.created is None:  # unsaved: nothing to compare against
            return base

        # One query for the whole group, this battle included. ``date=None``
        # becomes IS NULL, so undated battles group with each other rather
        # than with dated ones. Archived siblings still count, so archiving
        # one battle doesn't silently rename another. Groups are small — a
        # handful of battles share a mission and date at most.
        siblings = list(
            # campaign_id, not self.campaign: reading the FK would fetch the
            # campaign for any battle not loaded with select_related, which is
            # how battle names get rendered in the campaign action log.
            Battle.objects.filter(
                campaign_id=self.campaign_id, mission=self.mission, date=self.date
            ).values_list("created", "pk")
        )
        if len(siblings) <= 1:
            return base

        # Rank by (created, pk): the pk breaks ties, so two battles saved in
        # the same instant still get distinct, stable ordinals.
        key = (self.created, self.pk)
        ordinal = sum(1 for sibling in siblings if sibling < key) + 1
        return f"{base} #{ordinal}"

    @property
    def result_recorded(self):
        """Whether anyone has said how this battle finished."""
        return self.result != self.RESULT_UNRECORDED

    @property
    def is_draw(self):
        """Whether the battle was explicitly recorded as a draw."""
        return self.result == self.RESULT_DRAW

    def can_edit(self, user):
        """
        Check if a user can edit this battle's details (date, mission,
        participants, winners) or archive it. Only the battle owner or a campaign
        admin (arbitrator) can. Not allowed if the battle or campaign is
        archived.
        """
        if not user or not user.is_authenticated:
            return False
        if self.archived or self.campaign.archived:
            return False
        return user == self.owner or self.campaign.is_admin(user)

    def can_manage(self, user):
        """
        Check if a user can run the battle flow: advance its state and assign
        participant roles. Allowed for the battle owner, campaign admins, and
        any gang owner taking part in the battle. Not allowed if the battle or
        campaign is archived.
        """
        if not user or not user.is_authenticated:
            return False
        if self.archived or self.campaign.archived:
            return False
        if user == self.owner or self.campaign.is_admin(user):
            return True
        # Owners of participating gangs can also manage the battle.
        return self.participants.filter(owner=user).exists()

    def can_add_notes(self, user):
        """
        Check if a user can add a battle report. Same set of people who can
        manage the battle (editors and participant gang owners).
        """
        return self.can_manage(user)

    def can_unarchive(self, user):
        """
        Check if a user can unarchive this battle. Only the battle owner or
        a campaign admin, and only while the campaign itself is not archived.
        """
        if not user or not user.is_authenticated:
            return False
        if not self.archived or self.campaign.archived:
            return False
        return user == self.owner or self.campaign.is_admin(user)

    def can_start(self):
        """Whether the battle can move from pre-battle to in-progress."""
        return self.states.current == self.PRE_BATTLE

    def can_end(self):
        """Whether the battle can move from in-progress to post-battle."""
        return self.states.current == self.IN_PROGRESS

    def has_ended(self):
        """Whether the battle has reached its post-battle state.

        This is the state check, not ``result_recorded``: it says the battle is
        over, not that a winner was chosen — a draw, or a legacy battle with no
        recorded result, is still "ended". The played-rating freeze happens at
        the end of the battle, so a crew confirmed *after* this point — recorded
        after the fact — has to freeze what it fielded at lock time instead (see
        ``handle_crew_lock``).
        """
        return self.states.current == self.POST_BATTLE

    def get_actions(self):
        """Get all campaign actions associated with this battle."""
        return self.campaign.actions.filter(battle=self)

    def participant_entries_with_roles(self):
        """
        BattleParticipant rows for this battle, with the gang and role option
        preloaded, ordered for display.
        """
        # owner__profile, not just owner: the participants pane renders
        # {% user_badge %} per row, and that tag reads the profile — one query
        # per gang without it (see badge_tags.user_badge).
        return self.participant_entries.select_related(
            "list",
            "list__owner",
            "list__owner__profile",
            "role_option",
            "role_option__role",
        )

    def set_participants(self, lists):
        """
        Replace the battle's participants with the given gangs, keeping the
        roles of any gangs that remain. Adds rows for new gangs and removes
        rows for gangs no longer taking part.
        """
        wanted = list(lists)
        wanted_ids = {lst.pk for lst in wanted}
        existing = {bp.list_id: bp for bp in self.participant_entries.all()}

        for list_id, bp in existing.items():
            if list_id not in wanted_ids:
                bp.delete()

        for lst in wanted:
            if lst.pk not in existing:
                BattleParticipant.objects.create(
                    battle=self, list=lst, owner=self.owner
                )

    def participants_grouped_by_role(self):
        """
        Participant entries grouped by role option, for display. Returns a list
        of dicts ``{"role_option": option_or_None, "participants": [...]}``,
        with named roles first (by name) and any unassigned gangs last.
        """
        groups = {}
        order = []
        for bp in self.participant_entries_with_roles():
            key = bp.role_option_id
            if key not in groups:
                groups[key] = {"role_option": bp.role_option, "participants": []}
                order.append(key)
            groups[key]["participants"].append(bp)

        result = [groups[key] for key in order]
        result.sort(
            key=lambda g: (
                g["role_option"] is None,
                g["role_option"].name if g["role_option"] else "",
            )
        )
        return result


class BattleParticipant(AppBase):
    """
    Through model linking a :model:`core.Battle` to a participating gang
    (:model:`core.List`), with an optional role such as Attacker or Defender.
    """

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="participant_entries",
        help_text="The battle this participant belongs to",
    )
    list = models.ForeignKey(
        "core.List",
        on_delete=models.CASCADE,
        related_name="battle_participations",
        help_text="The participating gang",
    )
    role_option = models.ForeignKey(
        "content.ContentBattleRoleOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="battle_participants",
        help_text="The role this gang took in the battle (e.g. Attacker or Defender)",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["role_option__name", "created"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "list"], name="unique_battle_participant"
            )
        ]

    def __str__(self):
        return f"{self.list} in {self.battle}"


class BattleNote(AppBase):
    """
    Notes added to a battle by different users.
    """

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="notes",
        help_text="The battle this note belongs to",
    )
    content = models.TextField(
        help_text="Note content (supports rich text formatting)",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["created"]
        indexes = [
            models.Index(fields=["battle", "created"]),
        ]

    def __str__(self):
        return f"Note by {self.owner} on {self.battle}"

    def can_edit(self, user):
        """
        Check if a user can edit this note.
        Only the note owner can edit their own notes.
        """
        if not user or not user.is_authenticated:
            return False
        return user == self.owner
