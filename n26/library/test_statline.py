"""Statline tests, simulating a small 'Person' statline type."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.library.models import (
    GangType,
    Profile,
    ProfileType,
    Stat,
    Statline,
    StatlineStat,
    StatlineType,
    StatlineTypeStat,
)

pytestmark = pytest.mark.django_db


class TestGangType:
    def test_has_a_name(self, default_pack):
        assert str(GangType.objects.create(name="Escher")) == "Escher"

    def test_lands_in_the_default_pack(self):
        assert GangType.objects.create(name="Escher").pack.slug == "n26"

    def test_name_is_unique_per_pack_case_insensitively(self, homebrew):
        GangType.objects.create(name="Escher")
        with pytest.raises(IntegrityError), transaction.atomic():
            GangType.objects.create(name="escher")

    def test_the_same_name_may_exist_in_another_pack(self, homebrew):
        GangType.objects.create(name="Escher")
        GangType.objects.create(name="Escher", pack=homebrew)
        assert GangType.objects.filter(name__iexact="escher").count() == 2


class TestStat:
    def test_field_name_is_derived_from_the_full_name(self, make_stat):
        stat = make_stat("Fr", "Front Toughness")
        assert stat.field_name == "front_toughness"

    def test_an_explicit_field_name_is_respected(self):
        stat = Stat.objects.create(
            short_name="M", full_name="Movement", field_name="move"
        )
        assert stat.field_name == "move"

    def test_str_shows_both_names(self, make_stat):
        assert str(make_stat("M", "Movement")) == "M (Movement)"

    @pytest.mark.parametrize(
        ("flags", "raw", "expected"),
        [
            ({"is_inches": True}, "4", '4"'),
            ({"is_inches": True}, '4"', '4"'),
            ({"is_target": True}, "3", "3+"),
            ({"is_target": True}, "3+", "3+"),
            ({"is_modifier": True}, "2", "+2"),
            ({"is_modifier": True}, "+2", "+2"),
            ({"is_modifier": True}, "-2", "-2"),
            ({}, "5", "5"),
            # Non-numeric values pass through untouched.
            ({"is_inches": True}, "D6", "D6"),
            ({"is_target": True}, "*", "*"),
            # Absent values normalise to a dash.
            ({}, "", "-"),
            ({}, "-", "-"),
            ({"is_inches": True}, "  ", "-"),
            # Smart quotes are straightened.
            ({"is_inches": True}, "4”", '4"'),
        ],
    )
    def test_format_value(self, make_stat, flags, raw, expected):
        stat = make_stat("X", "Example", **flags)
        assert stat.format_value(raw) == expected

    @pytest.mark.parametrize(
        ("flags", "expected"),
        [
            ({"is_inches": True}, '4"'),
            ({"is_target": True}, "3+"),
            ({"is_modifier": True}, "+1"),
            ({}, "3"),
        ],
    )
    def test_placeholder(self, make_stat, flags, expected):
        assert make_stat("X", "Example", **flags).placeholder == expected

    def test_field_name_is_unique_per_pack(self, make_stat):
        make_stat("M", "Movement")
        with pytest.raises(IntegrityError), transaction.atomic():
            make_stat("Mv", "Movement")


class TestStatlineType:
    def test_stats_come_back_in_position_order(self, person_statline_type):
        assert person_statline_type.field_names == [
            "movement",
            "weapon_skill",
            "toughness",
        ]

    def test_a_stat_may_appear_only_once_in_a_type(
        self, person_statline_type, make_stat
    ):
        existing = person_statline_type.stats.first().stat
        with pytest.raises(IntegrityError), transaction.atomic():
            StatlineTypeStat.objects.create(
                statline_type=person_statline_type, stat=existing, position=9
            )

    def test_a_stat_may_be_reused_across_types(self, person_statline_type):
        movement = person_statline_type.stats.first().stat
        vehicle = StatlineType.objects.create(name="Vehicle")
        StatlineTypeStat.objects.create(
            statline_type=vehicle, stat=movement, position=0
        )
        assert movement.statline_type_stats.count() == 2

    def test_type_stat_proxies_the_stat_names(self, person_statline_type):
        type_stat = person_statline_type.stats.first()
        assert (type_stat.short_name, type_stat.full_name) == ("M", "Movement")


class TestProfileType:
    def test_fixes_the_statline_shape(self, person_type, person_statline_type):
        assert person_type.statline_type == person_statline_type

    def test_str_is_the_name(self, person_type):
        assert str(person_type) == "Fighter"


class TestProfile:
    def test_has_name_type_and_rating(self, person_type, gang_type):
        profile = Profile.objects.create(
            name="Juve", profile_type=person_type, gang_type=gang_type, price=25
        )
        assert (profile.name, profile.price) == ("Juve", 25)
        assert profile.profile_type == person_type

    def test_rating_defaults_to_zero(self, make_profile):
        assert make_profile("Juve").price == 0

    def test_rating_rejects_negatives(self, make_profile):
        profile = make_profile("Juve")
        profile.price = -1
        with pytest.raises(ValidationError):
            profile.full_clean()

    def test_gang_type_is_required(self, person_type):
        with pytest.raises(IntegrityError), transaction.atomic():
            Profile.objects.create(name="Stray", profile_type=person_type)

    def test_belongs_to_a_gang_type(self, make_profile, gang_type):
        profile = make_profile("Juve")
        assert profile.gang_type == gang_type
        assert list(gang_type.profiles.all()) == [profile]

    def test_a_gang_type_holds_many_profiles(self, make_profile, gang_type, names):
        make_profile("Juve")
        make_profile("Ganger")
        other = GangType.objects.create(name="Goliath")
        make_profile("Bruiser", gang_type=other)
        assert names(gang_type.profiles.all()) == ["Ganger", "Juve"]
        assert names(other.profiles.all()) == ["Bruiser"]

    def test_gang_type_is_protected_from_deletion_while_referenced(
        self, make_profile, gang_type
    ):
        from django.db.models import ProtectedError

        make_profile("Juve")
        with pytest.raises(ProtectedError):
            gang_type.delete()

    def test_a_profile_may_take_a_gang_type_from_another_pack(
        self, make_profile, homebrew
    ):
        """Cross-pack references are not blocked — see the README."""
        goliath = GangType.objects.create(name="Goliath", pack=homebrew)
        assert make_profile("Juve", gang_type=goliath).gang_type.pack == homebrew

    def test_statline_type_comes_from_the_profile_type(
        self, make_profile, person_statline_type
    ):
        assert make_profile("Juve").statline_type == person_statline_type

    def test_has_no_statline_by_default(self, make_profile):
        profile = make_profile("Juve")
        assert profile.has_statline is False
        assert profile.stats() == {}

    def test_profile_type_is_protected_from_deletion(self, make_profile, person_type):
        from django.db.models import ProtectedError

        make_profile("Juve")
        with pytest.raises(ProtectedError):
            person_type.delete()


class TestStatline:
    def test_values_render_through_each_stat_display_rule(
        self, make_profile, make_statline
    ):
        profile = make_profile("Juve")
        make_statline(profile, movement=4, weapon_skill=3, toughness=5)
        assert profile.stats() == {
            "movement": '4"',
            "weapon_skill": "3+",
            "toughness": "5",
        }

    def test_stats_are_ordered_by_position(self, make_profile, make_statline):
        profile = make_profile("Juve")
        statline = make_statline(profile, toughness=5, movement=4, weapon_skill=3)
        assert list(statline.as_dict()) == ["movement", "weapon_skill", "toughness"]

    def test_statline_type_is_derived_not_stored(self, make_profile, make_statline):
        """It cannot drift from the profile type — there is nothing to drift."""
        profile = make_profile("Juve")
        statline = make_statline(profile, movement=4)
        assert statline.statline_type == profile.profile_type.statline_type
        assert not hasattr(Statline, "statline_type_id")

    def test_one_statline_per_profile(self, make_profile, make_statline):
        profile = make_profile("Juve")
        make_statline(profile, movement=4)
        with pytest.raises(IntegrityError), transaction.atomic():
            Statline.objects.create(profile=profile)

    def test_a_stat_may_appear_once_per_statline(self, make_profile, make_statline):
        profile = make_profile("Juve")
        statline = make_statline(profile, movement=4)
        movement = profile.statline_type.stats.first()
        with pytest.raises(IntegrityError), transaction.atomic():
            StatlineStat.objects.create(
                statline=statline, statline_type_stat=movement, value="6"
            )

    def test_empty_values_render_as_a_dash(self, make_profile, make_statline):
        profile = make_profile("Juve")
        make_statline(profile, movement="", weapon_skill="-", toughness=5)
        assert profile.stats() == {
            "movement": "-",
            "weapon_skill": "-",
            "toughness": "5",
        }

    def test_str_names_the_profile(self, make_profile, make_statline):
        profile = make_profile("Juve")
        assert str(make_statline(profile, movement=4)) == "Juve statline"


class TestStatlineValidation:
    def test_a_complete_statline_validates(self, make_profile, make_statline):
        profile = make_profile("Juve")
        statline = make_statline(profile, movement=4, weapon_skill=3, toughness=5)
        statline.full_clean()

    def test_a_missing_stat_is_reported(self, make_profile, make_statline):
        profile = make_profile("Juve")
        statline = make_statline(profile, movement=4)
        with pytest.raises(ValidationError) as excinfo:
            statline.clean()
        assert "Weapon Skill" in str(excinfo.value)
        assert "Toughness" in str(excinfo.value)

    def test_validation_is_skipped_before_the_first_save(self, make_profile):
        """Stats are attached after the statline exists, so this must not raise."""
        Statline(profile=make_profile("Juve")).clean()

    def test_a_stat_from_another_statline_type_is_rejected(
        self, make_profile, make_statline, make_stat
    ):
        profile = make_profile("Juve")
        statline = make_statline(profile, movement=4)
        vehicle = StatlineType.objects.create(name="Vehicle")
        foreign = StatlineTypeStat.objects.create(
            statline_type=vehicle, stat=make_stat("Hp", "Hull Points"), position=0
        )
        stray = StatlineStat(statline=statline, statline_type_stat=foreign, value="3")
        with pytest.raises(ValidationError) as excinfo:
            stray.clean()
        assert "Hull Points" in str(excinfo.value)

    def test_a_stray_stat_is_reported_by_the_statline(
        self, make_profile, make_statline, make_stat
    ):
        profile = make_profile("Juve")
        statline = make_statline(profile, movement=4, weapon_skill=3, toughness=5)
        vehicle = StatlineType.objects.create(name="Vehicle")
        foreign = StatlineTypeStat.objects.create(
            statline_type=vehicle, stat=make_stat("Hp", "Hull Points"), position=0
        )
        StatlineStat.objects.create(
            statline=statline, statline_type_stat=foreign, value="3"
        )
        with pytest.raises(ValidationError, match="Hull Points"):
            statline.clean()


class TestStatlinesArePackScoped:
    def test_a_pack_can_define_its_own_statline_type(self, homebrew, make_stat):
        """Nothing is global — a pack brings its own stats and shapes."""
        stat = Stat.objects.create(short_name="Sn", full_name="Sneak", pack=homebrew)
        statline_type = StatlineType.objects.create(name="Sneaker", pack=homebrew)
        StatlineTypeStat.objects.create(
            statline_type=statline_type, stat=stat, position=0, pack=homebrew
        )
        # A pack brings its own shape; the Type is still one of two.
        profile_type = ProfileType.objects.create(
            name="Fighter", statline_type=statline_type, pack=homebrew
        )
        profile = Profile.objects.create(
            name="Shadow",
            profile_type=profile_type,
            gang_type=GangType.objects.create(name="Delaque", pack=homebrew),
            pack=homebrew,
        )
        Statline.objects.create(profile=profile, pack=homebrew)
        StatlineStat.objects.create(
            statline=profile.statline,
            statline_type_stat=statline_type.stats.first(),
            value="7",
            pack=homebrew,
        )
        assert profile.stats() == {"sneak": "7"}

    def test_default_manager_still_returns_everything(
        self, homebrew, make_profile, names
    ):
        make_profile("Base")
        assert Statline.objects.count() == 0
        assert names(Profile.objects.all()) == ["Base"]
