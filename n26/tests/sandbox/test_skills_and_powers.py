"""Skills, skill sets, placements, and Wyrd powers.

The design (design/collections.md gets the log):

* a skill set is a **home category** — the taxonomy every collection
  shares; a skill's D6 number is its position within the set;
* the catalogue is a **collection with sweeps** — one for skills, one
  for powers;
* a category is fundamental, its **section is dynamic**: ``PlacesCategory``
  modifiers carried by the profile (declared sets) or by a subtype (the
  Wyrd reveal) say where each set sits for this fighter, folded off the
  card like everything else, with "Other" as the browse-time fallback;
* the picker is a **regrouping of a browse**: sections come from the
  fighter's placements, skill sets are the categories beneath.

The proof point: Wyrd powers are NOT skills — a different kind entirely —
yet they show up in the fighter-sectioned views with no special casing:
set-ness lives in the Category and the sweep, not in the kind.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import (
    browse,
    narrow,
    offered_by,
    placements_for,
    regrouped_by_placement,
)
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_model_card
from n26.library.models import Power, Skill
from n26.tests.sandbox.actions import (
    adds,
    assign,
    choose,
    create_category,
    create_collection,
    create_power,
    create_skill,
    create_subtype,
    create_wargear,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    places,
    remove,
    section_of,
    targets_model,
)

pytestmark = pytest.mark.django_db


# --- The content library ---------------------------------------------------


@pytest.fixture
def sets(db):
    """Skill sets and the power family — one taxonomy, two kinds."""
    return {
        "agility": create_category("Skills", "Agility", position=0),
        "brawn": create_category("Skills", "Brawn", position=1),
        "cunning": create_category("Skills", "Cunning", position=2),
        "savant": create_category("Skills", "Savant", position=3),
        "inherent": create_category("Skills", "Inherent", position=6),
        "powers": create_category("Wyrd Powers", "Wyrd Powers", position=10),
    }


@pytest.fixture
def library(sets):
    """A few skills with their D6 positions, and the six core powers."""
    skills = {}
    for set_key, names in [
        ("agility", ["Catfall", "Clamber", "Dodge"]),
        ("brawn", ["Bull Charge", "Bulging Biceps"]),  # D6 order ≠ alphabetical
        ("cunning", ["Backstab", "Infiltrate"]),
        ("savant", ["Connected", "Medicate"]),
        ("inherent", ["Hit & Run", "Inspiring"]),
    ]:
        for number, name in enumerate(names, start=1):
            skills[name] = create_skill(name, category=sets[set_key], position=number)

    powers = {}
    for number, (name, annotation) in enumerate(
        [
            ("Force Blast", "Free, Continuous"),
            ("Flaming Weapon", "Free, Continuous"),
            ("Freeze Time", "Double"),
            ("Weapon Jinx", "Single"),
            ("Terrify", "Double"),
            ("Quickening", "Basic, Continuous"),
        ],
        start=1,
    ):
        powers[name] = create_power(
            name, annotation, category=sets["powers"], position=number
        )
    return {"skills": skills, "powers": powers}


@pytest.fixture
def catalogue(library):
    """The one collection: every skill and every power, by sweep.

    The proof point in fixture form — the powers arrive via a second
    sweep line, and nothing downstream knows or cares that they are a
    different kind.
    """
    return create_collection("Skills & Powers", contains=[Skill, Power])


@pytest.fixture
def tiers(catalogue):
    """The collection's schema: its tiers, their order, and the default.

    Declared once — placements then pick "Primary (Skills & Powers)" by
    row, never restating a string and a magic number.
    """
    return {
        "primary": section_of(catalogue, "Primary", 0),
        "secondary": section_of(catalogue, "Secondary", 1),
        "other": section_of(catalogue, "Other", 9, is_default=True),
    }


@pytest.fixture
def wyrd(sets, tiers):
    """The Wyrd subtype: places the powers family under Secondary
    ("Wyrds treat the Wyrd Powers as a Secondary Skill Set")."""
    subtype = create_subtype("Wyrd")
    modifier(
        "Wyrd reveals the powers",
        targets_model(),
        places(sets["powers"], tiers["secondary"]),
        carried_by=subtype,
    )
    return subtype


@pytest.fixture
def gang_sister(make_profile, sets, tiers):
    """A fighter entry with declared sets: Agility and Cunning under
    Primary, Savant under Secondary — modifiers on the profile, exactly
    like the reveal, each picking a tier row from the schema."""
    profile = make_profile("Escher Gang Sister", price=55)
    for category, tier in [
        (sets["agility"], tiers["primary"]),
        (sets["cunning"], tiers["primary"]),
        (sets["savant"], tiers["secondary"]),
    ]:
        modifier(
            f"Gang Sister: {category.name} under {tier.name}",
            targets_model(),
            places(category, tier),
            carried_by=profile,
        )
    return profile


@pytest.fixture
def gang(gang_type):
    player = User.objects.create_user("tom")
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


def view_for(miniature, catalogue):
    """Browse the catalogue as this fighter sees it: their placements,
    scoped to this collection, falling back to its declared default."""
    card = build_card(miniature)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    placements = placements_for(compute(card, index), catalogue)
    return regrouped_by_placement(
        browse(catalogue), placements, fallback=catalogue.default_section()
    )


def section_names(view):
    return [section.name for section in view.sections]


def categories_in(view, section_name):
    section = next(s for s in view.sections if s.name == section_name)
    return [c.name for c in section.categories]


# --- The fighter-sectioned views ------------------------------------------


class TestTheGradedView:
    def test_the_profile_s_declared_sets_become_the_sections(
        self, gang, gang_sister, catalogue
    ):
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        view = view_for(fighter, catalogue)

        assert section_names(view) == ["Primary", "Secondary", "Other"]
        assert categories_in(view, "Primary") == ["Agility", "Cunning"]
        assert categories_in(view, "Secondary") == ["Savant"]

    def test_unplaced_sets_gather_under_other(self, gang, gang_sister, catalogue):
        """Inherent and the unrevealed powers sit in Other — visible in the
        data, collapsible by a surface. We inform, not police."""
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        view = view_for(fighter, catalogue)

        assert "Brawn" in categories_in(view, "Other")
        assert "Inherent" in categories_in(view, "Other")
        assert "Wyrd Powers" in categories_in(view, "Other")

    def test_the_d6_numbers_are_the_positions(self, gang, gang_sister, catalogue):
        """Random generation is 'roll against the set': an item's position
        within its home category is its D6 number, and the listing shows in
        that order — not alphabetically."""
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        view = view_for(fighter, catalogue)

        section = next(s for s in view.sections if s.name == "Other")
        brawn = next(c for c in section.categories if c.name == "Brawn")
        # Alphabetical would put Bulging Biceps first; the D6 table does not.
        assert [line.name for line in brawn.lines] == [
            "Bull Charge",
            "Bulging Biceps",
        ]

    def test_a_fighter_with_no_placements_sees_everything_as_other(
        self, gang, make_profile, catalogue
    ):
        fighter = hire_with_option(gang, make_profile("Plain", price=30), "Nobody")
        view = view_for(fighter, catalogue)
        assert section_names(view) == ["Other"]

    def test_narrowing_to_primary_is_the_advancement_wording(
        self, gang, gang_sister, catalogue
    ):
        """'Select a new Primary skill' is narrow(view, sections=["Primary"])."""
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        picker = narrow(view_for(fighter, catalogue), sections=["Primary"])

        names = {line.name for line in picker.all_lines()}
        assert "Catfall" in names and "Backstab" in names
        assert "Connected" not in names  # Savant is secondary
        assert "Hit & Run" not in names  # Inherent is nobody's


class TestTheWyrdProofPoint:
    """Powers are not skills, and nothing here special-cases them."""

    def test_the_wyrd_subtype_reveals_the_powers_at_secondary(
        self, gang, gang_sister, catalogue, wyrd
    ):
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assign(wyrd, miniature=fighter)

        view = view_for(fighter, catalogue)
        assert "Wyrd Powers" in categories_in(view, "Secondary")
        assert "Wyrd Powers" not in categories_in(view, "Other")

        section = next(s for s in view.sections if s.name == "Secondary")
        family = next(c for c in section.categories if c.name == "Wyrd Powers")
        assert [line.name for line in family.lines][:2] == [
            "Force Blast (Free, Continuous)",
            "Flaming Weapon (Free, Continuous)",
        ]

    def test_the_reveal_disappears_with_the_subtype(
        self, gang, gang_sister, catalogue, wyrd
    ):
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        carried = assign(wyrd, miniature=fighter)
        remove(carried)

        view = view_for(fighter, catalogue)
        assert "Wyrd Powers" in categories_in(view, "Other")

    def test_wargear_granting_wyrd_reveals_transitively(
        self, gang, gang_sister, catalogue, wyrd
    ):
        """The mount-grants-Mounted precedent: a charm grants the Wyrd
        subtype computedly, and the subtype's own reveal fires through
        the fixed point. Two hops, no rows."""
        charm = create_wargear("Warp-touched Charm")
        modifier("Charm makes a Wyrd", targets_model(), adds(wyrd), carried_by=charm)

        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assign(charm, miniature=fighter, paid=30)

        view = view_for(fighter, catalogue)
        assert "Wyrd Powers" in categories_in(view, "Secondary")

    def test_a_psy_gheist_out_places_the_subtype(
        self, gang, make_profile, sets, tiers, catalogue, wyrd
    ):
        """Profile places powers under Primary (position 0); the subtype
        places them under Secondary (position 1). Lowest section position
        wins — ordering from the schema, not a rule here."""
        psy_gheist = make_profile("Psy-Gheist", price=90)
        modifier(
            "Psy-Gheist: powers under Primary",
            targets_model(),
            places(sets["powers"], tiers["primary"]),
            carried_by=psy_gheist,
        )

        fighter = hire_with_option(gang, psy_gheist, "Echo")
        assign(wyrd, miniature=fighter)

        view = view_for(fighter, catalogue)
        assert "Wyrd Powers" in categories_in(view, "Primary")
        assert "Secondary" not in section_names(view)

    def test_placements_carry_their_provenance(
        self, gang, gang_sister, catalogue, wyrd
    ):
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assign(wyrd, miniature=fighter)

        card = build_card(fighter)
        index = build_modifier_index([n.assignable for n in card.all_nodes()])
        computed = compute(card, index)

        by_category = {p.category.name: p for p in computed.placements}
        assert by_category["Wyrd Powers"].source == "Wyrd"
        assert by_category["Wyrd Powers"].source_kind == "subtype"
        assert by_category["Agility"].source == "Escher Gang Sister"
        assert by_category["Agility"].source_kind == "profile"


class TestTheSchemaIsTheCollections:
    def test_placements_are_scoped_to_their_collection(
        self, gang, gang_sister, sets, catalogue, library
    ):
        """A placement aims at a section row, and section rows belong to
        a collection — so a placement into some other collection's schema
        never leaks into this view."""
        other_collection = create_collection("Somewhere Else", contains=[Skill])
        elsewhere_primary = section_of(other_collection, "Primary", 0)
        exotic = make_exotic = create_subtype("Exotic")
        modifier(
            "Exotic: Brawn primary — but only Somewhere Else",
            targets_model(),
            places(sets["brawn"], elsewhere_primary),
            carried_by=exotic,
        )

        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assign(make_exotic, miniature=fighter)

        here = view_for(fighter, catalogue)
        assert "Brawn" in categories_in(here, "Other")  # not placed HERE

        there = view_for(fighter, other_collection)
        assert "Brawn" in categories_in(there, "Primary")  # placed THERE

    def test_the_default_section_is_content_too(self, gang, make_profile, library):
        """A collection that names its own fallback: unplaced categories
        fall where the schema says, not where code says."""
        from n26.library.models import Power, Skill

        stash = create_collection("The Long List", contains=[Skill, Power])
        section_of(stash, "Uncatalogued", 0, is_default=True)

        fighter = hire_with_option(gang, make_profile("Plain", price=30), "Nobody")
        view = view_for(fighter, stash)
        assert section_names(view) == ["Uncatalogued"]

    def test_a_collection_with_no_declared_default_still_works(
        self, gang, make_profile, library
    ):
        """The code-level "Other", last — a safety net, not the design."""
        from n26.library.models import Skill

        bare = create_collection("Bare List", contains=[Skill])
        fighter = hire_with_option(gang, make_profile("Plain", price=30), "Nobody")
        view = view_for(fighter, bare)
        assert section_names(view) == ["Other"]


class TestKnowingAPower:
    def test_a_wyrd_chooses_a_power_like_a_specialist_chooses(
        self, gang, gang_sister, library, wyrd
    ):
        """Same machinery as the Specialist: the offer is a computed slot,
        the answer is a stored assignment caused by the anchor."""
        from n26.library.models import OffersChoice

        modifier(
            "Wyrd knows a power",
            targets_model(),
            OffersChoice.of(Power),
            carried_by=wyrd,
        )
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        anchor = assign(wyrd, miniature=fighter)

        def card_with_effects():
            card = build_card(fighter, with_statlines=True)
            index = build_modifier_index([n.assignable for n in card.all_nodes()])
            return build_model_card(fighter, card=card, computed=compute(card, index))

        (choice,) = card_with_effects().choices
        assert choice.kind_label == "power"
        assert choice.is_resolved is False

        choose(anchor, library["powers"]["Terrify"])
        (choice,) = card_with_effects().choices
        assert choice.chosen == "Terrify (Double)"

    def test_a_known_power_draws_on_its_own_row(self, gang, gang_sister, library):
        from n26.core.render_text import render_model_card

        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assign(library["powers"]["Quickening"], miniature=fighter)

        card = build_model_card(fighter)
        assert [line.name for line in card.powers] == ["Quickening (Basic, Continuous)"]
        assert card.skills == []
        assert card.equipment == []

        text = "\n".join(render_model_card(card))
        print("\n" + text)
        assert "Powers: Quickening (Basic, Continuous)" in text

    def test_powers_are_priced_like_anything_else(self, gang, gang_sister, sets):
        """Route 6: some powers are bought. The mixin already did the work."""
        from n26.tests.sandbox.actions import buy

        paid_power = create_power("Ember Storm", "Double", price=30)
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assignment = buy(fighter, thing=paid_power)

        assert assignment.ledger_entry.paid == 30
        gang.refresh_from_db()
        assert gang.rating == 55 + 30


class TestWhoMayUseWhat:
    """ "(Fighter Or Walker Only)" as data: an OR-list of profile types
    and subtypes on the item, empty meaning everyone. Marks ride the
    views; nothing is ever removed or blocked."""

    @pytest.fixture
    def walker(self, db):
        return create_subtype("Walker")

    @pytest.fixture
    def beast_type(self, person_statline_type):
        from n26.library.models import ProfileType

        return ProfileType.objects.create(
            name="Vehicle", statline_type=person_statline_type
        )

    def noted_view(self, miniature, catalogue):
        from n26.core.browse import usability_for, with_use_notes

        card = build_card(miniature)
        index = build_modifier_index([n.assignable for n in card.all_nodes()])
        computed = compute(card, index)
        view = regrouped_by_placement(
            browse(catalogue),
            placements_for(computed, catalogue),
            fallback=catalogue.default_section(),
        )
        return with_use_notes(view, usability_for(computed))

    def line(self, view, name):
        return next(ln for ln in view.all_lines() if ln.name.startswith(name))

    def test_unrestricted_means_everyone(self, gang, gang_sister, catalogue):
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        view = self.noted_view(fighter, catalogue)
        assert all(line.notes == () for line in view.all_lines())

    def test_a_type_restriction_excludes_other_types(
        self, gang, gang_sister, library, catalogue, person_type, beast_type, gang_type
    ):
        from n26.tests.sandbox.actions import restrict_use

        restrict_use(library["skills"]["Clamber"], person_type)  # "(Person Only)"

        person = hire_with_option(gang, gang_sister, "Yolanda")
        assert self.line(self.noted_view(person, catalogue), "Clamber").notes == ()

        from n26.library.models import Profile

        beast_profile = Profile.objects.create(
            name="Sump Beast", profile_type=beast_type, gang_type=gang_type, price=40
        )
        beast = hire_with_option(gang, beast_profile, "Growler")
        noted = self.noted_view(beast, catalogue)
        (note,) = self.line(noted, "Clamber").notes
        # The note points at the row itself — identity, never text-matching.
        assert note.about == library["skills"]["Clamber"]
        assert note.level == "warning"
        assert "only" in note.text
        # Noted, not missing: we inform, never police.
        assert self.line(noted, "Clamber") is not None

    def test_the_or_reaches_subtypes(
        self, gang, library, catalogue, beast_type, gang_type, walker, person_type
    ):
        """ "(Person Or Walker Only)": a Walker beast qualifies via the
        subtype even though its type does not match."""
        from n26.library.models import Profile
        from n26.tests.sandbox.actions import restrict_use

        restrict_use(library["skills"]["Catfall"], person_type, walker)

        beast_profile = Profile.objects.create(
            name="Sump Beast", profile_type=beast_type, gang_type=gang_type, price=40
        )
        beast = hire_with_option(gang, beast_profile, "Growler")
        assert self.line(self.noted_view(beast, catalogue), "Catfall").notes

        assign(walker, miniature=beast)
        assert self.line(self.noted_view(beast, catalogue), "Catfall").notes == ()

    def test_a_computed_subtype_counts(
        self,
        gang,
        gang_sister,
        library,
        catalogue,
        walker,
        person_type,
        beast_type,
        gang_type,
    ):
        """Servo-legs grant Walker computedly; walker-only skills follow."""
        from n26.library.models import Profile
        from n26.tests.sandbox.actions import restrict_use

        restrict_use(library["skills"]["Catfall"], walker)
        legs = create_wargear("Servo-legs")
        modifier("Legs grant Walker", targets_model(), adds(walker), carried_by=legs)

        beast_profile = Profile.objects.create(
            name="Sump Beast", profile_type=beast_type, gang_type=gang_type, price=40
        )
        beast = hire_with_option(gang, beast_profile, "Growler")
        assign(legs, miniature=beast, paid=25)

        assert self.line(self.noted_view(beast, catalogue), "Catfall").notes == ()

    def test_powers_can_be_wyrd_only(self, gang, gang_sister, library, catalogue, wyrd):
        from n26.tests.sandbox.actions import restrict_use

        for power in library["powers"].values():
            restrict_use(power, wyrd)

        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        noted = self.noted_view(fighter, catalogue)
        assert self.line(noted, "Force Blast").notes

        assign(wyrd, miniature=fighter)
        noted = self.noted_view(fighter, catalogue)
        assert self.line(noted, "Force Blast").notes == ()

    def test_roll_12_is_a_narrow(
        self, gang, gang_sister, library, catalogue, person_type, beast_type, gang_type
    ):
        """ "Any set — but not what your Type/Subtype cannot use":
        narrow(marked, usable=True), grades ignored."""
        from n26.library.models import Profile
        from n26.tests.sandbox.actions import restrict_use

        restrict_use(library["skills"]["Clamber"], person_type)

        beast_profile = Profile.objects.create(
            name="Sump Beast", profile_type=beast_type, gang_type=gang_type, price=40
        )
        beast = hire_with_option(gang, beast_profile, "Growler")
        anything_legal = narrow(
            self.noted_view(beast, catalogue),
            without_warnings=True,
            name="Roll 12",
        )

        names = {line.name for line in anything_legal.all_lines()}
        assert "Clamber" not in names
        assert "Catfall" in names  # unrestricted: everyone
        assert "Hit & Run" in names  # even Inherent — roll 12 ignores grades

    def test_noting_a_bigger_listing_costs_no_more_queries(
        self, gang, gang_sister, catalogue, sets, person_type
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.tests.sandbox.actions import restrict_use

        fighter = hire_with_option(gang, gang_sister, "Yolanda")

        def measure():
            with CaptureQueriesContext(connection) as captured:
                view = self.noted_view(fighter, catalogue)
                assert any(line.notes for line in view.all_lines())
            return len(captured.captured_queries)

        restrict_use(create_skill("Fated", category=sets["brawn"]), person_type)
        restrict_use(
            create_skill("Doomed", category=sets["brawn"]),
            create_subtype("Chosen"),
        )
        few = measure()

        for index in range(8):
            restrict_use(
                create_skill(f"Extra {index}", category=sets["savant"]),
                create_subtype(f"Cult {index}"),
            )
        assert measure() == few


# --- Picking a skill ------------------------------------------------------


class TestPickingASkill:
    """A Leader arrives with a skill from a set that is Primary for them.

    The last step of the collections design: the offer names a *tier row* — the
    same ``CollectionSection`` a placement aims at — so what a fighter may
    pick is their own view with one section showing. No second
    mechanism, no access table, and the answer differs per fighter
    because their placements do.
    """

    @pytest.fixture
    def leader(self, tiers):
        """The Leader subtype: offers one skill from a Primary set."""
        subtype = create_subtype("Leader")
        modifier(
            "A Leader starts with a Primary skill",
            targets_model(),
            offers_choice(Skill, from_section=tiers["primary"]),
            carried_by=subtype,
        )
        return subtype

    @pytest.fixture
    def yolanda(self, gang, gang_sister, leader, catalogue, library):
        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assign(leader, miniature=fighter)
        return fighter

    def computed_for(self, miniature):
        card = build_card(miniature)
        index = build_modifier_index([n.assignable for n in card.all_nodes()])
        return compute(card, index)

    def slot_of(self, miniature):
        (slot,) = self.computed_for(miniature).choices
        return slot

    def test_the_slot_names_the_tier_it_offers(self, yolanda):
        assert self.slot_of(yolanda).kind_label == "Primary skill"
        assert self.slot_of(yolanda).is_resolved is False

    def test_it_offers_exactly_this_fighter_s_primary_sets(self, yolanda, catalogue):
        computed = self.computed_for(yolanda)
        (slot,) = computed.choices
        offered = offered_by(slot, computed)

        # The Gang Sister declares Agility and Cunning as Primary, so those
        # sets — and only those — are what she may pick from.
        assert [s.name for s in offered.sections] == ["Primary"]
        assert categories_in(offered, "Primary") == ["Agility", "Cunning"]
        names = [line.name for line in offered.all_lines()]
        assert "Catfall" in names  # Agility
        assert "Bull Charge" not in names  # Brawn is not hers

    def test_another_fighter_is_offered_something_else(
        self, gang, make_profile, sets, tiers, leader, catalogue, library
    ):
        """The offer is one content row; the answer is per fighter."""
        goliath = make_profile("Goliath Champion", price=120)
        modifier(
            "Goliath Champion: Brawn under Primary",
            targets_model(),
            places(sets["brawn"], tiers["primary"]),
            carried_by=goliath,
        )
        fighter = hire_with_option(gang, goliath, "Grendel")
        assign(leader, miniature=fighter)

        computed = self.computed_for(fighter)
        (slot,) = computed.choices
        offered = offered_by(slot, computed)

        assert categories_in(offered, "Primary") == ["Brawn"]
        assert [line.name for line in offered.all_lines()] == [
            "Bull Charge",
            "Bulging Biceps",
        ]

    def test_the_offered_skills_keep_their_d6_order(self, yolanda, catalogue):
        """A picker is a shop: same sections, same ordering rules."""
        computed = self.computed_for(yolanda)
        (slot,) = computed.choices
        offered = offered_by(slot, computed)
        agility = next(
            c for s in offered.sections for c in s.categories if c.name == "Agility"
        )
        assert [line.thing.position for line in agility.lines] == sorted(
            line.thing.position for line in agility.lines
        )

    def test_picking_resolves_the_slot_and_lands_on_the_card(self, yolanda, library):
        anchor = yolanda.assignments.get(subtype__name="Leader")
        choose(anchor, library["skills"]["Catfall"])

        slot = self.slot_of(yolanda)
        assert slot.is_resolved is True
        assert slot.chosen_name == "Catfall"

        card = build_model_card(yolanda, computed=self.computed_for(yolanda))
        # Drawn as the choice's own row, not doubled as a loose skill.
        assert [c.chosen for c in card.choices] == ["Catfall"]
        assert "Catfall" not in [s.name for s in card.skills]

    def test_losing_the_leader_takes_the_skill_with_it(self, yolanda, library):
        anchor = yolanda.assignments.get(subtype__name="Leader")
        choose(anchor, library["skills"]["Catfall"])
        remove(anchor)

        computed = self.computed_for(yolanda)
        assert computed.choices == []
        card = build_model_card(yolanda, computed=computed)
        assert "Catfall" not in [s.name for s in card.skills]

    def test_an_off_list_pick_is_still_allowed(self, yolanda, library):
        """Inform, don't police: the narrowing shortens the list a picker
        shows; it is not a rule. The owner may hand a Brawn skill
        to a Gang Sister, and the slot reads as answered."""
        anchor = yolanda.assignments.get(subtype__name="Leader")
        choose(anchor, library["skills"]["Bull Charge"])

        assert self.slot_of(yolanda).chosen_name == "Bull Charge"

    def test_a_wargear_that_grants_a_set_widens_the_offer(
        self, yolanda, sets, tiers, catalogue, library
    ):
        """Transitive, like the Wyrd reveal: anything that places a set
        under Primary widens what the Leader may pick, with no change
        here."""
        manual = create_wargear("Combat manual")
        modifier(
            "Combat manual: Brawn under Primary",
            targets_model(),
            places(sets["brawn"], tiers["primary"]),
            carried_by=manual,
        )
        assign(manual, miniature=yolanda)

        computed = self.computed_for(yolanda)
        (slot,) = computed.choices
        assert categories_in(offered_by(slot, computed), "Primary") == [
            "Agility",
            "Brawn",
            "Cunning",
        ]

    def test_offering_a_kind_with_no_tier_offers_all_of_it(self, yolanda, library):
        """An unnarrowed offer still works — it just answers with the kind."""
        plain = create_subtype("Studious")
        modifier(
            "Studious offers any skill",
            targets_model(),
            offers_choice(Skill),
            carried_by=plain,
        )
        assign(plain, miniature=yolanda)

        computed = self.computed_for(yolanda)
        slot = next(s for s in computed.choices if s.source == "Studious")
        assert slot.kind_label == "skill"
        assert set(offered_by(slot, computed)) == set(Skill.objects.all())

    def test_offering_the_pick_costs_a_fixed_number_of_queries(
        self, yolanda, catalogue, library, sets, tiers
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure():
            with CaptureQueriesContext(connection) as captured:
                computed = self.computed_for(yolanda)
                (slot,) = computed.choices
                assert list(offered_by(slot, computed).all_lines())
            return len(captured.captured_queries)

        few = measure()
        for index in range(8):
            create_skill(
                f"Filler {index}", category=sets["agility"], position=index + 10
            )
        assert measure() == few
