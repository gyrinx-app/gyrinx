"""Gang book concepts (Gangs of the Underhive / Outlands), built for real.

Rules names and behaviour only — the wording stays in the book. This
suite takes the most structurally demanding concepts in those books
and builds each from shipped pieces, no new machinery:

* **Chaos Corruption** (the corrupted-gang pattern, shared by
  Genestealer and Malstrain corruption): a founding-time gang choice
  whose pick *suppresses* the house's own rules, asks its own
  follow-up (which Dark God?), opens a corruption-only equipment list,
  and sells the Leader a priced Wyrd ascension whose power pick falls
  out of a placement.
* **Warped Monstrosity** (Chaos Spawn, both books): a random statline
  table becomes option groups — the player rolls at the table, the
  roster takes the option matching each die. Inform, not police.
* **The Justicar Court Delegation**: an alliance is a gang-hosted
  carrier; its stored effects hire the delegation free, and breaking
  the alliance takes the delegation with it through the ordinary
  cascade — the pets pattern at gang scale.
* **Master of Whispers** (Delaque): a +35 credit hire option that
  awakens the fighter — subtype, family placement, and the narrowed
  power pick, all riding one Hidden in a priced option set.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Assignment, Miniature
from n26.core.render import render_gang
from n26.core.render_text import render_gang_sheet, render_model_card
from n26.library.authoring import (
    counter_at_least,  # noqa: F401 — the promotion pattern, referenced in prose
    create_affiliation,
    create_category,
    create_collection,
    create_counter,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_option_group,
    create_power,
    create_profile,
    create_rule,
    create_subtype,
    create_wargear,
    ef_adds,
    ef_changes_stat,
    ef_offers_choice,
    ef_places,
    ef_removes,
    has_subtypes,
    modifier,
    op_adds_model,
    restrict_use,
    section_of,
    set_statline,
    targets_gang,
    targets_model,
)
from n26.library.models import Affiliation, Power
from n26.tests.sandbox.actions import (
    assign,
    buy,
    choose,
    found_gang,
    hire_with_option,
    remove,
    tally,
)

pytestmark = pytest.mark.django_db


def show(lines):
    print("\n" + "\n".join(lines))


def card_for(gang, name):
    """One model's rendered card, computed the way the sheet computes it."""
    sheet = render_gang(gang)
    return next(card for card in sheet.models if card.name == name)


# =========================================================================
# Chaos Corruption — the corrupted-gang pattern
# =========================================================================


@pytest.fixture
def ranks(default_pack):
    return {
        name.lower(): create_subtype(name) for name in ("Leader", "Champion", "Ganger")
    }


@pytest.fixture
def skills_catalogue(default_pack):
    collection = create_collection("Skills & Powers")
    return collection, {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
        "other": section_of(collection, "Other", 2, is_default=True),
    }


@pytest.fixture
def chaos_powers(default_pack):
    """The Chaos Helot Wyrd Powers — names and their family, only."""
    family = create_category("Powers", "Chaos Wyrd Powers", 10)
    powers = {
        name: create_power(name, category=family)
        for name in (
            "Scouring",
            "Levitation",
            "Warp Strength",
            "Warp Shield",
            "Maddening Visions",
            "Assail",
        )
    }
    return family, powers


@pytest.fixture
def escher(ranks, default_pack):
    """A slim House Escher: its rule, and the founding corruption slot.

    The charter Hidden is the gang type's anchor row — founding assigns
    it, so gang-level questions have an assignment to hang picks off.
    """
    nimble = create_rule("Nimble")
    charter = create_hidden(
        "House Escher charter",
        effects=[
            (targets_model(), ef_adds(nimble)),
            # "During Gang Creation a player can decide that their gang
            # has been corrupted" — an open question on the gang's own
            # card, chosen for or simply left.
            (targets_gang(), ef_offers_choice(Affiliation, label="corruption")),
        ],
    )
    gang_type = create_gang_type("Escher")
    gang_type.built_ins = create_default_set("Escher founding", members=[charter])
    gang_type.save()
    return gang_type, nimble, charter


@pytest.fixture
def chaos_corruption(escher, ranks, chaos_powers, skills_catalogue):
    """Everything 'Embracing the Chaos Gods' means, hanging off one pick."""
    _, nimble, _ = escher
    family, powers = chaos_powers
    _, tiers = skills_catalogue
    wyrd = create_subtype("Wyrd")

    # The Dark Gods are chosen carriers of their own — the dedication is
    # a chained choice, and each god's battle favour is names-only.
    gods = {
        name: create_affiliation(f"Dedicated: the {name}")
        for name in ("Blood God", "Plague Lord", "Dark Prince", "Architect of Fate")
    }

    # "The Leader can be upgraded to become a Wyrd for +35 credits" — a
    # priced purchasable carrier. Its power pick falls out of the
    # placement, the Enforcer Haunt pattern.
    ascension = create_wargear("Chaos Wyrd Ascension", price=35)
    for scope, effect in [
        (targets_model(), ef_adds(wyrd)),
        (targets_model(), ef_places(family, tiers["primary"])),
        (
            targets_model(),
            ef_offers_choice(Power, from_section=tiers["primary"], label="wyrd power"),
        ),
    ]:
        modifier(f"Ascension: {effect}", scope, effect, attach_to=ascension)

    # "Leaders and Champions may purchase Chaos Familiars" — plain
    # usability, said on the line, never a block.
    familiar = create_wargear("Chaos Familiar", price=40)
    restrict_use(familiar, ranks["leader"], ranks["champion"])

    options = create_collection(
        "Chaos Corruption Options", entries=[(ascension, {}), (familiar, {})]
    )

    corruption = create_affiliation(
        "Chaos Corrupted",
        effects=[
            # "Members of the gang do not benefit from any of the gang's
            # special rules" — computed removal; removes always win.
            (targets_model(), ef_removes(nimble)),
            # The Post-cycle rituals, printed on who may perform them.
            (
                targets_model(has_subtypes(ranks["leader"])),
                ef_adds(create_rule("Lead Ritual", annotation="Leader only")),
            ),
            (
                targets_model(),
                ef_adds(create_rule("Ritual Focus", annotation="max one Fighter")),
            ),
            # "The gang must select one of the Chaos gods" — what is
            # chosen asks its own follow-up. Chained by construction.
            (targets_gang(), ef_offers_choice(Affiliation, label="dedication")),
            # The corruption-only equipment list, opened for everyone.
            (targets_model(), ef_adds(options)),
        ],
    )
    return corruption, gods, options, powers


@pytest.fixture
def leader_profile(fighter_type, escher, ranks):
    gang_type, _, _ = escher
    profile = create_profile("Gang Queen", fighter_type, gang_type, price=125)
    set_statline(
        profile,
        movement=5,
        weapon_skill=3,
        ballistic_skill=3,
        strength=3,
        toughness=3,
        wounds=3,
        initiative=5,
        attacks=3,
        save=5,
        leadership=8,
        cool=8,
        willpower=7,
        intelligence=7,
    )
    profile.built_ins = create_default_set("Queen built-ins", members=[ranks["leader"]])
    profile.save()
    return profile


@pytest.fixture
def ganger_profile(fighter_type, escher, ranks):
    """The rulebook's own example profile — the Escher Gang Sister."""
    gang_type, _, _ = escher
    profile = create_profile("Sister", fighter_type, gang_type, price=50)
    set_statline(
        profile,
        movement=5,
        weapon_skill=4,
        ballistic_skill=4,
        strength=3,
        toughness=3,
        wounds=1,
        initiative=4,
        attacks=1,
        save=6,
        leadership=6,
        cool=6,
        willpower=6,
        intelligence=6,
    )
    profile.built_ins = create_default_set(
        "Sister built-ins", members=[ranks["ganger"]]
    )
    profile.save()
    return profile


class TestChaosCorruption:
    def corrupted_gang(self, escher, chaos_corruption):
        gang_type, _, charter = escher
        corruption, gods, _, _ = chaos_corruption
        gang = found_gang(
            "The Tainted",
            gang_type,
            owner=User.objects.create_user("heretic"),
            budget=1000,
        )
        anchor = Assignment.objects.get(gang=gang, hidden=charter)
        corrupted = choose(anchor, corruption)
        choose(corrupted, gods["Blood God"])
        return gang

    def test_the_founding_pick_suppresses_the_house_rules(
        self, escher, chaos_corruption, leader_profile, ganger_profile
    ):
        gang = self.corrupted_gang(escher, chaos_corruption)
        hire_with_option(gang, ganger_profile, "Vex")

        card = card_for(gang, "Vex")
        rule_names = [rule.name for rule in card.rules]
        assert "Nimble" not in rule_names  # granted by the house, removed
        assert "Ritual Focus (max one Fighter)" in rule_names
        assert "Lead Ritual (Leader only)" not in rule_names  # Leader's alone

    def test_the_dedication_is_a_chained_choice_on_the_gang(
        self, escher, chaos_corruption, leader_profile
    ):
        gang = self.corrupted_gang(escher, chaos_corruption)

        sheet = render_gang(gang)
        settled = {line.kind_label: line.chosen for line in sheet.choices}
        assert settled["Corruption"] == "Chaos Corrupted"
        assert settled["Dedication"] == "Dedicated: the Blood God"

    def test_the_leaders_ascension_and_the_favour_counter(
        self, escher, chaos_corruption, leader_profile
    ):
        corruption, gods, options_list, powers = chaos_corruption
        gang = self.corrupted_gang(escher, chaos_corruption)
        queen = hire_with_option(gang, leader_profile, "Mother Doubt")

        from n26.core.browse import browse

        line = next(
            line
            for line in browse(options_list).all_lines()
            if line.name == "Chaos Wyrd Ascension"
        )
        bought = buy(queen, line)
        assert bought.ledger_entry.paid == 35

        choose(bought, powers["Scouring"])

        # Favour is campaign state the arbiter marks — a gang counter,
        # tallied when a ritual lands. Its battle effect is a name.
        favour = assign(create_counter("Favour of the Blood God"), gang=gang)
        tally(favour, +1)

        card = card_for(gang, "Mother Doubt")
        show(render_model_card(card))
        assert "Wyrd" in [s.name for s in card.subtypes]
        (power_line,) = [c for c in card.choices if c.kind_label == "Wyrd power"]
        assert power_line.chosen == "Scouring"
        assert "Lead Ritual (Leader only)" in [rule.name for rule in card.rules]
        assert "Nimble" not in [rule.name for rule in card.rules]

        sheet = render_gang(gang)
        print("\n" + render_gang_sheet(sheet))
        assert [(c.name, c.value) for c in sheet.counters] == [
            ("Favour of the Blood God", 1)
        ]

    def test_uncorrupted_neighbours_keep_nimble(
        self, escher, chaos_corruption, ganger_profile
    ):
        """The corruption is one gang's choice, not a library edit."""
        gang_type, _, _ = escher
        pure = found_gang(
            "The Untainted", gang_type, owner=User.objects.create_user("loyal")
        )
        hire_with_option(pure, ganger_profile, "Faith")
        card = card_for(pure, "Faith")
        assert "Nimble" in [rule.name for rule in card.rules]


# =========================================================================
# Warped Monstrosity — a random statline table as option groups
# =========================================================================

#: The book's table, column by column. M and BS are blank in print.
#: "2-5" is the profile's own statline; the other bands are option sets.
WARPED_TABLE = {
    "weapon_skill": {"1": 5, "2-5": 4, "6": 3},
    "strength": {"1": 3, "2-5": 4, "6": 5},
    "toughness": {"1": 4, "2-5": 5, "6": 6},
    "wounds": {"1": 1, "2-5": 2, "6": 3},
    "initiative": {"1": 2, "2-5": 3, "6": 4},
    "attacks": {"1": 1, "2-5": 2, "6": 3},
    "save": {"1": 6, "2-5": 5, "6": 4},
}


@pytest.fixture
def spawn(default_pack, gang_type, fighter_type, fighter_stats):
    """The Chaos Spawn: the middle band printed, the dice as options.

    A real Fighter profile on the full characteristics statline. The
    book's table leaves M and BS blank and rolls the other seven; the
    unrolled columns simply stay unwritten, and the card shows the dash.
    """
    shorts = {
        "weapon_skill": "WS",
        "strength": "S",
        "toughness": "T",
        "wounds": "W",
        "initiative": "I",
        "attacks": "A",
        "save": "Sv",
    }
    stats = {name: fighter_stats[short] for name, short in shorts.items()}
    profile = create_profile("Chaos Spawn", fighter_type, gang_type, price=0)
    set_statline(
        profile, **{name: bands["2-5"] for name, bands in WARPED_TABLE.items()}
    )
    profile.built_ins = create_default_set(
        "Spawn built-ins",
        members=[
            create_rule("Blessed by the Chaos Gods"),
            create_rule("Out of Control"),
        ],
    )
    profile.save()

    rolls = {}
    for position, (name, bands) in enumerate(WARPED_TABLE.items()):
        stat = stats[name]
        group = create_option_group(
            profile, f"Warped Monstrosity: {stat.full_name}", position=position
        )
        # The head: rolled 2-5, the statline as printed, nothing added.
        offer_sets = {"2-5": create_default_set(f"{stat.full_name} rolled 2-5")}
        for band in ("1", "6"):
            setter = create_hidden(
                f"{stat.full_name} rolled {band}",
                effects=[
                    (
                        targets_model(),
                        ef_changes_stat(stat, mode="set", amount=bands[band]),
                    )
                ],
            )
            offer_sets[band] = create_default_set(
                f"{stat.full_name} rolled {band} set", members=[setter]
            )
        from n26.library.authoring import offer_option

        for band_position, band in enumerate(("2-5", "1", "6")):
            offer_option(
                profile,
                f"rolled {band}",
                default_set=offer_sets[band],
                position=band_position,
                group=group,
            )
        rolls[name] = offer_sets
    return profile, rolls


class TestWarpedMonstrosity:
    def test_the_dice_pick_the_options(self, spawn, gang_type):
        """The player rolls at the table; the roster takes the matching
        option per characteristic. Unrolled groups keep the printed
        band — nothing is ever enforced, the card just says."""
        profile, rolls = spawn
        gang = found_gang(
            "Spawn Keepers", gang_type, owner=User.objects.create_user("keeper")
        )
        hire_with_option(
            gang,
            profile,
            "The Thing Below",
            option=[
                rolls["weapon_skill"]["6"],  # rolled a 6: WS 3+
                rolls["toughness"]["1"],  # rolled a 1: T 4
                rolls["attacks"]["6"],  # rolled a 6: A 3
                # every other characteristic rolled 2-5: the head applies
            ],
        )

        card = card_for(gang, "The Thing Below")
        show(render_model_card(card))
        assert card.statline.get("WS").value == "3+"
        assert card.statline.get("T").value == "4"
        assert card.statline.get("A").value == "3"
        assert card.statline.get("S").value == "4"  # the printed band
        assert card.statline.get("Sv").value == "5+"
        assert [rule.name for rule in card.rules] == [
            "Blessed by the Chaos Gods",
            "Out of Control",
        ]


# =========================================================================
# The Justicar Court Delegation — an alliance that brings fighters
# =========================================================================


@pytest.fixture
def justicar_profiles(default_pack, gang_type, fighter_type):
    magistrate = create_profile(
        "Justicar Magistrate", fighter_type, gang_type, price=150
    )
    bailiff = create_profile("Bailiff", fighter_type, gang_type, price=75)
    for profile, statline in (
        (
            magistrate,
            dict(
                movement=4,
                weapon_skill=3,
                ballistic_skill=3,
                strength=3,
                toughness=3,
                wounds=2,
                initiative=4,
                attacks=2,
                save=4,
                leadership=7,
                cool=7,
                willpower=7,
                intelligence=8,
            ),
        ),
        (
            bailiff,
            dict(
                movement=4,
                weapon_skill=4,
                ballistic_skill=4,
                strength=3,
                toughness=3,
                wounds=1,
                initiative=3,
                attacks=1,
                save=5,
                leadership=6,
                cool=6,
                willpower=6,
                intelligence=6,
            ),
        ),
    ):
        set_statline(profile, **statline)
    return magistrate, bailiff


@pytest.fixture
def delegation(justicar_profiles):
    """The alliance carrier. Its stored effects hire the delegation.

    The scope is honest: the alliance **targets the
    gang** and adds each model once — the "adds a Magistrate" note
    belongs on the gang's card, never echoed onto members.
    """
    magistrate, bailiff = justicar_profiles
    alliance = create_affiliation("Justicar Court Alliance")
    modifier(
        "Delegation: the Magistrate",
        targets_gang(),
        op_adds_model(magistrate),
        attach_to=alliance,
    )
    for ordinal in ("first", "second"):
        modifier(
            f"Delegation: the {ordinal} Bailiff",
            targets_gang(),
            op_adds_model(bailiff),
            attach_to=alliance,
        )
    return alliance


class TestJusticarCourts:
    def test_the_tithe_buys_the_delegation_free(self, delegation, gang_type):
        """'a gang must pay 200 credits from their Stash' … 'These
        Fighters do not cost any credits.'"""
        gang = found_gang(
            "The Deputised",
            gang_type,
            owner=User.objects.create_user("sheriff"),
            budget=500,
        )
        pact = assign(delegation, gang=gang, paid=200)
        gang.refresh_from_db()
        assert gang.credits == 300

        members = Miniature.objects.filter(membership__gang=gang).order_by("name")
        assert [m.name for m in members] == [
            "Bailiff",
            "Bailiff",
            "Justicar Magistrate",
        ]
        assert all(m.membership.rating == 0 for m in members)

        sheet = render_gang(gang)
        print("\n" + render_gang_sheet(sheet))
        assert sheet.rating == 200  # the pact is what the gang is worth

        # The scope says where the news lands: targets_gang puts the
        # three "adds a …" notes on the gang's own card, happened, and
        # keeps them off every member's.
        from n26.core.card import build_gang_card, build_modifier_index
        from n26.core.effects import compute_gang

        gang_card = build_gang_card(gang)
        index = build_modifier_index(
            [
                node.assignable
                for card in (gang_card, *gang_card.members.values())
                for node in card.all_nodes()
            ]
        )
        computed = compute_gang(gang_card, index)
        assert sorted(
            (effect.description, effect.happened) for effect in computed.effects
        ) == [
            ("adds a Bailiff", True),
            ("adds a Bailiff", True),
            ("adds a Justicar Magistrate", True),
        ]
        assert all(card.effects == [] for card in sheet.models)

        # Breaking the alliance: the delegation leaves with it — the
        # same cascade that sells a pet with its collar.
        remove(pact)
        for member in members:
            member.membership.refresh_from_db()
            assert member.membership.archived

    def test_the_composer_builds_the_delegation_modifier(self, justicar_profiles):
        """The same row through the authoring stack: spec → generated
        form panes → composer submit → the three-row assembly. What an
        admin's one submit would write."""
        from n26.library.forms import ModifierComposerForm

        magistrate, _ = justicar_profiles
        alliance = create_affiliation("Justicar Court Alliance (composed)")

        form = ModifierComposerForm(
            {
                "scope_kind": "targets_gang",
                "effect_kind": "op_adds_model",
                "what-profile": str(magistrate.pk),
            },
            attach_to=alliance,
        )
        assert form.is_valid(), form.errors
        row = form.save()

        assert str(row.scope) == "the gang"
        assert str(row.effect) == "adds a Justicar Magistrate"
        # Attached and not made reusable, so the carrier stands where the
        # scope would: this reaches the gang because it hangs on the gang's
        # affiliation, and saying so twice tells the reader nothing.
        assert (
            row.name == "Justicar Court Alliance (composed): adds a Justicar Magistrate"
        )
        assert list(alliance.modifiers.all()) == [row]


# =========================================================================
# Master of Whispers — a priced awakening at hire
# =========================================================================


@pytest.fixture
def phantom(default_pack, fighter_type, gang_type, skills_catalogue):
    _, tiers = skills_catalogue
    whispers = create_category("Powers", "Psychoteric Whispers", 11)
    powers = {
        name: create_power(name, category=whispers)
        for name in ("Terrible Truths", "Psychotic Lure", "A Perfect Void")
    }
    profile = create_profile("Phantom", fighter_type, gang_type, price=205)
    set_statline(
        profile,
        movement=5,
        weapon_skill=4,
        ballistic_skill=3,
        strength=3,
        toughness=3,
        wounds=2,
        initiative=4,
        attacks=2,
        save=5,
        leadership=7,
        cool=7,
        willpower=8,
        intelligence=8,
    )

    awakening = create_hidden(
        "Master of Whispers",
        effects=[
            (targets_model(), ef_adds(create_subtype("Wyrd"))),
            (targets_model(), ef_places(whispers, tiers["primary"])),
            (
                targets_model(),
                ef_offers_choice(
                    Power, from_section=tiers["primary"], label="whispers power"
                ),
            ),
        ],
    )
    from n26.library.authoring import offer_option

    offer_option(
        profile, "Unawakened", default_set=create_default_set("Unawakened"), position=0
    )
    offer_option(
        profile,
        "Awakened",
        default_set=create_default_set(
            "Master of Whispers option", members=[awakening], price=35
        ),
        position=1,
    )
    return profile, powers


class TestMasterOfWhispers:
    def test_the_thirty_five_credit_awakening(self, phantom, gang_type):
        profile, powers = phantom
        gang = found_gang(
            "The Quiet", gang_type, owner=User.objects.create_user("delaque")
        )
        awakened = hire_with_option(
            gang,
            profile,
            "Silence",
            option=[profile.options.get(default_set__price=35).default_set],
        )
        assert awakened.membership.ledger_entry.paid == 205 + 35

        card = card_for(gang, "Silence")
        (slot,) = [c for c in card.choices if c.kind_label == "Whispers power"]
        assert slot.chosen is None  # open until the choice is made

        anchor = Assignment.objects.get(
            miniature__name="Silence", hidden__name="Master of Whispers"
        )
        choose(anchor, powers["Terrible Truths"])

        card = card_for(gang, "Silence")
        show(render_model_card(card))
        assert "Wyrd" in [s.name for s in card.subtypes]
        (slot,) = [c for c in card.choices if c.kind_label == "Whispers power"]
        assert slot.chosen == "Terrible Truths"

    def test_declining_costs_nothing_and_asks_nothing(self, phantom, gang_type):
        profile, _ = phantom
        gang = found_gang(
            "The Quieter", gang_type, owner=User.objects.create_user("delaque2")
        )
        plain = hire_with_option(gang, profile, "Hush")
        assert plain.membership.ledger_entry.paid == 205

        card = card_for(gang, "Hush")
        assert [c for c in card.choices if c.kind_label == "Whispers power"] == []
        assert "Wyrd" not in [s.name for s in card.subtypes]


# =========================================================================
# Immovable Brutes — a whole gang rule, previewed before it exists
# =========================================================================


class TestImmovableBrutes:
    """'All Leaders and Champions in a Free Ogryn gang gain the
    Juggernaut skill.' One composer payload — and the scratch card
    endpoint shows it working before a single row is saved."""

    def test_the_rule_previews_before_anything_is_saved(self, default_pack):
        from n26.core.preview import preview

        result = preview(
            {
                "create": [
                    {"kind": "subtype", "name": "Leader"},
                    {"kind": "subtype", "name": "Champion"},
                    {"kind": "skill", "name": "Juggernaut"},
                    {"kind": "rule", "name": "Immovable Brutes"},
                ],
                "modifiers": [
                    {
                        "attach_to": "@Immovable Brutes",
                        "scope_kind": "targets_model",
                        "effect_kind": "ef_adds",
                        "conditions-TOTAL_FORMS": "1",
                        "conditions-INITIAL_FORMS": "0",
                        "conditions-0-kind": "has_subtypes",
                        "conditions-0-subtypes": ["@Leader", "@Champion"],
                        "what-thing_kind": "skill",
                        "what-thing_skill": "@Juggernaut",
                    }
                ],
                "gang": {"carries": ["@Immovable Brutes"]},
                "fighters": [
                    {"name": "Scratch Overboss", "subtypes": ["@Leader"]},
                    {"name": "Scratch Lobo", "subtypes": []},
                ],
            }
        )

        import json

        print("\n" + json.dumps(result.as_dict(), indent=2))
        overboss, lobo = result.cards
        assert overboss["skills"] == ["Juggernaut"]
        assert lobo["skills"] == []  # not a Leader or Champion
        from n26.library.models import Rule, Skill

        assert not Skill.objects.filter(name="Juggernaut").exists()
        assert not Rule.objects.filter(name="Immovable Brutes").exists()
