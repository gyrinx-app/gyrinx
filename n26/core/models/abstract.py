"""
Shared abstract models.

These are deliberately small and composable. Concrete models mix in whichever
they need, e.g.::

    class Thing(Base, Owned, Archived):
        ...

Ported from ``gyrinx/models.py``.
"""

from django.db import models
from django.utils import timezone

from n26.core.fields import ULIDField


class Base(models.Model):
    """Identity and timestamps. Everything persistent inherits this."""

    id = ULIDField(primary_key=True, editable=False)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    modified = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class Archived(models.Model):
    """An Archived object is no longer in use.

    Archiving is a soft delete: archived rows stay readable and nothing filters
    them out by default. Callers that want to hide archived rows must say so
    explicitly — see the note on default-open filtering in
    ``library/models/base.py``.

    Subclasses may define an ``archive_with`` property returning related
    objects that should be archived alongside this one.
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
    """An Owned object is owned by a User."""

    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=False, db_index=True
    )

    class Meta:
        abstract = True


class Rated(models.Model):
    """Something with a pinned rating — a sum of what it and its parts are
    worth.

    The number is a cache. It is rewritten at the end of every operation
    that touches the thing (see ``n26.operations``), and ``n26.reconcile``
    proves it still matches a fresh recompute. Subclasses say what the sum
    is over.
    """

    rating = models.PositiveIntegerField(
        default=0,
        help_text="Pinned. Rewritten at operation boundaries, checked by reconcile.",
    )

    class Meta:
        abstract = True

    def recompute_rating(self):
        """The rating, summed fresh from the ledger. Subclasses implement."""
        raise NotImplementedError

    def repin_rating(self):
        self.rating = self.recompute_rating()
        self.save(update_fields=["rating", "modified"])
        return self.rating
