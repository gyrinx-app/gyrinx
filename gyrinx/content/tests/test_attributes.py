import pytest

from gyrinx.content.models import ContentAttribute, ContentAttributeValue


@pytest.mark.django_db
def test_content_attribute_creation():
    """Test creating a ContentAttribute."""
    attribute = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )

    assert attribute.name == "Alignment"
    assert attribute.is_single_select is True
    assert str(attribute) == "Alignment (single-select)"


@pytest.mark.django_db
def test_content_attribute_multi_select():
    """Test creating a multi-select ContentAttribute."""
    attribute = ContentAttribute.objects.create(
        name="Affiliations",
        is_single_select=False,
    )

    assert attribute.name == "Affiliations"
    assert attribute.is_single_select is False
    assert str(attribute) == "Affiliations (multi-select)"


@pytest.mark.django_db
def test_content_attribute_value_creation():
    """Test creating ContentAttributeValue."""
    attribute = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )

    value1 = ContentAttributeValue.objects.create(
        attribute=attribute,
        name="Law Abiding",
        description="Follows the law of the underhive",
    )

    ContentAttributeValue.objects.create(
        attribute=attribute,
        name="Outlaw",
        description="Operates outside the law",
    )

    assert value1.attribute == attribute
    assert value1.name == "Law Abiding"
    assert str(value1) == "Alignment: Law Abiding"

    assert attribute.values.count() == 2
    assert list(attribute.values.values_list("name", flat=True)) == [
        "Law Abiding",
        "Outlaw",
    ]


@pytest.mark.django_db
def test_attribute_value_unique_constraint():
    """Test that attribute values must be unique within an attribute."""
    attribute = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )

    ContentAttributeValue.objects.create(
        attribute=attribute,
        name="Law Abiding",
    )

    # Try to create duplicate value
    with pytest.raises(Exception):  # IntegrityError
        ContentAttributeValue.objects.create(
            attribute=attribute,
            name="Law Abiding",
        )


@pytest.mark.django_db
def test_multiple_attributes():
    """Test creating multiple attributes with values."""
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )

    alliance = ContentAttribute.objects.create(
        name="Alliance",
        is_single_select=True,
    )

    # Alignment values
    ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
    )
    ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Outlaw",
    )

    # Alliance values
    ContentAttributeValue.objects.create(
        attribute=alliance,
        name="Guild",
    )
    ContentAttributeValue.objects.create(
        attribute=alliance,
        name="Noble House",
    )
    ContentAttributeValue.objects.create(
        attribute=alliance,
        name="Criminal Organisation",
    )

    assert ContentAttribute.objects.count() == 2
    assert ContentAttributeValue.objects.count() == 5
    assert alignment.values.count() == 2
    assert alliance.values.count() == 3

