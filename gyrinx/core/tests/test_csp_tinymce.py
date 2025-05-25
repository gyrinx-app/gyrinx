import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_tinymce_with_csp(user):
    """Test that TinyMCE editor works with CSP enabled."""
    client = Client()
    client.force_login(user)

    # Test campaign creation page
    response = client.get(reverse("core:campaigns-new"))
    assert response.status_code == 200

    # Check CSP header allows necessary TinyMCE resources
    csp_header = response["Content-Security-Policy"]

    # TinyMCE requires unsafe-inline for scripts and styles
    assert "'unsafe-inline'" in csp_header
    assert "script-src 'self' 'unsafe-inline'" in csp_header
    assert "style-src 'self' 'unsafe-inline'" in csp_header

    # Check that form.media is in the response (TinyMCE scripts)
    assert "tinymce" in response.content.decode()


@pytest.mark.django_db
def test_campaign_form_submission_with_csp(user):
    """Test that campaign form with TinyMCE can be submitted with CSP enabled."""
    client = Client()
    client.force_login(user)

    # Submit a campaign with HTML content
    data = {
        "name": "Test Campaign with CSP",
        "summary": "<p>This is a <strong>test</strong> summary with HTML</p>",
        "narrative": "<h2>Test Narrative</h2><p>This is a longer narrative with <em>formatting</em>.</p>",
        "public": False,
    }

    response = client.post(reverse("core:campaigns-new"), data)

    # Should redirect on success
    assert response.status_code == 302

    # Verify the campaign was created
    from gyrinx.core.models.campaign import Campaign

    campaign = Campaign.objects.get(name="Test Campaign with CSP")
    assert campaign.summary == data["summary"]
    assert campaign.narrative == data["narrative"]
