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
    attach_interstitial,
    create_default_set,
    create_interstitial,
    create_pickable,
    create_picklist,
    create_rule,
    create_slot,
    create_slot_type,
    create_wargear,
    detach_interstitial,
    revise,
)
from n26.library.models import DefaultAssignment, Interstitial, Slot

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
    happened, so "31-46" on a D66 is a band of twelve rolls, not sixteen.
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

    def test_the_database_refuses_a_backwards_band_too(self, table, injury):
        from n26.library.models import PicklistMember

        with pytest.raises(IntegrityError), transaction.atomic():
            PicklistMember.objects.create(
                picklist=table,
                pickable=create_pickable("Backwards", injury),
                roll_low=26,
                roll_high=21,
            )

    def test_a_band_on_a_list_that_names_no_dice_is_refused_in_words(
        self, legacies, legacy
    ):
        """Refused by the verb, which is the path every page and every
        importer takes; the model's own check is the backstop for a
        bare write."""
        with pytest.raises(ValidationError, match="names no dice"):
            add_picklist_member(
                legacies, create_pickable("Escher", legacy), roll_low=11
            )

    def test_a_half_roll_table_is_refused_in_words(self, injury):
        with pytest.raises(ValidationError, match="names its dice and how"):
            create_picklist("Half", injury, dice="d66")
        with pytest.raises(ValidationError, match="names its dice and how"):
            create_picklist("Other half", injury, roll_selects="band")

    def test_the_database_refuses_a_half_roll_table_too(self, injury):
        from n26.library.models import Picklist

        with pytest.raises(IntegrityError), transaction.atomic():
            Picklist.objects.create(name="Bare", slot_type=injury, dice="d66")

    def test_the_model_refuses_a_half_roll_table_where_a_verb_was_bypassed(
        self, injury
    ):
        """An edit through the admin, or any path that runs clean(), is
        turned away in words rather than by the database."""
        from n26.library.models import Picklist

        half = Picklist(name="Half", slot_type=injury, dice="d66")
        with pytest.raises(ValidationError, match="names its dice and how"):
            half.clean()

    def test_the_high_end_of_a_band_alone_is_refused_in_words(self, table, injury):
        with pytest.raises(ValidationError, match="both ends or neither"):
            add_picklist_member(
                table, create_pickable("Half", injury), roll_low=None, roll_high=51
            )

    def test_a_band_running_backwards_is_refused_in_words(self, table, injury):
        with pytest.raises(ValidationError, match="runs upwards"):
            add_picklist_member(
                table, create_pickable("Backwards", injury), roll_low=26, roll_high=21
            )

    def test_the_model_says_the_same_where_a_verb_was_bypassed(self, table, injury):
        from n26.library.models import PicklistMember

        member = PicklistMember(
            picklist=table, pickable=create_pickable("Stray", injury), roll_high=51
        )
        with pytest.raises(ValidationError, match="both ends or neither"):
            member.clean()

    def test_the_dice_are_a_closed_set(self, injury):
        from n26.library.models import Picklist

        picklist = Picklist(name="Loaded", slot_type=injury, dice="d20")
        with pytest.raises(ValidationError):
            picklist.full_clean()

    def test_a_list_that_is_not_a_roll_table_names_no_dice(self, legacies):
        assert legacies.dice == ""
        assert legacies.roll_selects == ""


class TestCoverage:
    """Whether a table's bands claim its die: gaps and overlaps make a
    table unrollable, and neither can be seen one row at a time — which
    is what the table page exists to show."""

    @pytest.fixture
    def injury(self, default_pack):
        return create_slot_type("Lasting Injury", allows_repeats=True)

    @pytest.fixture
    def table(self, injury):
        return create_picklist(
            "Lasting Injury Table", injury, dice="d66", roll_selects="band"
        )

    def add(self, table, injury, name, low, high=None):
        return add_picklist_member(
            table, create_pickable(name, injury), roll_low=low, roll_high=high
        )

    def test_a_band_counts_only_rolls_the_die_can_produce(self, table, injury):
        """ "31-46" on a D66 is twelve rolls, not sixteen: 37 through 40
        can never come up."""
        from n26.library.views import coverage

        self.add(table, injury, "Grievous Wound", 31, 46)
        said = coverage(table)
        assert said.total == 36
        assert said.covered == 12

    def test_unclaimed_rolls_are_named(self, table, injury):
        from n26.library.views import coverage

        self.add(table, injury, "Out Cold", 21, 26)
        said = coverage(table)
        assert 11 in said.unclaimed and 66 in said.unclaimed
        assert 22 not in said.unclaimed
        assert 37 not in said.unclaimed

    def test_a_roll_claimed_twice_names_both_results(self, table, injury):
        from n26.library.views import coverage

        self.add(table, injury, "Eye Injury", 51)
        self.add(table, injury, "Hand Injury", 51, 52)
        said = coverage(table)
        assert [m.label for m in dict(said.doubled)[51]] == [
            "Eye Injury",
            "Hand Injury",
        ]
        assert 52 not in dict(said.doubled)

    def test_a_complete_table_reports_itself_whole(self, injury):
        from n26.library.views import coverage

        table = create_picklist("Whole", injury, dice="d6", roll_selects="band")
        self.add(table, injury, "Low", 1, 3)
        self.add(table, injury, "High", 4, 6)
        said = coverage(table)
        assert said.covered == said.total == 6
        assert said.unclaimed == []
        assert said.doubled == []

    def test_a_bandless_result_claims_nothing_and_is_named(self, table, injury):
        from n26.library.views import coverage

        add_picklist_member(table, create_pickable("Lesson Learnt", injury))
        said = coverage(table)
        assert [m.label for m in said.bandless] == ["Lesson Learnt"]
        assert said.covered == 0


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


class TestAnInterstitialOnASlot:
    """An interstitial is a screen attached to slots. Its own contract:
    one per pack by name, attached to a slot once, and read back off
    the slot in the order it was attached."""

    @pytest.fixture
    def house_legacy(self, legacy, legacies):
        return create_slot("House legacy", legacy, legacies, label="Gang Legacy")

    @pytest.fixture
    def archetype(self, legacy, legacies):
        return create_slot("Archetype", legacy, legacies)

    def test_two_interstitials_of_one_name_are_refused(self, default_pack):
        create_interstitial("Outcast archetype")
        with pytest.raises(IntegrityError), transaction.atomic():
            create_interstitial("outcast archetype")

    def test_the_heading_is_the_title_where_there_is_one(self, default_pack):
        shown = create_interstitial("Outcast archetype", title="Choose an archetype")
        assert shown.heading == "Choose an archetype"

    def test_the_name_stands_in_where_there_is_not(self, default_pack):
        assert create_interstitial("Outcast archetype").heading == "Outcast archetype"

    def test_it_cannot_be_skipped_unless_an_author_says_so(self, default_pack):
        assert create_interstitial("Outcast archetype").skippable is False

    def test_it_is_attached_to_a_slot_once(self, house_legacy):
        shown = create_interstitial("Outcast archetype", slots=[house_legacy])
        with pytest.raises(ValidationError, match="already attached to House legacy"):
            attach_interstitial(shown, house_legacy)

    def test_the_database_refuses_a_second_attachment_too(self, house_legacy):
        """An importer writing rows straight through the ORM is caught by
        the constraint the verb's sentence stands in front of."""
        from n26.library.models import InterstitialSlot

        shown = create_interstitial("Outcast archetype", slots=[house_legacy])
        with pytest.raises(IntegrityError), transaction.atomic():
            InterstitialSlot.objects.create(interstitial=shown, slot=house_legacy)

    def test_each_attachment_lands_after_the_last_unless_placed(
        self, house_legacy, archetype
    ):
        shown = create_interstitial("Outcast archetype")
        first = attach_interstitial(shown, house_legacy)
        second = attach_interstitial(shown, archetype)
        placed = attach_interstitial(
            shown, create_slot("Third", archetype.slot_type, archetype.picklist), 7
        )
        assert (first.position, second.position, placed.position) == (0, 1, 7)

    def test_a_default_position_lands_after_the_last_whatever_it_was_numbered(
        self, house_legacy, archetype
    ):
        shown = create_interstitial("Outcast archetype")
        attach_interstitial(shown, house_legacy, position=7)
        later = attach_interstitial(shown, archetype)

        assert later.position == 8
        assert [a.slot for a in shown.attachments.all()] == [house_legacy, archetype]

    def test_an_archived_attachment_still_counts_for_the_next_position(
        self, house_legacy, archetype
    ):
        shown = create_interstitial("Outcast archetype")
        revise(attach_interstitial(shown, house_legacy, position=3), archived=True)

        assert attach_interstitial(shown, archetype).position == 4

    def test_an_attachment_reads_as_both_of_its_ends(self, house_legacy):
        shown = create_interstitial("Outcast archetype")
        assert str(attach_interstitial(shown, house_legacy)) == (
            "Outcast archetype on House legacy"
        )

    def test_a_slot_reads_its_interstitials_in_the_order_they_were_attached(
        self, house_legacy
    ):
        later = create_interstitial("Said later", position=0)
        first = create_interstitial("Said first", position=5)
        attach_interstitial(first, house_legacy, position=0)
        attach_interstitial(later, house_legacy, position=1)

        assert list(house_legacy.interstitials) == [first, later]

    def test_an_archived_interstitial_is_not_read_off_the_slot(self, house_legacy):
        shown = create_interstitial("Outcast archetype", slots=[house_legacy])
        revise(shown, archived=True)

        assert list(house_legacy.interstitials) == []

    def test_an_attachment_in_an_archived_pack_is_not_read_off_the_slot(
        self, house_legacy, homebrew
    ):
        shown = create_interstitial("Outcast archetype")
        attach_interstitial(shown, house_legacy, pack=homebrew)
        revise(homebrew, archived=True)

        assert list(house_legacy.interstitials) == []

    def test_an_attachment_lands_in_its_interstitials_pack(
        self, house_legacy, homebrew
    ):
        shown = create_interstitial("Outcast archetype", pack=homebrew)

        assert attach_interstitial(shown, house_legacy).pack == homebrew

    def test_a_refused_attachment_leaves_the_transaction_around_it_usable(
        self, house_legacy
    ):
        """The constraint stands behind the check, for two attachments
        made at once; it refuses inside a savepoint of its own, so a
        page that made the attempt inside a transaction can still say
        so rather than finding its transaction aborted."""
        from unittest import mock

        from n26.library.models import InterstitialSlot

        shown = create_interstitial("Outcast archetype")
        InterstitialSlot.objects.create(interstitial=shown, slot=house_legacy)
        nothing_yet = mock.Mock(return_value=mock.Mock(exists=lambda: False))
        with transaction.atomic():
            with mock.patch.object(InterstitialSlot.objects, "filter", nothing_yet):
                with pytest.raises(ValidationError, match="already attached"):
                    attach_interstitial(shown, house_legacy, position=1)
            # Still inside the outer transaction, and it still answers.
            assert InterstitialSlot.objects.count() == 1

    def test_an_archived_attachment_is_not_read_off_the_slot(self, house_legacy):
        shown = create_interstitial("Outcast archetype")
        attachment = attach_interstitial(shown, house_legacy)
        revise(attachment, archived=True)

        assert list(house_legacy.interstitials) == []
        # Withdrawn from this slot only: the interstitial itself stands.
        assert Interstitial.objects.filter(pk=shown.pk).exists()

    def test_detaching_leaves_the_slot_and_the_interstitial_standing(
        self, house_legacy
    ):
        shown = create_interstitial("Outcast archetype")
        detach_interstitial(attach_interstitial(shown, house_legacy))

        assert list(house_legacy.interstitials) == []
        assert Interstitial.objects.filter(pk=shown.pk).exists()
        assert Slot.objects.filter(pk=house_legacy.pk).exists()

    def test_a_slot_carrying_an_interstitial_cannot_be_deleted_under_it(
        self, house_legacy
    ):
        """The attachment protects the slot the way a picklist member
        protects its pickable: the screen has to be detached first."""
        from django.db.models import ProtectedError

        create_interstitial("Outcast archetype", slots=[house_legacy])
        with pytest.raises(ProtectedError), transaction.atomic():
            house_legacy.delete()

    def test_the_deletion_plan_sends_the_author_to_the_interstitials_page(
        self, house_legacy
    ):
        """An attachment has no page of its own, so the refusal names the
        act that clears it rather than a row nobody can open."""
        from n26.library.deletion import plan_deletion

        create_interstitial("Outcast archetype", slots=[house_legacy])
        plan = plan_deletion([house_legacy])

        assert not plan.ok
        assert any(
            "“Outcast archetype” is shown when House legacy arrives; stop showing it there first"
            in words
            for words in plan.refusals
        ), plan.refusals

    def test_deleting_the_interstitial_too_frees_the_slot(self, house_legacy):
        """Whichever order the two are named in: the attachment goes with
        the interstitial, and the slot is free once it has."""
        from n26.library.deletion import plan_deletion

        shown = create_interstitial("Outcast archetype", slots=[house_legacy])

        assert plan_deletion([shown, house_legacy]).ok
        assert plan_deletion([house_legacy, shown]).ok
