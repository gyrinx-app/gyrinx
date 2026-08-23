from django.db import models

from n26.core.models.abstract import Base


class Availability(models.TextChoices):
    """How widely a feature is open.

    Three states rather than a tick box, because "nobody", "a few people"
    and "everybody" are three different answers and the middle one is the
    whole point of gating something. Off wins over the allowlist, which is
    what makes it the control to reach for when a half-built screen starts
    writing bad rows.
    """

    OFF = "off", "Off — nobody, whatever the group says"
    ALLOWLIST = "allowlist", "Allowlist — whoever is in the group"
    EVERYONE = "everyone", "Everyone — any signed-in reader"


class FeatureFlag(Base):
    """A feature that is still being built, and who may reach it.

    A feature under construction ships gated: its code lands on the main
    branch like any other, but only the accounts named here can open it, so
    half a screen is never a stranger's first impression of it.

    A row per feature, edited in the admin, so opening a feature to another
    player is a change somebody makes on a page rather than a deploy. The
    two ways to move are deliberately different acts: change
    ``availability`` to open or shut the feature as a whole, or leave it on
    the allowlist and add people to the group one at a time.

    ``slug`` is what code asks for and never changes; ``name`` is what the
    admin reads. A slug with no row is treated as off, so a feature whose
    row has not been created yet fails shut rather than open.
    """

    slug = models.SlugField(
        unique=True,
        help_text="What the code asks for. Changing this turns the feature off.",
    )
    name = models.CharField(
        max_length=100,
        help_text="What this feature is called on this page.",
    )
    availability = models.CharField(
        max_length=20,
        choices=Availability,
        default=Availability.OFF,
        help_text="Off shuts the feature for everyone, the group included.",
    )
    group = models.ForeignKey(
        "auth.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="n26_feature_flags",
        help_text=(
            "Who gets the feature while it is on the allowlist. Add and "
            "remove people here or on the group itself. No group means an "
            "empty allowlist, not an open door."
        ),
    )
    note = models.TextField(
        blank=True,
        default="",
        help_text="What this feature is, for whoever finds this page later.",
    )

    class Meta:
        verbose_name = "feature flag"
        verbose_name_plural = "feature flags"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_availability_display()})"

    def open_to(self, user):
        """Whether this account may reach the feature.

        A visitor never qualifies, even where the feature is open to
        everyone: a page nobody is supposed to know about should not
        announce itself to someone who is not signed in.

        There is no bypass for staff or superusers. An account that should
        see a gated feature goes in the group, so what a person can reach
        is one question with one answer rather than two rules that drift.
        """
        if self.availability == Availability.OFF:
            return False
        if not user or not user.is_authenticated:
            return False
        if self.availability == Availability.EVERYONE:
            return True
        if self.group_id is None:
            return False
        return user.groups.filter(pk=self.group_id).exists()
