import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import ContentHouse
from gyrinx.core.forms.list import NewListForm


User = get_user_model()


@pytest.mark.django_db
def test_newlistform_required_fields():
    """Test that required fields are properly validated"""
    # Create a house to use in tests
    ContentHouse.objects.create(name="Test House", generic=False)

    # Test empty form
    form = NewListForm(data={})
    assert not form.is_valid()
    assert "name" in form.errors
    assert "content_house" in form.errors

    # Test with only name
    form = NewListForm(data={"name": "Test List"})
    assert not form.is_valid()
    assert "name" not in form.errors
    assert "content_house" in form.errors

    # Test with only content_house
    house = ContentHouse.objects.create(name="Another House", generic=False)
    form = NewListForm(data={"content_house": house.id})
    assert not form.is_valid()
    assert "name" in form.errors
    assert "content_house" not in form.errors


@pytest.mark.django_db
def test_newlistform_valid_data():
    """Test form accepts valid data"""
    house = ContentHouse.objects.create(name="Valid House", generic=False)

    valid_data = {
        "name": "Test List",
        "content_house": house.id,
        "narrative": "Test narrative",
        "public": True,
        "show_stash": True,
    }

    form = NewListForm(data=valid_data)
    assert form.is_valid()
    assert not form.errors


@pytest.mark.django_db
def test_newlistform_invalid_house_selection():
    """Test form rejects invalid house choices"""
    # Create generic house (should not be selectable)
    generic_house = ContentHouse.objects.create(name="Generic House", generic=True)
    regular_house = ContentHouse.objects.create(name="Regular House", generic=False)

    # Test with non-existent house ID
    form = NewListForm(data={"name": "Test", "content_house": 99999})
    assert not form.is_valid()
    assert "content_house" in form.errors

    # Test with generic house (should not be allowed)
    form = NewListForm(data={"name": "Test", "content_house": generic_house.id})
    assert not form.is_valid()
    assert "content_house" in form.errors

    # Test with valid regular house
    form = NewListForm(data={"name": "Test", "content_house": regular_house.id})
    assert form.is_valid()


@pytest.mark.django_db
def test_newlistform_edge_cases():
    """Test form handles edge cases properly"""
    house = ContentHouse.objects.create(name="Test House", generic=False)

    # Test with very long name (max_length is 255)
    long_name = "A" * 256  # One character over limit
    form = NewListForm(data={"name": long_name, "content_house": house.id})
    assert not form.is_valid()
    assert "name" in form.errors
    # Check that it's a length error
    error_msg = str(form.errors["name"][0]).lower()
    assert "255" in error_msg or "length" in error_msg or "long" in error_msg

    # Test with special characters in name
    special_chars_name = "Test List !@#$%^&*()_+-=[]{}|;':\",./<>?"
    form = NewListForm(data={"name": special_chars_name, "content_house": house.id})
    assert form.is_valid()  # Special characters should be allowed

    # Test with Unicode characters
    unicode_name = "Test 测试 テスト список тест"
    form = NewListForm(data={"name": unicode_name, "content_house": house.id})
    assert form.is_valid()  # Unicode should be allowed

    # Test with HTML in narrative (should be allowed as it uses TinyMCE)
    html_narrative = '<p>Test <strong>narrative</strong> with <a href="#">HTML</a></p>'
    form = NewListForm(
        data={"name": "Test", "content_house": house.id, "narrative": html_narrative}
    )
    assert form.is_valid()

    # Test with script tags in narrative (TinyMCE should handle this)
    script_narrative = '<p>Test</p><script>alert("XSS")</script>'
    form = NewListForm(
        data={"name": "Test", "content_house": house.id, "narrative": script_narrative}
    )
    # Form validation itself should pass - security is handled by TinyMCE and template rendering
    assert form.is_valid()


@pytest.mark.django_db
def test_newlistform_boolean_fields():
    """Test boolean field handling"""
    house = ContentHouse.objects.create(name="Test House", generic=False)

    # Test with explicit boolean values
    form = NewListForm(
        data={
            "name": "Test",
            "content_house": house.id,
            "public": True,
            "show_stash": False,
        }
    )
    assert form.is_valid()
    assert form.cleaned_data["public"] is True
    assert form.cleaned_data["show_stash"] is False

    # Test with string boolean values (as they come from HTML forms)
    form = NewListForm(
        data={
            "name": "Test",
            "content_house": house.id,
            "public": "on",  # HTML checkbox checked value
            "show_stash": "",  # HTML checkbox unchecked value
        }
    )
    assert form.is_valid()
    assert form.cleaned_data["public"] is True
    assert form.cleaned_data["show_stash"] is False

    # Test without boolean fields (they're optional)
    form = NewListForm(
        data={
            "name": "Test",
            "content_house": house.id,
        }
    )
    assert form.is_valid()
    assert (
        form.cleaned_data["public"] is False
    )  # Default for BooleanField when not provided
    # show_stash is not in cleaned_data when not provided because required=False
    assert form.cleaned_data.get("show_stash", False) is False


@pytest.mark.django_db
def test_newlistform_empty_narrative():
    """Test that narrative field is optional"""
    house = ContentHouse.objects.create(name="Test House", generic=False)

    # Test with empty narrative
    form = NewListForm(
        data={
            "name": "Test",
            "content_house": house.id,
            "narrative": "",
        }
    )
    assert form.is_valid()

    # Test without narrative field
    form = NewListForm(
        data={
            "name": "Test",
            "content_house": house.id,
        }
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_newlistform_whitespace_handling():
    """Test how form handles whitespace in fields"""
    house = ContentHouse.objects.create(name="Test House", generic=False)

    # Test with whitespace-only name (should be invalid)
    form = NewListForm(
        data={
            "name": "   ",  # Only spaces
            "content_house": house.id,
        }
    )
    assert not form.is_valid()
    assert "name" in form.errors

    # Test with leading/trailing whitespace (Django typically strips this)
    form = NewListForm(
        data={
            "name": "  Test List  ",
            "content_house": house.id,
        }
    )
    assert form.is_valid()
    # Django's CharField strips whitespace by default
    assert form.cleaned_data["name"] == "Test List"
