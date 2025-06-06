import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .base import AppBase


def upload_to(instance, filename):
    """Generate upload path using UUID."""
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return filename


class UploadedFile(AppBase):
    """Model to track user file uploads with metadata."""

    # File field
    file = models.FileField(upload_to=upload_to)

    # Metadata fields
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    content_type = models.CharField(max_length=100)

    # Upload tracking
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Usage tracking
    last_accessed = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)

    # History tracking
    history = HistoricalRecords()

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["owner", "uploaded_at"]),
            models.Index(fields=["content_type"]),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.owner.username})"

    @property
    def file_url(self):
        """Get the URL for the file, using CDN domain if configured."""
        if self.file:
            if hasattr(settings, "CDN_DOMAIN") and settings.CDN_DOMAIN:
                return f"https://{settings.CDN_DOMAIN}/{self.file.name}"
            return self.file.url
        return None

    @property
    def file_size_mb(self):
        """Get file size in megabytes."""
        return self.file_size / (1024 * 1024)

    def increment_access_count(self):
        """Increment access count and update last accessed time."""
        self.access_count += 1
        self.last_accessed = timezone.now()
        self.save(update_fields=["access_count", "last_accessed"])

    @classmethod
    def get_user_usage_today(cls, user):
        """Get total bytes uploaded by user today."""
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        total = (
            cls.objects.filter(owner=user, uploaded_at__gte=today_start).aggregate(
                total_size=models.Sum("file_size")
            )["total_size"]
            or 0
        )

        return total

    @classmethod
    def check_user_quota(cls, user, file_size):
        """Check if user can upload a file of given size.

        Returns:
            tuple: (can_upload: bool, remaining_bytes: int, message: str)
        """
        # Daily quota in bytes (100MB)
        daily_quota = 100 * 1024 * 1024

        current_usage = cls.get_user_usage_today(user)
        remaining = daily_quota - current_usage

        if file_size > remaining:
            message = f"Daily upload limit exceeded. You have {remaining / (1024 * 1024):.1f}MB remaining today."
            return False, remaining, message

        return True, remaining, ""

    def clean(self):
        """Validate the file upload."""
        super().clean()

        # Check file size (10MB limit)
        if self.file_size:
            max_size = 10 * 1024 * 1024  # 10MB in bytes
            if self.file_size > max_size:
                raise ValidationError(
                    f"File size cannot exceed 10MB. Your file is {self.file_size_mb:.1f}MB."
                )

        # Check allowed content types
        if self.content_type:
            allowed_types = [
                "image/jpeg",
                "image/jpg",
                "image/png",
                "image/gif",
                "image/webp",
                "image/svg+xml",
            ]

            if self.content_type not in allowed_types:
                raise ValidationError(
                    f"File type '{self.content_type}' is not allowed. Allowed types: JPEG, PNG, GIF, WebP, SVG."
                )

    def save(self, *args, **kwargs):
        """Override save to validate before saving."""
        # Always validate before saving
        self.full_clean()
        super().save(*args, **kwargs)
