"""The hire view: a card for a fighter nobody has hired yet.

A preview is built from library alone — a profile and its default
equipment — and produces the same ``ModelCard`` a real hire produces. The
equivalence test below is the point of the whole design: it is what stops
the "what you'd get" screen and the gang sheet from drifting apart.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card_from_profile, build_modifier_index
from n26.core.effects import compute
from n26.core.hire import build_hire_entry, build_hire_list, section_hire_list
from n26.core.render import build_model_card, card_to_model_card
from n26.core.render_text import render_model_card
from n26.core.taxonomy import UNCATEGORISED
from n26.library.models import (
    AddsAssignable,
    OpAddsMiniature,
    Profile,
    Specialisation,
    TargetsMiniature,
)
from n26.tests.sandbox.actions import (
    create_default_set,
    create_skill,
    create_specialisation,
    create_subtype,
    create_wargear,
    create_weapon,
    found_gang,
    hire_with_option,
    modifier,
    offer_option,
    offers_choice,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def weapons(db):
    return {
        name: create_weapon(name, profiles=[("Attack", 0)])
        for name in (
            "Chemical cloud breath",
            "Gaseous eruption breath",
            "Talons",
            "Razor-sharp talons",
        )
    }


@pytest.fixture
def khimerix(person_type, gang_type, weapons, default_pack):
    profile = Profile.objects.create(
        name="Khimerix", profile_type=person_type, gang_type=gang_type, price=210
    )
    profile.built_ins = create_default_set(
        "Khimerix built-ins", members=[create_subtype("Exotic Beast")]
    )
    profile.save()
    for position, (name, members, price) in enumerate(
        [
            ("Standard Khimerix", ["Chemical cloud breath", "Talons"], 0),
            ("Eruption breath", ["Gaseous eruption breath", "Talons"], 25),
            (
                "Eruption and razors",
                ["Gaseous eruption breath", "Razor-sharp talons"],
                50,
            ),
        ]
    ):
        offer_option(
            profile,
            name,
            default_set=create_default_set(
                name, members=[weapons[n] for n in members], price=price
            ),
            position=position,
        )
    return profile


def preview(profile, option=None):
    card = build_card_from_profile(profile, option=option)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return card_to_model_card(card, computed=compute(card, index), name=profile.name)


class TestAPreviewCard:
    def test_it_needs_no_gang_and_no_model(self, khimerix):
        """Nothing is written; there is nothing to write it to."""
        from n26.core.models import Assignment, Miniature

        card = preview(khimerix)

        assert card.name == "Khimerix"
        assert Miniature.objects.count() == 0
        assert Assignment.objects.count() == 0

    def test_it_shows_the_built_ins_and_the_default_option(self, khimerix):
        card = preview(khimerix)
        assert card.type_line == "Fighter (Exotic Beast)"
        assert [w.name for w in card.weapons] == [
            "Chemical cloud breath",
            "Talons",
        ]

    def test_it_shows_the_advertised_price(self, khimerix):
        assert preview(khimerix).rating == 210

    def test_naming_an_option_changes_what_is_shown_and_charged(self, khimerix):
        both = khimerix.options.get(default_set__name="Eruption and razors").default_set
        card = preview(khimerix, option=both)

        assert [w.name for w in card.weapons] == [
            "Gaseous eruption breath",
            "Razor-sharp talons",
        ]
        assert card.rating == 260

    def test_weapons_carry_their_profiles(self, khimerix):
        """The whole point of a preview: seeing what the thing does."""
        for weapon in preview(khimerix).weapons:
            assert weapon.profiles, f"{weapon.name} has no profile lines"

    def test_everything_says_it_came_from_the_profile(self, khimerix):
        card = preview(khimerix)
        (subtype,) = card.subtypes
        assert subtype.provenance.source == "Khimerix"
        assert subtype.provenance.source_kind == "profile"
        assert subtype.provenance.reason == "default"

    def test_it_renders(self, khimerix):
        text = "\n".join(render_model_card(preview(khimerix)))
        print("\n" + text)
        assert "Khimerix — 210cr" in text
        assert "Talons" in text
        assert "— 0cr" not in text


class TestTheCardYouGetIsTheCardYouWerePromised:
    """The guarantee that makes two loaders safe."""

    def _comparable(self, card):
        return (
            card.rating,
            card.type_line,
            [(w.name, [p.name for p in w.profiles]) for w in card.weapons],
            [(s.name, s.provenance) for s in card.skills],
            [(e.name, e.provenance) for e in card.equipment],
            [(s.name, s.provenance) for s in card.subtypes],
            [(c.kind_label, c.chosen) for c in card.choices],
            [(e.description, e.provenance) for e in card.effects],
        )

    def test_the_default_hire_matches_its_preview(self, gang, khimerix):
        promised = preview(khimerix)
        beast = hire_with_option(gang, khimerix, "Growler")
        delivered = build_model_card(beast)

        assert self._comparable(promised) == self._comparable(delivered)

    def test_an_optioned_hire_matches_its_preview(self, gang, khimerix):
        chosen = khimerix.options.get(default_set__name="Eruption breath").default_set

        promised = preview(khimerix, option=chosen)
        beast = hire_with_option(gang, khimerix, "Growler", option=chosen)
        delivered = build_model_card(beast)

        assert self._comparable(promised) == self._comparable(delivered)

    def test_only_the_name_and_experience_differ(self, gang, khimerix):
        promised = preview(khimerix)
        beast = hire_with_option(gang, khimerix, "Growler")

        assert promised.name == "Khimerix"
        assert build_model_card(beast).name == "Growler"


class TestModifiersRunInAPreview:
    def test_a_granted_skill_shows_before_you_buy(self, person_type, gang_type):
        """Built-ins carry modifiers, and a preview computes them."""
        mounted = create_subtype("Mounted")
        modifier(
            "Mounted grants Hit & Run",
            TargetsMiniature.objects.create(),
            AddsAssignable.objects.create(skill=create_skill("Hit & Run")),
            carried_by=mounted,
        )
        profile = Profile.objects.create(
            name="Outrider", profile_type=person_type, gang_type=gang_type, price=90
        )
        profile.built_ins = create_default_set("Outrider kit", members=[mounted])
        profile.save()

        card = preview(profile)
        assert card.type_line == "Fighter (Mounted)"
        assert [s.name for s in card.skills] == ["Hit & Run"]
        assert card.skills[0].provenance.computed is True

    def test_an_unresolved_choice_shows_as_an_open_row(self, person_type, gang_type):
        specialist = create_subtype("Specialist")
        modifier(
            "Specialist chooses a specialisation",
            TargetsMiniature.objects.create(),
            offers_choice(Specialisation),
            carried_by=specialist,
        )
        create_specialisation("Sharpshooter", grants_skill=create_skill("Fast Shot"))

        profile = Profile.objects.create(
            name="Specialist Ganger",
            profile_type=person_type,
            gang_type=gang_type,
            price=60,
        )
        profile.built_ins = create_default_set("Specialist kit", members=[specialist])
        profile.save()

        card = preview(profile)
        (choice,) = card.choices
        assert choice.kind_label == "Specialisation"
        assert choice.is_resolved is False

    def test_a_pet_wargear_says_what_it_will_bring(self, person_type, gang_type):
        """Point 4: a stored effect is visible before it has happened."""
        mastiff = Profile.objects.create(
            name="Cyber-mastiff",
            profile_type=person_type,
            gang_type=gang_type,
            price=100,
        )
        wargear = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "Cyber-mastiff wargear brings a pet",
            TargetsMiniature.objects.create(),
            OpAddsMiniature.objects.create(profile=mastiff),
            carried_by=wargear,
        )
        profile = Profile.objects.create(
            name="Beast Handler",
            profile_type=person_type,
            gang_type=gang_type,
            price=80,
        )
        profile.built_ins = create_default_set("Handler kit", members=[wargear])
        profile.save()

        card = preview(profile)
        (effect,) = card.effects
        assert effect.description == "adds a Cyber-mastiff"
        assert effect.happened is False
        assert effect.provenance.source == "Cyber-mastiff (pet)"

        text = "\n".join(render_model_card(card))
        print("\n" + text)
        assert "Adds a Cyber-mastiff (when taken)" in text

    def test_previewing_a_pet_wargear_creates_no_pet(self, person_type, gang_type):
        from n26.core.models import Miniature

        mastiff = Profile.objects.create(
            name="Cyber-mastiff",
            profile_type=person_type,
            gang_type=gang_type,
            price=100,
        )
        wargear = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "brings a pet",
            TargetsMiniature.objects.create(),
            OpAddsMiniature.objects.create(profile=mastiff),
            carried_by=wargear,
        )
        profile = Profile.objects.create(
            name="Handler", profile_type=person_type, gang_type=gang_type, price=80
        )
        profile.built_ins = create_default_set("kit", members=[wargear])
        profile.save()

        preview(profile)
        preview(profile)
        assert Miniature.objects.count() == 0


class TestTheHireEntry:
    def test_every_option_gets_its_own_card(self, khimerix):
        entry = build_hire_entry(khimerix)

        assert [option.name for option in entry.options] == [
            "Standard Khimerix",
            "Eruption breath",
            "Eruption and razors",
        ]
        assert [option.total_price for option in entry.options] == [210, 235, 260]
        for option in entry.options:
            assert option.card.weapons

    def test_the_head_of_the_list_is_the_default(self, khimerix):
        entry = build_hire_entry(khimerix)
        assert entry.default_option.name == "Standard Khimerix"
        assert entry.base_price == 210
        assert entry.offers_a_choice is True

    def test_the_price_is_the_surcharge_and_the_total_is_the_bill(self, khimerix):
        entry = build_hire_entry(khimerix)
        eruption = next(o for o in entry.options if o.name == "Eruption breath")
        assert eruption.price == 25
        assert eruption.total_price == 235

    def test_a_profile_with_no_options_still_offers_one(self, make_profile):
        """So a UI never branches on whether choices exist."""
        plain = make_profile("Escher Ganger", price=55)
        entry = build_hire_entry(plain)

        (only,) = entry.options
        assert only.name == "As standard"
        assert only.is_default is True
        assert only.total_price == 55
        assert only.default_set is None
        assert entry.offers_a_choice is False

    def test_the_option_carries_the_set_to_hire_with(self, gang, khimerix):
        """What the UI hands back to ``hire``."""
        entry = build_hire_entry(khimerix)
        chosen = next(o for o in entry.options if o.name == "Eruption breath")

        beast = hire_with_option(gang, khimerix, "Growler", option=chosen.default_set)
        assert beast.membership.ledger_entry.paid == chosen.total_price


class TestAnOptionalPickOnTheRow:
    """A one-or-none set on the hire screen: radios, none of them
    checked by the data, and a "None" row that makes taking nothing
    pressable — a pressed radio group cannot otherwise be unpressed."""

    @pytest.fixture
    def grenadier(self, person_type, gang_type, default_pack):
        from n26.library.authoring import create_option_group

        profile = Profile.objects.create(
            name="Grenadier",
            profile_type=person_type,
            gang_type=gang_type,
            price=100,
        )
        maybe = create_option_group(profile, "A grenade", choose="one-or-none")
        offer_option(
            profile,
            "Choke gas",
            price=15,
            thing=create_wargear("Choke gas grenades"),
            group=maybe,
        )
        return profile

    def test_the_entry_marks_no_default_and_charges_nothing_for_it(self, grenadier):
        entry = build_hire_entry(grenadier)
        maybe = entry.groups[1]
        assert maybe.choose == "one-or-none"
        # Even a single option is a choice: taking it or not.
        assert maybe.offers_a_choice is True
        assert not any(option.is_default for option in maybe.options)
        assert entry.base_price == 100

    def test_the_row_draws_a_checked_none_radio(self, grenadier):
        from django.template import Context, Template
        from django_cotton.compiler_regex import CottonCompiler

        entry = build_hire_entry(grenadier)
        drawn = Template(
            CottonCompiler().process(
                '<c-n26.profile-picker.row :entry="entry" value="grenadier" />'
            )
        ).render(Context({"entry": entry}))
        assert "Choose one, or none" in drawn
        assert ">None</span>" in drawn
        assert 'value=""' in drawn

    def test_taking_nothing_is_not_a_pick(self, grenadier):
        from django.http import QueryDict

        from n26.core.views.hire import _picks

        entry = build_hire_entry(grenadier)
        scope = str(grenadier.pk).lower()
        none_taken = QueryDict(f"{scope}:1=")
        assert _picks(none_taken, grenadier, entry) == []

        one_taken = QueryDict(f"{scope}:1=0")
        (pick,) = _picks(one_taken, grenadier, entry)
        assert pick.option.name == "Choke gas"


class TestTheWholeScreen:
    @pytest.fixture
    def roster(self, person_type, gang_type, default_pack, weapons, make_statline):
        for name, rating in [("Juve", 25), ("Ganger", 55), ("Champion", 110)]:
            profile = Profile.objects.create(
                name=name,
                profile_type=person_type,
                gang_type=gang_type,
                price=rating,
            )
            make_statline(profile, movement=5, weapon_skill=4)
            profile.built_ins = create_default_set(
                f"{name} kit", members=[weapons["Talons"]]
            )
            profile.save()
        return gang_type

    def test_it_lists_everything_hireable_cheapest_first(self, roster):
        entries = build_hire_list(roster)
        assert [entry.name for entry in entries] == ["Juve", "Ganger", "Champion"]
        assert [entry.base_price for entry in entries] == [25, 55, 110]

    def test_every_entry_has_a_drawable_card(self, roster):
        for entry in build_hire_list(roster):
            card = entry.default_option.card
            assert card.statline.cells
            assert card.weapons[0].profiles

    def test_a_longer_list_costs_no_more_queries(
        self, roster, person_type, weapons, default_pack
    ):
        """The house rule: invariance, not a magic number."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert build_hire_list(roster)
            return len(captured.captured_queries)

        few = measure()

        for index in range(9):
            profile = Profile.objects.create(
                name=f"Extra {index}",
                profile_type=person_type,
                gang_type=roster,
                price=40 + index,
            )
            profile.built_ins = create_default_set(
                f"Extra kit {index}", members=[weapons["Talons"]]
            )
            profile.save()

        assert len(build_hire_list(roster)) == 12
        assert measure() == few


class TestSectioningTheList:
    """The picker's shape: sections of categories, each drawn once.

    Nothing here needs a request. The page draws what this returns, so
    what a tab is called, what a heading is called and what a row filters
    under are all one answer, checked here rather than through HTML.
    """

    @pytest.fixture
    def sections(self, default_pack):
        from n26.library.models import Section

        return {
            name: Section.objects.create(name=name, position=position)
            for position, name in enumerate(["Gang List", "Brutes", "Hangers-on"])
        }

    @pytest.fixture
    def categorised(self, sections, make_profile):
        from n26.library.models import Category

        def _make(name, price, section=None, category=None, position=0):
            home = None
            if section is not None:
                home, _ = Category.objects.get_or_create(
                    section=sections[section], name=category, position=position
                )
            return make_profile(name, price=price, category=home)

        return _make

    def test_headings_come_in_taxonomy_order_with_entries_cheapest_first(
        self, gang_type, categorised
    ):
        categorised("Khimerix", 190, "Brutes", "Beasts")
        categorised("Ganger", 55, "Gang List", "Gangers", position=1)
        categorised("Juve", 25, "Gang List", "Juves", position=2)
        categorised("Leader", 120, "Gang List", "Gangers", position=1)

        drawn = section_hire_list(build_hire_list(gang_type))

        assert [section.name for section in drawn] == ["Gang List", "Brutes"]
        assert [category.name for category in drawn[0].categories] == [
            "Gangers",
            "Juves",
        ]
        assert [entry.name for entry in drawn[0].categories[0].entries] == [
            "Ganger",
            "Leader",
        ]

    def test_a_profile_with_no_home_gathers_at_the_end(self, gang_type, categorised):
        categorised("Ganger", 55, "Gang List", "Gangers")
        categorised("Stray", 40)

        drawn = section_hire_list(build_hire_list(gang_type))

        assert [section.name for section in drawn] == ["Gang List", UNCATEGORISED]
        # The category stays unnamed: the content really did file nothing,
        # and the picker draws such rows straight inside the section.
        (homeless,) = drawn[-1].categories
        assert homeless.name == ""
        assert [entry.name for entry in homeless.entries] == ["Stray"]

    def test_two_headings_of_the_same_name_are_one_section(
        self, gang_type, sections, categorised, make_profile
    ):
        """A section drawn twice is a tab drawn twice, and the strip keys
        its tabs by name — so one of the two would show the other's rows,
        and a reader would meet the same heading further down the page
        holding different fighters.

        Two packs each naming a heading "Gang List" is how it happens: a
        heading's name is unique within a pack and nowhere else.
        """
        from n26.library.authoring import create_pack
        from n26.library.models import Category, Section

        theirs = create_pack("House rules", slug="house-rules")
        second = Section.objects.create(name="Gang List", position=2, pack=theirs)
        theirs_category = Category.objects.create(
            section=second, name="Bounty hunters", position=9, pack=theirs
        )
        categorised("Ganger", 55, "Gang List", "Gangers")
        categorised("Khimerix", 190, "Brutes", "Beasts")
        make_profile("Bounty Hunter", price=80, category=theirs_category)

        drawn = section_hire_list(build_hire_list(gang_type))

        assert [section.name for section in drawn] == ["Gang List", "Brutes"]
        assert [category.name for category in drawn[0].categories] == [
            "Gangers",
            "Bounty hunters",
        ]

    def test_one_category_name_under_two_headings_stays_two_categories(
        self, gang_type, categorised
    ):
        """A category name is only unique within its heading, so matching
        on the string would fold two different categories into one."""
        categorised("Ganger", 55, "Gang List", "Specialists")
        categorised("Rogue Doc", 80, "Hangers-on", "Specialists")

        drawn = section_hire_list(build_hire_list(gang_type))

        assert [
            (section.name, [category.name for category in section.categories])
            for section in drawn
        ] == [("Gang List", ["Specialists"]), ("Hangers-on", ["Specialists"])]

    def test_every_entry_is_reachable_from_the_sections(self, gang_type, categorised):
        """The structure is the whole screen: an entry the grouping drops
        is a fighter served nowhere."""
        for number, name in enumerate(["Juve", "Ganger", "Champion", "Stray"]):
            categorised(name, 25 + number, "Gang List" if number < 3 else None, "Crew")

        entries = build_hire_list(gang_type)
        drawn = section_hire_list(entries)

        assert sorted(
            entry.name for section in drawn for entry in section.all_entries()
        ) == sorted(entry.name for entry in entries)
