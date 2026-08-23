"""Taking a built-in off a carrier, and how a grant remembers its origin.

An author removing a built-in changes what future acquisitions come
with; what fighters already hold stands untouched. That only works if
the membership row survives the removal, so removal archives it — and
every copy a member materialises names that member and the carrier it
came for (``materialised_from`` / ``materialised_for``), which is how a
later reader tells a built-in's copy from an owner's own purchase of
the same thing.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from n26.core.card import build_card_from_profile
from n26.core.models import Assignment
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.models import DefaultAssignment, Profile, WeaponProfile
from n26.tests.sandbox.actions import (
    add_built_in,
    add_legacy_profile,
    create_collection,
    create_default_set,
    create_rule,
    create_weapon,
    found_gang,
    hire,
    hire_with_option,
    offer_option,
    remove,
    remove_default_member,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def ganger(person_type, gang_type, default_pack):
    """A profile whose built-ins carry a weapon, a rule, and its list."""
    profile = Profile.objects.create(
        name="Ganger", profile_type=person_type, gang_type=gang_type, price=50
    )
    add_built_in(profile, create_weapon("Stub gun", profiles=[("Standard", 0)]))
    add_built_in(profile, create_rule("Gang Fighter"))
    add_built_in(profile, create_collection("House List"))
    return profile


def member_named(carrier, name):
    """The built-in membership whose thing prints ``name``."""
    return next(
        member
        for member in carrier.built_ins.members.all()
        if str(member.assignable) == name
    )


def held_names(miniature):
    return sorted(
        str(assignment.assignable)
        for assignment in Assignment.objects.filter(
            miniature_root=miniature, archived=False, profile__isnull=True
        )
        if not assignment.weapon_profile_id
    )


class TestRemovingABuiltIn:
    """Removal is archival: the future changes, the past stands."""

    def test_what_a_fighter_already_holds_stands(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        remove_default_member(member_named(ganger, "Stub gun"))

        assert "Stub gun" in held_names(fighter)
        assert_reconciled(gang)

    def test_the_next_hire_comes_without_it(self, gang, ganger):
        hire(gang, ganger, "Ana", paid=50)
        remove_default_member(member_named(ganger, "Stub gun"))
        fighter = hire(gang, ganger, "Bea", paid=50)

        assert "Stub gun" not in held_names(fighter)
        assert "Gang Fighter" in held_names(fighter)
        assert_reconciled(gang)

    def test_the_membership_is_archived_and_off_the_listing(self, gang, ganger):
        hire(gang, ganger, "Ana", paid=50)
        member = member_named(ganger, "Stub gun")
        remove_default_member(member)

        member.refresh_from_db()
        assert member.archived is True
        assert "Stub gun" not in [
            str(row.assignable) for row in ganger.built_in_members
        ]
        assert_reconciled(gang)

    def test_a_copy_with_no_link_still_keeps_the_membership(self, gang, ganger):
        """A copy carrying no provenance link cannot name its membership,
        so a free-granted copy of the same thing keeps it archived rather
        than deleted — the row is what a link repair anchors to."""
        hire(gang, ganger, "Ana", paid=50)
        member = member_named(ganger, "Stub gun")
        for row in Assignment.objects.filter(materialised_from=member):
            row.materialised_from = None
            row.materialised_for = None
            row.save(update_fields=["materialised_from", "materialised_for"])

        remove_default_member(member)

        member.refresh_from_db()
        assert member.archived is True
        assert_reconciled(gang)

    def test_a_member_nothing_materialised_from_goes_completely(self, ganger):
        """Archival exists for the copies that name a member; with none,
        an archived member would only linger invisibly, holding its
        assignable under PROTECT with no page left to show why."""
        member = member_named(ganger, "Stub gun")
        thing = member.assignable
        remove_default_member(member)

        assert not DefaultAssignment.objects.filter(pk=member.pk).exists()
        thing.refresh_from_db()

    def test_the_hire_preview_drops_it(self, ganger):
        remove_default_member(member_named(ganger, "Stub gun"))
        card = build_card_from_profile(ganger)

        shown = [str(node.assignable) for node in card.roots]
        assert "Stub gun" not in shown
        assert "Gang Fighter" in shown

    def test_ammo_goes_with_its_gun(self, gang, ganger):
        launcher = create_weapon("Launcher", profiles=[("Frag", 0)])
        smoke = WeaponProfile.objects.create(
            name="Smoke", weapon=launcher, price=10, position=1
        )
        gun_member = add_built_in(ganger, launcher)
        ammo_member = add_built_in(ganger, smoke)
        hire(gang, ganger, "Ana", paid=50)

        remove_default_member(gun_member)

        ammo_member.refresh_from_db()
        assert ammo_member.archived is True
        assert_reconciled(gang)

    def test_only_the_named_guns_lines_go_with_it(self, gang, ganger):
        """What goes with a gun is what names it — its twin of the same
        weapon keeps its own lines."""
        launcher = create_weapon("Launcher", profiles=[("Frag", 0)])
        smoke = WeaponProfile.objects.create(
            name="Smoke", weapon=launcher, price=10, position=1
        )
        choke = WeaponProfile.objects.create(
            name="Choke", weapon=launcher, price=10, position=2
        )
        gun_one = add_built_in(ganger, launcher)
        gun_two = add_built_in(ganger, launcher)
        smoke_member = add_built_in(ganger, smoke, gun_member=gun_one)
        choke_member = add_built_in(ganger, choke, gun_member=gun_two)
        hire(gang, ganger, "Ana", paid=50)

        remove_default_member(gun_one)

        smoke_member.refresh_from_db()
        choke_member.refresh_from_db()
        assert smoke_member.archived is True
        assert choke_member.archived is False
        assert_reconciled(gang)


class TestProvenance:
    """Every materialised copy names its member and its carrier."""

    def test_a_hire_writes_where_each_grant_came_from(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        membership = fighter.membership

        for name in ("Stub gun", "Gang Fighter", "House List"):
            copy = Assignment.objects.get(
                materialised_from=member_named(ganger, name),
                materialised_for=membership,
            )
            assert copy.archived is False
        assert_reconciled(gang)

    def test_a_purchase_carries_none(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        membership = fighter.membership
        assert membership.materialised_from_id is None
        assert membership.materialised_for_id is None
        assert_reconciled(gang)

    def test_a_founding_writes_it_too(self, gang_type, player, default_pack):
        add_built_in(gang_type, create_rule("Home Turf"))
        gang = found_gang("The Founders", gang_type, owner=player, budget=1000)

        copy = Assignment.objects.get(
            materialised_from=member_named(gang_type, "Home Turf")
        )
        assert copy.materialised_for_id == gang.founding.pk
        assert copy.gang_id == gang.pk
        assert_reconciled(gang)

    def test_granted_ammo_names_its_member_not_its_gun(self, gang, ganger):
        launcher = create_weapon("Launcher", profiles=[("Frag", 0)])
        smoke = WeaponProfile.objects.create(
            name="Smoke", weapon=launcher, price=0, position=1
        )
        add_built_in(ganger, launcher)
        ammo_member = add_built_in(ganger, smoke)

        fighter = hire(gang, ganger, "Ana", paid=50)
        copy = Assignment.objects.get(materialised_from=ammo_member, archived=False)
        gun = Assignment.objects.get(
            miniature_root=fighter, weapon=launcher, archived=False
        )
        assert copy.materialised_for_id == fighter.membership.pk
        assert copy.caused_by_id == gun.pk
        assert_reconciled(gang)

    def test_a_legacy_profile_writes_it_for_the_list_it_brings(
        self, gang, ganger, person_type, gang_type
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        legacy = Profile.objects.create(
            name="Legacy entry", profile_type=person_type, gang_type=gang_type
        )
        list_member = add_built_in(legacy, create_collection("Legacy List"))
        association = add_legacy_profile(fighter, legacy)

        copy = Assignment.objects.get(materialised_from=list_member)
        assert copy.materialised_for_id == association.pk
        assert_reconciled(gang)

    def test_one_live_copy_per_member_per_carrier(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        membership = fighter.membership
        member = member_named(ganger, "Gang Fighter")
        copy = Assignment.objects.get(
            materialised_from=member, materialised_for=membership
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                with operation(gang, actor=gang.owner) as op:
                    op.assign(
                        member.assignable,
                        miniature=fighter,
                        caused_by=membership,
                        materialised_from=member,
                        materialised_for=membership,
                        paid=0,
                    )

        # An archived copy stands aside: the owner parted with the
        # thing, and a deliberate re-grant is a fresh live copy.
        remove(copy)
        with operation(gang, actor=gang.owner) as op:
            op.assign(
                member.assignable,
                miniature=fighter,
                caused_by=membership,
                materialised_from=member,
                materialised_for=membership,
                paid=0,
            )
        assert (
            Assignment.objects.filter(
                materialised_from=member, materialised_for=membership
            ).count()
            == 2
        )
        assert_reconciled(gang)


@pytest.fixture
def chooser(person_type, gang_type, default_pack):
    """A profile with a pick-one group of two sets, for rechoosing."""
    profile = Profile.objects.create(
        name="Chooser", profile_type=person_type, gang_type=gang_type, price=100
    )
    for position, (name, weapon_name, price) in enumerate(
        [("Standard kit", "Knife", 0), ("Fancy kit", "Sword", 25)]
    ):
        offer_option(
            profile,
            name,
            default_set=create_default_set(
                name,
                members=[create_weapon(weapon_name, profiles=[("Attack", 0)])],
                price=price,
            ),
            position=position,
        )
    return profile


def weapon_names(miniature):
    return sorted(
        str(assignment.assignable)
        for assignment in Assignment.objects.filter(
            miniature_root=miniature, archived=False, weapon__isnull=False
        )
    )


class TestRechooseFindsGrantsByProvenance:
    """A swap unwinds the departing set whether its copies carry
    provenance (written at hire) or carry none (found by their ledger
    shape)."""

    def sets_of(self, profile):
        return {
            option.default_set.name: option.default_set
            for option in profile.options.all()
        }

    def rechoose(self, gang, miniature, option):
        with operation(gang, actor=gang.owner) as op:
            op.rechoose(miniature.membership, option=option)

    def test_provenance_tagged_copies_leave_with_their_set(self, gang, chooser):
        fighter = hire_with_option(gang, chooser, "Ana")
        assert weapon_names(fighter) == ["Knife"]

        self.rechoose(gang, fighter, self.sets_of(chooser)["Fancy kit"])

        assert weapon_names(fighter) == ["Sword"]
        sword = Assignment.objects.get(
            miniature_root=fighter, archived=False, weapon__isnull=False
        )
        assert sword.materialised_for_id == fighter.membership.pk
        assert_reconciled(gang)

    def test_copies_without_provenance_leave_too(self, gang, chooser):
        fighter = hire_with_option(gang, chooser, "Ana")
        # Wiped to stand in for copies that carry no provenance link,
        # which the unwind must still find by their written shape.
        for row in Assignment.objects.filter(
            miniature_root=fighter, materialised_from__isnull=False
        ):
            row.materialised_from = None
            row.materialised_for = None
            row.save(update_fields=["materialised_from", "materialised_for"])

        self.rechoose(gang, fighter, self.sets_of(chooser)["Fancy kit"])

        assert weapon_names(fighter) == ["Sword"]
        assert_reconciled(gang)

    def test_an_archived_members_copy_still_leaves_with_its_set(self, gang, chooser):
        """An author's removal never strands a copy: rechoosing away
        from the set still takes what the archived member materialised."""
        fancy = self.sets_of(chooser)["Fancy kit"]
        fighter = hire_with_option(gang, chooser, "Ana", option=fancy)
        member = fancy.members.get()
        remove_default_member(member)

        self.rechoose(gang, fighter, self.sets_of(chooser)["Standard kit"])

        assert weapon_names(fighter) == ["Knife"]
        assert not Assignment.objects.filter(
            materialised_from=member, archived=False
        ).exists()
        assert_reconciled(gang)


class TestTheMemberRowOutlivesItsSetsUses:
    def test_a_materialised_member_cannot_be_hard_deleted(self, gang, ganger):
        """PROTECT is what lets provenance point at members forever;
        the authoring path archives instead and never trips this."""
        hire(gang, ganger, "Ana", paid=50)
        member = member_named(ganger, "Stub gun")

        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            member.delete()
        assert_reconciled(gang)


class TestTheRemovePage:
    """The authoring page's removal archives, and a removed member's
    address has nothing left to ask about."""

    @pytest.fixture
    def author(self, client):
        user = User.objects.create_user("author", is_staff=True)
        client.force_login(user)
        return user

    def test_the_post_archives_a_materialised_membership(
        self, client, author, gang, ganger
    ):
        from django.urls import reverse

        hire(gang, ganger, "Ana", paid=50)
        member = member_named(ganger, "Stub gun")
        response = client.post(reverse("authoring-built-in-remove", args=[member.pk]))
        assert response.status_code == 302
        member.refresh_from_db()
        assert member.archived is True
        assert DefaultAssignment.objects.filter(pk=member.pk).exists()
        assert_reconciled(gang)

    def test_an_archived_members_address_is_gone(self, client, author, ganger):
        from django.urls import reverse

        member = member_named(ganger, "Stub gun")
        address = reverse("authoring-built-in-remove", args=[member.pk])
        remove_default_member(member)
        assert client.get(address).status_code == 404
        assert client.post(address).status_code == 404


class TestArchivedMembersAndNewGrants:
    def test_rechoosing_into_an_emptied_set_brings_nothing(self, gang, chooser):
        sets = {
            option.default_set.name: option.default_set
            for option in chooser.options.all()
        }
        fighter = hire_with_option(gang, chooser, "Ana")
        remove_default_member(sets["Fancy kit"].members.get())

        with operation(gang, actor=gang.owner) as op:
            op.rechoose(fighter.membership, option=sets["Fancy kit"])

        # The set still swaps in — it simply brings nothing now.
        assert weapon_names(fighter) == []
        assert_reconciled(gang)
