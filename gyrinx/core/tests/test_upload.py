import os
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from gyrinx.core.models import UploadedFile

User = get_user_model()


@pytest.fixture
def authenticated_client(db):
    """Create an authenticated test client."""
    user = User.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )
    client = Client()
    client.login(username="testuser", password="testpass123")
    return client, user


@pytest.fixture
def test_image():
    """Create a test image file."""
    # Create a minimal valid PNG file
    # PNG header + IHDR chunk for a 1x1 pixel image
    png_data = (
        b"\x89PNG\r\n\x1a\n"  # PNG signature
        b"\x00\x00\x00\rIHDR"  # IHDR chunk
        b"\x00\x00\x00\x01\x00\x00\x00\x01"  # 1x1 pixel
        b"\x08\x02\x00\x00\x00"  # 8-bit RGB
        b"\x90wS\xde"  # CRC
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"  # Image data
        b"\x18\xdd\x8d\xb4"  # CRC
        b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND chunk
    )
    return SimpleUploadedFile("test_image.png", png_data, content_type="image/png")


@pytest.fixture
def large_image():
    """Create a large test image file (>10MB)."""
    # Create a fake large file by repeating data
    # This won't be a valid image but that's OK for testing file size
    large_data = b"x" * (11 * 1024 * 1024)  # 11MB of data
    return SimpleUploadedFile("large_image.png", large_data, content_type="image/png")


@pytest.fixture
def test_text_file():
    """Create a test text file (invalid type)."""
    return SimpleUploadedFile(
        "test.txt", b"This is a text file", content_type="text/plain"
    )


@pytest.mark.django_db
class TestTinyMCEUpload:
    """Test the TinyMCE upload endpoint."""

    def test_upload_requires_authentication(self):
        """Test that upload requires user to be logged in."""
        client = Client()
        url = reverse("core:tinymce-upload")

        response = client.post(url)
        assert response.status_code == 302  # Redirect to login
        assert "/accounts/login/" in response.url

    def test_upload_requires_post(self, authenticated_client):
        """Test that only POST requests are allowed."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        response = client.get(url)
        assert response.status_code == 405  # Method not allowed

    def test_upload_requires_file(self, authenticated_client):
        """Test that a file must be provided."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        response = client.post(url)
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "No file provided"

    @override_settings(MEDIA_ROOT="/tmp/test_media")
    def test_successful_upload(self, authenticated_client, test_image):
        """Test successful image upload."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        response = client.post(url, {"file": test_image})
        assert response.status_code == 200

        data = response.json()
        assert "location" in data
        assert "id" in data
        assert data["filename"] == "test_image.png"
        assert data["size"] > 0

        # Check that file was saved to database
        upload = UploadedFile.objects.get(id=data["id"])
        assert upload.owner == user
        assert upload.original_filename == "test_image.png"
        assert upload.content_type == "image/png"
        assert upload.file_size == data["size"]

        # Clean up
        if os.path.exists(upload.file.path):
            os.remove(upload.file.path)

    def test_upload_invalid_file_type(self, authenticated_client, test_text_file):
        """Test that invalid file types are rejected."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        response = client.post(url, {"file": test_text_file})
        assert response.status_code == 400

        data = response.json()
        assert data["error"] == "File upload failed due to validation errors"

    def test_upload_file_too_large(self, authenticated_client, large_image):
        """Test that files over 10MB are rejected."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        # Check if the image is actually large enough
        if large_image.size <= 10 * 1024 * 1024:
            pytest.skip("Test image not large enough")

        response = client.post(url, {"file": large_image})
        assert response.status_code == 400

        data = response.json()
        assert data["error"] == "File upload failed due to validation errors"

    @override_settings(MEDIA_ROOT="/tmp/test_media")
    def test_daily_quota_limit(self, authenticated_client, test_image):
        """Test that daily upload quota is enforced."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        # Mock the quota check to simulate quota exceeded
        with patch.object(
            UploadedFile, "get_user_usage_today", return_value=100 * 1024 * 1024
        ):
            response = client.post(url, {"file": test_image})
            assert response.status_code == 400

            data = response.json()
            assert "Daily upload limit exceeded" in data["error"]

    @override_settings(MEDIA_ROOT="/tmp/test_media")
    def test_upload_tracks_access(self, authenticated_client, test_image):
        """Test that file access is tracked."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        response = client.post(url, {"file": test_image})
        assert response.status_code == 200

        data = response.json()
        upload = UploadedFile.objects.get(id=data["id"])

        # Initially no access
        assert upload.access_count == 0
        assert upload.last_accessed is None

        # Increment access
        upload.increment_access_count()
        upload.refresh_from_db()

        assert upload.access_count == 1
        assert upload.last_accessed is not None

        # Clean up
        if os.path.exists(upload.file.path):
            os.remove(upload.file.path)

    @override_settings(MEDIA_ROOT="/tmp/test_media")
    def test_upload_generates_unique_filename(self, authenticated_client, test_image):
        """Test that uploaded files get unique UUID filenames."""
        client, user = authenticated_client
        url = reverse("core:tinymce-upload")

        response = client.post(url, {"file": test_image})
        assert response.status_code == 200

        data = response.json()
        upload = UploadedFile.objects.get(id=data["id"])

        # Check that the stored filename is a UUID
        filename = os.path.basename(upload.file.name)
        name_parts = filename.split(".")
        assert len(name_parts) == 2  # UUID.extension
        assert len(name_parts[0]) == 36  # UUID with hyphens
        assert name_parts[1] == "png"

        # Clean up
        if os.path.exists(upload.file.path):
            os.remove(upload.file.path)

    def test_csrf_token_required(self):
        """Test that CSRF token is required."""
        client = Client(enforce_csrf_checks=True)
        User.objects.create_user(
            username="testuser2", email="test2@example.com", password="testpass123"
        )
        client.login(username="testuser2", password="testpass123")

        url = reverse("core:tinymce-upload")

        # Post without CSRF token
        response = client.post(url, {"file": "dummy"})
        assert response.status_code == 403  # CSRF failure


@pytest.mark.django_db
class TestUploadedFileModel:
    """Test the UploadedFile model."""

    def test_file_size_mb_property(self):
        """Test the file_size_mb property."""
        upload = UploadedFile(file_size=5 * 1024 * 1024)  # 5MB
        assert upload.file_size_mb == 5.0

    def test_get_user_usage_today(self, authenticated_client):
        """Test calculating daily usage for a user."""
        client, user = authenticated_client

        # Create some uploads (using create_with_user to bypass validation)
        UploadedFile.objects.create_with_user(
            user=user,
            owner=user,
            file_size=1024 * 1024,  # 1MB
            original_filename="test1.png",
            content_type="image/png",
        )
        UploadedFile.objects.create_with_user(
            user=user,
            owner=user,
            file_size=2 * 1024 * 1024,  # 2MB
            original_filename="test2.png",
            content_type="image/png",
        )

        # Create an old upload (should not count)
        old_upload = UploadedFile.objects.create_with_user(
            user=user,
            owner=user,
            file_size=10 * 1024 * 1024,  # 10MB
            original_filename="old.png",
            content_type="image/png",
        )
        # Manually set uploaded_at to yesterday using update to bypass validation
        UploadedFile.objects.filter(id=old_upload.id).update(
            uploaded_at=timezone.now() - timedelta(days=1)
        )

        # Check usage
        usage = UploadedFile.get_user_usage_today(user)
        assert usage == 3 * 1024 * 1024  # Only today's uploads

    def test_check_user_quota(self, authenticated_client):
        """Test quota checking logic."""
        client, user = authenticated_client

        # Check with no existing uploads
        can_upload, remaining, message = UploadedFile.check_user_quota(
            user, 1024 * 1024
        )
        assert can_upload is True
        assert remaining == 100 * 1024 * 1024  # Full quota available
        assert message == ""

        # Check with quota exceeded
        can_upload, remaining, message = UploadedFile.check_user_quota(
            user, 101 * 1024 * 1024
        )
        assert can_upload is False
        assert "Daily upload limit exceeded" in message

    @override_settings(CDN_DOMAIN="https://cdn.example.com")
    def test_file_url_with_cdn(self, authenticated_client):
        """Test that file_url uses CDN domain when configured."""
        client, user = authenticated_client
        
        # Create an upload with a mock file
        upload = UploadedFile.objects.create_with_user(
            user=user,
            owner=user,
            file_size=1024,
            original_filename="test.png",
            content_type="image/png",
        )
        # Mock the file name
        upload.file.name = "uploads/test-uuid.png"
        
        # Test CDN URL
        assert upload.file_url == "https://cdn.example.com/uploads/test-uuid.png"

    def test_file_url_without_cdn(self, authenticated_client):
        """Test that file_url returns normal URL when CDN not configured."""
        client, user = authenticated_client
        
        # Create an upload with a mock file
        upload = UploadedFile.objects.create_with_user(
            user=user,
            owner=user,
            file_size=1024,
            original_filename="test.png",
            content_type="image/png",
        )
        # Mock the file URL
        upload.file.url = "/media/uploads/test-uuid.png"
        
        # Test regular URL (no CDN)
        assert upload.file_url == "/media/uploads/test-uuid.png"
