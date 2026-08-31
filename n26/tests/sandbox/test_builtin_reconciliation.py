"""Reconciling a carrier against its sets — built-ins as desired state.

``Operation.reconcile_defaults`` re-reads what a carrier's sets say it
should hold and creates only what is missing, judged by provenance
alone: a copy naming the member and the carrier. Run twice it creates
nothing; an owner's own copy of the same thing never stands in for a
built-in; an archived copy still satisfies, because what an owner
parted with is never handed back. This is what lets a built-in added
to a profile later reach the fighters already hired from it.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.core.models import Assignment, ChosenProfileOption, Miniature, Reason
from n26.core.operations import LibraryError, operation
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import add_default_member
from n26.library.models import WeaponProfile
from n26.tests.sandbox.actions import (
    add_built_in,
    add_legacy_profile,
    choose,
    create_collection,
    create_counter,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    create_subtype,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    hire_with_option,
    modifier,
    offer_option,
    op_adds_model,
    remove,
    targets_model,
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
    """A profile whose built-ins carry a weapon and a rule."""
    profile = create_profile("Ganger", person_type, gang_type, price=50)
    add_built_in(profile, create_weapon("Stub gun", profiles=[("Standard", 0)]))
    add_built_in(profile, create_rule("Gang Fighter"))
    return profile


def member_named(carrier, name):
    """The built-in membership whose thing prints ``name``."""
    return next(
        member
        for member in carrier.built_ins.members.all()
        if str(member.assignable) == name
    )


def reconcile(gang, carrier, **kwargs):
    """A bare reconcile pass — hosted on the gang for a gang-hosted
    carrier about no model, the same inference rechoose makes."""
    if carrier.miniature_root_id is None and carrier.gang_id is not None:
        kwargs.setdefault("gang", carrier.gang)
    with operation(gang, actor=gang.owner) as op:
        return op.reconcile_defaults(carrier, **kwargs)


def copies_by_member(carrier):
    """Copy counts keyed by member, archived included — the provenance
    pairs are what idempotency is asserted over, not a bare copy count."""
    counts = {}
    for copy in Assignment.objects.filter(materialised_for=carrier):
        counts[copy.materialised_from_id] = counts.get(copy.materialised_from_id, 0) + 1
    return counts


class TestReconcilingTwiceCreatesNothing:
    """The engine is idempotent: a pass over a settled carrier is a no-op,
    and a member added later arrives exactly once."""

    def test_a_second_pass_over_a_fresh_hire_creates_nothing(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        membership = fighter.membership
        before = copies_by_member(membership)

        outcome = reconcile(gang, membership)

        assert outcome.created == []
        assert outcome.skipped == []
        assert copies_by_member(membership) == before
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_member_added_later_arrives_once_however_often_it_runs(
        self, gang, ganger, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        member = add_built_in(ganger, create_rule("Nerves of Steel"))

        reconcile(gang, fighter.membership)
        reconcile(gang, fighter.membership)

        assert copies_by_member(fighter.membership)[member.pk] == 1
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestAnOwnersOwnCopyNeverStandsIn:
    """Satisfaction is provenance, not appearance: an independent copy of
    the same thing does not block the grant, and the duplicate stands."""

    def test_an_independent_copy_does_not_block_the_grant(
        self, gang, ganger, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        steel = create_rule("Nerves of Steel")
        with operation(gang, actor=gang.owner) as op:
            op.assign(steel, miniature=fighter, paid=0)
        member = add_built_in(ganger, steel)

        reconcile(gang, fighter.membership)

        copies = Assignment.objects.filter(
            rule=steel, miniature_root=fighter, archived=False
        )
        assert copies.count() == 2
        assert copies.filter(materialised_from=member).count() == 1
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestWhatAnOwnerPartedWithStaysGone:
    """An archived copy still satisfies its member — removing or selling
    a grant is settled, never quietly undone by a later reconcile."""

    def test_an_archived_copy_blocks_the_regrant(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        member = member_named(ganger, "Stub gun")
        copy = Assignment.objects.get(
            materialised_from=member, materialised_for=fighter.membership
        )
        remove(copy)

        outcome = reconcile(gang, fighter.membership)

        assert outcome.created == []
        assert (
            Assignment.objects.filter(
                materialised_from=member, materialised_for=fighter.membership
            ).count()
            == 1
        )
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestAnOwnersRemovalIsMachinery:
    """A ``removes`` assignment suppresses a thing; it is not a copy of
    one. It never satisfies a member, and the grant never disturbs it."""

    def test_a_take_away_never_satisfies_and_survives_the_grant(
        self, gang, ganger, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        fury = create_rule("Fury")
        with operation(gang, actor=gang.owner) as op:
            op.take_away(fighter, fury)
        member = add_built_in(ganger, fury)

        reconcile(gang, fighter.membership)

        copy = Assignment.objects.get(
            materialised_from=member, materialised_for=fighter.membership
        )
        assert copy.archived is False
        removal = Assignment.objects.get(
            rule=fury, removes=True, miniature_root=fighter
        )
        assert removal.archived is False
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_database_refuses_a_removal_carrying_provenance(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        member = member_named(ganger, "Gang Fighter")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                with operation(gang, actor=gang.owner) as op:
                    op.assign(
                        member.assignable,
                        miniature=fighter,
                        paid=0,
                        reason=Reason.EDITED,
                        removes=True,
                        materialised_from=member,
                        materialised_for=fighter.membership,
                    )


class TestWeaponsArriveWhole:
    def test_a_weapon_added_later_brings_its_free_profiles_once(
        self, gang, ganger, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        launcher = create_weapon("Launcher", profiles=[("Frag", 0)])
        add_built_in(ganger, launcher)

        reconcile(gang, fighter.membership)
        reconcile(gang, fighter.membership)

        guns = Assignment.objects.filter(
            miniature_root=fighter, weapon=launcher, archived=False
        )
        assert guns.count() == 1
        lines = Assignment.objects.filter(
            parent=guns.get(), weapon_profile__isnull=False, archived=False
        )
        assert [line.weapon_profile.name for line in lines] == ["Frag"]
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestAmmoFindsItsGun:
    """A weapon-profile member stacks on a gun's assignment. An anchored
    member names its gun member and lands on that member's own copy; an
    unanchored one rides whatever matching gun the host holds."""

    @pytest.fixture
    def launcher(self, default_pack):
        return create_weapon("Launcher", profiles=[("Frag", 0)])

    @pytest.fixture
    def smoke(self, launcher):
        """The launcher's priced line — never free, so only a member or
        a purchase brings it."""
        return WeaponProfile.objects.create(
            name="Smoke", weapon=launcher, price=10, position=1
        )

    def test_anchored_twins_each_feed_their_own_gun(
        self, gang, person_type, gang_type, launcher, smoke
    ):
        choke = WeaponProfile.objects.create(
            name="Choke", weapon=launcher, price=10, position=2
        )
        profile = create_profile("Twin gunner", person_type, gang_type, price=50)
        gun_one = add_built_in(profile, launcher)
        gun_two = add_built_in(profile, launcher)
        add_built_in(profile, smoke, gun_member=gun_one)
        add_built_in(profile, choke, gun_member=gun_two)

        fighter = hire(gang, profile, "Ana", paid=50)

        membership = fighter.membership
        first_gun = Assignment.objects.get(
            materialised_from=gun_one, materialised_for=membership
        )
        second_gun = Assignment.objects.get(
            materialised_from=gun_two, materialised_for=membership
        )
        smoke_copy = Assignment.objects.get(
            weapon_profile=smoke, miniature_root=fighter, archived=False
        )
        choke_copy = Assignment.objects.get(
            weapon_profile=choke, miniature_root=fighter, archived=False
        )
        # Neither gun starves: each line sits on the gun its member names.
        assert smoke_copy.parent_id == first_gun.pk
        assert choke_copy.parent_id == second_gun.pk

        outcome = reconcile(gang, fighter.membership)
        assert outcome.created == []
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_twin_add_without_an_anchor_is_refused_in_words(
        self, gang, person_type, gang_type, launcher, smoke
    ):
        """Two matching gun members and no anchor is unanswerable, so
        the verb refuses rather than deciding which gun for good."""
        profile = create_profile("Twin gunner", person_type, gang_type, price=50)
        add_built_in(profile, launcher)
        add_built_in(profile, launcher)

        with pytest.raises(ValidationError) as refusal:
            add_built_in(profile, smoke)
        assert "which gun" in str(refusal.value)

    def test_a_single_gun_add_anchors_itself(
        self, gang, person_type, gang_type, launcher, smoke
    ):
        """With one matching gun member there is nothing to ask — the
        add settles on it, the way an import resolves."""
        profile = create_profile("Gunner", person_type, gang_type, price=50)
        gun_member = add_built_in(profile, launcher)

        member = add_built_in(profile, smoke)

        assert member.gun_member_id == gun_member.pk

    def test_an_add_never_anchors_to_a_removed_gun(
        self, gang, person_type, gang_type, launcher, smoke
    ):
        """A gun an author took off the set no longer brings anything,
        so naming it as an anchor is refused in words — and an unnamed
        add settles past it to nothing, the cross-set meaning."""
        profile = create_profile("Gunner", person_type, gang_type, price=50)
        gun_member = add_built_in(profile, launcher)
        gun_member.archive()

        with pytest.raises(ValidationError) as refusal:
            add_built_in(profile, smoke, gun_member=gun_member)
        assert "taken off" in str(refusal.value)
        assert add_built_in(profile, smoke).gun_member_id is None

    def test_a_set_founded_whole_anchors_its_lines(self, launcher, smoke):
        """Founding a set with a gun and its line in one statement —
        what an import does — settles the anchor the same way an add
        does: every member goes through the one verb."""
        default_set = create_default_set("Gun kit", members=[launcher, smoke])

        line = default_set.members.get(weapon_profile=smoke)
        assert line.gun_member == default_set.members.get(weapon=launcher)

    def test_a_founded_sets_lines_anchor_whatever_order_was_stated(
        self, launcher, smoke
    ):
        """A line before its gun in the founding statement still anchors:
        anchors resolve against the completed set, and the stated order
        survives as each member's position."""
        default_set = create_default_set("Gun kit", members=[smoke, launcher])

        line = default_set.members.get(weapon_profile=smoke)
        assert line.gun_member == default_set.members.get(weapon=launcher)
        assert line.position == 0
        assert line.gun_member.position == 1

    def test_a_twin_founding_refuses_whole(self, launcher, smoke):
        """Founding a set whose line has two guns to ride is refused,
        and nothing of the set survives — not the guns that were written
        before the refusal, and not the set itself."""
        from n26.library.models import DefaultAssignmentSet

        with pytest.raises(ValidationError):
            create_default_set("Gun kit", members=[launcher, launcher, smoke])

        assert not DefaultAssignmentSet.objects.filter(name="Gun kit").exists()

    def test_an_anchored_line_never_rides_a_hand_given_gun(
        self, gang, person_type, gang_type, launcher, smoke
    ):
        """The anchor is a receipt, not a preference: with the built-in
        gun's copy removed, the line is skipped rather than rehomed onto
        another gun of the same type the owner holds."""
        profile = create_profile("Gunner", person_type, gang_type, price=50)
        gun_member = add_built_in(profile, launcher)
        fighter = hire(gang, profile, "Ana", paid=50)
        give_weapon(fighter, launcher)
        remove(
            Assignment.objects.get(
                materialised_from=gun_member, materialised_for=fighter.membership
            )
        )
        ammo_member = add_built_in(profile, smoke, gun_member=gun_member)

        outcome = reconcile(gang, fighter.membership, strict=False)

        assert [entry.member for entry, _ in outcome.skipped] == [ammo_member]
        assert not Assignment.objects.filter(weapon_profile=smoke).exists()
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_ammo_lands_on_a_gun_the_owner_gave_by_hand(
        self, gang, ganger, launcher, smoke
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        gun = give_weapon(fighter, launcher)
        member = add_built_in(ganger, smoke)

        reconcile(gang, fighter.membership)

        copy = Assignment.objects.get(
            materialised_from=member, materialised_for=fighter.membership
        )
        assert copy.parent_id == gun.pk
        assert copy.caused_by_id == gun.pk
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_orphan_ammo_is_recorded_on_a_reconcile_and_refused_at_hire(
        self, gang, ganger, launcher, smoke
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        add_built_in(ganger, smoke)

        outcome = reconcile(gang, fighter.membership, strict=False)

        assert len(outcome.skipped) == 1
        entry, why = outcome.skipped[0]
        assert entry.member.assignable == smoke
        assert "Launcher" in why
        assert not Assignment.objects.filter(weapon_profile=smoke).exists()

        with pytest.raises(LibraryError):
            hire(gang, ganger, "Bea", paid=50)
        gang.refresh_from_db()
        assert_reconciled(gang)


@pytest.fixture
def legacy_slot_type(default_pack):
    return create_slot_type(
        "Gang Legacy", plural_name="Gang Legacies", allows_repeats=False
    )


@pytest.fixture
def houses(legacy_slot_type):
    return {
        name: create_pickable(name, legacy_slot_type) for name in ("Cawdor", "Escher")
    }


@pytest.fixture
def legacy_slot(legacy_slot_type, houses):
    return create_slot(
        "Gang Legacy",
        legacy_slot_type,
        create_picklist(
            "Gang Legacies", legacy_slot_type, members=list(houses.values())
        ),
    )


class TestSlotsAndPicks:
    def test_an_answered_slot_is_left_untouched(
        self, gang, person_type, gang_type, legacy_slot, houses
    ):
        profile = create_profile("Hunter", person_type, gang_type, price=100)
        add_built_in(profile, legacy_slot)
        fighter = hire(gang, profile, "Ana", paid=100)
        slot_copy = Assignment.objects.get(
            miniature_root=fighter, slot__isnull=False, archived=False
        )
        choose(slot_copy, houses["Cawdor"])

        outcome = reconcile(gang, fighter.membership)

        assert outcome.created == []
        picks = Assignment.objects.filter(chosen_for=slot_copy, archived=False)
        assert picks.count() == 1
        assert picks.get().pickable == houses["Cawdor"]
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_slot_with_a_default_added_later_arrives_settled(
        self, gang, ganger, legacy_slot, houses
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        member = add_built_in(ganger, legacy_slot, default_pickable=houses["Escher"])

        reconcile(gang, fighter.membership)
        reconcile(gang, fighter.membership)

        slot_copy = Assignment.objects.get(
            materialised_from=member,
            materialised_for=fighter.membership,
            archived=False,
        )
        picks = Assignment.objects.filter(chosen_for=slot_copy, archived=False)
        assert picks.count() == 1
        assert picks.get().pickable == houses["Escher"]
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestCountersOpenOnce:
    def test_a_counter_added_later_opens_once_at_its_amount(
        self, gang, ganger, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        xp = create_counter("XP")
        add_built_in(ganger, xp, amount=61)

        reconcile(gang, fighter.membership)
        reconcile(gang, fighter.membership)

        copies = Assignment.objects.filter(
            counter=xp, miniature_root=fighter, archived=False
        )
        assert copies.count() == 1
        assert copies.get().counter_value.value == 61
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestStoredEffectsRunOnce:
    """Stored effects fire inside ``assign``, so a satisfied member must
    be skipped before assign runs at all — a false miss breeds pets."""

    def test_a_pet_riding_a_built_in_is_spawned_exactly_once(
        self, gang, ganger, person_type, gang_type, default_pack
    ):
        cat = create_profile("Gyrinx cat", person_type, gang_type, price=0)
        collar = create_wargear("Cat collar")
        modifier(
            "Collar: brings the cat",
            targets_model(),
            op_adds_model(cat),
            carried_by=collar,
        )
        fighter = hire(gang, ganger, "Ana", paid=50)
        add_built_in(ganger, collar)

        reconcile(gang, fighter.membership)
        reconcile(gang, fighter.membership)

        assert Miniature.objects.filter(membership__profile=cat).count() == 1
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestGangAndStashHostedCarriers:
    def test_the_founding_gains_a_member_added_to_the_gang_type(
        self, gang, gang_type, default_pack
    ):
        member = add_built_in(gang_type, create_rule("Home Turf"))

        reconcile(gang, gang.founding)
        reconcile(gang, gang.founding)

        copies = Assignment.objects.filter(
            materialised_from=member, materialised_for=gang.founding
        )
        assert copies.count() == 1
        assert copies.get().gang_id == gang.pk
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_stash_purchase_reconciles_where_it_lives(self, gang, default_pack):
        toolkit = create_wargear("Toolkit", price=10)
        with operation(gang, actor=gang.owner) as op:
            bought = op.buy(gang.stash, thing=toolkit)
        member = add_built_in(toolkit, create_hidden("Fine tools"))

        reconcile(gang, bought)

        copy = Assignment.objects.get(materialised_from=member, materialised_for=bought)
        assert copy.stash_id == gang.stash.pk
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestLegacyProfilesBringOnlyLists:
    """A Legacy association brings equipment lists and nothing else, and
    a bare reconcile derives that from the carrier's role — no caller
    has to remember to narrow it."""

    def test_a_bare_reconcile_of_a_legacy_carrier_brings_only_collections(
        self, gang, ganger, person_type, gang_type, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        legacy = create_profile("Legacy entry", person_type, gang_type, price=0)
        association = add_legacy_profile(fighter, legacy)
        list_member = add_built_in(legacy, create_collection("Legacy List"))
        add_built_in(legacy, create_weapon("Legacy blade", profiles=[("Slash", 0)]))

        outcome = reconcile(gang, association)

        assert [copy.materialised_from_id for copy in outcome.created] == [
            list_member.pk
        ]
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestRefoundingStaysSettled:
    def test_refound_then_reconcile_duplicates_nothing(
        self, gang_type, player, default_pack
    ):
        delaque = create_gang_type("Delaque")
        member = add_built_in(delaque, create_rule("Shadowy"))
        gang = found_gang("The Movers", gang_type, owner=player, budget=1000)
        with operation(gang, actor=player) as op:
            op.refound(delaque)
        gang.refresh_from_db()

        reconcile(gang, gang.founding)

        assert Assignment.objects.filter(materialised_from=member).count() == 1
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestChosenSetsGrowLater:
    def test_a_chosen_set_grown_later_reaches_the_carrier_once(
        self, gang, person_type, gang_type, default_pack
    ):
        profile = create_profile("Chooser", person_type, gang_type, price=100)
        fancy = create_default_set(
            "Fancy kit",
            members=[create_weapon("Sword", profiles=[("Slash", 0)])],
            price=25,
        )
        offer_option(profile, "Fancy kit", default_set=fancy)
        fighter = hire_with_option(gang, profile, "Ana", option=fancy)
        grown = add_default_member(fancy, create_rule("Flair"))

        reconcile(gang, fighter.membership)
        reconcile(gang, fighter.membership)

        assert Assignment.objects.filter(materialised_from=grown).count() == 1
        assert (
            ChosenProfileOption.objects.filter(
                assignment=fighter.membership, default_set=fancy
            ).count()
            == 1
        )
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestBuiltInsOfBuiltIns:
    """A copy a set creates is an arrival of its own: a subtype granted by
    a profile brings the counters built into the subtype, caused by the
    subtype's copy — the same provenance the propagation pass writes."""

    @pytest.fixture
    def spyrer(self, default_pack):
        subtype = create_subtype("Spyrer")
        add_built_in(subtype, create_counter("Kill Count"))
        add_built_in(subtype, create_counter("Glitch Count"), amount=2)
        return subtype

    @pytest.fixture
    def hunter(self, person_type, gang_type, spyrer):
        profile = create_profile("Spyre Hunter", person_type, gang_type, price=100)
        add_built_in(profile, spyrer)
        return profile

    def test_a_hire_brings_what_its_built_ins_are_built_with(
        self, gang, hunter, spyrer
    ):
        fighter = hire(gang, hunter, "Ana", paid=100)

        subtype_copy = Assignment.objects.get(subtype=spyrer, miniature_root=fighter)
        counters = Assignment.objects.filter(
            counter__isnull=False, miniature_root=fighter, archived=False
        )
        assert counters.count() == 2
        for copy in counters:
            assert copy.caused_by == subtype_copy
            assert copy.materialised_for == subtype_copy
            assert copy.materialised_from.default_set == spyrer.built_ins
        assert copies_by_member(subtype_copy) == {
            member.pk: 1 for member in spyrer.built_ins.members.all()
        }
        glitch = counters.get(counter__name="Glitch Count")
        assert glitch.counter_value.value == 2
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_second_pass_creates_nothing_at_either_level(self, gang, hunter, spyrer):
        fighter = hire(gang, hunter, "Ana", paid=100)
        subtype_copy = Assignment.objects.get(subtype=spyrer, miniature_root=fighter)
        before = Assignment.objects.filter(miniature_root=fighter).count()

        assert reconcile(gang, fighter.membership).created == []
        assert reconcile(gang, subtype_copy).created == []

        assert Assignment.objects.filter(miniature_root=fighter).count() == before
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_founding_brings_nested_built_ins_onto_the_gang(
        self, gang_type, player, spyrer, default_pack
    ):
        add_built_in(gang_type, spyrer)

        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)

        subtype_copy = Assignment.objects.get(subtype=spyrer, gang_root=gang)
        counters = Assignment.objects.filter(
            counter__isnull=False, gang_root=gang, archived=False
        )
        assert counters.count() == 2
        assert {copy.caused_by for copy in counters} == {subtype_copy}
        assert {copy.gang_id for copy in counters} == {gang.pk}
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_library_that_nests_a_thing_inside_itself_is_refused_in_words(
        self, gang, hunter, spyrer
    ):
        hunted = create_subtype("Hunted")
        add_built_in(spyrer, hunted)
        add_built_in(hunted, spyrer)

        with pytest.raises(LibraryError, match="Built-ins nest in a circle"):
            hire(gang, hunter, "Ana", paid=100)
        assert not Miniature.objects.filter(membership__gang_root=gang).exists()
