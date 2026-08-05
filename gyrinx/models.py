"""Platform base models and generic helpers.

Abstract bases shared by every app — platform and edition alike. Game concepts
that used to live here (fighter categories, the cost mixins, credit formatting)
moved to ``n23.models``: they are edition vocabulary, not infrastructure.
"""

import logging
import uuid
from typing import List, TypeVar, Union
from uuid import UUID

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone

logger = logging.getLogger(__name__)


SMART_QUOTES = {
    "LEFT_DOUBLE": chr(0x201C),  # " LEFT DOUBLE QUOTATION MARK
    "RIGHT_DOUBLE": chr(0x201D),  # " RIGHT DOUBLE QUOTATION MARK
    "LEFT_SINGLE": chr(0x2018),  # ' LEFT SINGLE QUOTATION MARK
    "RIGHT_SINGLE": chr(0x2019),  # ' RIGHT SINGLE QUOTATION MARK
}


def is_int(value):
    """Check if a value is a number."""
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def is_valid_uuid(uuid_to_test, version=4):
    """
    Check if uuid_to_test is a valid UUID.

     Parameters
    ----------
    uuid_to_test : str
    version : {1, 2, 3, 4}

     Returns
    -------
    `True` if uuid_to_test is a valid UUID, otherwise `False`.

     Examples
    --------
    >>> is_valid_uuid('c9bf9e57-1685-4c89-bafb-ff5af830be8a')
    True
    >>> is_valid_uuid('c9bf9e58')
    False
    """

    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


class Archived(models.Model):
    """An Archived object is no longer in use."""

    archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    def archive(self):
        self.archived = True
        self.archived_at = timezone.now()
        self.save()
        if hasattr(self, "archive_with"):
            for related in self.archive_with:
                if hasattr(related, "archive"):
                    related.archive()

    def unarchive(self):
        self.archived = False
        self.archived_at = None
        self.save()
        if hasattr(self, "archive_with"):
            for related in self.archive_with:
                if hasattr(related, "unarchive"):
                    related.unarchive()

    class Meta:
        abstract = True


class Owned(models.Model):
    """An Owned object is owned by a User."""

    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=False, db_index=True
    )

    class Meta:
        abstract = True


class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    modified = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


T = TypeVar("T")
QuerySetOf = Union[QuerySet, List[T]]
