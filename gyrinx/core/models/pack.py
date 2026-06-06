from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .base import AppBase
from .upload import upload_to


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
    featured = models.BooleanField(
        default=False,
        help_text="Whether this content pack is featured on the Customisation page.",
    )
    featured_description = models.TextField(
        blank=True,
        help_text="A short description shown when this pack is featured.",
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

    def can_edit(self, user):
        """Return True if the user can edit this pack (owner or editor)."""
        if not user.is_authenticated:
            return False
        if user == self.owner:
            return True
        return self.permissions.filter(user=user, role="editor").exists()

    def can_view(self, user):
        """Return True if the user can view this pack."""
        if self.listed:
            return True
        if not user.is_authenticated:
            return False
        if user == self.owner:
            return True
        return self.permissions.filter(user=user).exists()


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
                condition=models.Q(archived=False),
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


class CustomContentPackPermission(AppBase):
    """Grants a user a role on a content pack (e.g. editor)."""

    ROLE_CHOICES = [
        ("editor", "Editor"),
    ]

    pack = models.ForeignKey(
        CustomContentPack,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pack_permissions",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="editor")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Content Pack Permission"
        verbose_name_plural = "Content Pack Permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["pack", "user"],
                name="unique_pack_user_permission",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_role_display()} on {self.pack}"


# Allowed MIME types for pack attachments: PDFs and raster images.
#
# SVG is deliberately excluded. Attachments are served from a public CDN via
# direct links (no Content-Disposition: attachment), so a file served as
# ``image/svg+xml`` renders as a document and executes any embedded
# ``<script>`` — a stored-XSS vector. Raster image formats render as inert
# images and PDFs open in the viewer, neither of which executes page script.
PACK_ATTACHMENT_ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
]

# Allowed file extensions, validated alongside the content type. The stored
# object keeps the user-supplied extension (see ``upload_to``), and the CDN
# derives the served Content-Type from that extension — so a file named
# ``evil.svg`` with a spoofed ``image/png`` content type would still be served
# as SVG. Validating the extension closes that spoofing path.
PACK_ATTACHMENT_ALLOWED_EXTENSIONS = {
    "pdf",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
}

# Per-file size cap (20MB).
PACK_ATTACHMENT_MAX_FILE_SIZE = 20 * 1024 * 1024

# Maximum number of (non-archived) attachments per pack.
PACK_ATTACHMENT_MAX_PER_PACK = 5

# Daily per-user upload quota for pack attachments (100MB), tracked
# separately from ``UploadedFile``'s image-upload quota.
PACK_ATTACHMENT_DAILY_QUOTA = 100 * 1024 * 1024


class CustomContentPackAttachment(AppBase):
    """A supplementary file attached to a content pack.

    Lets pack owners bundle scenario PDFs, campaign rules, reference sheets
    and similar documents/images alongside the structured content of a pack.

    Unlike :class:`CustomContentPackItem`, this is not a polymorphic link to
    a content model — it stores an uploaded file directly.
    """

    pack = models.ForeignKey(
        CustomContentPack,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=upload_to)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    content_type = models.CharField(max_length=100)
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="An optional display title for this file.",
    )
    description = models.TextField(
        blank=True,
        help_text="An optional description of this file.",
    )
    order = models.PositiveIntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Content Pack Attachment"
        verbose_name_plural = "Content Pack Attachments"
        ordering = ["order", "original_filename"]

    def __str__(self):
        return f"{self.pack.name}: {self.title or self.original_filename}"

    @property
    def display_name(self):
        """The title if set, otherwise the original filename."""
        return self.title or self.original_filename

    @property
    def file_url(self):
        """Get the URL for the file, using the CDN domain if configured."""
        if self.file:
            if getattr(settings, "CDN_DOMAIN", None):
                return f"https://{settings.CDN_DOMAIN}/{self.file.name}"
            return self.file.url
        return None

    @property
    def file_size_mb(self):
        """Get file size in megabytes."""
        return self.file_size / (1024 * 1024)

    def clean(self):
        """Validate the attachment's size, content type, and extension."""
        super().clean()

        if self.file_size:
            if self.file_size > PACK_ATTACHMENT_MAX_FILE_SIZE:
                raise ValidationError(
                    f"File size cannot exceed "
                    f"{PACK_ATTACHMENT_MAX_FILE_SIZE // (1024 * 1024)}MB. "
                    f"Your file is {self.file_size_mb:.1f}MB."
                )

        if self.content_type:
            if self.content_type not in PACK_ATTACHMENT_ALLOWED_CONTENT_TYPES:
                raise ValidationError(
                    f"File type '{self.content_type}' is not allowed. "
                    f"Allowed types: PDF, JPEG, PNG, GIF, WebP."
                )

        # Validate the file extension as well as the content type. The CDN
        # serves the stored object with a Content-Type derived from its
        # extension, so an executable extension (e.g. .svg, .html) must be
        # rejected even if the client-supplied content type looks benign.
        name = (self.file.name if self.file else "") or self.original_filename
        if name:
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in PACK_ATTACHMENT_ALLOWED_EXTENSIONS:
                raise ValidationError(
                    f"File extension '.{ext}' is not allowed. "
                    f"Allowed: PDF, JPG, PNG, GIF, WebP."
                )

    @classmethod
    def get_user_usage_today(cls, user):
        """Get total bytes of pack attachments uploaded by user today."""
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        total = (
            cls.objects.filter(owner=user, created__gte=today_start).aggregate(
                total_size=models.Sum("file_size")
            )["total_size"]
            or 0
        )
        return total

    @classmethod
    def check_user_quota(cls, user, file_size):
        """Check if the user can upload a file of the given size today.

        Returns:
            tuple: (can_upload: bool, remaining_bytes: int, message: str)
        """
        current_usage = cls.get_user_usage_today(user)
        remaining = PACK_ATTACHMENT_DAILY_QUOTA - current_usage

        if file_size > remaining:
            message = (
                f"Daily upload limit exceeded. You have "
                f"{remaining / (1024 * 1024):.1f}MB remaining today."
            )
            return False, remaining, message

        return True, remaining, ""
