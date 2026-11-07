"""Build gang-book rule patterns using the shipped authoring API.

Chaos Corruption combines gang choices, rule suppression, collection access
and priced power selection. Warped Monstrosity represents rolled characteristics
as option groups. Justicar alliances create dependent delegation models.
Master of Whispers adds a priced subtype, power placement and choice.
Immovable Brutes exercises the same composition through an unsaved preview.
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
    create_pickable,
    create_picklist,
    create_power,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
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
    targets_every_model,
    targets_gang,
    targets_model,
)
from n26.library.models import Power
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
    """Render the named model card from the gang sheet."""
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
def corruption_choice(default_pack):
    """Create a Variant choice and a separate Chaos God choice for chained selection."""
    variant_type = create_slot_type("Variant", allows_repeats=False)
    god_type = create_slot_type(
        "Chaos God", plural_name="Chaos Gods", allows_repeats=False
    )
    gods = {
        name: create_pickable(f"Dedicated: the {name}", god_type)
        for name in ("Blood God", "Plague Lord", "Dark Prince", "Architect of Fate")
    }
    god_slot = create_slot(
        "Chaos God",
        god_type,
        create_picklist("Chaos Gods", god_type, members=list(gods.values())),
        label="Dedication",
        assigned_to="gang",
        min_picks=0,
        max_picks=1,
    )
    corrupted = create_pickable("Chaos Corrupted", variant_type)
    variant_slot = create_slot(
        "Variant",
        variant_type,
        create_picklist("Variants", variant_type, members=[corrupted]),
        label="Corruption",
        assigned_to="gang",
        min_picks=0,
        max_picks=1,
    )
    return variant_slot, god_slot, corrupted, gods


@pytest.fixture
def escher(ranks, default_pack, corruption_choice):
    """Build a charter into Escher to anchor its gang choice and grant Nimble to models."""
    variant_slot, _, _, _ = corruption_choice
    nimble = create_rule("Nimble")
    charter = create_hidden(
        "House Escher charter",
        effects=[
            (targets_every_model(), ef_adds(nimble)),
            # Expose an optional gang-level corruption choice at founding.
            (targets_gang(), ef_adds(variant_slot)),
        ],
    )
    gang_type = create_gang_type("Escher")
    gang_type.built_ins = create_default_set("Escher founding", members=[charter])
    gang_type.save()
    return gang_type, nimble, charter


@pytest.fixture
def chaos_corruption(escher, ranks, chaos_powers, skills_catalogue, corruption_choice):
    """Attach rule suppression, ritual rules, a follow-up choice and equipment access to the corruption pick."""
    _, nimble, _ = escher
    _, god_slot, corruption, gods = corruption_choice
    family, powers = chaos_powers
    _, tiers = skills_catalogue
    wyrd = create_subtype("Wyrd")

    # A priced carrier grants the Wyrd subtype, family placement and power choice.
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

    # Note the familiar's Leader or Champion restriction without blocking purchase.
    familiar = create_wargear("Chaos Familiar", price=40)
    restrict_use(familiar, ranks["leader"], ranks["champion"])

    options = create_collection(
        "Chaos Corruption Options", entries=[(ascension, {}), (familiar, {})]
    )

    for scope, effect in [
        # Suppress the House rule through a computed removal effect.
        (targets_every_model(), ef_removes(nimble)),
        # The Post-cycle rituals, printed on who may perform them.
        (
            targets_every_model(has_subtypes(ranks["leader"])),
            ef_adds(create_rule("Lead Ritual", annotation="Leader only")),
        ),
        (
            targets_every_model(),
            ef_adds(create_rule("Ritual Focus", annotation="max one Fighter")),
        ),
        # The corruption pick grants the follow-up God choice and anchors its lifetime.
        (targets_gang(), ef_adds(god_slot)),
        # The corruption-only equipment list, opened for everyone.
        (targets_every_model(), ef_adds(options)),
    ]:
        modifier(f"Chaos Corrupted: {effect}", scope, effect, attach_to=corruption)
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
        from n26.library.models import Slot

        gang_type, _, charter = escher
        corruption, gods, _, _ = chaos_corruption
        gang = found_gang(
            "The Tainted",
            gang_type,
            owner=User.objects.create_user("heretic"),
            budget=1000,
        )
        anchor = Assignment.objects.get(gang=gang, hidden=charter)
        corrupted = choose(anchor, corruption, slot=Slot.objects.get(name="Variant"))
        choose(corrupted, gods["Blood God"], slot=Slot.objects.get(name="Chaos God"))
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
    """Create a full-statline Spawn with the middle band as defaults and other rolls as options.

    Movement and Ballistic Skill remain unset and display as dashes.
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
        """Use supplied option selections for rolled characteristics and retain defaults for unselected groups."""
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
    """Attach gang-scoped stored effects that create the delegation once and describe it on the gang sheet."""
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
        """Pay for the alliance while its dependent delegation models contribute no separate rating."""
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

        # Gang-targeted stored effects are described on the gang sheet without duplication on model cards.
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

        # Removing the alliance archives its dependent delegation models.
        remove(pact)
        for member in members:
            member.membership.refresh_from_db()
            assert member.membership.archived

    def test_the_composer_builds_the_delegation_modifier(self, justicar_profiles):
        """Create the attached delegation modifier through the generated composer form."""
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
        # The attached modifier name inherits its alliance carrier and omits redundant scope wording.
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
    """Preview a gang rule granting Juggernaut to Leaders and Champions without saving content."""

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
                        "scope_kind": "targets_every_model",
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
