"""The site banner's icon keys, and the way out of the old free-text field.

Banner.icon used to hold a Bootstrap Icons class typed into a text box. That
worked while Bootstrap was the only thing reading it and broke the moment a
second edition rendered the same row — n26's icon registry raises on a name it
does not have, so a banner set to bi-blockquote-left 500'd every page of that
edition. The column now holds a meaning, and each edition draws it.

The n26 half of the table is checked in n26/tests/test_platform_integration.py,
which may import an edition package; this module may not.
"""

from importlib import import_module

import pytest

from gyrinx.site import icons as banner_icons
from gyrinx.site.models import Banner

MIGRATION = import_module("gyrinx.site.migrations.0004_banner_icon_keys")


class TestTheTable:
    def test_keys_are_unique(self):
        keys = [entry.key for entry in banner_icons.BANNER_ICONS]
        assert len(keys) == len(set(keys))

    def test_every_key_names_a_bootstrap_class(self):
        """The platform's own templates interpolate this straight into a
        class attribute, so it has to look like one."""
        wrong = [
            entry.key
            for entry in banner_icons.BANNER_ICONS
            if not entry.bootstrap.startswith("bi-")
        ]
        assert not wrong

    def test_choices_offer_every_key_and_nothing_else(self):
        assert banner_icons.CHOICES == [
            (entry.key, entry.label) for entry in banner_icons.BANNER_ICONS
        ]

    def test_there_is_no_blank_choice(self):
        """The field is blank=True, so Django supplies the empty option
        itself; a second one would show two ways to say no icon."""
        assert "" not in dict(banner_icons.CHOICES)

    @pytest.mark.parametrize("key", ["nonsense", "", None, "bi-info-circle"])
    def test_the_lookups_are_total(self, key):
        """Including a leftover Bootstrap class, which is exactly what a
        row written before this change holds."""
        assert banner_icons.bootstrap_class(key) == ""
        assert banner_icons.n26_name(key) == ""

    def test_a_known_key_resolves_in_both_sets(self):
        assert banner_icons.bootstrap_class("warning") == "bi-exclamation-triangle"
        assert banner_icons.n26_name("warning") == "exclamation-triangle"


@pytest.mark.django_db
class TestTheModel:
    def test_the_property_resolves_the_key(self):
        banner = Banner.objects.create(
            text="Scheduled maintenance.", icon="maintenance"
        )
        assert banner.bootstrap_icon == "bi-gear"

    def test_a_banner_with_no_icon_has_no_class(self):
        """The platform template guards on this, so "" has to mean "draw
        nothing" rather than "draw an empty <i>"."""
        banner = Banner.objects.create(text="Quietly.", icon="")
        assert banner.bootstrap_icon == ""

    def test_the_admin_gets_a_select_box(self):
        """The whole point of the change: choices on the field is what
        makes the default widget a select rather than a text input."""
        field = Banner._meta.get_field("icon")
        assert field.choices
        assert field.formfield().widget.__class__.__name__ == "Select"


class TestTheLegacyMigration:
    """The data migration's maps, tested directly. Tests run
    --nomigrations, so the migration itself never executes here."""

    def test_the_value_prod_was_running_becomes_news(self):
        """bi-blockquote-left: a "we have news" banner wearing a
        quotation mark, because the free-text field offered nothing
        better. This is the row that took n26 down."""
        assert MIGRATION.LEGACY_KEYS["bi-blockquote-left"] == "news"

    def test_every_legacy_value_maps_to_a_real_key(self):
        keys = {entry.key for entry in banner_icons.BANNER_ICONS}
        unknown = {
            source: target
            for source, target in MIGRATION.LEGACY_KEYS.items()
            if target not in keys
        }
        assert not unknown

    def test_the_reverse_map_covers_every_key(self):
        """Otherwise reversing the migration silently blanks whichever
        key it forgot."""
        keys = {entry.key for entry in banner_icons.BANNER_ICONS}
        assert set(MIGRATION.BOOTSTRAP_BY_KEY) == keys

    def test_the_reverse_map_agrees_with_the_table(self):
        for entry in banner_icons.BANNER_ICONS:
            assert MIGRATION.BOOTSTRAP_BY_KEY[entry.key] == entry.bootstrap

    def test_going_back_and_forward_returns_the_same_key(self):
        """Not every old class survives the round trip — several
        collapsed onto one key — but every *key* must."""
        for entry in banner_icons.BANNER_ICONS:
            back = MIGRATION.BOOTSTRAP_BY_KEY[entry.key]
            assert MIGRATION.LEGACY_KEYS[back] == entry.key
