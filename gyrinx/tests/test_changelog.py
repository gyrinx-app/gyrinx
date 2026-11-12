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
def test_changelog_tag_admin_form_saves_colour_and_rejects_unknown_values(rf):
    from django.contrib import admin

    form_class = admin.site._registry[ChangelogEntryTag].get_form(rf.get("/admin/"))
    form = form_class(data={"name": "Release", "colour": "purple"})
    assert form.is_valid(), form.errors
    tag = form.save()
    assert ChangelogEntryTag.objects.get(pk=tag.pk).colour == "purple"

    invalid = form_class(data={"name": "Release", "colour": "custom"}, instance=tag)
    assert not invalid.is_valid()
    assert "colour" in invalid.errors


@pytest.mark.django_db
def test_changelog_tag_palette_matches_the_core_colours():
    from n26.core.colours import GANG_COLOURS

    assert list(ChangelogEntryTag.Colour.values) == ["default", *GANG_COLOURS]


@pytest.mark.django_db
def test_changelog_tag_admin_uses_a_native_colour_select(rf):
    from bs4 import BeautifulSoup
    from django.contrib import admin

    form_class = admin.site._registry[ChangelogEntryTag].get_form(rf.get("/admin/"))
    form = form_class(instance=ChangelogEntryTag(name="Release", colour="teal"))
    page = BeautifulSoup(str(form["colour"]), "html.parser")
    select = page.select_one('select[name="colour"]')
    assert select is not None
    assert select.select_one("option[selected]")["value"] == "teal"
    assert [option["value"] for option in select.select("option")] == list(
        ChangelogEntryTag.Colour.values
    )


def changelog_entry_form(**kwargs):
    from django.contrib import admin
    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory

    request = RequestFactory().get("/admin/")
    request.user = AnonymousUser()
    form_class = admin.site._registry[ChangelogEntry].get_form(request)
    return form_class(**kwargs)


@pytest.mark.django_db
def test_changelog_flair_round_trip_and_history():
    entry = ChangelogEntry.objects.create(
        date="2026-11-12",
        title="Release",
        flair_text="New",
        flair_colour="teal",
        flair_pulse=True,
    )
    entry.refresh_from_db()
    assert (entry.flair_text, entry.flairs[0]["colour"], entry.flair_pulse) == (
        "New",
        "teal",
        True,
    )
    assert entry.history.first().flair_text == "New"
    entry.flair_text = ""
    entry.save()
    assert entry.history.first().flair_text == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    "text,valid",
    [("", True), ("12345678901234567890", True), ("123456789012345678901", False)],
)
def test_changelog_flair_text_limit(text, valid, user):

    form = changelog_entry_form(
        data={
            "date": "2026-11-12",
            "title": "Release",
            "flair_text": text,
            "flair_colour": "default",
            "second_flair_colour": "default",
            "owner": user.pk,
        }
    )
    assert form.is_valid() is valid, form.errors
    if not valid:
        assert "flair_text" in form.errors


@pytest.mark.django_db
def test_changelog_flair_rejects_unknown_colour():
    entry = ChangelogEntry(date="2026-11-12", title="Release", flair_colour="custom")
    with pytest.raises(ValidationError) as error:
        entry.full_clean()
    assert "flair_colour" in error.value.message_dict


@pytest.mark.django_db
def test_changelog_flair_sidebar_has_no_deferred_queries(django_assert_num_queries):
    from n26.core.views.changelog import _menu_entries, _sidebar

    for index in range(8):
        ChangelogEntry.objects.create(
            date="2026-11-12",
            title=f"Release {index}",
            second_flair_text="Updated",
            second_flair_colour="violet",
            flair_text="New",
            flair_colour="teal",
            flair_pulse=True,
        )
    with django_assert_num_queries(1):
        sidebar = _sidebar(_menu_entries(None))
    assert len(sidebar) == 8
    assert all(len(item["flairs"]) == 2 for item in sidebar)
    assert all(
        item["flairs"][0]["text"] == "New" and item["flairs"][0]["pulse"]
        for item in sidebar
    )


@pytest.mark.django_db
def test_changelog_flair_is_escaped_and_optional():
    from django.template.loader import render_to_string

    entry = ChangelogEntry(
        flair_text="<b>New</b>", flair_colour="teal", flair_pulse=True
    )
    html = render_to_string("n26/_changelog_flair.html", {"entry": entry})
    assert "&lt;b&gt;New&lt;/b&gt;" in html
    assert "bg-teal-100" in html
    assert "n26-changelog-flair-pulse" in html
    entry.flair_text = ""
    assert not render_to_string("n26/_changelog_flair.html", {"entry": entry}).strip()


@pytest.mark.django_db
def test_two_changelog_flairs_keep_independent_content_colours_and_pulses():
    from django.template.loader import render_to_string

    entry = ChangelogEntry.objects.create(
        date="2026-11-12",
        title="Release",
        flair_text="New",
        flair_colour="teal",
        flair_pulse=True,
        second_flair_text="Important",
        second_flair_colour="rose",
        second_flair_pulse=False,
    )
    entry.refresh_from_db()
    assert entry.flairs == [
        {"text": "New", "colour": "teal", "pulse": True},
        {"text": "Important", "colour": "rose", "pulse": False},
    ]
    history = entry.history.first()
    assert (
        history.second_flair_text,
        history.second_flair_colour,
        history.second_flair_pulse,
    ) == ("Important", "rose", False)
    html = render_to_string("n26/_changelog_flair.html", {"entry": entry})
    assert "bg-teal-100" in html and "bg-rose-100" in html
    assert html.count("n26-changelog-flair-pulse") == 1
    entry.flair_text = ""
    entry.second_flair_pulse = True
    assert entry.flairs == [{"text": "Important", "colour": "rose", "pulse": True}]
    entry.second_flair_text = ""
    assert entry.flairs == []


@pytest.mark.django_db
@pytest.mark.parametrize("length,valid", [(20, True), (21, False)])
def test_second_changelog_flair_admin_validation(length, valid, user):
    from django import forms

    form = changelog_entry_form(
        data={
            "owner": user.pk,
            "date": "2026-11-12",
            "title": "Release",
            "flair_colour": "default",
            "second_flair_colour": "violet",
            "second_flair_text": "x" * length,
            "second_flair_active": True,
            "second_flair_pulse": True,
        }
    )
    assert isinstance(form.fields["second_flair_colour"].widget, forms.Select)
    assert form.is_valid() is valid, form.errors
    if valid:
        entry = form.save()
        assert entry.flairs == [
            {"text": "x" * length, "colour": "violet", "pulse": True}
        ]
    else:
        assert "second_flair_text" in form.errors


@pytest.mark.django_db
def test_second_changelog_flair_rejects_unknown_colour():
    entry = ChangelogEntry(
        date="2026-11-12", title="Release", second_flair_colour="custom"
    )
    with pytest.raises(ValidationError) as error:
        entry.full_clean()
    assert "second_flair_colour" in error.value.message_dict


@pytest.mark.django_db
def test_flair_active_checkboxes_hide_each_flair_independently():
    entry = ChangelogEntry(flair_text="New", second_flair_text="Preview")
    entry.flair_active = False
    assert [flair["text"] for flair in entry.flairs] == ["Preview"]
    entry.second_flair_active = False
    assert entry.flairs == []
    entry.flair_active = True
    assert [flair["text"] for flair in entry.flairs] == ["New"]


@pytest.mark.django_db
def test_flair_active_admin_saves_independently_and_preserves_content(user):

    entry = ChangelogEntry.objects.create(
        owner=user,
        date="2026-11-12",
        title="Release",
        flair_text="New",
        flair_colour="teal",
        flair_pulse=True,
        second_flair_text="Preview",
        second_flair_colour="violet",
    )
    data = dict(
        owner=user.pk,
        date="2026-11-12",
        title="Release",
        flair_text="New",
        flair_colour="teal",
        flair_pulse=True,
        second_flair_text="Preview",
        second_flair_colour="violet",
        flair_active=False,
        second_flair_active=True,
    )
    form = changelog_entry_form(instance=entry, data=data)
    assert form.is_valid(), form.errors
    entry = form.save()
    entry.refresh_from_db()
    assert [flair["text"] for flair in entry.flairs] == ["Preview"]
    assert not entry.history.first().flair_active
    data.update(flair_active=True, second_flair_active=False)
    form = changelog_entry_form(instance=entry, data=data)
    assert form.is_valid(), form.errors
    entry = form.save()
    entry.refresh_from_db()
    assert entry.flairs == [{"text": "New", "colour": "teal", "pulse": True}]
    assert entry.second_flair_text == "Preview"
    assert entry.second_flair_colour == "violet"
