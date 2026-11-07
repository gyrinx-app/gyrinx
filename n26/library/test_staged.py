"""Verify staging fields, selectable querysets, access checks and authoring operations.

Player-facing integration coverage is in n26/tests/sandbox/test_staged_content.py.
"""

import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import ValidationError

from n26.library.authoring import (
    create_category,
    create_gang_type,
    create_skill,
    create_weapon,
    put_live,
    put_selected_live,
    stage,
)
from n26.library.models import (
    Category,
    Collection,
    CollectionEntry,
    GangType,
    Modifier,
    Pickable,
    PicklistMember,
    Profile,
    Rule,
    Skill,
    Trait,
    Weapon,
    WeaponProfile,
)
from n26.library.staged import (
    content_kinds,
    sees_staged,
    stageable,
    stageable_kinds,
    staged_count,
    staged_rows,
)

pytestmark = pytest.mark.django_db


class TestTheQuerysetGate:
    """Discovery excludes staged content unless the caller permits it."""

    @pytest.fixture
    def weapons(self, default_pack):
        live = create_weapon("Lasgun", price=15)
        held = stage(create_weapon("Plasma caliver", price=90))
        return live, held

    def test_live_drops_what_is_staged(self, weapons):
        live, held = weapons
        assert list(Weapon.objects.live()) == [live]

    def test_selectable_drops_what_is_staged_by_default(self, weapons):
        live, held = weapons
        assert list(Weapon.objects.selectable()) == [live]

    def test_selectable_keeps_it_for_a_reader_who_may_see_it(self, weapons):
        live, held = weapons
        assert set(Weapon.objects.selectable(include_staged=True)) == {live, held}

    def test_the_plain_manager_still_returns_everything(self, weapons):
        """No implicit filtering: a card following a foreign key to a staged
        weapon must resolve it, exactly as it resolves an archived one."""
        assert Weapon.objects.count() == 2

    def test_archived_content_stays_out_whoever_is_looking(self, weapons):
        live, held = weapons
        live.archive()
        assert list(Weapon.objects.selectable(include_staged=True)) == [held]


class TestWhoSeesStagedContent:
    @pytest.fixture
    def flag(self, db):
        from gyrinx.site.models import Availability, FeatureFlag
        from n26.flags import STAGED_CONTENT

        def _flag(availability, group=None):
            return FeatureFlag.objects.create(
                slug=STAGED_CONTENT,
                name="Staged content",
                availability=availability,
                group=group,
            )

        return _flag, Availability

    def test_nobody_signed_in_never_does(self):
        assert sees_staged(None) is False
        assert sees_staged(AnonymousUser()) is False

    def test_a_player_does_not_until_a_flag_says_so(self):
        assert sees_staged(User.objects.create_user("player")) is False

    def test_staff_always_do(self):
        assert sees_staged(User.objects.create_user("author", is_staff=True)) is True

    def test_a_flag_that_is_off_opens_nothing(self, flag):
        make, availability = flag
        make(availability.OFF)
        assert sees_staged(User.objects.create_user("player")) is False

    def test_the_allowlist_opens_it_to_the_group_and_nobody_else(self, flag):
        make, availability = flag
        group = Group.objects.create(name="Testers")
        make(availability.ALLOWLIST, group=group)
        tester = User.objects.create_user("tester")
        tester.groups.add(group)
        assert sees_staged(tester) is True
        assert sees_staged(User.objects.create_user("player")) is False

    def test_open_to_everyone_means_every_signed_in_reader(self, flag):
        make, availability = flag
        make(availability.EVERYONE)
        assert sees_staged(User.objects.create_user("player")) is True
        assert sees_staged(AnonymousUser()) is False

    def test_the_flag_is_read_once_per_user(self, django_assert_num_queries):
        """A screen asks several times; the second time is free."""
        player = User.objects.create_user("player")
        sees_staged(player)
        with django_assert_num_queries(0):
            assert sees_staged(player) is False


class TestWhichKindsCanBeStaged:
    """Only kinds a player is offered somewhere — read off the registries
    that offer them, never listed by hand."""

    def test_the_kinds_players_are_offered(self):
        kinds = stageable_kinds()
        assert {GangType, Profile, Weapon, WeaponProfile, Skill, Pickable} <= kinds
        # Offered to tick on a model's own page.
        assert Rule in kinds

    def test_the_lines_that_offer_a_thing_count_too(self):
        """A new line on a live list is what puts a live thing in front of a
        player, so an import holds the lines back along with the things."""
        assert {CollectionEntry, PicklistMember} <= stageable_kinds()

    def test_a_screen_shown_to_a_player_counts_and_so_does_its_attachment(self):
        """An interstitial is put in front of a player by the slot it is
        attached to, so an author can draft one against a live slot and
        hold it back until it reads right."""
        from n26.library.models import Interstitial, InterstitialSlot

        assert {Interstitial, InterstitialSlot} <= stageable_kinds()

    def test_not_the_kinds_reached_only_through_them(self):
        assert not stageable(Category)
        assert not stageable(Modifier)
        assert not stageable(Trait)
        assert not stageable(Collection)

    def test_every_content_kind_carries_the_column(self):
        kinds = content_kinds()
        assert len(kinds) >= 30
        assert all(kind._meta.get_field("staged") for kind in kinds)
        assert set(stageable_kinds()) <= set(kinds)


class TestTheVerbs:
    def test_stage_and_put_live_move_one_row(self, default_pack):
        lasgun = create_weapon("Lasgun")
        assert lasgun.staged is False
        stage(lasgun)
        assert Weapon.objects.get(pk=lasgun.pk).staged is True
        put_live(lasgun)
        assert Weapon.objects.get(pk=lasgun.pk).staged is False

    def test_selected_content_goes_live_across_kinds(self, default_pack):
        weapon = stage(create_weapon("Lasgun"))
        skill = stage(create_skill("Parry"))
        held = stage(create_gang_type("Ash Wastes Nomads"))
        already = create_weapon("Stub gun")

        assert put_selected_live([f"weapon:{weapon.pk}", f"skill:{skill.pk}"]) == 2

        assert not Weapon.objects.filter(staged=True).exists()
        assert not Skill.objects.filter(staged=True).exists()
        assert GangType.objects.get(pk=held.pk).staged is True
        assert Weapon.objects.get(pk=already.pk).staged is False

    def test_empty_selection_is_refused(self, default_pack):
        held = stage(create_weapon("Lasgun"))
        with pytest.raises(ValidationError, match="Select content"):
            put_selected_live([])
        assert Weapon.objects.get(pk=held.pk).staged is True

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "all",
            "weapon:x",
            "contentpack:x",
            "unknown:x",
            "weapon:01AAAAAAAAAAAAAAAAAAAAAAAA",
        ],
    )
    def test_invalid_selection_releases_nothing(self, default_pack, bad):
        held = stage(create_gang_type("Nomads"))
        with pytest.raises(ValidationError):
            put_selected_live([f"gangtype:{held.pk}", bad])
        assert GangType.objects.get(pk=held.pk).staged is True

    def test_duplicate_and_repeated_selections_are_harmless(self, default_pack):
        held = stage(create_weapon("Lasgun"))
        selection = [f"weapon:{held.pk}"] * 2
        assert put_selected_live(selection) == 1
        assert put_selected_live(selection) == 0

    def test_a_later_update_failure_rolls_back_the_whole_selection(
        self, default_pack, monkeypatch
    ):
        weapon = stage(create_weapon("Lasgun"))
        skill = stage(create_skill("Parry"))
        from n26.library.models.base import ContentQuerySet

        update = ContentQuerySet.update

        def fail_on_weapon(queryset, **kwargs):
            if queryset.model is Weapon:
                raise RuntimeError("Release failed")
            return update(queryset, **kwargs)

        monkeypatch.setattr(ContentQuerySet, "update", fail_on_weapon)
        with pytest.raises(RuntimeError, match="Release failed"):
            put_selected_live([f"skill:{skill.pk}", f"weapon:{weapon.pk}"])
        assert Skill.objects.get(pk=skill.pk).staged is True
        assert Weapon.objects.get(pk=weapon.pk).staged is True

    def test_the_listing_groups_staged_rows_by_kind(self, default_pack):
        parry = stage(create_skill("Parry"))
        lasgun = stage(create_weapon("Lasgun"))
        create_weapon("Stub gun")
        create_category("Skills", "Combat")

        listed = staged_rows()

        assert [(model, rows) for model, rows in listed] == [
            (Skill, [parry]),
            (Weapon, [lasgun]),
        ]
        assert staged_count() == 2
