"""Rendering a gang: the data structures, then a crude text view of them.

The statline shape follows the rulebook's Escher Gang Sister example
(04-characteristics-and-profiles): M WS BS S T W I A Sv on one line, then
Ld Cl Wil Int — the psychology stats, which are highlighted — then Type and
Current/Target XP.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card
from n26.core.render import build_ledger, build_model_card, render_gang
from n26.core.render_text import gang_to_text, ledger_to_text, render_model_card
from n26.library.models import Profile, ProfileType, StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    assign,
    buy_weapon_profile,
    create_skill,
    create_stat,
    create_subtype,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    remove,
    set_statline,
)

pytestmark = pytest.mark.django_db

#: (short, full, flags, first_of_group, highlighted) in card order.
FIGHTER_STATS = [
    ("M", "Movement", {"is_inches": True}, True, False),
    ("WS", "Weapon Skill", {"is_target": True, "is_inverted": True}, False, False),
    ("BS", "Ballistic Skill", {"is_target": True, "is_inverted": True}, False, False),
    ("S", "Strength", {}, False, False),
    ("T", "Toughness", {}, False, False),
    ("W", "Wounds", {}, False, False),
    ("I", "Initiative", {}, False, False),
    ("A", "Attacks", {}, False, False),
    ("Sv", "Save", {"is_target": True, "is_inverted": True}, False, False),
    ("Ld", "Leadership", {}, True, True),
    ("Cl", "Cool", {}, False, True),
    ("Wil", "Willpower", {}, False, True),
    ("Int", "Intelligence", {}, False, True),
]

GANG_SISTER = {
    "movement": 5,
    "weapon_skill": 4,
    "ballistic_skill": 4,
    "strength": 3,
    "toughness": 3,
    "wounds": 1,
    "initiative": 4,
    "attacks": 1,
    "save": 6,
    "leadership": 6,
    "cool": 6,
    "willpower": 6,
    "intelligence": 6,
}


@pytest.fixture
def fighter_statline_type(db):
    statline_type = StatlineType.objects.create(name="Fighter")
    for position, (short, full, flags, first, highlighted) in enumerate(FIGHTER_STATS):
        StatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=create_stat(short, full, **flags),
            position=position,
            is_first_of_group=first,
            is_highlighted=highlighted,
        )
    return statline_type


@pytest.fixture
def fighter_type(fighter_statline_type):
    return ProfileType.objects.create(
        name="Fighter", statline_type=fighter_statline_type
    )


@pytest.fixture
def gang_sister(fighter_type, gang_type, default_pack):
    profile = Profile.objects.create(
        name="Escher Gang Sister",
        profile_type=fighter_type,
        gang_type=gang_type,
        price=55,
    )
    set_statline(profile, **GANG_SISTER)
    return profile


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def yolanda(gang_sister, gang_type, player):
    gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
    mini = hire(gang, gang_sister, "Yolanda", paid=55)
    mini.xp, mini.xp_target = 13, 19
    mini.save()

    assign(create_subtype("Ganger"), miniature=mini)
    assign(create_subtype("Specialist"), miniature=mini)
    assign(create_skill("Nerves of Steel"), miniature=mini)
    shotgun = give_weapon(
        mini,
        create_weapon(
            "Combat Shotgun", profiles=[("Salvo ammo", 0), ("Firestorm ammo", 30)]
        ),
        paid=60,
    )
    buy_weapon_profile(shotgun, shotgun.weapon.profiles.get(price=30))
    assign(create_wargear("Mesh Armour"), miniature=mini, paid=15)
    return mini


class TestTheStatline:
    def test_every_characteristic_is_present_in_order(self, yolanda):
        card = build_model_card(yolanda)
        assert [cell.short_name for cell in card.statline.cells] == [
            short for short, *_ in FIGHTER_STATS
        ]

    def test_values_are_formatted_by_their_own_rules(self, yolanda):
        statline = build_model_card(yolanda).statline
        assert statline.get("M").value == '5"'  # a distance
        assert statline.get("WS").value == "4+"  # a roll target
        assert statline.get("S").value == "3"  # a plain number
        assert statline.get("Sv").value == "6+"

    def test_it_splits_into_the_card_s_two_groups(self, yolanda):
        groups = build_model_card(yolanda).statline.groups()
        assert [[cell.short_name for cell in group] for group in groups] == [
            ["M", "WS", "BS", "S", "T", "W", "I", "A", "Sv"],
            ["Ld", "Cl", "Wil", "Int"],
        ]

    def test_the_psychology_stats_are_highlighted(self, yolanda):
        statline = build_model_card(yolanda).statline
        highlighted = [cell.short_name for cell in statline.cells if cell.highlighted]
        assert highlighted == ["Ld", "Cl", "Wil", "Int"]


class TestTheCard:
    def test_the_type_line_lists_type_then_subtypes(self, yolanda):
        assert build_model_card(yolanda).type_line == "Fighter (Ganger, Specialist)"

    def test_cost_is_everything_on_the_model(self, yolanda):
        assert build_model_card(yolanda).rating == 55 + 60 + 30 + 15

    def test_a_weapon_shows_base_extras_and_total(self, yolanda):
        weapon = build_model_card(yolanda).weapons[0]
        assert weapon.name == "Combat Shotgun"
        assert weapon.base_rating == 60
        assert weapon.extras_rating == 30
        assert weapon.total_rating == 90

    def test_each_ammo_shows_what_it_contributed(self, yolanda):
        weapon = build_model_card(yolanda).weapons[0]
        contributions = {p.name: p.rating for p in weapon.profiles}
        assert contributions == {
            # Free with the gun — the mandatory first profile.
            "Salvo ammo": 0,
            # Bought separately.
            "Firestorm ammo": 30,
        }
        # Deliberately no "is this free" question here: a zero says the
        # line added nothing to the rating, which is also true of ammo
        # bundled into a hire that the package price paid 50cr for.

    def test_skills_and_equipment_are_split_out(self, yolanda):
        card = build_model_card(yolanda)
        assert [s.name for s in card.skills] == ["Nerves of Steel"]
        assert [e.name for e in card.equipment] == ["Mesh Armour"]

    def test_xp_reads_as_current_over_target(self, yolanda):
        assert build_model_card(yolanda).xp_display == "13/19"

    def test_an_unknown_target_is_shown_as_a_dash(self, yolanda):
        yolanda.xp_target = None
        yolanda.save()
        assert build_model_card(yolanda).xp_display == "13/–"

    def test_a_model_with_no_statline_still_renders(
        self, gang_type, player, fighter_type
    ):
        bare = Profile.objects.create(
            name="Nameless", profile_type=fighter_type, gang_type=gang_type
        )
        gang = found_gang("Nobodies", gang_type, owner=player, budget=100)
        mini = hire(gang, bare, "Nobody", paid=10)
        card = build_model_card(mini)
        assert card.statline.cells == []
        assert card.type_line == "Fighter"


class TestTheGangSheet:
    def test_it_carries_the_headline_numbers(self, yolanda):
        gang = yolanda.gang
        gang.refresh_from_db()
        sheet = render_gang(gang)

        assert sheet.name == "The Bad Girls"
        assert sheet.rating == 160
        assert sheet.credits == 1000 - 160
        assert sheet.wealth == 1000
        assert [card.name for card in sheet.models] == ["Yolanda"]

    def test_query_count_does_not_grow_with_the_gang(
        self, yolanda, gang_sister, default_pack
    ):
        """The real property: more models must not mean more queries.

        Both measurements are of the *same* gang with the *same* kit per
        model, so only the number of models differs — otherwise a prefetch
        that only fires for weapons would make the comparison meaningless.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        gang = yolanda.gang
        gang.starting_credits = 5000
        gang.save()

        def equip(name):
            mini = hire(gang, gang_sister, name, paid=55)
            give_weapon(
                mini,
                create_weapon(f"{name}'s gun", profiles=[("Solid ammo", 0)]),
                paid=25,
            )

        def measure():
            gang.refresh_from_db()
            with CaptureQueriesContext(connection) as captured:
                sheet = render_gang(gang)
                assert all(card.statline.cells for card in sheet.models)
            return len(captured.captured_queries), len(sheet.models)

        equip("Mad Donna")
        few, few_models = measure()

        for index in range(10):
            equip(f"Sister {index}")
        many, many_models = measure()

        assert (few_models, many_models) == (2, 12)
        assert few == many, f"{few} queries for 2 models, {many} for 12"
        # Roughly: the models, the two flat assignment fetches, a narrow
        # hydration pass per relation the cards hold, the statline
        # prefetch chain and the shapes it is drawn to, whatever their
        # owners set by hand, one per assignable kind for the modifier
        # index, the stash read that wealth includes, what a trading post
        # allowance has left, the campaign the gang is playing and the
        # campaign's tokens it holds (design/gang-sheet.md).
        assert many <= 36, f"{many} queries is more than this should ever need"


class TestTheTextRenderer:
    def test_a_card_reads_sensibly(self, yolanda):
        text = "\n".join(render_model_card(build_model_card(yolanda)))
        print("\n" + text)

        assert "Yolanda — 160cr" in text
        assert "Fighter (Ganger, Specialist)" in text
        assert "Combat Shotgun — 90cr (base 60 + extras 30)" in text
        # A line that added nothing carries no number at all — never the
        # word "free", which would claim the thing is worth nothing.
        assert "- Salvo ammo" in text
        assert "(free)" not in text
        # On its own weapon's card a line needs only its own name; the
        # ledger, where a profile stands alone, still says the weapon.
        assert "- Firestorm ammo (+30cr)" in text
        assert "Skills: Nerves of Steel" in text
        assert "Equipment: Mesh Armour" in text
        assert "XP: 13/19" in text

    def test_the_statline_prints_as_two_rows_of_headings_and_values(self, yolanda):
        text = "\n".join(render_model_card(build_model_card(yolanda)))
        assert "M     WS    BS    S     T     W     I     A     Sv" in text
        assert '5"    4+    4+    3     3     1     4     1     6+' in text
        # Highlighted stats are starred by this very basic renderer.
        assert "*Ld   *Cl   *Wil  *Int" in text

    def test_a_whole_gang_renders(self, yolanda):
        gang = yolanda.gang
        gang.refresh_from_db()
        text = gang_to_text(gang)
        print("\n" + text)

        assert text.startswith("The Bad Girls (Escher)")
        assert "Rating 160  Credits 840  Wealth 1000" in text
        assert "Yolanda — 160cr" in text


class TestTheLedger:
    def test_every_acquisition_is_listed(self, yolanda):
        view = build_ledger(yolanda.gang)

        assert [line.what for line in view.lines] == [
            # The gang's founding: free, but an acquisition like any other.
            "Escher",
            "Escher Gang Sister",
            "Ganger",
            "Specialist",
            "Nerves of Steel",
            "Combat Shotgun",
            "Salvo ammo (Combat Shotgun)",
            "Firestorm ammo (Combat Shotgun)",
            "Mesh Armour",
        ]

    def test_it_says_what_each_thing_is_attached_to(self, yolanda):
        view = build_ledger(yolanda.gang)
        where = {line.what: line.where for line in view.lines}

        assert where["Escher Gang Sister"] == "in the gang"
        assert where["Combat Shotgun"] == "on Yolanda"
        assert where["Firestorm ammo (Combat Shotgun)"] == "on Combat Shotgun"

    def test_free_things_are_recorded_with_a_reason(self, yolanda):
        view = build_ledger(yolanda.gang)
        salvo = next(line for line in view.lines if line.what.startswith("Salvo"))

        assert salvo.paid == 0
        assert salvo.reason == "Default equipment"

    def test_the_totals_match_the_gang(self, yolanda):
        gang = yolanda.gang
        gang.refresh_from_db()
        view = build_ledger(gang)

        assert view.total_spent == 160
        assert view.total_rating == gang.rating == 160
        assert view.credits_remaining == gang.credits == 840

    def test_each_line_carries_its_events(self, yolanda):
        view = build_ledger(yolanda.gang)
        shotgun = next(line for line in view.lines if line.what == "Combat Shotgun")

        assert [event.kind for event in shotgun.events] == ["Purchased"]
        assert shotgun.events[0].credits == 60
        assert shotgun.events[0].actor == "player"

    def test_removal_appends_rather_than_erasing(self, yolanda):
        card = build_model_card(yolanda)
        shotgun_assignment = next(
            node.assignment
            for node in build_card(yolanda).roots
            if node.name == "Combat Shotgun"
        )
        remove(shotgun_assignment, note="traded away")
        gang = yolanda.gang
        gang.refresh_from_db()
        view = build_ledger(gang)

        # Still there, still says what it cost.
        shotgun = next(line for line in view.lines if line.what == "Combat Shotgun")
        assert shotgun.removed is True
        assert shotgun.paid == 60
        assert shotgun.rating == 60
        assert [event.kind for event in shotgun.events] == ["Purchased", "Removed"]
        assert shotgun.events[-1].note == "traded away"

        # But it stops counting, while the money stays spent.
        assert view.total_rating == 160 - 90 == gang.rating
        assert view.total_spent == 160
        assert view.credits_remaining == 840
        assert card.rating == 160  # the card built before removal is unchanged

    def test_it_is_a_fixed_number_of_queries(
        self, yolanda, gang_type, gang_sister, player
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count_for(gang):
            with CaptureQueriesContext(connection) as captured:
                view = build_ledger(gang)
                assert all(line.events for line in view.lines)
            return len(captured.captured_queries), len(view.lines)

        one, small_lines = count_for(yolanda.gang)

        crowded = found_gang("The Worse Girls", gang_type, owner=player, budget=5000)
        for index in range(10):
            hire(crowded, gang_sister, f"Sister {index}", paid=55)
        many, big_lines = count_for(crowded)

        assert big_lines > small_lines
        assert one == many, (
            f"{one} queries for {small_lines} lines, {many} for {big_lines}"
        )


class TestTheLedgerText:
    def test_it_reads_sensibly(self, yolanda):
        text = ledger_to_text(yolanda.gang)
        print("\n" + text)

        assert "Ledger — The Bad Girls" in text
        assert "Budget 1000  Spent 160  Remaining 840  Rating 160" in text
        assert "Combat Shotgun on Yolanda — 60cr, rating 60 [Bought]" in text
        assert "Purchased: +60cr, rating +60, by player" in text

    def test_removed_things_are_marked_not_dropped(self, yolanda):
        shotgun_assignment = next(
            node.assignment
            for node in build_card(yolanda).roots
            if node.name == "Combat Shotgun"
        )
        remove(shotgun_assignment, note="traded away")
        text = ledger_to_text(yolanda.gang)
        print("\n" + text)

        assert "[removed]" in text
        assert "Removed: +0cr, rating +0, by player — traded away" in text


class TestAcquisitionReasons:
    """Free and granted are different things; the ledger must not conflate them."""

    def test_something_bought_says_bought(self, yolanda):
        view = build_ledger(yolanda.gang)
        line = next(line for line in view.lines if line.what == "Combat Shotgun")
        assert line.reason == "Bought"
        assert [e.kind for e in line.events] == ["Purchased"]

    def test_something_free_that_nobody_granted_says_free(self, yolanda):
        """Ganger was assigned directly — nothing caused it."""
        view = build_ledger(yolanda.gang)
        line = next(line for line in view.lines if line.what == "Ganger")
        assert line.reason == "Free"
        assert [e.kind for e in line.events] == ["Added"]

    def test_something_another_assignment_brought_says_granted(self, yolanda):
        """The free ammo came with the gun, so it is caused by it."""
        salvo = next(
            node
            for weapon in build_card(yolanda).roots
            for node in weapon.children
            if node.name.startswith("Salvo")
        )
        assert salvo.assignment.caused_by is not None

        view = build_ledger(yolanda.gang)
        line = next(line for line in view.lines if line.what.startswith("Salvo"))
        # give_weapon labels these more precisely still.
        assert line.reason == "Default equipment"
        assert [e.kind for e in line.events] == ["Granted"]

    def test_a_granted_thing_with_no_explicit_reason_says_granted(self, yolanda):
        from n26.core.operations import operation
        from n26.library.models import Subtype

        gang = yolanda.gang
        cause = yolanda.membership
        with operation(gang, actor=gang.owner) as op:
            op.assign(
                Subtype.objects.create(name="Mounted"),
                miniature=yolanda,
                caused_by=cause,
            )

        view = build_ledger(gang)
        line = next(line for line in view.lines if line.what == "Mounted")
        assert line.reason == "Granted by something else"
        assert [e.kind for e in line.events] == ["Granted"]


class TestTheProfileOnTheCard:
    """A card holds three separate facts about what a model is, and none
    can be worked out from another: the name its owner gave it, the
    library entry it was hired from, and its Type."""

    def test_all_three_are_distinct(self, yolanda):
        card = build_model_card(yolanda)
        assert card.name == "Yolanda"  # this one model
        assert card.profile_name == "Escher Gang Sister"  # the shared entry
        assert card.profile_type == "Fighter"  # one of only two Types
        assert card.type_line == "Fighter (Ganger, Specialist)"

    def test_renaming_the_model_leaves_the_profile_alone(self, yolanda):
        """The reason the card cannot derive one from the other: an
        owner renames a miniature the moment they paint it."""
        yolanda.name = "Vesna Krail"
        yolanda.save()

        card = build_model_card(yolanda)
        assert card.name == "Vesna Krail"
        assert card.profile_name == "Escher Gang Sister"

    def test_the_text_card_draws_it_under_the_name(self, yolanda):
        yolanda.name = "Vesna Krail"
        yolanda.save()

        lines = render_model_card(build_model_card(yolanda))
        assert lines[0].startswith("Vesna Krail — ")
        assert lines[1] == "Escher Gang Sister"
        assert lines[2].startswith("Fighter (")

    def test_a_card_with_no_profile_says_nothing_rather_than_a_dash(self):
        """A preview built from loose assignables has no entry to name,
        and a blank draws as nothing."""
        from n26.core.render import ModelCard, Statline

        card = ModelCard(name="Nobody", rating=0, statline=Statline())
        assert card.profile_name == ""
        assert render_model_card(card)[1] == card.type_line
