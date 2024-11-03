# The content import process is an upsert:
#   - if the object already exists, it is updated
#   - if it does not exist, it is created
#
# The complexity is that content can have fields added or removed, so we need
# to be able to handle that.

from pathlib import Path

import pytest

from gyrinx.content.management.imports import ImportConfig, Importer
from gyrinx.content.management.utils import by_label, data_for_type, gather_data
from gyrinx.content.models import ContentCategory, ContentHouse


# Let's make some mock data to test with.
def make_data_sources(dir="content"):
    return gather_data(Path(__file__).parent / "fixtures" / dir)


def test_basic():
    data_sources = make_data_sources()
    assert data_sources
    assert len(data_for_type("fighter", data_sources)) > 0


@pytest.mark.django_db
def test_import_simple_house():
    ic = ImportConfig(
        source="house",
        id=lambda x: x["name"],
        model=ContentHouse,
        fields=lambda x: {
            "name": by_label(ContentHouse.Choices, x["name"]),
        },
    )

    imp = Importer(
        ruleset_dir=Path(__file__).parent / "fixtures/content",
        directory="fixtures/content",
        dry_run=False,
    )

    imp.do(ic, make_data_sources())

    assert ContentHouse.objects.count() == 1
    assert ContentHouse.objects.first().name == ContentHouse.Choices.SQUAT_PROSPECTORS


@pytest.mark.django_db
def test_import_simple_multiple():
    ic_house = ImportConfig(
        source="house",
        id=lambda x: x["name"],
        model=ContentHouse,
        fields=lambda x: {
            "name": by_label(ContentHouse.Choices, x["name"]),
        },
    )
    ic_category = ImportConfig(
        source="category",
        id=lambda x: x["name"],
        model=ContentCategory,
        fields=lambda x: {
            "name": by_label(ContentCategory.Choices, x["name"]),
        },
    )

    imp = Importer(
        ruleset_dir=Path(__file__).parent / "fixtures/content",
        directory="fixtures/content",
        dry_run=False,
    )

    dss = make_data_sources()
    imp.do(ic_house, dss)
    imp.do(ic_category, dss)

    assert ContentHouse.objects.count() == 1
    assert ContentHouse.objects.first().name == ContentHouse.Choices.SQUAT_PROSPECTORS
    assert ContentCategory.objects.count() == 3
    assert ContentCategory.objects.filter(name=ContentCategory.Choices.LEADER).exists()
    assert ContentCategory.objects.filter(
        name=ContentCategory.Choices.CHAMPION
    ).exists()
    assert ContentCategory.objects.filter(name=ContentCategory.Choices.GANGER).exists()


@pytest.mark.django_db
def test_import_removal():
    ic_category = ImportConfig(
        source="category",
        id=lambda x: x["name"],
        model=ContentCategory,
        fields=lambda x: {
            "name": by_label(ContentCategory.Choices, x["name"]),
        },
    )

    imp = Importer(
        ruleset_dir=Path(__file__).parent / "fixtures/content",
        directory="fixtures/content",
        dry_run=False,
    )

    dss = make_data_sources()
    dss_removal = make_data_sources("content_with_removals")
    imp.do(ic_category, dss)
    with pytest.raises(
        ValueError,
        match="Data sources do not match existing objects: something was removed and allow_removal is False.",
    ):
        imp.do(ic_category, dss_removal)


@pytest.mark.django_db
def test_import_removal_allowed():
    ic_category = ImportConfig(
        source="category",
        id=lambda x: x["name"],
        model=ContentCategory,
        fields=lambda x: {
            "name": by_label(ContentCategory.Choices, x["name"]),
        },
        allow_removal=True,
    )

    imp = Importer(
        ruleset_dir=Path(__file__).parent / "fixtures/content",
        directory="fixtures/content",
        dry_run=False,
    )

    dss = make_data_sources()
    dss_removal = make_data_sources("content_with_removals")
    imp.do(ic_category, dss)
    imp.do(ic_category, dss_removal)

    assert ContentCategory.objects.count() == 2


@pytest.mark.django_db
def test_import_changed_name():
    ic_category = ImportConfig(
        source="category",
        id=lambda x: x["name"],
        model=ContentCategory,
        fields=lambda x: {
            "name": by_label(ContentCategory.Choices, x["name"]),
        },
    )

    imp = Importer(
        ruleset_dir=Path(__file__).parent / "fixtures/content",
        directory="fixtures/content",
        dry_run=False,
    )

    dss = make_data_sources()
    dss_changes = make_data_sources("content_with_changes")
    imp.do(ic_category, dss)
    with pytest.raises(
        ValueError,
        match="Data sources do not match existing objects: an ID field has changed.",
    ):
        imp.do(ic_category, dss_changes)

    assert ContentCategory.objects.count() == 3


# TODO: Test for adding fields to an object that already exists. This will only work
#       on fighters. There could also be a flag to allow this or not.

# TODO: Think about error handling, and make sure errors are properly handled. Partial imports
#       should not be allowed.
