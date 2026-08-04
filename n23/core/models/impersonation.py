from django.db import models

from n23.core.models.base import AppBase

__all__ = ["ImpersonationLog"]


class ImpersonationLog(AppBase):
    """Audit record of an admin impersonation session.

    ``owner`` (inherited from :class:`~gyrinx.models.Owned`) is the impersonator —
    the admin who started the session. ``target`` is the user who was impersonated.
    ``created`` marks the start; ``ended_at`` / ``ended_reason`` are filled in when
    the session stops (manually, on logout, on timeout, or when it is revoked
    automatically because the admin lost privileges or the target went away).

    This is an append-only audit log — like :class:`~n23.core.models.events.Event`
    it does not declare ``HistoricalRecords``.
    """

    class EndedReason(models.TextChoices):
        MANUAL = "manual", "Stopped manually"
        LOGOUT = "logout", "Logged out"
        EXPIRED = "expired", "Timed out"
        REVOKED = "revoked", "Ended automatically"

    target = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="impersonated_by_sessions",
        help_text="The user who was impersonated.",
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the impersonation session ended (null while active).",
    )
    ended_reason = models.CharField(
        max_length=20,
        choices=EndedReason.choices,
        blank=True,
        help_text="Why the impersonation session ended.",
    )

    class Meta:
        verbose_name = "impersonation log"
        verbose_name_plural = "impersonation logs"
        ordering = ["-created"]

    @property
    def impersonator(self):
        """Alias for ``owner`` — the admin who started the session."""
        return self.owner

    def __str__(self):
        state = "active" if self.ended_at is None else self.ended_reason
        return f"{self.owner} → {self.target} ({state})"
