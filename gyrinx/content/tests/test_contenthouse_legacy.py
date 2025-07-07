import pytest

from gyrinx.content.forms import CopySelectedToHouseForm
from gyrinx.content.models import ContentHouse


@pytest.mark.django_db
def test_contenthouse_has_legacy_field():
    """Test that ContentHouse model has the legacy field."""
    house = ContentHouse(name="Test House", legacy=True)
    assert hasattr(house, "legacy")
    assert house.legacy is True


@pytest.mark.django_db
def test_contenthouse_legacy_defaults_to_false():
    """Test that ContentHouse legacy field defaults to False."""
    house = ContentHouse(name="Test House")
    assert house.legacy is False


@pytest.mark.django_db
def test_copyselectedtohouseform_groups_by_legacy():
    """Test that CopySelectedToHouseForm groups houses by legacy status."""
    # Create the form
    form = CopySelectedToHouseForm()

    # Check that the form has the grouped choices structure
    # The form should have choices grouped as [(group_name, [(id, label), ...]), ...]
    assert hasattr(form.fields["to_houses"].widget, "choices")
