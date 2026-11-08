"""Verify weapon-profile authoring for built-in sets. A weapon-member URL identifies its
anchor directly; a set URL first selects a weapon. Set-level additions anchor to one
matching member, remain unanchored when none exists, and refuse ambiguous duplicate
weapons.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.library.models import DefaultAssignment, WeaponProfile
from n26.tests.sandbox.actions import (
    add_built_in,
    create_default_set,
    create_profile,
    create_weapon,
    offer_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def launcher(default_pack):
    weapon = create_weapon("Launcher", profiles=[("Frag", 0)])
    WeaponProfile.objects.create(name="Smoke", weapon=weapon, price=10, position=1)
    WeaponProfile.objects.create(name="Choke", weapon=weapon, price=15, position=2)
    return weapon


@pytest.fixture
def gunner(person_type, gang_type, launcher, default_pack):
    profile = create_profile("Gunner", person_type, gang_type, price=50)
    add_built_in(profile, launcher)
    return profile


def gun_member_of(carrier):
    return carrier.built_ins.members.get(weapon__isnull=False)


class TestTheGunMembersOwnPage:
    """Use the weapon member in the URL to anchor added profiles to the intended copy."""

    def test_it_lists_the_priced_lines_and_not_the_free_ones(
        self, client, author, gunner
    ):
        page = client.get(
            reverse("authoring-built-in-profiles", args=[gun_member_of(gunner).pk])
        )
        text = page.content.decode()
        assert "Smoke" in text
        assert "Choke" in text
        # Free profiles are granted automatically with the weapon, so only priced
        # additions are offered.
        assert "Frag" not in text
        assert "Free profiles are not listed" in text

    def test_choosing_a_line_writes_it_anchored_to_the_gun(
        self, client, author, gunner, launcher
    ):
        gun = gun_member_of(gunner)
        smoke = launcher.profiles.get(name="Smoke")

        response = client.post(
            reverse("authoring-built-in-profiles", args=[gun.pk]),
            {"weapon_profile": str(smoke.pk)},
        )

        assert response.status_code == 302
        member = DefaultAssignment.objects.get(weapon_profile=smoke)
        assert member.gun_member_id == gun.pk
        assert member.default_set_id == gunner.built_ins_id

    def test_two_lines_added_in_turn_nest_in_add_order(
        self, client, author, gunner, launcher
    ):
        """Append profiles in insertion order and nest them by weapon anchor rather than
        requiring adjacent set positions.
        """
        gun = gun_member_of(gunner)
        for name in ("Smoke", "Choke"):
            client.post(
                reverse("authoring-built-in-profiles", args=[gun.pk]),
                {"weapon_profile": str(launcher.profiles.get(name=name).pk)},
            )

        smoke, choke = (
            DefaultAssignment.objects.get(weapon_profile__name=name)
            for name in ("Smoke", "Choke")
        )
        assert smoke.position != choke.position
        assert smoke.position < choke.position

        page = client.get(reverse("authoring-detail", args=["profile", gunner.pk]))
        comes_with = next(
            section
            for section in page.context["part_sections"]
            if section["act"] == "built_in"
        )
        gun_row = next(row for row in comes_with["parts"] if row["label"] == "Launcher")
        assert [line["label"] for line in gun_row["children"]] == ["Smoke", "Choke"]

    def test_the_listing_nests_the_line_under_its_gun(
        self, client, author, gunner, launcher
    ):
        gun = gun_member_of(gunner)
        smoke = launcher.profiles.get(name="Smoke")
        client.post(
            reverse("authoring-built-in-profiles", args=[gun.pk]),
            {"weapon_profile": str(smoke.pk)},
        )

        page = client.get(reverse("authoring-detail", args=["profile", gunner.pk]))

        comes_with = next(
            section
            for section in page.context["part_sections"]
            if section["act"] == "built_in"
        )
        gun_row = next(row for row in comes_with["parts"] if row["label"] == "Launcher")
        assert [line["label"] for line in gun_row["children"]] == ["Smoke"]

        assert all(row["label"] != "Smoke" for row in comes_with["parts"])
        assert gun_row["add_profile_url"]

    def test_an_archived_members_address_is_gone(self, client, author, gunner):
        gun = gun_member_of(gunner)
        gun.archive()
        address = reverse("authoring-built-in-profiles", args=[gun.pk])
        assert client.get(address).status_code == 404


class TestTheSetsOwnDoor:
    """A set without the weapon can grant an unanchored profile for an existing matching
    weapon. Preserve the selected weapon in request state.
    """

    @pytest.fixture
    def smoke_rounds(self, person_type, gang_type, launcher, default_pack):
        profile = create_profile("Chooser", person_type, gang_type, price=50)
        add_built_in(profile, launcher)
        rounds = create_default_set("Smoke rounds", price=10)
        offer_option(profile, "Smoke rounds", default_set=rounds)
        return rounds

    def test_without_a_weapon_it_asks_for_one(self, client, author, smoke_rounds):
        page = client.get(reverse("authoring-set-profiles", args=[smoke_rounds.pk]))
        text = page.content.decode()
        assert "Whose lines?" in text
        assert "Launcher" in text

    def test_with_a_weapon_it_says_where_the_line_lands(
        self, client, author, smoke_rounds, launcher
    ):
        page = client.get(
            reverse("authoring-set-profiles", args=[smoke_rounds.pk]),
            {"weapon": str(launcher.pk)},
        )
        text = page.content.decode()
        assert "does not bring" in text
        assert "already holds" in text

    def test_choosing_a_line_writes_it_unanchored(
        self, client, author, smoke_rounds, launcher
    ):
        smoke = launcher.profiles.get(name="Smoke")

        response = client.post(
            reverse("authoring-set-profiles", args=[smoke_rounds.pk]),
            {"weapon": str(launcher.pk), "weapon_profile": str(smoke.pk)},
        )

        assert response.status_code == 302
        member = DefaultAssignment.objects.get(weapon_profile=smoke)
        assert member.default_set_id == smoke_rounds.pk
        assert member.gun_member_id is None

    def test_a_set_bringing_the_gun_twice_refuses_in_words(
        self, client, author, launcher, person_type, gang_type, default_pack
    ):
        profile = create_profile("Twin gunner", person_type, gang_type, price=50)
        add_built_in(profile, launcher)
        add_built_in(profile, launcher)
        smoke = launcher.profiles.get(name="Smoke")

        response = client.post(
            reverse("authoring-set-profiles", args=[profile.built_ins_id]),
            {"weapon": str(launcher.pk), "weapon_profile": str(smoke.pk)},
            follow=True,
        )

        assert not DefaultAssignment.objects.filter(weapon_profile=smoke).exists()
        said = [str(message) for message in response.context["messages"]]
        assert any("which gun" in sentence for sentence in said)
