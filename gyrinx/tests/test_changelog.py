import pytest
from django.db import IntegrityError

from gyrinx.site.models import ChangelogEntry, ChangelogEntryTag


@pytest.mark.django_db
def test_changelog_entry_tags_round_trip():
    tag = ChangelogEntryTag.objects.create(name="N26")
    entry = ChangelogEntry.objects.create(date="2026-08-08", title="Tagging ships")

    entry.tags.add(tag)

    assert list(entry.tags.values_list("name", flat=True)) == ["N26"]
    assert list(tag.entries.all()) == [entry]


@pytest.mark.django_db
def test_changelog_entry_tag_names_are_unique():
    ChangelogEntryTag.objects.create(name="N26")
    with pytest.raises(IntegrityError):
        ChangelogEntryTag.objects.create(name="N26")
