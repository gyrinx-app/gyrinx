"""The hire view: a card for a fighter nobody has hired yet.

A preview is built from library alone — a profile and its default
equipment — and produces the same ``ModelCard`` a real hire produces. The
equivalence test below is the point of the whole design: it is what stops
the "what you'd get" screen and the gang sheet from drifting apart.
"""

from urllib.parse import urlencode

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

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
    Stat,
    TargetsMiniature,
)
from n26.tests.sandbox.actions import (
    create_default_set,
    create_hidden,
    create_option_group,
    create_profile,
    create_rule,
    create_skill,
    create_specialisation,
    create_subtype,
    create_wargear,
    create_weapon,
    ef_changes_stat,
    found_gang,
    hire_with_option,
    modifier,
    offer_option,
    offers_choice,
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


class TestStartingXPOnThePreview:
    """A hire opens at its printed Starting XP, and the preview card says
    so before anyone is hired — the built-in carries the opening value,
    and a card built from library alone reads it from there."""

    def test_the_preview_card_opens_at_the_printed_xp(
        self, person_type, gang_type, default_pack
    ):
        from n26.library.authoring import add_built_in, create_counter

        profile = Profile.objects.create(
            name="Brute Ogryn",
            profile_type=person_type,
            gang_type=gang_type,
            price=210,
        )
        add_built_in(profile, create_counter("XP"), amount=61)

        entry = build_hire_entry(profile)
        assert entry.default_option.card.xp == 61

    def test_the_card_you_get_still_matches_it(self, gang, person_type, gang_type):
        """The equivalence this file exists for, extended to XP: the
        preview and the hired card say the same number."""
        from n26.library.authoring import add_built_in, create_counter

        profile = Profile.objects.create(
            name="Brute Ogryn",
            profile_type=person_type,
            gang_type=gang_type,
            price=210,
        )
        add_built_in(profile, create_counter("XP"), amount=61)

        promised = build_hire_entry(profile).default_option.card
        hired = build_model_card(hire_with_option(gang, profile, "Grunt"))
        assert promised.xp == hired.xp == 61


class TestTheCardFollowsTheMainPick:
    """Pick the arc welder and the card in front of you carries it.

    Every main-pick option's card is served in the row's HTML — each was
    already built, one per option against an otherwise-default selection
    — and the radios only decide which is visible. Without scripting the
    default card shows.
    """

    @pytest.fixture
    def ogryn(self, person_type, gang_type, default_pack):
        profile = Profile.objects.create(
            name="Brute Ogryn",
            profile_type=person_type,
            gang_type=gang_type,
            price=210,
        )
        offer_option(profile, "As standard", price=0, position=0)
        offer_option(
            profile,
            "With arc welder",
            price=25,
            thing=create_wargear("Arc welder mk-VII"),
            position=1,
        )
        return profile

    def drawn(self, profile):
        from django.template import Context, Template
        from django_cotton.compiler_regex import CottonCompiler

        entry = build_hire_entry(profile)
        return Template(
            CottonCompiler().process(
                '<c-n26.profile-picker.row :entry="entry" value="ogryn" />'
            )
        ).render(Context({"entry": entry}))

    def test_every_main_pick_card_is_on_the_row(self, ogryn):
        body = self.drawn(ogryn)
        # The wargear's own name renders only inside its option's card —
        # the radio label says "With arc welder", never the item's name.
        assert "Arc welder mk-VII" in body
        assert 'x-show="mainpick === 0"' in body
        assert 'x-show="mainpick === 1"' in body

    def test_only_the_default_card_shows_before_anything_is_pressed(self, ogryn):
        """The alternatives arrive cloaked; scripting only ever narrows
        what is already there."""
        body = self.drawn(ogryn)
        cloaked = body.count('x-show="mainpick === 1" x-cloak')
        assert cloaked == 1
        assert 'x-show="mainpick === 0" x-cloak' not in body


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


# =========================================================================
# The card behind a row, for the whole of what the row is set to
# =========================================================================


@pytest.fixture
def hirer(db):
    return User.objects.create_user("keeper")


@pytest.fixture
def spawn_gang(gang_type, hirer):
    return found_gang("Spawn Keepers", gang_type, owner=hirer, budget=1000)


@pytest.fixture
def spawn(person_type, gang_type, default_pack, make_statline):
    """A Chaos Spawn: the printed band, and the dice as option groups.

    The book rolls each characteristic at a table and the roster takes
    the option matching the die, so the sets do not add kit — they *set*
    a characteristic outright. Two such groups is what makes this the
    content to test a preview with: answering both is a fighter neither
    group's own card depicts.

    A third set of options grants a mutation instead, which is the other
    thing a set can carry: kit and a rule, priced.
    """
    profile = create_profile("Chaos Spawn", person_type, gang_type, price=90)
    make_statline(profile, movement=4, weapon_skill=4, toughness=5)

    rolled = {}
    for position, (short, band) in enumerate([("WS", 3), ("T", 6)]):
        stat = Stat.objects.get(short_name=short)
        group = create_option_group(
            profile, f"Warped Monstrosity: {short}", position=position
        )
        offer_option(
            profile,
            "rolled 2-5",
            default_set=create_default_set(f"{short} rolled 2-5"),
            position=0,
            group=group,
        )
        rolled[short] = create_default_set(
            f"{short} rolled 6 set",
            members=[
                create_hidden(
                    f"{short} rolled 6",
                    effects=[
                        (
                            targets_model(),
                            ef_changes_stat(stat, mode="set", amount=band),
                        )
                    ],
                )
            ],
        )
        offer_option(
            profile, "rolled 6", default_set=rolled[short], position=1, group=group
        )

    mutations = create_option_group(profile, "Mutations", choose="any", position=2)
    rolled["horns"] = create_default_set(
        "Iron horns",
        members=[create_wargear("Iron horns"), create_rule("Berserk Charge")],
        price=15,
    )
    offer_option(
        profile, "Iron horns", default_set=rolled["horns"], position=0, group=mutations
    )
    return profile, rolled


def hire_screen(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def card_address(gang, profile, *sets, entry=None):
    """Where the card for this selection is served — the address the row
    builds, written out here the way a reader's browser would."""
    address = reverse("n26-hire-card", args=[gang.pk, profile.pk])
    params = [
        *(("option", str(chosen.pk)) for chosen in sets),
        *([("entry", str(entry.pk))] if entry is not None else []),
    ]
    return f"{address}?{urlencode(params)}" if params else address


class TestThePreviewFollowsEveryOption:
    """A hire row's card shows the fighter as configured — every option
    ticked on it, not the one group the main pick answers.

    The card is fetched, because the alternative is a card per
    combination and enumerating those is exactly the explosion the option
    groups exist to avoid. So the selection is in the address: repeat
    ``option`` and the fragment composes them.
    """

    def test_two_answered_groups_both_show_on_one_card(
        self, client, hirer, spawn_gang, spawn
    ):
        """Roll a 6 for Weapon Skill and a 6 for Toughness and the card
        says both. Each group's own card knows only its own answer, so a
        card following one of them shows a fighter nobody is buying."""
        profile, rolled = spawn
        client.force_login(hirer)
        response = client.get(
            card_address(spawn_gang, profile, rolled["WS"], rolled["T"])
        )

        card = response.context["card"]
        assert card.statline.get("WS").value == "3+"
        assert card.statline.get("T").value == "6"

        # And on the fragment itself: a changed cell says what changed it,
        # which is the only place either roll's name can appear.
        body = response.content.decode()
        assert "WS changed by WS rolled 6" in body
        assert "T changed by T rolled 6" in body

    def test_answering_one_group_leaves_the_others_printed(
        self, client, hirer, spawn_gang, spawn
    ):
        """One option is what a row asked for before, and it still means
        what it meant: this set taken, everything else as standard."""
        profile, rolled = spawn
        client.force_login(hirer)
        response = client.get(card_address(spawn_gang, profile, rolled["WS"]))

        card = response.context["card"]
        assert card.statline.get("WS").value == "3+"
        assert card.statline.get("T").value == "5"

    def test_a_card_asked_for_nothing_is_the_default_hire(
        self, client, hirer, spawn_gang, spawn
    ):
        profile, _ = spawn
        client.force_login(hirer)
        response = client.get(card_address(spawn_gang, profile))

        card = response.context["card"]
        assert card.statline.get("WS").value == "4+"
        assert card.statline.get("T").value == "5"
        assert card.rating == 90

    def test_a_set_that_grants_kit_and_a_rule_shows_both(
        self, client, hirer, spawn_gang, spawn
    ):
        """What an option set brings is what the hire would write, so it
        is on the card that stands for the hire: the whole payload, not
        the surcharge alone."""
        profile, rolled = spawn
        client.force_login(hirer)
        response = client.get(
            card_address(spawn_gang, profile, rolled["T"], rolled["horns"])
        )

        card = response.context["card"]
        assert [line.name for line in card.equipment] == ["Iron horns"]
        assert [line.name for line in card.rules] == ["Berserk Charge"]
        assert card.statline.get("T").value == "6"

        body = response.content.decode()
        assert "Iron horns" in body
        assert "Berserk Charge" in body

    def test_the_price_is_every_option_on_top_of_the_base(
        self, client, hirer, spawn_gang, spawn
    ):
        """The card quotes what the hire would charge for exactly this
        selection — the same arithmetic the dialog quotes, so a reader
        never meets two numbers for one fighter."""
        profile, rolled = spawn
        client.force_login(hirer)
        response = client.get(
            card_address(spawn_gang, profile, rolled["WS"], rolled["horns"])
        )

        quoted = profile.price_with([rolled["WS"], rolled["horns"]])
        assert quoted == 105
        assert response.context["card"].rating == quoted
        assert f"{quoted}¢" in response.content.decode()

    def test_a_set_this_fighter_does_not_offer_is_a_broken_link(
        self, client, hirer, spawn_gang, spawn
    ):
        """One forged option in a selection spoils the address, however
        genuine the rest of it is."""
        from n26.library.models import DefaultAssignmentSet

        profile, rolled = spawn
        stray = DefaultAssignmentSet.objects.create(name="Someone else's", price=10)
        client.force_login(hirer)

        response = client.get(card_address(spawn_gang, profile, rolled["WS"], stray))
        assert response.status_code == 404

    def test_two_answers_to_one_group_are_refused(
        self, client, hirer, spawn_gang, spawn
    ):
        """A group offering one answer cannot be given two — no row can
        produce it, and the hire itself refuses the same selection."""
        profile, rolled = spawn
        client.force_login(hirer)
        both = card_address(
            spawn_gang, profile, rolled["WS"], profile.options.first().default_set
        )

        assert client.get(both).status_code == 404

    def test_the_row_says_which_set_each_control_stands_for(
        self, client, hirer, spawn_gang, spawn
    ):
        """The address is composed from the controls, so each input has to
        name the set it would take. Without that the row can build one
        option's address and no combination's."""
        profile, rolled = spawn
        client.force_login(hirer)
        body = client.get(hire_screen(spawn_gang)).content.decode()

        assert f'data-set="{rolled["WS"].pk}"' in body
        assert f'data-set="{rolled["horns"].pk}"' in body

    def test_the_card_follows_the_rows_own_address(
        self, client, hirer, spawn_gang, spawn
    ):
        """One fetched card per row, refetched as the address changes —
        rather than one per main-pick option, switched between."""
        profile, _ = spawn
        client.force_login(hirer)
        body = client.get(hire_screen(spawn_gang)).content.decode()

        assert 'x-effect="fetchIt(card)"' in body
        assert card_address(spawn_gang, profile) in body
        # Still no drawn cards in the document: the statline is the
        # marker, because nothing else on this list draws one.
        assert "Weapon Skill" not in body
