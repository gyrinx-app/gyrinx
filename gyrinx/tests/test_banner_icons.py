"""Banner icon keys, edition mappings and legacy migration coverage.

N26 rendering is tested in n26/tests/test_platform_integration.py because
platform tests must not import edition code.
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
        """Platform templates place this value directly in a class attribute."""
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
        """Django adds the empty option for blank=True fields."""
        assert "" not in dict(banner_icons.CHOICES)

    @pytest.mark.parametrize("key", ["nonsense", "", None, "bi-info-circle"])
    def test_the_lookups_are_total(self, key):
        """Unknown keys and legacy Bootstrap classes resolve to no icon."""
        assert banner_icons.bootstrap_class(key) == ""
        assert banner_icons.n26_name(key) == ""

    def test_a_known_key_resolves_in_both_sets(self):
        assert banner_icons.bootstrap_class("warning") == "bi-exclamation-triangle"
        assert banner_icons.n26_name("warning") == "triangle-alert"


@pytest.mark.django_db
class TestTheModel:
    def test_the_property_resolves_the_key(self):
        banner = Banner.objects.create(
            text="Scheduled maintenance.", icon="maintenance"
        )
        assert banner.bootstrap_icon == "bi-gear"

    def test_a_banner_with_no_icon_has_no_class(self):
        """A blank icon must suppress the template's icon element."""
        banner = Banner.objects.create(text="Quietly.", icon="")
        assert banner.bootstrap_icon == ""

    def test_the_admin_gets_a_select_box(self):
        """Field choices provide the admin select widget."""
        field = Banner._meta.get_field("icon")
        assert field.choices
        assert field.formfield().widget.__class__.__name__ == "Select"


class TestTheLegacyMigration:
    """Test migration maps directly because the suite runs with --nomigrations."""

    def test_the_value_prod_was_running_becomes_news(self):
        """Map the legacy quotation icon to the news key."""
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
        """Every current key needs a reverse mapping to avoid silently clearing it."""
        keys = {entry.key for entry in banner_icons.BANNER_ICONS}
        assert set(MIGRATION.BOOTSTRAP_BY_KEY) == keys

    def test_the_reverse_map_agrees_with_the_table(self):
        for entry in banner_icons.BANNER_ICONS:
            assert MIGRATION.BOOTSTRAP_BY_KEY[entry.key] == entry.bootstrap

    def test_going_back_and_forward_returns_the_same_key(self):
        """Preserve semantic keys across reversal and reapplication, even when legacy classes merge."""
        for entry in banner_icons.BANNER_ICONS:
            back = MIGRATION.BOOTSTRAP_BY_KEY[entry.key]
            assert MIGRATION.LEGACY_KEYS[back] == entry.key
