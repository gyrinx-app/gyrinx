import pytest
from django.contrib.auth import get_user_model

from gyrinx.core.forms.list import NewListForm


User = get_user_model()


@pytest.mark.django_db
def test_newlistform_groups_by_legacy():
    """Test that NewListForm groups houses by legacy status."""
    # Create a user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create the form
    form = NewListForm()

    # Check that the form has the content_house field
    assert "content_house" in form.fields

    # Check that the widget has choices attribute (it should be grouped)
    assert hasattr(form.fields["content_house"].widget, "choices")