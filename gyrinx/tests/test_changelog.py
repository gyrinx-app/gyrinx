import pytest
from django.core.exceptions import ValidationError
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


@pytest.mark.django_db
def test_changelog_tag_colour_defaults_and_history():
    tag = ChangelogEntryTag.objects.create(name="Release")
    assert tag.colour == "default"
    tag.colour = "teal"
    tag.save()
    tag.refresh_from_db()
    assert tag.colour == "teal"
    assert list(tag.history.values_list("colour", flat=True)) == ["teal", "default"]


@pytest.mark.django_db
def test_changelog_tag_colour_rejects_unknown_values():
    tag = ChangelogEntryTag(name="Release", colour="custom")
    with pytest.raises(ValidationError) as error:
        tag.full_clean()
    assert "colour" in error.value.message_dict


@pytest.mark.django_db
def test_changelog_tag_admin_form_saves_colour_and_rejects_unknown_values():
    from gyrinx.site.admin import ChangelogEntryTagForm
    from gyrinx.site.widgets import ChangelogTagColourSelect

    form = ChangelogEntryTagForm(data={"name": "Release", "colour": "purple"})
    assert isinstance(form.fields["colour"].widget, ChangelogTagColourSelect)
    assert form.is_valid(), form.errors
    tag = form.save()
    assert ChangelogEntryTag.objects.get(pk=tag.pk).colour == "purple"

    invalid = ChangelogEntryTagForm(
        data={"name": "Release", "colour": "custom"}, instance=tag
    )
    assert not invalid.is_valid()
    assert "colour" in invalid.errors


@pytest.mark.django_db
def test_changelog_tag_palette_matches_the_core_colours():
    from n26.core.colours import GANG_COLOURS

    assert list(ChangelogEntryTag.Colour.values) == ["default", *GANG_COLOURS]


@pytest.mark.django_db
def test_changelog_tag_admin_widget_keeps_a_native_select_for_fallback():
    from bs4 import BeautifulSoup

    from gyrinx.site.admin import ChangelogEntryTagForm

    form = ChangelogEntryTagForm(
        instance=ChangelogEntryTag(name="Release", colour="teal")
    )
    page = BeautifulSoup(str(form["colour"]), "html.parser")
    select = page.select_one('select[name="colour"]')
    assert select is not None
    assert select.select_one("option[selected]")["value"] == "teal"
    assert [option["value"] for option in select.select("option")] == list(
        ChangelogEntryTag.Colour.values
    )
    assert page.select_one('template [role="listbox"]') is not None
