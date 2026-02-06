from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords

from .base import AppBase


class CustomContentPack(AppBase):
    """A user-created content pack that groups custom content items together.

    Content packs allow users to create collections of custom content
    (fighters, equipment, etc.) that can be shared and used across lists.
    """

    name = models.CharField(max_length=255)
    summary = models.TextField(
        blank=True,
        help_text="A brief summary of this content pack.",
    )
    description = models.TextField(
        blank=True,
        help_text="A detailed description of this content pack.",
    )
    listed = models.BooleanField(
        default=False,
        help_text="Whether this content pack is publicly listed.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Custom Content Pack"
        verbose_name_plural = "Custom Content Packs"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("core:pack", args=(self.id,))


class CustomContentPackItem(AppBase):
    """A polymorphic through model linking content items to packs.

    Uses Django's ContentType framework to allow any content model
    to be associated with a pack via a single table.
    """

    pack = models.ForeignKey(
        CustomContentPack,
        on_delete=models.CASCADE,
        related_name="items",
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={"app_label": "content"},
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Custom Content Pack Item"
        verbose_name_plural = "Custom Content Pack Items"
        constraints = [
            models.UniqueConstraint(
                fields=["pack", "content_type", "object_id"],
                name="unique_pack_content_item",
            ),
        ]
        indexes = [
            models.Index(
                fields=["content_type", "object_id"],
                name="idx_pack_item_ct_oid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.content_type_id and self.object_id:
            model_class = self.content_type.model_class()
            # Use all_content() to bypass pack filtering, since the object
            # we're linking may itself be pack content.
            manager = model_class._default_manager
            if hasattr(manager, "all_content"):
                qs = manager.all_content()
            else:
                qs = manager.all()
            if not qs.filter(pk=self.object_id).exists():
                raise ValidationError(
                    {
                        "object_id": f"No {model_class._meta.verbose_name} "
                        f"found with ID {self.object_id}."
                    }
                )

    def __str__(self):
        return f"{self.pack.name}: {self.content_object}"
