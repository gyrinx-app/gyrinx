"""The slot models' own contract: one slot type throughout, and the words
an author is turned away with.

Everything here would still be true with no gang, no fighter and no
rulebook — how a choice behaves once it is on a card is
``n26/tests/sandbox/test_slots_and_picks.py``.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.library.authoring import (
    add_built_in,
    add_default_member,
    add_picklist_member,
    create_default_set,
    create_pickable,
    create_picklist,
    create_rule,
    create_slot,
    create_slot_type,
    create_wargear,
)
from n26.library.models import DefaultAssignment, Slot

pytestmark = pytest.mark.django_db


@pytest.fixture
def legacy(default_pack):
    return create_slot_type("Gang Legacy", plural_name="Gang Legacies")


@pytest.fixture
def affiliation(default_pack):
    return create_slot_type("Affiliation")


@pytest.fixture
def cawdor(legacy):
    return create_pickable("Cawdor", legacy)


@pytest.fixture
def legacies(legacy, cawdor):
    return create_picklist("Gang Legacies", legacy, members=[cawdor])


class TestASlotTypeNamesWhatIsChosen:
    def test_the_plural_is_the_authors_where_they_gave_one(self, legacy):
        assert legacy.plural == "Gang Legacies"

    def test_an_s_stands_in_where_they_did_not(self, affiliation):
        assert affiliation.plural == "Affiliations"

    def test_two_slot_types_of_one_name_are_refused(self, legacy):
        with pytest.raises(IntegrityError), transaction.atomic():
            create_slot_type("gang legacy")


class TestOneSlotTypeThroughout:
    """A slot, its list and every pickable on it share one slot type.

    The check is an authoring sense check rather than a database one:
    the columns are each perfectly valid on their own, and only the row
    seeing both can tell they disagree.
    """

    def test_a_list_refuses_a_pickable_of_another_slot_type(
        self, legacies, affiliation
    ):
        aranthian = create_pickable("Aranthian", affiliation)
        with pytest.raises(ValidationError, match="belongs to Affiliation"):
            add_picklist_member(legacies, aranthian)

    def test_a_choice_refuses_a_list_of_another_slot_type(self, affiliation, legacies):
        with pytest.raises(ValidationError, match="Gang Legacy pickables"):
            create_slot("Affiliation", affiliation, legacies)

    def test_the_model_says_it_too_where_a_verb_was_bypassed(
        self, legacy, affiliation, legacies
    ):
        """An importer writing rows straight through the ORM is caught by
        ``clean``, which is where cross-row sense checks live."""
        stray = Slot(name="Stray", slot_type=affiliation, picklist=legacies)
        with pytest.raises(ValidationError, match="Gang Legacy pickables"):
            stray.clean()

    def test_a_pickable_is_listed_once_on_one_list(self, legacies, cawdor):
        with pytest.raises(IntegrityError), transaction.atomic():
            add_picklist_member(legacies, cawdor)


class TestHowManyPicksAChoiceHolds:
    def test_a_minimum_above_the_maximum_is_refused(self, legacy, legacies):
        with pytest.raises(IntegrityError), transaction.atomic():
            create_slot("Too many", legacy, legacies, min_picks=2, max_picks=1)

    def test_one_of_one_is_what_a_choice_asks_for_unless_told_otherwise(
        self, legacy, legacies
    ):
        slot = create_slot("Gang Legacy", legacy, legacies)
        assert (slot.min_picks, slot.max_picks) == (1, 1)
        assert slot.assigned_to == Slot.WillBeAssignedTo.BEARER
        assert slot.hidden is False


class TestWhatTheCardCallsAChoice:
    def test_the_label_where_there_is_one(self, legacy, legacies):
        slot = create_slot("Hunter legacy slot", legacy, legacies, label="Gang Legacy")
        assert slot.choice_label == "Gang Legacy"

    def test_the_slots_own_name_where_there_is_not(self, legacy, legacies):
        assert (
            create_slot("Gang Legacy", legacy, legacies).choice_label == "Gang Legacy"
        )

    def test_a_list_may_call_a_pickable_something_else(self, legacies, legacy):
        squats = create_pickable("Ironhead Squats", legacy)
        member = add_picklist_member(legacies, squats, label_override="Squats")
        assert member.label == "Squats"


class TestWhatAListMayBeOffered:
    """The picker on a list's page offers its slot type's pickables — the ones
    still on offer. Archiving one takes it out of what may be *newly*
    listed; every list already naming it goes on naming it."""

    def test_its_slot_types_pickables(self, legacies, cawdor):
        assert list(legacies.may_offer) == [cawdor]

    def test_and_not_another_slot_types(self, legacies, affiliation):
        create_pickable("Aranthian", affiliation)
        assert list(legacies.may_offer) == list(legacies.slot_type.pickables.all())

    def test_an_archived_pickable_is_not_offered_again(self, legacies, legacy):
        squats = create_pickable("Ironhead Squats", legacy)
        squats.archived = True
        squats.save()

        assert squats not in legacies.may_offer

    def test_a_list_that_already_names_one_goes_on_naming_it(self, legacies, cawdor):
        cawdor.archived = True
        cawdor.save()

        assert [member.pickable for member in legacies.members.all()] == [cawdor]


class TestABarePickableIsRefused:
    """A pickable built into something, with no choice behind it, would
    sit in the library unread — so the verb turns it away in words,
    whoever is writing."""

    REFUSAL = (
        "A pickable without its slot shows nothing and does nothing. "
        "Build in the slot, or a slot-with-default."
    )

    def test_building_one_into_a_thing(self, cawdor, default_pack):
        gear = create_wargear("Chem-stash")
        with pytest.raises(ValidationError) as refused:
            add_built_in(gear, cawdor)
        assert self.REFUSAL in str(refused.value)
        gear.refresh_from_db()
        assert gear.built_ins_id is None

    def test_adding_one_to_a_set_that_already_exists(self, cawdor, default_pack):
        kit = create_default_set("Some kit")
        with pytest.raises(ValidationError) as refused:
            add_default_member(kit, cawdor)
        assert self.REFUSAL in str(refused.value)

    def test_naming_one_when_the_set_is_made(self, cawdor, default_pack):
        with pytest.raises(ValidationError) as refused:
            create_default_set("Some kit", members=[cawdor])
        assert self.REFUSAL in str(refused.value)

    def test_the_slot_is_the_way_to_say_it(self, legacy, legacies, cawdor):
        """What the refusal points at: the choice, and its starting pick."""
        gear = create_wargear("Chem-stash")
        slot = create_slot("Gang Legacy", legacy, legacies)
        member = add_built_in(gear, slot, default_pickable=cawdor)
        assert member.assignable == slot
        assert member.default_pickable == cawdor


class TestAStartingPickBelongsToItsChoice:
    def test_one_without_a_slot_is_refused(self, cawdor, default_pack):
        rule = create_rule("Something else")
        kit = create_default_set("Some kit")
        with pytest.raises(ValidationError, match="A starting pick belongs to a slot"):
            add_default_member(kit, rule, default_pickable=cawdor)

    def test_one_from_another_slot_type_is_refused(
        self, legacy, legacies, affiliation, default_pack
    ):
        slot = create_slot("Gang Legacy", legacy, legacies)
        aranthian = create_pickable("Aranthian", affiliation)
        kit = create_default_set("Some kit")
        with pytest.raises(ValidationError, match="belongs to Affiliation"):
            add_default_member(kit, slot, default_pickable=aranthian)

    def test_the_slot_declares_what_building_one_in_asks_for(self):
        """Kinds declare and forms derive: the starting pick appears on
        the built-ins form because the slot says it needs one."""
        from n26.library.offers import attachment_asks

        asks = attachment_asks(Slot, DefaultAssignment)
        assert [ask.name for ask in asks] == ["default_pickable"]


class TestSayingExcept:
    """A condition read the other way round: everyone it does not name.

    Scoping usually names the ranks it reaches, and that is what the
    grounded content does. This is the grammar for the rule easier to
    state as an exception, where listing everyone else would go stale
    the day a subtype is added.
    """

    def test_a_plain_row_reaches_what_it_names(self, default_pack):
        from n26.core import select
        from n26.library.authoring import create_subtype, has_subtypes, targets_model

        champion = create_subtype("Champion")
        scope = targets_model(has_subtypes(champion))
        assert scope.as_selector().matches(select.matchable(None, [champion]))
        assert not scope.as_selector().matches(select.matchable(None, []))

    def test_a_negated_row_reaches_everything_else(self, default_pack):
        from n26.core import select
        from n26.library.authoring import create_subtype, has_subtypes, targets_model

        champion = create_subtype("Champion")
        scope = targets_model(has_subtypes(champion, negate=True))
        assert not scope.as_selector().matches(select.matchable(None, [champion]))
        assert scope.as_selector().matches(select.matchable(None, []))

    def test_it_reads_as_an_exception(self, default_pack):
        from n26.library.authoring import create_subtype, has_subtypes, targets_model

        champion = create_subtype("Champion")
        scope = targets_model(has_subtypes(champion, negate=True))
        assert str(scope) == "every model except Champion"

    def test_a_negated_row_naming_nothing_narrows_nothing(self, default_pack):
        """Never "everybody but nobody": an empty row is an unfinished
        one, and an unfinished condition must not silently invert."""
        from n26.core import select
        from n26.library.authoring import has_subtypes, targets_model

        scope = targets_model(has_subtypes(negate=True))
        assert scope.as_selector().matches(select.matchable(None, []))

    def test_rows_still_stack(self, default_pack):
        """Conditions are ANDed across and any-of within, negation or
        not: every Mounted model that is not a Champion."""
        from n26.core import select
        from n26.library.authoring import create_subtype, has_subtypes, targets_model

        champion = create_subtype("Champion")
        mounted = create_subtype("Mounted")
        scope = targets_model(
            has_subtypes(mounted), has_subtypes(champion, negate=True)
        )
        selector = scope.as_selector()
        assert selector.matches(select.matchable(None, [mounted]))
        assert not selector.matches(select.matchable(None, [mounted, champion]))
        assert not selector.matches(select.matchable(None, [champion]))

    def test_naming_a_pick_reaches_whoever_made_it(self, cawdor, default_pack):
        from n26.core import select
        from n26.library.authoring import has_pickable, targets_model

        scope = targets_model(has_pickable(cawdor))
        assert scope.as_selector().matches(select.matchable(None, [cawdor]))
        assert not scope.as_selector().matches(select.matchable(None, []))

    def test_naming_a_pick_the_other_way_round(self, cawdor, default_pack):
        from n26.core import select
        from n26.library.authoring import has_pickable, targets_model

        scope = targets_model(has_pickable(cawdor, negate=True))
        assert not scope.as_selector().matches(select.matchable(None, [cawdor]))
        assert scope.as_selector().matches(select.matchable(None, []))


class TestARollTable:
    """A picklist may be a roll table: it names its dice, and each
    member claims the band of rolls that lands on it. The bands are
    numbers and nothing else — a lookup only ever asks about a roll that
    happened, so "31-46" on a D66 is a band of twelve rolls, not sixteen,
    and no arithmetic here pretends otherwise.
    """

    @pytest.fixture
    def injury(self, default_pack):
        return create_slot_type("Lasting Injury", allows_repeats=True)

    @pytest.fixture
    def table(self, injury):
        return create_picklist(
            "Lasting Injury Table", injury, dice="d66", roll_selects="band"
        )

    def test_the_bands_read_back_as_authored(self, injury, table):
        eye = add_picklist_member(
            table, create_pickable("Eye Injury", injury), roll_low=51, roll_high=51
        )
        cold = add_picklist_member(
            table, create_pickable("Out Cold", injury), roll_low=21, roll_high=26
        )
        assert (eye.roll_low, eye.roll_high) == (51, 51)
        assert (cold.roll_low, cold.roll_high) == (21, 26)
        assert eye.band == "51"
        assert cold.band == "21-26"

    def test_a_member_with_no_band_says_nothing(self, table, injury):
        plain = add_picklist_member(table, create_pickable("Lesson Learnt", injury))
        assert plain.roll_low is None and plain.roll_high is None
        assert plain.band == ""

    def test_one_roll_alone_is_a_band_of_one(self, table, injury):
        """The verb fills the high end in: "51" is the band 51-51."""
        eye = add_picklist_member(
            table, create_pickable("Eye Injury", injury), roll_low=51
        )
        assert (eye.roll_low, eye.roll_high) == (51, 51)

    def test_one_end_of_a_band_alone_is_refused_where_the_verb_was_bypassed(
        self, table, injury
    ):
        from n26.library.models import PicklistMember

        with pytest.raises(IntegrityError), transaction.atomic():
            PicklistMember.objects.create(
                picklist=table,
                pickable=create_pickable("Half", injury),
                roll_low=None,
                roll_high=51,
            )

    def test_a_band_running_backwards_is_refused(self, table, injury):
        with pytest.raises(IntegrityError), transaction.atomic():
            add_picklist_member(
                table, create_pickable("Backwards", injury), roll_low=26, roll_high=21
            )

    def test_a_band_on_a_list_that_names_no_dice_is_refused_in_words(
        self, injury, legacies, legacy
    ):
        member = add_picklist_member(legacies, create_pickable("Escher", legacy))
        member.roll_low = member.roll_high = 11
        with pytest.raises(ValidationError, match="names no dice"):
            member.full_clean()

    def test_the_dice_are_a_closed_set(self, injury):
        from n26.library.models import Picklist

        picklist = Picklist(name="Loaded", slot_type=injury, dice="d20")
        with pytest.raises(ValidationError):
            picklist.full_clean()

    def test_a_list_that_is_not_a_roll_table_names_no_dice(self, legacies):
        assert legacies.dice == ""
        assert legacies.roll_selects == ""


class TestWhatEachDieCanRoll:
    """The rolls a table has to cover, per die. D66 is the one worth
    stating: it is two D6 read as tens and units, so 37 through 40 can
    never come up and a table that claims them claims nothing."""

    def test_d3_d6_and_2d6(self):
        from n26.library.models import Dice

        assert Dice.rolls(Dice.D3) == (1, 2, 3)
        assert Dice.rolls(Dice.D6) == (1, 2, 3, 4, 5, 6)
        assert Dice.rolls(Dice.TWO_D6) == tuple(range(2, 13))

    def test_d66_is_thirty_six_rolls_with_gaps_between_the_tens(self):
        from n26.library.models import Dice

        rolls = Dice.rolls(Dice.D66)
        assert len(rolls) == 36
        assert rolls[:6] == (11, 12, 13, 14, 15, 16)
        assert rolls[-1] == 66
        assert 37 not in rolls and 40 not in rolls and 47 not in rolls

    def test_a_blank_die_rolls_nothing(self):
        from n26.library.models import Dice

        assert Dice.rolls("") == ()
