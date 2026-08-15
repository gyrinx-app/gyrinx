"""The reach prose: what a piece of content does, and how anyone gets it.

Every sentence here is pinned to its exact wording, so a change to the
voice is a change somebody made on purpose. The setups are the rulebook's
own — the Master of Whispers, a corrupted gang, a line one house's
equipment list restricts — because a voice is only right if it is right
about those.
"""

import pytest

from n26.library import prose
from n26.library.authoring import (
    add_built_in,
    add_default_member,
    add_entry,
    attach_modifiers_to,
    counter_at_least,
    create_affiliation,
    create_category,
    create_collection,
    create_counter,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_power,
    create_profile,
    create_rule,
    create_section,
    create_skill,
    create_subtype,
    create_trait,
    create_wargear,
    create_weapon,
    ef_adds,
    ef_allows_at_most,
    ef_changes_category,
    ef_changes_stat,
    ef_offers_choice,
    ef_places,
    ef_removes,
    ef_requires_companions,
    has_subtypes,
    has_traits,
    modifier,
    offer_option,
    op_adds_model,
    op_changes_counter,
    section_of,
    targets_gang,
    targets_model,
    targets_weapons,
)
from n26.library.prose import prose_for, sentence_for
from n26.library.references import references_to
from n26.tests.sandbox.actions import assign, buy, found_gang, hire

pytestmark = pytest.mark.django_db


def texts(said):
    return [sentence.text for sentence in said]


@pytest.fixture
def backstab(default_pack):
    return create_trait("Backstab")


@pytest.fixture
def mounted(default_pack):
    return create_subtype("Mounted")


@pytest.fixture
def escher(default_pack):
    return create_gang_type("Escher")


@pytest.fixture
def buffs_weapons(backstab):
    """One modifier — the same row, whoever ends up carrying it."""
    return modifier("Backstab", targets_weapons(), ef_adds(backstab))


class TestWhoTheSentenceIsAbout:
    """The same modifier reads three ways, and the carrier decides which.

    Nothing about the modifier changes: what changes is who holds it, so
    the subject is worked out from the carriage rather than written down
    anywhere on the row.
    """

    def test_a_subtype_speaks_of_anyone_with_that_subtype(self, buffs_weapons, mounted):
        attach_modifiers_to(mounted, [buffs_weapons])

        assert texts(prose_for(mounted).does) == [
            "A Mounted fighter's weapons gain Backstab, while the subtype stands."
        ]

    def test_wargear_speaks_of_whoever_carries_it(self, buffs_weapons, default_pack):
        cutter = create_wargear("Cutter")
        attach_modifiers_to(cutter, [buffs_weapons])

        assert texts(prose_for(cutter).does) == [
            "Its bearer's weapons gain Backstab, while they carry it."
        ]

    def test_a_rule_the_gang_holds_speaks_of_every_fighter(self, buffs_weapons, escher):
        house_rule = create_rule("Blade Honed")
        attach_modifiers_to(house_rule, [buffs_weapons])
        add_built_in(escher, house_rule)

        assert texts(prose_for(house_rule).does) == [
            "Every fighter's weapons gain Backstab, while the gang holds this."
        ]

    def test_a_modifier_nothing_carries_names_no_one(self, buffs_weapons):
        assert sentence_for(buffs_weapons).text == (
            "The weapons of whoever ends up carrying this gain Backstab, "
            "while they carry it."
        )

    def test_the_composer_reads_an_unattached_modifier_the_same_way(
        self, buffs_weapons
    ):
        said = prose_for(buffs_weapons)

        assert texts(said.does) == [
            "The weapons of whoever ends up carrying this gain Backstab, "
            "while they carry it."
        ]
        assert said.referenced_by == ()
        assert said.assigned_to is None

    def test_a_carried_modifier_says_who_carries_it(self, buffs_weapons, mounted):
        attach_modifiers_to(mounted, [buffs_weapons])

        assert texts(prose_for(buffs_weapons).referenced_by) == [
            "Carried by the Mounted subtype."
        ]


class TestTheArticleFollowsTheName:
    """The article bends to the name after it — "an Ambot", "a Mounted".
    The names are the book's, and plenty of them open with a vowel."""

    def test_a_subtype_opening_with_a_vowel_reads_an(self, buffs_weapons, default_pack):
        ambot = create_subtype("Ambot")
        attach_modifiers_to(ambot, [buffs_weapons])

        assert texts(prose_for(ambot).does) == [
            "An Ambot fighter's weapons gain Backstab, while the subtype stands."
        ]

    def test_a_model_opening_with_a_vowel_joins_as_an(self, escher, person_type):
        aberrant = create_profile(
            "Aberrant", profile_type=person_type, gang_type=escher, hireable=False
        )
        rune = create_wargear("Ambull rune", price=45)
        attach_modifiers_to(
            rune, [modifier("The aberrant", targets_model(), op_adds_model(aberrant))]
        )

        assert texts(prose_for(rune).does) == [
            "When this arrives, an Aberrant joins the gang, free — and leaves "
            "again if this goes."
        ]


class TestTheMasterOfWhispers:
    """One power from a family, as a Primary pick — a rule doing three
    things, said as a paragraph.

    The three modifiers are one setup, and the order they are said in is
    the order the rules run them: what is given settles before anything
    that could depend on it.
    """

    @pytest.fixture
    def whispers(self, default_pack):
        return create_category(create_section("Wyrd Powers"), "Psychoteric Whispers")

    @pytest.fixture
    def primary(self, default_pack):
        return section_of(create_collection("Skills & Powers"), "Primary", 0)

    @pytest.fixture
    def master(self, whispers, primary):
        from n26.library.models import Power

        wyrd = create_subtype("Wyrd")
        rule = create_rule("Master of Whispers")
        attach_modifiers_to(
            rule,
            [
                modifier("Whispers 1: gives Wyrd", targets_model(), ef_adds(wyrd)),
                modifier(
                    "Whispers 2: places the family",
                    targets_model(),
                    ef_places(whispers, primary),
                ),
                modifier(
                    "Whispers 3: the founding power",
                    targets_model(),
                    ef_offers_choice(Power, from_section=primary),
                ),
            ],
        )
        return rule

    def test_the_paragraph_reads_as_one_setup(self, master):
        assert texts(prose_for(master).does) == [
            "They gain the Wyrd subtype, while they have it.",
            "Their Psychoteric Whispers set appears as Primary.",
            "It asks them to choose one Primary power — the card says Choose "
            "until they pick.",
        ]

    def test_the_offer_says_what_narrows_it(self, master):
        offer = prose_for(master).does[2]

        assert "Only what appears as Primary for that model is listed" in offer.hint
        assert "has nothing on it" in offer.hint

    def test_every_sentence_points_at_the_modifier_behind_it(self, master):
        keys = {sentence.key for sentence in prose_for(master).does}

        assert len(keys) == 3
        assert all(label == "library.modifier" for label, _ in keys)

    def test_a_view_decorates_by_key_and_never_by_reading_the_words(self, master):
        """The compiler leaves the address blank; a view fills it in from
        the identity, which is why the identity is there."""
        said = prose_for(master).does[0]

        assert said.href == ""
        assert said.at(f"/n26/authoring/modifier/{said.key[1]}/").href.endswith(
            f"/{said.key[1]}/"
        )

    def test_a_power_says_it_may_be_chosen_for_the_offered_choice(
        self, master, whispers, primary
    ):
        whisper = create_power("Crawling Doom", category=whispers)
        add_entry(primary.collection, whisper)

        assert texts(prose_for(whisper).referenced_by) == [
            "Offered by Skills & Powers free.",
            "May be chosen for the Primary power choice offered by the Master "
            "of Whispers special rule.",
        ]

    def test_a_choice_nothing_offers_yet_is_still_a_way_in(self, whispers):
        """Written in the composer, before anything carries it: the kind is
        already enough to say a power could be chosen for it."""
        from n26.library.models import Power

        modifier("A loose offer", targets_model(), ef_offers_choice(Power))
        whisper = create_power("Crawling Doom", category=whispers)

        assert texts(prose_for(whisper).referenced_by) == [
            "May be chosen for an offered choice of Power."
        ]


class TestACorruptedGang:
    """What an affiliation hands a gang, said in the gang's own terms.

    Everything a corruption does rides the chosen affiliation as
    ordinary modifiers, all of them aimed at the gang — so every
    sentence is about the gang, whoever made the pick.
    """

    @pytest.fixture
    def corruption(self, escher, person_type):
        armoury = create_collection("Corruption Armoury")
        house_rules = create_hidden("Escher gang rules")
        add_built_in(escher, house_rules)
        aberrant = create_profile(
            "Aberrant", profile_type=person_type, gang_type=escher, price=60
        )
        chaos = create_affiliation("Chaos Corrupted")
        attach_modifiers_to(
            chaos,
            [
                modifier("Chaos 1: the armoury", targets_gang(), ef_adds(armoury)),
                modifier(
                    "Chaos 2: loses the house rules",
                    targets_gang(),
                    ef_removes(house_rules),
                ),
                modifier(
                    "Chaos 3: no more than two Aberrants",
                    targets_gang(),
                    ef_allows_at_most(2, aberrant),
                ),
            ],
        )
        return chaos

    def test_the_payload_is_three_things_the_gang_gets(self, corruption):
        assert texts(prose_for(corruption).does) == [
            "The gang gains access to Corruption Armoury, and every member "
            "may buy from it.",
            "The gang loses Escher gang rules, and everything it gave goes with it.",
            "The gang should hold at most 2 Aberrant — the gang page warns "
            "when it holds more; nothing is blocked.",
        ]

    def test_the_grant_says_the_gang_reaches_its_fighters(self, corruption):
        assert "affects every fighter in it" in prose_for(corruption).does[0].hint

    def test_the_limit_says_that_zero_is_a_ban(self, corruption):
        assert "A limit of 0 is a ban" in prose_for(corruption).does[2].hint

    def test_a_ban_is_written_as_a_limit_of_nought(self, default_pack):
        brute = create_subtype("Brute")
        rules = create_affiliation("Malstrain Corrupted")
        attach_modifiers_to(
            rules,
            [modifier("No brutes", targets_gang(), ef_allows_at_most(0, brute))],
        )

        assert texts(prose_for(rules).does) == [
            "The gang should hold no Brute at all — the gang page warns when "
            "it holds more; nothing is blocked."
        ]

    def test_the_hidden_bundle_says_where_it_comes_from_and_what_removes_it(
        self, corruption
    ):
        from n26.library.models import Hidden

        bundle = Hidden.objects.get(name="Escher gang rules")

        assert texts(prose_for(bundle).referenced_by) == [
            "Built into the Escher gang type.",
            "Taken away from the gang by the Chaos Corrupted affiliation.",
        ]

    def test_the_bundle_says_that_dropping_the_corruption_brings_it_back(
        self, corruption
    ):
        from n26.library.models import Hidden

        bundle = Hidden.objects.get(name="Escher gang rules")

        assert "and this comes back" in prose_for(bundle).referenced_by[1].hint


class TestChainsAndBundles:
    """A grant that hands over something which itself hands over
    something — the reader should not have to open two pages."""

    def test_a_granted_thing_that_itself_grants_says_so(self, mounted, default_pack):
        nerves = create_skill("Nerves of Steel")
        attach_modifiers_to(
            mounted, [modifier("Mounted: nerves", targets_model(), ef_adds(nerves))]
        )
        cutter = create_wargear("Cutter")
        attach_modifiers_to(
            cutter, [modifier("Cutter: mounted", targets_model(), ef_adds(mounted))]
        )

        assert texts(prose_for(cutter).does) == [
            "Its bearer gains the Mounted subtype, while they carry it — "
            "which itself gives Nerves of Steel."
        ]

    def test_a_bundle_names_everything_it_hands_over(self, escher):
        chems = create_rule("Combat Chems Stash")
        fighters = create_rule("Gang Fighters")
        bundle = create_hidden("Escher gang rules")
        attach_modifiers_to(
            bundle,
            [
                modifier("Escher 1: chems", targets_gang(), ef_adds(chems)),
                modifier("Escher 2: fighters", targets_gang(), ef_adds(fighters)),
            ],
        )
        modifier(
            "Escher 3: the bundle", targets_gang(), ef_adds(bundle), attach_to=escher
        )

        assert texts(prose_for(escher).does) == [
            "The gang gains Escher gang rules, which draws no line of its "
            "own — which itself gives Combat Chems Stash and Gang Fighters."
        ]


class TestConditions:
    """How a scope's narrowing reads: ranks replace the subject, a
    threshold opens the sentence, a weapon filter joins the noun."""

    def test_a_rank_condition_names_the_ranks(self, default_pack):
        """The ranks come in the library's own order — by name, as every
        other sentence naming a set of subtypes says them — so a
        modifier's name and its reach sentence cannot list them
        differently."""
        leader = create_subtype("Leader")
        champion = create_subtype("Champion")
        nerves = create_skill("Nerves of Steel")
        rule = create_rule("Veterans")
        attach_modifiers_to(
            rule,
            [
                modifier(
                    "Veterans: nerves",
                    targets_model(has_subtypes(leader, champion)),
                    ef_adds(nerves),
                )
            ],
        )

        assert texts(prose_for(rule).does) == [
            "Champion and Leader gain the Nerves of Steel skill, while they have it."
        ]

    def test_a_threshold_opens_the_sentence_and_says_while_only_once(
        self, default_pack
    ):
        xp = create_counter("XP")
        veteran = create_subtype("Veteran")
        rule = create_rule("Hardened")
        attach_modifiers_to(
            rule,
            [
                modifier(
                    "Hardened: veteran at 75",
                    targets_model(counter_at_least(xp, 75)),
                    ef_adds(veteran),
                )
            ],
        )

        assert texts(prose_for(rule).does) == [
            "While their XP is 75 or more, they gain the Veteran subtype."
        ]

    def test_a_weapon_narrowing_joins_the_noun_phrase(self, backstab, default_pack):
        melee = create_trait("Melee")
        cutter = create_wargear("Cutter")
        attach_modifiers_to(
            cutter,
            [
                modifier(
                    "Backstab on blades",
                    targets_weapons(has_traits(melee)),
                    ef_adds(backstab),
                )
            ],
        )

        assert texts(prose_for(cutter).does) == [
            "Its bearer's weapons with Melee gain Backstab, while they carry it."
        ]


class TestWhatIsWrittenOnce:
    """The stored effects run at purchase rather than on every read, and
    the sentence has to say which of them comes back."""

    def test_moving_a_counter_says_the_ledger_keeps_it(self, default_pack):
        xp = create_counter("XP")
        rule = create_rule("Selected as Outcast Leader")
        attach_modifiers_to(
            rule,
            [
                modifier(
                    "Outcast Leader: starting XP",
                    targets_model(),
                    op_changes_counter(xp, mode="set", amount=61),
                )
            ],
        )

        assert texts(prose_for(rule).does) == [
            "When this arrives, their XP is set to 61 — written on the ledger "
            "once; taking this away does not take it back."
        ]

    def test_bringing_a_model_says_it_leaves_again(self, escher, person_type):
        mastiff = create_profile(
            "Cyber-mastiff", profile_type=person_type, gang_type=escher, hireable=False
        )
        collar = create_wargear("Cyber-mastiff collar", price=45)
        attach_modifiers_to(
            collar, [modifier("The mastiff", targets_model(), op_adds_model(mastiff))]
        )

        assert texts(prose_for(collar).does) == [
            "When this arrives, a Cyber-mastiff joins the gang, free — and "
            "leaves again if this goes."
        ]

    def test_the_model_it_brings_says_who_brought_it(self, escher, person_type):
        mastiff = create_profile(
            "Cyber-mastiff", profile_type=person_type, gang_type=escher, hireable=False
        )
        collar = create_wargear("Cyber-mastiff collar", price=45)
        attach_modifiers_to(
            collar, [modifier("The mastiff", targets_model(), op_adds_model(mastiff))]
        )

        assert texts(prose_for(mastiff).referenced_by) == [
            "Brought by the Cyber-mastiff collar wargear."
        ]


class TestWhereAThingIsSold:
    """Two routes to being sold: a list that names it, and a sweep that
    catches it."""

    @pytest.fixture
    def saw(self, default_pack):
        return create_weapon("Heavy rock saw", price=40)

    def test_a_listing_says_the_list_and_the_price(self, saw):
        goliath = create_collection("Goliath Equipment List")
        add_entry(goliath, saw, price_override=35)

        assert texts(prose_for(saw).referenced_by) == [
            "Offered by Goliath Equipment List at 35 credits."
        ]

    def test_a_narrowed_line_says_who_the_list_offers_it_to(
        self, saw, escher, person_type
    ):
        goliath = create_collection("Goliath Equipment List")
        forge_born = create_profile(
            "Forge-born", profile_type=person_type, gang_type=escher
        )
        add_entry(goliath, saw, price_override=35, usable_by_profiles=[forge_born])

        assert texts(prose_for(saw).referenced_by) == [
            "Offered by Goliath Equipment List at 35 credits, to Forge-born only."
        ]

    def test_the_hint_behind_a_line_says_both_halves_of_the_price(self, saw):
        """What a listing's own words leave out: whether the Trading Post
        sells it, and for how many trade points."""
        goliath = create_collection("Goliath Equipment List")
        add_entry(goliath, saw, price_override=35, trade_point_override=2)

        assert prose_for(saw).referenced_by[0].hint == (
            "35 credits; 2 trade points at the Trading Post."
        )

    def test_a_narrowed_line_says_the_others_still_see_it(
        self, saw, escher, person_type
    ):
        goliath = create_collection("Goliath Equipment List")
        forge_born = create_profile(
            "Forge-born", profile_type=person_type, gang_type=escher
        )
        add_entry(goliath, saw, price_override=35, usable_by_profiles=[forge_born])

        assert (
            "Other fighters still see it on the list, with a note — nothing "
            "is blocked." in prose_for(saw).referenced_by[0].hint
        )

    def test_a_sweep_says_what_caught_it(self, saw):
        from n26.library.models import CollectionSelector, Weapon

        post = create_collection("Trading Post")
        CollectionSelector.of(post, Weapon)

        assert texts(prose_for(saw).referenced_by) == [
            "Offered by Trading Post at 40 credits, swept in as every weapon."
        ]

    def test_a_free_line_says_free_rather_than_nought(self, default_pack):
        knife = create_weapon("Stub knife")
        post = create_collection("Trading Post")
        add_entry(post, knife)

        assert texts(prose_for(knife).referenced_by) == [
            "Offered by Trading Post free."
        ]

    def test_a_list_that_both_names_it_and_sweeps_it_speaks_once(self, saw):
        """The price the list's own line states is the one a buyer is
        asked for, so the sweep behind it says nothing further."""
        from n26.library.models import CollectionSelector, Weapon

        post = create_collection("Trading Post")
        add_entry(post, saw, price_override=35)
        CollectionSelector.of(post, Weapon)

        assert texts(prose_for(saw).referenced_by) == [
            "Offered by Trading Post at 35 credits."
        ]

    def test_a_different_list_sweeping_it_in_still_speaks(self, saw):
        """Only the list that named it goes quiet: a second list sweeping
        the same kind is a route of its own."""
        from n26.library.models import CollectionSelector, Weapon

        goliath = create_collection("Goliath Equipment List")
        add_entry(goliath, saw, price_override=35)
        post = create_collection("Trading Post")
        CollectionSelector.of(post, Weapon)

        assert texts(prose_for(saw).referenced_by) == [
            "Offered by Goliath Equipment List at 35 credits.",
            "Offered by Trading Post at 40 credits, swept in as every weapon.",
        ]


class TestWhatMayBeChosenForAnOfferedChoice:
    """A choice drawn from a tier is settled by what that tier's
    collection holds, and only those things say they may be chosen.

    Nothing else can be picked: a narrowed choice offers the collection
    browsed and resectioned for that model, so a power no collection
    holds is on nobody's list however many choices of Power exist.
    """

    @pytest.fixture
    def whispers(self, default_pack):
        return create_category(create_section("Wyrd Powers"), "Psychoteric Whispers")

    @pytest.fixture
    def primary(self, default_pack):
        return section_of(create_collection("Skills & Powers"), "Primary", 0)

    @pytest.fixture
    def master(self, primary):
        from n26.library.models import Power

        rule = create_rule("Master of Whispers")
        attach_modifiers_to(
            rule,
            [
                modifier(
                    "Whispers: the founding power",
                    targets_model(),
                    ef_offers_choice(Power, from_section=primary),
                )
            ],
        )
        return rule

    def test_a_power_the_list_neither_names_nor_sweeps_cannot_be_chosen(
        self, master, whispers
    ):
        whisper = create_power("Crawling Doom", category=whispers)

        assert texts(prose_for(whisper).referenced_by) == []

    def test_a_power_the_list_names_may_be_chosen_for_it(
        self, master, primary, whispers
    ):
        whisper = create_power("Crawling Doom", category=whispers)
        add_entry(primary.collection, whisper)

        assert texts(prose_for(whisper).referenced_by) == [
            "Offered by Skills & Powers free.",
            "May be chosen for the Primary power choice offered by the Master "
            "of Whispers special rule.",
        ]

    def test_a_power_the_list_sweeps_in_may_be_chosen_for_it(
        self, master, primary, whispers
    ):
        from n26.library.models import CollectionSelector, Power

        whisper = create_power("Crawling Doom", category=whispers)
        CollectionSelector.of(primary.collection, Power)

        assert texts(prose_for(whisper).referenced_by) == [
            "Offered by Skills & Powers free, swept in as every power.",
            "May be chosen for the Primary power choice offered by the Master "
            "of Whispers special rule.",
        ]

    def test_a_power_on_another_list_entirely_cannot_be_chosen(self, master, whispers):
        """Being sold somewhere is not being in the tier the choice draws
        from — the offer names one collection's section, not the world."""
        whisper = create_power("Crawling Doom", category=whispers)
        add_entry(create_collection("Wyrd Compendium"), whisper)

        assert texts(prose_for(whisper).referenced_by) == [
            "Offered by Wyrd Compendium free."
        ]


class TestBuiltInAndOptional:
    """The two ways a set of defaults hands something over."""

    def test_a_built_in_names_what_comes_with_it(self, escher, person_type):
        knife = create_weapon("Stub knife")
        ganger = create_profile("Ganger", profile_type=person_type, gang_type=escher)
        add_built_in(ganger, knife)

        assert texts(prose_for(knife).referenced_by) == [
            "Built into the Ganger profile."
        ]

    def test_an_option_says_which_option_brings_it(self, escher, person_type):
        spawn = create_profile(
            "Chaos Spawn", profile_type=person_type, gang_type=escher
        )
        rolled = create_hidden("Strength rolled 6")
        offer_option(spawn, "rolled 6", thing=rolled)

        assert texts(prose_for(rolled).referenced_by) == [
            "Taken with the “rolled 6” option of the Chaos Spawn profile."
        ]

    def test_a_set_nothing_holds_says_so(self, default_pack):
        orphan = create_default_set("Nobody's kit")
        knife = create_weapon("Stub knife")
        add_default_member(orphan, knife)

        assert texts(prose_for(knife).referenced_by) == [
            "Part of the “Nobody's kit” kit, which nothing uses yet."
        ]


class TestADomainOfChoice:
    """A choice and its options, explained: what a choice asks for, what
    lists an option is on, and which choices could settle on it.

    An option is only ever reached through a choice, so the routes into
    one are the lists that hold it and the choices that draw on those.
    """

    @pytest.fixture
    def legacy(self, default_pack):
        from n26.library.authoring import create_slot_type

        return create_slot_type(
            "Gang Legacy", plural_name="Gang Legacies", allows_repeats=False
        )

    @pytest.fixture
    def cawdor(self, legacy):
        from n26.library.authoring import create_pickable

        return create_pickable("Cawdor", legacy)

    @pytest.fixture
    def houses(self, legacy, cawdor):
        from n26.library.authoring import create_picklist

        return create_picklist("House Legacies", legacy, members=[cawdor])

    @pytest.fixture
    def choice(self, legacy, houses):
        from n26.library.authoring import create_slot

        return create_slot("House legacy", legacy, houses, label="Gang Legacy")

    def test_a_choice_says_what_it_asks_for(self, choice):
        assert texts(prose_for(choice).does) == [
            "Asks for one Gang Legacy, chosen from House Legacies."
        ]

    def test_a_choice_of_several_says_how_many(self, legacy, houses):
        from n26.library.authoring import create_slot

        pair = create_slot("Two legacies", legacy, houses, min_picks=2, max_picks=2)

        assert texts(prose_for(pair).does) == [
            "Asks for 2 Gang Legacies, chosen from House Legacies."
        ]

    def test_a_choice_the_gang_holds_says_whose_the_pick_is(self, legacy, houses):
        from n26.library.authoring import create_slot

        leaders = create_slot("Gang legacy", legacy, houses, assigned_to="gang")

        assert texts(prose_for(leaders).does) == [
            "Asks for one Gang Legacy, chosen from House Legacies. What is "
            "chosen belongs to the gang, not to whoever was asked."
        ]

    def test_a_hidden_choice_says_it_asks_nothing(self, legacy, houses):
        from n26.library.authoring import create_slot

        bundle = create_slot("The Cawdor bundle", legacy, houses, hidden=True)

        assert texts(prose_for(bundle).does) == [
            "Holds one Gang Legacy from House Legacies, and asks nothing."
        ]

    def test_a_choice_says_where_it_is_built_in(self, choice, escher, person_type):
        hunter = create_profile("Hunter", profile_type=person_type, gang_type=escher)
        add_built_in(hunter, choice)

        assert texts(prose_for(choice).referenced_by) == [
            "Built into the Hunter profile."
        ]

    def test_an_option_says_which_lists_offer_it(self, cawdor, houses):
        assert texts(prose_for(cawdor).referenced_by) == ["Listed in House Legacies."]

    def test_an_option_says_which_choices_could_settle_on_it(self, cawdor, choice):
        assert texts(prose_for(cawdor).referenced_by) == [
            "Listed in House Legacies.",
            "May be chosen for the House legacy slot.",
        ]

    def test_an_option_no_list_holds_is_reached_by_nothing(self, cawdor, choice):
        """A choice names a list, so an option nobody listed is on no
        route at all — an owner may still hand it over."""
        from n26.library.models import PicklistMember

        PicklistMember.objects.all().delete()

        assert texts(prose_for(cawdor).referenced_by) == []

    def test_an_option_a_choice_starts_with_says_so(
        self, cawdor, choice, escher, person_type
    ):
        squats = create_profile(
            "Squats Hunter", profile_type=person_type, gang_type=escher
        )
        add_built_in(squats, choice, default_pickable=cawdor)

        assert texts(prose_for(cawdor).referenced_by) == [
            "Chosen from the start for the House legacy slot.",
            "Listed in House Legacies.",
            "May be chosen for the House legacy slot.",
        ]

    def test_an_option_says_what_it_gives(self, cawdor, houses, default_pack):
        attach_modifiers_to(
            cawdor,
            [
                modifier(
                    "Cawdor: its equipment list",
                    targets_model(),
                    ef_adds(create_collection("Cawdor Word-Keeper")),
                )
            ],
        )

        assert texts(prose_for(cawdor).does) == [
            "They gain access to Cawdor Word-Keeper, while they have it."
        ]


class TestWhatIsAssignedToIt:
    """The player side: what would be disturbed if this went."""

    @pytest.fixture
    def knife(self, escher, person_type, django_user_model):
        owner = django_user_model.objects.create_user("kal")
        knife = create_weapon("Stub knife", price=10)
        ganger = create_profile(
            "Ganger", profile_type=person_type, gang_type=escher, price=45
        )
        for name in ("Wild Cats", "Bad Cats"):
            gang = found_gang(name, escher, owner=owner)
            fighter = hire(gang, ganger, "Someone")
            buy(fighter, thing=knife, paid=10)
        return knife

    def test_it_counts_the_rows_and_the_gangs_behind_them(self, knife):
        count = prose_for(knife).assigned_to

        assert (count.rows, count.gangs) == (2, 2)

    def test_a_thing_nobody_holds_counts_nought(self, default_pack):
        spare = create_weapon("Spare knife")
        count = prose_for(spare).assigned_to

        assert (count.rows, count.gangs) == (0, 0)

    def test_a_kind_nobody_can_be_assigned_has_no_count(self, buffs_weapons):
        assert prose_for(buffs_weapons).assigned_to is None


class TestAssignmentsAreNotReferences:
    """A gang holding the thing is a tally, never a sentence: the
    references say how anyone comes to have it, not who does."""

    def test_holding_it_adds_no_sentence(self, escher, django_user_model):
        owner = django_user_model.objects.create_user("rin")
        rule = create_rule("Combat Chems Stash")
        gang = found_gang("Wild Cats", escher, owner=owner)
        assign(rule, gang=gang)

        said = prose_for(rule)

        assert said.referenced_by == ()
        assert (said.assigned_to.rows, said.assigned_to.gangs) == (1, 1)


class TestTheRemainingEffects:
    """The renderers the setups above do not reach, each said once."""

    def test_a_stat_change_names_the_characteristic(self, fighter_stats):
        rule = create_rule("Eye Injury")
        attach_modifiers_to(
            rule,
            [
                modifier(
                    "Eye Injury: BS",
                    targets_model(),
                    ef_changes_stat(fighter_stats["BS"], mode="worsen", amount=1),
                )
            ],
        )

        assert texts(prose_for(rule).does) == [
            "Their Ballistic Skill is 1 worse, while they have it."
        ]

    def test_a_category_change_says_where_they_file(self, default_pack):
        leaders = create_category(create_section("Gang"), "Leaders")
        rule = create_rule("Selected as Outcast Leader")
        attach_modifiers_to(
            rule,
            [
                modifier(
                    "Outcast Leader: files with the leaders",
                    targets_model(),
                    ef_changes_category(leaders),
                )
            ],
        )

        assert texts(prose_for(rule).does) == [
            "They file under Leaders on the gang page, while they have it."
        ]

    def test_a_composition_ask_says_what_the_sheet_will_say(self, default_pack):
        champion = create_subtype("Champion")
        scum = create_subtype("Hive Scum")
        rules = create_affiliation("Outcast")
        attach_modifiers_to(
            rules,
            [
                modifier(
                    "Lead the Masses",
                    targets_gang(),
                    ef_requires_companions(champion, 3, scum),
                )
            ],
        )

        assert texts(prose_for(rules).does) == [
            "The gang should field at least 3 Hive Scum for each Champion — "
            "the gang page warns when it has fewer; nothing is blocked."
        ]

    def test_a_per_model_limit_counts_one_model_at_a_time(self, default_pack):
        familiar = create_wargear("Psychic Familiar")
        rule = create_rule("Familiars")
        attach_modifiers_to(
            rule,
            [
                modifier(
                    "One familiar each",
                    targets_model(),
                    ef_allows_at_most(1, familiar),
                )
            ],
        )

        assert texts(prose_for(rule).does) == [
            "No model should hold more than 1 Psychic Familiar — their card "
            "warns when one does; nothing is blocked."
        ]


class TestTheQueryCountStaysFlat:
    """Building one thing's prose is a fixed number of queries.

    The point of the budget is not the number but its flatness: a rule
    ten things reference must be read at the price of a rule one thing
    references, or the page about a much-used row would be the slow one.

    What the budget *is* made of is the kinds involved, not the rows: a
    scope or an effect nothing uses is never fetched at all, so the first
    modifier of some shape costs a little more than the tenth. The rule
    below carries one of each shape the tests then add more of.
    """

    @pytest.fixture
    def much_used(self, escher, backstab):
        """One rule, referenced from every direction there is."""
        skill = create_skill("Nerves of Steel")
        rule = create_rule("Combat Chems Stash")
        attach_modifiers_to(
            rule,
            [
                modifier("Chems: nerves", targets_model(), ef_adds(skill)),
                modifier("Chems: backstab", targets_weapons(), ef_adds(backstab)),
            ],
        )
        add_built_in(escher, rule)
        giver = create_wargear("Chem-stash")
        attach_modifiers_to(
            giver, [modifier("Chem-stash: the rule", targets_model(), ef_adds(rule))]
        )
        # The content-type rows a sweep and an offer look up are cached for
        # the life of the process, so the first prose read anywhere pays for
        # them. Read once here, or the budget below would be one query
        # larger whenever this test happened to run first.
        prose_for(rule)
        return rule

    def _more_references(self, rule, how_many):
        for number in range(how_many):
            carrier = create_wargear(f"Chem-stash {number}")
            attach_modifiers_to(
                carrier,
                [
                    modifier(
                        f"Chem-stash {number}: the rule",
                        targets_model(),
                        ef_adds(rule),
                    )
                ],
            )
            add_built_in(create_wargear(f"Holder {number}"), rule)

    def _budget(self, thing):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            prose_for(thing)
        return len(captured.captured_queries)

    def test_the_count_holds_when_more_things_reference_it(
        self, much_used, django_assert_num_queries
    ):
        budget = self._budget(much_used)

        self._more_references(much_used, 6)

        with django_assert_num_queries(budget):
            prose_for(much_used)

    def test_the_count_holds_when_it_carries_more_modifiers(
        self, much_used, django_assert_num_queries
    ):
        budget = self._budget(much_used)

        for number in range(6):
            trait = create_trait(f"Trait {number}")
            attach_modifiers_to(
                much_used,
                [modifier(f"Chems: trait {number}", targets_weapons(), ef_adds(trait))],
            )

        with django_assert_num_queries(budget):
            prose_for(much_used)

    def test_the_budget_is_what_it_is(self, much_used, django_assert_num_queries):
        """Pinned so that a new sweep is a decision somebody made.

        Most of the number is the price of assignables having no shared
        table: "what carries this modifier" and "what holds this set" are
        each one query per kind, and there are twenty-odd kinds.
        """
        with django_assert_num_queries(68):
            prose_for(much_used)


class TestEveryEffectCanBeSaid:
    """A discovering guard: an effect with no renderer is one the reach
    column would drop without a word."""

    def test_there_is_something_to_check(self):
        from n26.library.models.modifier import EFFECT_FIELDS

        assert len(EFFECT_FIELDS) > 5

    def test_every_effect_kind_has_a_sentence(self):
        from n26.library.models.modifier import EFFECT_FIELDS

        missing = [name for name in EFFECT_FIELDS if name not in prose.DOWNSTREAM]

        assert not missing, (
            f"No reach sentence for {', '.join(missing)}. Add a renderer in "
            "n26/library/prose.py decorated @_renders(<the effect's column on "
            "Modifier>), returning the sentence and its hint — an effect "
            "nothing can say is one the reach column drops in silence."
        )

    def test_every_scope_kind_has_words_for_who_it_reaches(self):
        from n26.library.models.modifier import SCOPE_FIELDS

        assert set(SCOPE_FIELDS) == {
            "targets_miniature",
            "targets_weapons",
            "targets_attached_weapon",
            "targets_gang",
        }, (
            "A new scope means a new subject in n26/library/prose.py: give "
            "_who the words for whoever it reaches, and pin the sentence here."
        )


class TestTheDeletePageAndTheProseAgree:
    """Both read the same edges through one reader, so neither can name
    a set of things the other does not."""

    def test_what_protects_a_row_is_what_the_prose_explains(self, escher, person_type):
        knife = create_weapon("Stub knife")
        ganger = create_profile("Ganger", profile_type=person_type, gang_type=escher)
        add_built_in(ganger, knife)

        protectors = [
            reference for reference in references_to(knife) if reference.protects
        ]

        assert [reference.label for reference in protectors] == [
            "library.defaultassignment"
        ]
        assert texts(prose_for(knife).referenced_by) == [
            "Built into the Ganger profile."
        ]

    def test_a_row_a_gang_holds_is_protected_by_that_assignment(
        self, escher, person_type, django_user_model
    ):
        owner = django_user_model.objects.create_user("nel")
        knife = create_weapon("Stub knife", price=10)
        ganger = create_profile(
            "Ganger", profile_type=person_type, gang_type=escher, price=45
        )
        gang = found_gang("Wild Cats", escher, owner=owner)
        fighter = hire(gang, ganger, "Someone")
        buy(fighter, thing=knife, paid=10)

        protectors = {
            reference.label for reference in references_to(knife) if reference.protects
        }

        assert "n26.assignment" in protectors

    def test_a_weapons_own_firing_lines_do_not_protect_it(self, default_pack):
        """A part of the thing is not a reference to it: deleting a
        weapon takes its lines with it."""
        from n26.library.authoring import add_weapon_profile

        knife = create_weapon("Stub knife")
        add_weapon_profile(knife, annotation="Stub knife")

        lines = [
            reference
            for reference in references_to(knife)
            if reference.label == "library.weaponprofile"
        ]

        assert lines and not any(reference.protects for reference in lines)
