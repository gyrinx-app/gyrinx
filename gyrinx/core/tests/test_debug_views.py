"""Tests for debug-only views."""

import pytest
from django.test import Client, override_settings

from gyrinx.core.views.debug import (
    TEST_PLANS_DIR,
    VALID_FILENAME_PATTERN,
)


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def test_plan_file():
    """Create a temporary test plan file in the actual test-plans directory."""
    # Ensure the directory exists
    TEST_PLANS_DIR.mkdir(parents=True, exist_ok=True)

    # Create a test plan file
    test_plan = TEST_PLANS_DIR / "test-fixture-plan.md"
    test_plan.write_text("# Test Plan: Fixture Test\n\nThis is a test plan.")

    yield test_plan

    # Cleanup
    if test_plan.exists():
        test_plan.unlink()


class TestFilenameValidation:
    """Tests for the filename validation regex - main security check."""

    def test_valid_filenames(self):
        """Test that valid filenames match the pattern."""
        valid_filenames = [
            "test.md",
            "2025-01-01-feature.md",
            "my_test_plan.md",
            "TEST-PLAN.md",
            "plan123.md",
            "a.md",
            "test-feature-name.md",
            "test_with_underscores.md",
        ]
        for filename in valid_filenames:
            assert VALID_FILENAME_PATTERN.match(filename), (
                f"Valid filename rejected: {filename}"
            )

    def test_invalid_filenames(self):
        """Test that invalid filenames don't match the pattern."""
        invalid_filenames = [
            "file.txt",  # Wrong extension
            "file",  # No extension
            "../file.md",  # Path component
            "file/sub.md",  # Subdirectory
            ".hidden.md",  # Hidden file
            "file with spaces.md",  # Spaces
            "",  # Empty
            ".md",  # Just extension
            "file..md",  # Double dots
            "file.md.txt",  # Double extension
            "../../../etc/passwd",  # Path traversal
            "test\x00.md",  # Null byte
        ]
        for filename in invalid_filenames:
            assert not VALID_FILENAME_PATTERN.match(filename), (
                f"Invalid filename accepted: {filename}"
            )


@pytest.mark.django_db
class TestDebugTestPlanIndex:
    """Tests for the debug test plan index view."""

    @override_settings(DEBUG=True)
    def test_index_loads_in_debug_mode(self, client):
        """Test that the index page loads when DEBUG=True."""
        response = client.get("/_debug/test-plans/")
        assert response.status_code == 200
        assert b"Test Plans" in response.content

    @override_settings(DEBUG=True)
    def test_index_shows_test_plans(self, client, test_plan_file):
        """Test that the index lists available test plans."""
        response = client.get("/_debug/test-plans/")
        assert response.status_code == 200
        assert b"test-fixture-plan" in response.content

    @override_settings(DEBUG=False)
    def test_index_returns_404_when_debug_false(self, client):
        """Test that the index returns 404 when DEBUG=False."""
        response = client.get("/_debug/test-plans/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDebugTestPlanDetail:
    """Tests for the debug test plan detail view."""

    @override_settings(DEBUG=True)
    def test_detail_returns_raw_content(self, client, test_plan_file):
        """Test that the detail view returns raw markdown content."""
        response = client.get("/_debug/test-plans/test-fixture-plan.md")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain; charset=utf-8"
        assert b"# Test Plan: Fixture Test" in response.content

    @override_settings(DEBUG=True)
    def test_detail_returns_404_for_missing_file(self, client):
        """Test that missing files return 404."""
        response = client.get("/_debug/test-plans/nonexistent-file.md")
        assert response.status_code == 404

    @override_settings(DEBUG=False)
    def test_detail_returns_404_when_debug_false(self, client, test_plan_file):
        """Test that the detail view returns 404 when DEBUG=False.

        Note: We follow redirects since APPEND_SLASH may redirect first.
        The view itself will return 404 regardless.
        """
        response = client.get("/_debug/test-plans/test-fixture-plan.md", follow=True)
        assert response.status_code == 404

    @override_settings(DEBUG=True)
    def test_detail_rejects_invalid_extension(self, client):
        """Test that files with wrong extension are rejected."""
        response = client.get("/_debug/test-plans/file.txt")
        assert response.status_code == 404
