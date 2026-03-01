"""
Base classes and utilities for content models.

This module provides the abstract Content base class that all content models
inherit from. The Content class inherits from gyrinx.models.Base which provides:
- UUID primary key
- created/modified timestamps

It also provides ContentQuerySet and ContentManager which handle filtering
of pack-associated content by default.
"""

from dataclasses import dataclass

from django.db import models

from gyrinx.models import Base


class ContentQuerySet(models.QuerySet):
    """Base QuerySet for content models with pack-awareness.

    Provides methods for filtering content based on pack membership.
    """

    def _pack_items_for_model(self):
        """Get pack items filtered to this model's content type.

        Uses field lookups rather than ContentType.objects.get_for_model()
        to avoid database queries at queryset construction time.
        """
        from gyrinx.core.models.pack import CustomContentPackItem

        return CustomContentPackItem.objects.filter(
            content_type__app_label=self.model._meta.app_label,
            content_type__model=self.model._meta.model_name,
        )

    def exclude_pack_content(self):
        """Exclude content that belongs to any pack."""
        from django.db.models import Exists, OuterRef

        pack_exists = self._pack_items_for_model().filter(object_id=OuterRef("pk"))
        return self.filter(~Exists(pack_exists))

    def with_packs(self, packs):
        """Return items not in any pack plus items from specified packs.

        Only non-archived pack items are considered when checking membership
        in the specified packs, so archived (soft-deleted) content is excluded.
        """
        from django.db.models import Exists, OuterRef

        pack_items = self._pack_items_for_model().filter(object_id=OuterRef("pk"))
        not_in_any_pack = ~Exists(pack_items)
        in_specified_packs = Exists(pack_items.filter(pack__in=packs, archived=False))
        return self.filter(not_in_any_pack | in_specified_packs)


class ContentManager(models.Manager):
    """Base manager for content models that excludes pack content by default.

    The default queryset filters out content that belongs to any pack.
    Use all_content() to bypass this filter, or with_packs() to include
    content from specific packs.
    """

    def get_queryset(self):
        return super().get_queryset().exclude_pack_content()

    def all_content(self):
        """Return all content including pack items."""
        return super().get_queryset()

    def with_packs(self, packs):
        """Return base content plus content from specified packs."""
        return super().get_queryset().with_packs(packs)


class Content(Base):
    """
    An abstract base model that captures common fields for all content-related
    models. Subclasses should inherit from this to store standard metadata.
    """

    objects = ContentManager.from_queryset(ContentQuerySet)()

    class Meta:
        abstract = True


@dataclass
class RulelineDisplay:
    """A dataclass for displaying rules in a consistent format."""

    value: str
    modded: bool = False


@dataclass
class StatlineDisplay:
    """A dataclass for displaying stats in a consistent format."""

    name: str
    field_name: str
    value: str
    classes: str = ""
    modded: bool = False
    highlight: bool = False
