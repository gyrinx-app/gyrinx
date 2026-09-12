"""Folding stat changes onto a printed value, within the stat's limits.

A characteristic is never worsened past its minimum or improved past its
maximum; the part of a change that would take it there is disregarded
rather than kept for later. No database: a stat is built in memory with
the flags and limits the shipped definitions carry.
"""

from datetime import datetime, timedelta

import pytest

from n26.core.card import Card, Node
from n26.core.effects import StatChange
from n26.core.render import (
    AssignableLine,
    Provenance,
    StashLine,
    _provenance_within,
    apply_changes,
    card_to_model_card,
    collapse,
)
from n26.library.models import Stat, Wargear, Weapon


def stat(short_name, full_name, **flags):
    """A stat in memory. The pack is left unset so that nothing here
    reaches for the database to find the default one."""
    return Stat(pack_id=None, short_name=short_name, full_name=full_name, **flags)


STRENGTH = stat("S", "Strength", minimum=1, maximum=10)
SAVE = stat("Sv", "Save", is_target=True, is_inverted=True, minimum=6, maximum=3)
WEAPON_SKILL = stat(
    "WS", "Weapon Skill", is_target=True, is_inverted=True, minimum=6, maximum=2
)
ARMOUR_PIERCING = stat("AP", "Armour Piercing", is_inverted=True)

T0 = datetime(2026, 1, 1)


def change(stat, mode, amount=1, at=None, source="a rule"):
    acquired = None if at is None else T0 + timedelta(days=at)
    return StatChange(
        stat=stat, mode=mode, amount=amount, source=source, acquired=acquired
    )


class TestWorseningStopsAtTheMinimum:
    def test_three_injuries_leave_a_strength_of_three_at_one(self):
        injuries = [change(STRENGTH, "worsen", at=day) for day in range(3)]
        value, sources, held = apply_changes(STRENGTH, "3", injuries)
        assert value == "1"
        assert held == "minimum"
        assert len(sources) == 3

    def test_a_fourth_injury_changes_nothing_more(self):
        injuries = [change(STRENGTH, "worsen", at=day) for day in range(4)]
        assert apply_changes(STRENGTH, "3", injuries)[0] == "1"

    def test_a_roll_target_stops_at_its_worst_number(self):
        """The minimum of a Save is 6+: a higher number, since the stat
        improves downwards, so the limit is a ceiling on the number."""
        value, _, held = apply_changes(SAVE, "5+", [change(SAVE, "worsen", 3)])
        assert value == "6"
        assert held == "minimum"

    def test_a_change_that_lands_exactly_on_the_limit_is_not_held(self):
        value, _, held = apply_changes(STRENGTH, "2", [change(STRENGTH, "worsen")])
        assert value == "1"
        assert held == ""


class TestImprovingStopsAtTheMaximum:
    def test_strength_stops_at_ten(self):
        value, _, held = apply_changes(STRENGTH, "9", [change(STRENGTH, "improve", 3)])
        assert value == "10"
        assert held == "maximum"

    def test_weapon_skill_stops_at_two_plus(self):
        value, _, held = apply_changes(
            WEAPON_SKILL, "3+", [change(WEAPON_SKILL, "improve", 2)]
        )
        assert value == "2"
        assert held == "maximum"


class TestTheSurplusIsDisregarded:
    """The part of a change past the limit is not kept for later: what
    is worsened to the floor and then improved stands one above it."""

    def test_an_improvement_after_the_injuries_lifts_the_stat_off_the_floor(self):
        changes = [change(STRENGTH, "worsen", at=day) for day in range(10)]
        changes.append(change(STRENGTH, "improve", at=10, source="Bionic arm"))
        assert apply_changes(STRENGTH, "3", changes)[0] == "2"

    def test_an_improvement_before_the_injuries_is_worn_away_by_them(self):
        changes = [change(STRENGTH, "improve", at=0, source="Bionic arm")]
        changes.extend(change(STRENGTH, "worsen", at=day) for day in range(1, 11))
        assert apply_changes(STRENGTH, "3", changes)[0] == "1"

    def test_changes_fold_in_the_order_acquired_whatever_order_they_arrive_in(self):
        later = change(STRENGTH, "improve", at=10, source="Bionic arm")
        earlier = [change(STRENGTH, "worsen", at=day) for day in range(3)]
        assert apply_changes(STRENGTH, "3", [later, *earlier])[0] == "2"

    def test_the_sources_read_in_the_order_the_changes_landed(self):
        later = change(STRENGTH, "improve", at=10, source="Bionic arm")
        earlier = change(STRENGTH, "worsen", at=0, source="Spinal Injury")
        _, sources, _ = apply_changes(STRENGTH, "3", [later, earlier])
        assert [source.source for source in sources] == ["Spinal Injury", "Bionic arm"]

    def test_the_latest_set_wins_whatever_order_the_sets_arrive_in(self):
        first = change(STRENGTH, "set", 5, at=0)
        second = change(STRENGTH, "set", 7, at=1)
        assert apply_changes(STRENGTH, "3", [second, first])[0] == "7"

    def test_a_stat_lifted_off_its_floor_is_no_longer_held_there(self):
        """Held at a limit describes the value as it stands: once a later
        change moves it away, the cell can be worsened again."""
        changes = [change(STRENGTH, "worsen", at=day) for day in range(3)]
        changes.append(change(STRENGTH, "improve", at=10, source="Bionic arm"))
        value, _, held = apply_changes(STRENGTH, "3", changes)
        assert (value, held) == ("2", "")

    def test_a_stat_held_at_its_floor_again_says_so(self):
        changes = [change(STRENGTH, "worsen", at=day) for day in range(3)]
        changes.append(change(STRENGTH, "improve", at=10, source="Bionic arm"))
        changes.append(change(STRENGTH, "worsen", 2, at=11))
        value, _, held = apply_changes(STRENGTH, "3", changes)
        assert (value, held) == ("1", "minimum")

    def test_a_change_nothing_stored_stands_behind_folds_first(self):
        """A built-in's change is part of what the card prints, so it
        lands before anything the model acquired."""
        printed = change(STRENGTH, "improve", source="Brute")
        acquired = [change(STRENGTH, "worsen", at=day) for day in range(3)]
        assert apply_changes(STRENGTH, "3", [*acquired, printed])[0] == "1"


class TestWhatTheLimitsLeaveAlone:
    def test_a_value_already_past_the_limit_is_not_pulled_back(self):
        """An owner may set a Strength of 0 by hand; an injury then
        changes nothing, and neither raises it to 1."""
        value, _, held = apply_changes(STRENGTH, "0", [change(STRENGTH, "worsen")])
        assert value == "0"
        assert held == "minimum"

    def test_a_stat_without_limits_moves_freely(self):
        assert (
            apply_changes(ARMOUR_PIERCING, "-", [change(ARMOUR_PIERCING, "improve")])[0]
            == "-1"
        )
        assert (
            apply_changes(
                ARMOUR_PIERCING, "-1", [change(ARMOUR_PIERCING, "improve", 5)]
            )[0]
            == "-6"
        )

    def test_a_value_that_is_not_a_number_passes_through(self):
        value, sources, held = apply_changes(
            STRENGTH, "S+1", [change(STRENGTH, "improve")]
        )
        assert value == "S+1"
        assert len(sources) == 1
        assert held == ""

    def test_a_set_lands_first_and_the_shifts_fold_onto_it(self):
        changes = [
            change(STRENGTH, "worsen", at=0),
            change(STRENGTH, "set", 5, at=1),
        ]
        assert apply_changes(STRENGTH, "3", changes)[0] == "4"

    def test_a_set_is_not_held_to_the_limits(self):
        """A set is authored content, like the printed value: the limits
        govern what folds on top of it, not the value itself."""
        assert apply_changes(STRENGTH, "3", [change(STRENGTH, "set", 12)])[0] == "12"

    def test_no_changes_means_no_touch(self):
        assert apply_changes(STRENGTH, "3", []) == ("3", [], "")


class TestGrantProvenance:
    """An explicit grant label takes precedence over the cause, even when blank."""

    @pytest.mark.parametrize("surface", ["model", "gang"])
    @pytest.mark.parametrize(
        "source, kind, expected_source, expected_kind",
        [
            ("", "", "", ""),
            ("Strength rolled 6", "", "Strength rolled 6", ""),
            (None, None, "Slashing claws", "weapon"),
            ("", None, "", "weapon"),
        ],
    )
    def test_only_missing_grant_labels_fall_back_to_the_cause(
        self, surface, source, kind, expected_source, expected_kind
    ):
        cause = Node(Weapon(pack_id=None, name="Slashing claws"), key=1)
        granted = Node(
            Wargear(pack_id=None, name="Armoured undersuit"),
            key=2,
            caused_by_key=cause.key,
            computed=True,
            granted_by=source,
            granted_by_kind=kind,
        )
        card = Card(miniature=None, roots=[cause], granted=[granted])

        if surface == "model":
            provenance = (
                card_to_model_card(card, name="Yolanda").equipment[0].provenance
            )
        else:
            provenance = _provenance_within(card)(granted)

        assert provenance.source == expected_source
        assert provenance.source_kind == expected_kind
        assert provenance.computed is True


def line(name, key="library.wargear:1", reason="bought", rating=0, id=""):
    return AssignableLine(
        name=name,
        key=key,
        provenance=Provenance(reason=reason),
        rating=rating,
        id=id,
    )


class TestCollapse:
    """Identical lines are drawn once with a count; anything that differs
    in content, provenance or rating keeps its own line."""

    def test_two_of_one_thing_are_one_line_counting_two(self):
        (kept,) = collapse([line("Respirator", id="a"), line("Respirator", id="b")])
        assert kept.name == "Respirator"
        assert kept.count == 2
        assert kept.count_mark == " (x2)"

    def test_a_line_standing_for_several_names_no_assignment(self):
        (kept,) = collapse([line("Respirator", id="a"), line("Respirator", id="b")])
        assert kept.id == ""

    def test_one_of_a_thing_reads_bare_and_keeps_its_assignment(self):
        (kept,) = collapse([line("Respirator", id="a")])
        assert kept.count == 1
        assert kept.count_mark == ""
        assert kept.id == "a"

    def test_the_first_keeps_its_place_and_later_ones_fold_into_it(self):
        kept = collapse(
            [
                line("Respirator"),
                line("Filter plugs", key="library.wargear:2"),
                line("Respirator"),
            ]
        )
        assert [(k.name, k.count) for k in kept] == [
            ("Respirator", 2),
            ("Filter plugs", 1),
        ]

    def test_one_bought_and_one_granted_are_two_lines(self):
        bought = line("Respirator")
        granted = AssignableLine(
            name="Respirator",
            key="library.wargear:1",
            provenance=Provenance(source="Mounted", computed=True),
        )
        kept = collapse([bought, granted])
        assert [k.count for k in kept] == [1, 1]
        assert [k.provenance.computed for k in kept] == [False, True]

    def test_two_pinned_at_different_figures_are_two_lines(self):
        kept = collapse([line("Respirator", rating=15), line("Respirator", rating=10)])
        assert [(k.rating, k.count) for k in kept] == [(15, 1), (10, 1)]

    def test_the_same_name_from_different_content_is_two_lines(self):
        kept = collapse(
            [
                line("Respirator", key="library.wargear:1"),
                line("Respirator", key="library.wargear:9"),
            ]
        )
        assert [k.count for k in kept] == [1, 1]

    def test_a_line_with_no_key_stands_alone_however_many_are_alike(self):
        kept = collapse(
            [line("Cyber-mastiff (pet)", key=""), line("Cyber-mastiff (pet)", key="")]
        )
        assert [k.count for k in kept] == [1, 1]

    def test_a_stash_line_folds_the_same_way_keeping_one_items_rating(self):
        lines = [
            StashLine(
                name="Lasgun", rating=15, kind="weapon", key="library.weapon:1", id="a"
            ),
            StashLine(
                name="Lasgun", rating=15, kind="weapon", key="library.weapon:1", id="b"
            ),
        ]
        (kept,) = collapse(lines)
        assert (kept.count, kept.rating, kept.id) == (2, 15, "")
        assert kept.count_mark == " (x2)"


RESPIRATOR = Wargear(pack_id=None, name="Respirator")


def held(thing, key, reason=None):
    """One assignment of ``thing`` on a card built in memory. Two nodes of
    one instance are two of one thing; a second instance is other content,
    since content carries its identity from the moment it is made."""
    return Node(thing, key=key, reason=reason)


class TestTheCardStacksItsRepeats:
    """A card built in memory: two of one wargear are one gear line,
    unless the card is built for a page whose lines carry acts."""

    def test_two_of_one_wargear_are_one_gear_line(self):
        card = Card(miniature=None, roots=[held(RESPIRATOR, 1), held(RESPIRATOR, 2)])
        (kept,) = card_to_model_card(card, name="Yolanda").equipment
        assert (kept.name, kept.count) == ("Respirator", 2)

    def test_the_models_own_page_keeps_one_line_per_assignment(self):
        card = Card(miniature=None, roots=[held(RESPIRATOR, 1), held(RESPIRATOR, 2)])
        drawn = card_to_model_card(card, name="Yolanda", collapse_repeats=False)
        assert [(k.name, k.count) for k in drawn.equipment] == [
            ("Respirator", 1),
            ("Respirator", 1),
        ]

    def test_different_reasons_keep_their_own_lines(self):
        card = Card(
            miniature=None,
            roots=[
                held(RESPIRATOR, 1, reason="bought"),
                held(RESPIRATOR, 2, reason="default"),
            ],
        )
        drawn = card_to_model_card(card, name="Yolanda")
        assert [k.provenance.reason for k in drawn.equipment] == ["bought", "default"]

    def test_other_content_of_the_same_name_keeps_its_own_line(self):
        other = Wargear(pack_id=None, name="Respirator")
        card = Card(miniature=None, roots=[held(RESPIRATOR, 1), held(other, 2)])
        drawn = card_to_model_card(card, name="Yolanda")
        assert [k.count for k in drawn.equipment] == [1, 1]
