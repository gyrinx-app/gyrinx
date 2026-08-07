"""Setting groups — small typed models carrying extra facts.

Each group is its own model with real columns and real foreign keys, rather
than a bag of JSON, so values can point at other rows and be queried in SQL.
A group registers under a stable key; an ``AssignableType`` declares which
keys apply to its assignables and assignments.

Adding a new kind of setting is a new small model plus a migration.
"""

from django.db import models

from n26.core.models.abstract import Base

#: group key -> model class
SETTING_GROUPS = {}


def setting_group(key, applies_to):
    """Register a setting-group model under a stable key."""

    def decorate(cls):
        cls.group_key = key
        cls.applies_to = applies_to
        SETTING_GROUPS[key] = cls
        return cls

    return decorate


@setting_group("profile-role", "assignment")
class ProfileRole(Base):
    """Whether a profile assignment is the model's primary one or a legacy."""

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        LEGACY = "legacy", "Legacy"

    assignment = models.OneToOneField(
        "n26.Assignment", on_delete=models.CASCADE, related_name="profile_role"
    )
    role = models.CharField(max_length=20, choices=Role, default=Role.PRIMARY)

    class Meta:
        verbose_name = "profile role"
        verbose_name_plural = "profile roles"

    def __str__(self):
        return f"{self.assignment.assignable}: {self.get_role_display()}"


@setting_group("chosen-option", "assignment")
class ChosenProfileOption(Base):
    """One option a hire took, recorded on the membership.

    Derivable from which default assignments exist, but stored: display
    wants "Khimerix (razor-sharp talons)" without reverse-engineering it,
    and a later edit needs to know what it is changing from. One row per
    set taken — a profile with several option groups records several.
    """

    assignment = models.ForeignKey(
        "n26.Assignment", on_delete=models.CASCADE, related_name="chosen_options"
    )
    default_set = models.ForeignKey(
        "library.DefaultAssignmentSet", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name = "chosen option"
        verbose_name_plural = "chosen options"
        constraints = [
            models.UniqueConstraint(
                "assignment", "default_set", name="chosen_option_unique"
            ),
        ]

    def __str__(self):
        return str(self.default_set)


@setting_group("counter-value", "assignment")
class CounterValue(Base):
    """The running value of one counter assignment.

    The first mutable player-side number on an assignment. Written only
    by ``op.tally``, which records a ledger event per change — the
    spend-with-audit discipline, on the one ledger.
    """

    assignment = models.OneToOneField(
        "n26.Assignment", on_delete=models.CASCADE, related_name="counter_value"
    )
    value = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "counter value"
        verbose_name_plural = "counter values"

    def __str__(self):
        return f"{self.assignment.assignable}: {self.value}"
