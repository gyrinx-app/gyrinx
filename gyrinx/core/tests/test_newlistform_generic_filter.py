import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import ContentHouse
from gyrinx.core.forms.list import NewListForm


User = get_user_model()


@pytest.mark.django_db
def test_newlistform_filters_out_generic_houses():
    """Test that NewListForm excludes generic houses from the dropdown."""

    # Get initial count of non-generic houses
    initial_non_generic_count = ContentHouse.objects.filter(generic=False).count()

    # Create some test houses
    regular_house1 = ContentHouse.objects.create(name="Test Goliath", generic=False)
    regular_house2 = ContentHouse.objects.create(name="Test Escher", generic=False)
    generic_house1 = ContentHouse.objects.create(name="Test Brutes", generic=True)
    generic_house2 = ContentHouse.objects.create(name="Test Outlaws", generic=True)

    # Create the form
    form = NewListForm()

    # Get the queryset for content_house field
    house_queryset = form.fields["content_house"].queryset

    # Assert that regular houses are included
    assert regular_house1 in house_queryset
    assert regular_house2 in house_queryset

    # Assert that generic houses are excluded
    assert generic_house1 not in house_queryset
    assert generic_house2 not in house_queryset

    # Verify the counts match expected values
    assert house_queryset.count() == initial_non_generic_count + 2
    assert house_queryset.filter(generic=False).count() == initial_non_generic_count + 2
    assert house_queryset.filter(generic=True).count() == 0


@pytest.mark.django_db
def test_newlistform_only_includes_non_generic_houses():
    """Test that NewListForm only includes houses where generic=False."""
    # Create houses with mix of generic and legacy flags
    regular_house = ContentHouse.objects.create(
        name="Van Saar", generic=False, legacy=False
    )
    legacy_house = ContentHouse.objects.create(
        name="Ash Waste Nomads", generic=False, legacy=True
    )
    generic_house = ContentHouse.objects.create(
        name="Slave Ogryns", generic=True, legacy=False
    )
    generic_legacy_house = ContentHouse.objects.create(
        name="Old Generic", generic=True, legacy=True
    )

    # Create the form
    form = NewListForm()

    # Get the queryset for content_house field
    house_queryset = form.fields["content_house"].queryset

    # Assert that only non-generic houses are included (regardless of legacy status)
    assert regular_house in house_queryset
    assert legacy_house in house_queryset
    assert generic_house not in house_queryset
    assert generic_legacy_house not in house_queryset
