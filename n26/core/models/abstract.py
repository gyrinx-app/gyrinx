from django.db import models
from django.utils import timezone

from n26.core.fields import ULIDField


class Base(models.Model):
    id = ULIDField(primary_key=True, editable=False)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    modified = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class Archived(models.Model):
    """Soft-delete flag. Nothing filters archived rows out by default;
    callers that want them hidden must ask. Subclasses may define
    ``archive_with`` — related objects archived alongside this one.
    """

    archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def archive(self):
        self.archived = True
        self.archived_at = timezone.now()
        self.save()
        for related in getattr(self, "archive_with", []):
            if hasattr(related, "archive"):
                related.archive()

    def unarchive(self):
        self.archived = False
        self.archived_at = None
        self.save()
        for related in getattr(self, "archive_with", []):
            if hasattr(related, "unarchive"):
                related.unarchive()


class Owned(models.Model):
    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=False, db_index=True
    )

    class Meta:
        abstract = True


class Rated(models.Model):
    """Pinned rating cache, rewritten at operation boundaries and checked
    by ``n26.reconcile``. Signed: a contribution can be negative, and an
    unsigned column would refuse a total the ledger already holds.
    """

    rating = models.IntegerField(
        default=0,
        help_text="Pinned. Rewritten at operation boundaries, checked by reconcile.",
    )

    class Meta:
        abstract = True

    def recompute_rating(self):
        raise NotImplementedError

    def repin_rating(self):
        self.rating = self.recompute_rating()
        self.save(update_fields=["rating", "modified"])
        return self.rating
