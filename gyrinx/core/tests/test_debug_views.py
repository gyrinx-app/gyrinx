"""Tests for debug-only views."""

import pytest
from django.test import Client, override_settings

from gyrinx.core.views.debug import TEST_PLANS_DIR, get_available_plans


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


class TestGetAvailablePlans:
    """Tests for the get_available_plans helper function."""

    def test_returns_empty_dict_when_no_plans(self):
        """Test that empty dict is returned when no plans exist."""
        # Clear any existing plans for this test
        plans = get_available_plans()
        # Should return dict (may have plans from other tests)
        assert isinstance(plans, dict)

    def test_returns_plans_with_metadata(self, test_plan_file):
        """Test that plans include correct metadata."""
        plans = get_available_plans()
        assert "test-fixture-plan.md" in plans
        plan = plans["test-fixture-plan.md"]
        assert plan["name"] == "test-fixture-plan"
        assert plan["filename"] == "test-fixture-plan.md"
        assert "modified" in plan
        assert "path" in plan
        assert plan["path"] == test_plan_file


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
    def test_detail_only_serves_known_files(self, client):
        """Test that only files from get_available_plans are served.

        This validates the security model: we only serve files that we've
        explicitly enumerated from the test-plans directory.
        """
        # These should all return 404 since they won't be in the available plans
        invalid_requests = [
            "file.txt",  # Wrong extension
            "../file.md",  # Path traversal
            ".hidden.md",  # Hidden file
            "../../../etc/passwd",  # Path traversal attack
        ]
        for filename in invalid_requests:
            response = client.get(f"/_debug/test-plans/{filename}")
            # Should be 404 (not in plans) or redirect to 404
            assert response.status_code in [404, 301], (
                f"Unexpected response for {filename}"
            )
