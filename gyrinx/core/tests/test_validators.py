"""Tests for custom validators in the core app."""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.core.validators import HTMLTextMaxLengthValidator


class TestHTMLTextMaxLengthValidator:
    """Tests for HTMLTextMaxLengthValidator."""

    def test_plain_text_under_limit_passes(self):
        """Plain text under the limit should pass validation."""
        validator = HTMLTextMaxLengthValidator(100)
        # Should not raise
        validator("This is a short text")

    def test_plain_text_at_limit_passes(self):
        """Plain text exactly at the limit should pass validation."""
        validator = HTMLTextMaxLengthValidator(10)
        # Should not raise
        validator("1234567890")

    def test_plain_text_over_limit_fails(self):
        """Plain text over the limit should fail validation."""
        validator = HTMLTextMaxLengthValidator(10)
        with pytest.raises(ValidationError) as exc_info:
            validator("12345678901")  # 11 characters
        assert "11" in str(exc_info.value)
        assert "10" in str(exc_info.value)

    def test_html_tags_not_counted(self):
        """HTML tags should not be counted towards the limit."""
        validator = HTMLTextMaxLengthValidator(20)
        # HTML with tags: "<p><strong>Hello</strong></p>" = 5 visible characters
        # Should pass because only "Hello" (5 chars) is counted
        validator("<p><strong>Hello</strong></p>")

    def test_html_with_long_text_fails(self):
        """HTML with text over the limit should fail."""
        validator = HTMLTextMaxLengthValidator(10)
        # Text content is "Hello World" = 11 characters
        with pytest.raises(ValidationError):
            validator("<p>Hello World</p>")

    def test_complex_html_only_counts_text(self):
        """Complex HTML should only count visible text."""
        validator = HTMLTextMaxLengthValidator(50)
        # Lots of HTML but only "Test message" = 12 characters
        html = """
        <div class="container">
            <p style="color: red;">
                <strong><em>Test</em></strong>
                <span>message</span>
            </p>
        </div>
        """
        # Should pass - only 12 chars of visible text
        validator(html)

    def test_empty_value_passes(self):
        """Empty string should pass validation."""
        validator = HTMLTextMaxLengthValidator(10)
        validator("")

    def test_none_value_passes(self):
        """None value should pass validation."""
        validator = HTMLTextMaxLengthValidator(10)
        validator(None)

    def test_html_entities_counted_as_text(self):
        """HTML entities should be decoded and counted as text."""
        validator = HTMLTextMaxLengthValidator(5)
        # "&amp;" decodes to "&" which is 1 character
        # "Hi&amp;" = "Hi&" = 3 characters
        validator("Hi&amp;")

    def test_nested_elements_text_extracted(self):
        """Text from nested elements should be extracted and counted."""
        validator = HTMLTextMaxLengthValidator(20)
        html = "<div><p><span>Nested</span> <b>text</b></p></div>"
        # Text content: "Nested text" = 11 characters
        validator(html)

    def test_whitespace_handling(self):
        """Multiple whitespace should be normalized."""
        validator = HTMLTextMaxLengthValidator(20)
        # Text with lots of whitespace between elements
        html = "<p>Word1</p>   <p>Word2</p>"
        # get_text with strip=True normalizes whitespace
        validator(html)

    def test_error_message_shows_actual_length(self):
        """Error message should show the actual text length."""
        validator = HTMLTextMaxLengthValidator(10)
        with pytest.raises(ValidationError) as exc_info:
            validator("<p>This is way too long for the limit</p>")
        # Check that the error contains the actual length
        error = exc_info.value
        assert error.code == "max_length"
        # The text "This is way too long for the limit" is 34 chars
        assert error.params["show_value"] == 34
        assert error.params["limit_value"] == 10

    def test_validator_equality(self):
        """Two validators with same limit should be equal."""
        v1 = HTMLTextMaxLengthValidator(100)
        v2 = HTMLTextMaxLengthValidator(100)
        v3 = HTMLTextMaxLengthValidator(200)
        assert v1 == v2
        assert v1 != v3

    def test_custom_message(self):
        """Custom message should be used in error."""
        custom_msg = "Too long! Max is %(limit_value)d, you have %(show_value)d"
        validator = HTMLTextMaxLengthValidator(5, message=custom_msg)
        with pytest.raises(ValidationError) as exc_info:
            validator("123456")
        assert "Too long!" in str(exc_info.value)


@pytest.mark.django_db
class TestCampaignSummaryValidation:
    """Integration tests for Campaign summary field validation."""

    def test_campaign_summary_with_html_under_limit(self):
        """Campaign summary with HTML under 300 char text limit should be valid."""
        from django.contrib.auth.models import User

        from gyrinx.core.models.campaign import Campaign

        user = User.objects.create_user(username="testuser", password="testpass")

        # HTML content with lots of tags but < 300 characters of text
        summary = (
            "<p><strong>This is a campaign</strong> with <em>HTML formatting</em>.</p>"
        )
        campaign = Campaign(
            name="Test Campaign",
            owner=user,
            summary=summary,
        )
        # Should not raise - text content is ~40 chars
        campaign.full_clean()

    def test_campaign_summary_with_html_over_limit_fails(self):
        """Campaign summary with text over 300 chars should fail validation."""
        from django.contrib.auth.models import User

        from gyrinx.core.models.campaign import Campaign

        user = User.objects.create_user(username="testuser", password="testpass")

        # Create text content that exceeds 300 characters
        long_text = "A" * 301
        summary = f"<p>{long_text}</p>"
        campaign = Campaign(
            name="Test Campaign",
            owner=user,
            summary=summary,
        )
        with pytest.raises(ValidationError) as exc_info:
            campaign.full_clean()
        assert "summary" in exc_info.value.message_dict

    def test_campaign_summary_html_not_counted(self):
        """HTML tags in summary should not count toward the 300 char limit."""
        from django.contrib.auth.models import User

        from gyrinx.core.models.campaign import Campaign

        user = User.objects.create_user(username="testuser", password="testpass")

        # 299 characters of text but wrapped in lots of HTML tags
        # This would exceed 300 if HTML was counted
        text_content = "A" * 299
        summary = f"<p><strong><em><span style='color: red;'>{text_content}</span></em></strong></p>"

        campaign = Campaign(
            name="Test Campaign",
            owner=user,
            summary=summary,
        )
        # Should not raise - only 299 chars of text
        campaign.full_clean()
