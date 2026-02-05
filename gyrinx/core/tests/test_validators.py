"""Tests for custom validators in the core app."""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.core.validators import HTMLTextMaxLengthValidator


# --- HTMLTextMaxLengthValidator unit tests ---


def test_plain_text_under_limit_passes():
    validator = HTMLTextMaxLengthValidator(100)
    validator("This is a short text")


def test_plain_text_at_limit_passes():
    validator = HTMLTextMaxLengthValidator(10)
    validator("1234567890")


def test_plain_text_over_limit_fails():
    validator = HTMLTextMaxLengthValidator(10)
    with pytest.raises(ValidationError) as exc_info:
        validator("12345678901")  # 11 characters
    assert "11" in str(exc_info.value)
    assert "10" in str(exc_info.value)


def test_html_tags_not_counted():
    validator = HTMLTextMaxLengthValidator(20)
    # "Hello" = 5 visible characters
    validator("<p><strong>Hello</strong></p>")


def test_html_with_long_text_fails():
    validator = HTMLTextMaxLengthValidator(10)
    # "Hello World" = 11 characters
    with pytest.raises(ValidationError):
        validator("<p>Hello World</p>")


def test_complex_html_only_counts_text():
    validator = HTMLTextMaxLengthValidator(50)
    # "Test message" = 12 characters
    html = """
    <div class="container">
        <p style="color: red;">
            <strong><em>Test</em></strong>
            <span>message</span>
        </p>
    </div>
    """
    validator(html)


def test_empty_value_passes():
    validator = HTMLTextMaxLengthValidator(10)
    validator("")


def test_none_value_passes():
    validator = HTMLTextMaxLengthValidator(10)
    validator(None)


def test_html_entities_counted_as_text():
    validator = HTMLTextMaxLengthValidator(5)
    # "&amp;" decodes to "&" which is 1 character
    # "Hi&amp;" = "Hi&" = 3 characters
    validator("Hi&amp;")


def test_nested_elements_text_extracted():
    validator = HTMLTextMaxLengthValidator(20)
    html = "<div><p><span>Nested</span> <b>text</b></p></div>"
    # "Nested text" = 11 characters
    validator(html)


def test_whitespace_handling():
    validator = HTMLTextMaxLengthValidator(20)
    # The validator uses get_text(strip=True, separator=" "), which strips
    # leading/trailing whitespace in text nodes and inserts a single space
    # between elements, collapsing inter-element whitespace.
    html = "<p>Word1</p>   <p>Word2</p>"
    validator(html)


def test_error_message_shows_actual_length():
    validator = HTMLTextMaxLengthValidator(10)
    with pytest.raises(ValidationError) as exc_info:
        validator("<p>This is way too long for the limit</p>")
    error = exc_info.value
    assert error.code == "max_length"
    # "This is way too long for the limit" = 34 chars
    assert error.params["show_value"] == 34
    assert error.params["limit_value"] == 10


def test_validator_equality():
    v1 = HTMLTextMaxLengthValidator(100)
    v2 = HTMLTextMaxLengthValidator(100)
    v3 = HTMLTextMaxLengthValidator(200)
    assert v1 == v2
    assert v1 != v3


def test_custom_message():
    custom_msg = "Too long! Max is %(limit_value)d, you have %(show_value)d"
    validator = HTMLTextMaxLengthValidator(5, message=custom_msg)
    with pytest.raises(ValidationError) as exc_info:
        validator("123456")
    assert "Too long!" in str(exc_info.value)


def test_script_tags_not_counted():
    validator = HTMLTextMaxLengthValidator(10)
    # Only "Hello" (5 chars) should be counted
    html = "<p>Hello</p><script>alert('this is a very long script')</script>"
    validator(html)


def test_style_tags_not_counted():
    validator = HTMLTextMaxLengthValidator(10)
    # Only "Hello" (5 chars) should be counted
    html = "<p>Hello</p><style>.class { color: red; background: blue; }</style>"
    validator(html)


def test_script_and_style_combined():
    validator = HTMLTextMaxLengthValidator(5)
    html = """
    <script>var x = 'very long script content';</script>
    <p>Hello</p>
    <style>.class { color: red; margin: 10px; }</style>
    """
    # Only "Hello" (5 chars) should be counted
    validator(html)


def test_validator_hashability():
    v1 = HTMLTextMaxLengthValidator(100)
    v2 = HTMLTextMaxLengthValidator(100)
    v3 = HTMLTextMaxLengthValidator(200)

    assert hash(v1) == hash(v2)

    validator_set = {v1, v2, v3}
    assert len(validator_set) == 2

    validator_dict = {v1: "first", v3: "third"}
    assert validator_dict[v2] == "first"


# --- Campaign summary integration tests ---


@pytest.mark.django_db
def test_campaign_summary_with_html_under_limit(user):
    from gyrinx.core.models.campaign import Campaign

    summary = (
        "<p><strong>This is a campaign</strong> with <em>HTML formatting</em>.</p>"
    )
    campaign = Campaign(name="Test Campaign", owner=user, summary=summary)
    campaign.full_clean()


@pytest.mark.django_db
def test_campaign_summary_with_html_over_limit_fails(user):
    from gyrinx.core.models.campaign import Campaign

    long_text = "A" * 301
    summary = f"<p>{long_text}</p>"
    campaign = Campaign(name="Test Campaign", owner=user, summary=summary)
    with pytest.raises(ValidationError) as exc_info:
        campaign.full_clean()
    assert "summary" in exc_info.value.message_dict


@pytest.mark.django_db
def test_campaign_summary_html_not_counted(user):
    from gyrinx.core.models.campaign import Campaign

    # 299 characters of text wrapped in lots of HTML tags
    text_content = "A" * 299
    summary = f"<p><strong><em><span style='color: red;'>{text_content}</span></em></strong></p>"
    campaign = Campaign(name="Test Campaign", owner=user, summary=summary)
    campaign.full_clean()
