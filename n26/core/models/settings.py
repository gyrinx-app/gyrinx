"""Setting groups — small typed models carrying extra facts.

Each group is its own model with real columns and real foreign keys,
registered under a stable key. The decorator records ``group_key`` and
``applies_to`` on the class. The model must be imported from
``models/__init__.py`` or ``SETTING_GROUPS`` never sees it.

Adding a new kind of setting is a new small model plus a migration.
"""

from django.db import models

from n26.core.models.abstract import Base

SETTING_GROUPS = {}


def setting_group(key, applies_to):
    def decorate(cls):
        cls.group_key = key
        cls.applies_to = applies_to
        SETTING_GROUPS[key] = cls
        return cls

    return decorate


@setting_group("profile-role", "assignment")
class ProfileRole(Base):
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
    wants the chosen name without reverse-engineering it, and a later
    edit needs to know what it is changing from. One row per set taken.
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

    User changes go through ``op.tally``, which records a ledger event.
    Hiring and cloning also create it.
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
