"""The ingest flow, end to end: file in, preview out, rows on the other side.

Each stage is verified on its own interface (design/ingest.md §8):

* ``read_csv`` — the file becomes rows.
* ``plan_ingest`` — rows become an :class:`IngestPlan`: every library row
  the upload intends, as data, with problems for what doesn't resolve.
* ``plan.preview()`` — the plan derives the upload preview: counts by
  kind, worked examples pairing sheet rows with the objects they plan,
  the problem list. Plain data, JSON-able.
* ``perform`` — the plan becomes database rows, through the
  ``n26.library.authoring`` verbs, and creates exactly what the preview said.

The fixture sheets are miniatures of the real pre-ingest worksheets,
column for column: the **equipment** catalogue (what exists, and its
price), the **weapon profiles** (statlines only), the **equipment
lists** (a named collection per Title) and the **gang list profiles**
(the fighters). They join on the ID the sheets compute,
``Name (Profile) (Category ← Section)``, which is why the fixture holds
two different weapons both called "Power fist".
"""

import json

import pytest

from n26.library.ingest import ItemId, perform, plan_ingest, read_csv
from n26.library.models import (
    Category,
    Profile,
    Rule,
    Trait,
    Wargear,
    Weapon,
)
from n26.library.models.collection import Collection, CollectionEntry
from n26.library.standard_content import STANDARD_CONTENT

# --- The upload: four small sheets in the real sheets' shape -----------------
#
# Miniatures of the team's exports, column for column. The ``ID`` column
# they carry is the sheets' own join key, printing
# ``Name (Profile) (Category ← Section)`` — ingest recomputes it from
# those four columns rather than trusting the cell, so it is here for
# fidelity, not because anything reads it.

EQUIPMENT_CSV = """
Assignable,Section,Category,Name,Profile,Cost,TP,ID
Weapon,Ranged weapons,Auto/stub weapons,Autogun,,20,0,Autogun () (Auto/stub weapons ← Ranged weapons)
Weapon Profile,Ranged weapons,Auto/stub weapons,Autogun,warp round,10,4,Autogun (warp round) (Auto/stub weapons ← Ranged weapons)
Weapon,Close combat weapons,Lances,Frag lance,,-,E,Frag lance () (Lances ← Close combat weapons)
Weapon,Close combat weapons,Power weapons,Power fist,,-,E,Power fist () (Power weapons ← Close combat weapons)
Weapon,Close combat weapons,Exo weapons,Power fist,,105,2,Power fist () (Exo weapons ← Close combat weapons)
Weapon,Close combat weapons,Natural weapons,Ferocious jaws,,-,E,Ferocious jaws () (Natural weapons ← Close combat weapons)
Wargear,Wargear,Personal equipment,Respirator,,15,1,Respirator () (Personal equipment ← Wargear)
Wargear,Wargear,Pets,Phelynx,,-,E,Phelynx () (Pets ← Wargear)
Wargear,Wargear,Grenades,Frag grenades,,30,2,Frag grenades () (Grenades ← Wargear)
"""

WEAPON_PROFILES_CSV = """
Section,Category,Name,Profile,Sub-profile,SR,LR,Str,AP,L,Traits,ID
Ranged weapons,Auto/stub weapons,Autogun,,,8",24",3,-,1,Rapid Fire (1),Autogun () (Auto/stub weapons ← Ranged weapons)
Ranged weapons,Auto/stub weapons,Autogun,warp round,,8",24",3,-,1,"Cursed, Single Shot",Autogun (warp round) (Auto/stub weapons ← Ranged weapons)
Close combat weapons,Lances,Frag lance,primed,,E,-,4,-1,1,"Heavy, Knockback (5+), Melee",Frag lance (primed) (Lances ← Close combat weapons)
Close combat weapons,Lances,Frag lance,spent,,E,-,S,-,1,"Heavy, Melee",Frag lance (spent) (Lances ← Close combat weapons)
Close combat weapons,Power weapons,Power fist,,,E,-,S+2,-2,2,"Melee, Power Pack",Power fist () (Power weapons ← Close combat weapons)
Close combat weapons,Exo weapons,Power fist,,,E,-,S+2,-2,2,Melee,Power fist () (Exo weapons ← Close combat weapons)
Close combat weapons,Natural weapons,Ferocious jaws,,,E,-,S,-1,1,"Melee, Rending (6+)",Ferocious jaws () (Natural weapons ← Close combat weapons)
Wargear,Grenades,Frag grenades,,,-,6",3,-,1,Grenade,Frag grenades () (Grenades ← Wargear)
"""

EQUIPMENT_LISTS_CSV = """
Collection,Title,Section,Category,Name,Profile,Credits,Restrictions,ID
Equipment List,Escher,Ranged weapons,Auto/stub weapons,Autogun,,20,,Autogun () (Auto/stub weapons ← Ranged weapons)
Equipment List,Escher,Close combat weapons,Power weapons,Power fist,,25,,Power fist () (Power weapons ← Close combat weapons)
Equipment List,Escher,Wargear,Personal equipment,Respirator,,15,,Respirator () (Personal equipment ← Wargear)
Equipment List,Escher,Wargear,Pets,Phelynx,,60,Maximum one per gang,Phelynx () (Pets ← Wargear)
Equipment List,Cawdor,Close combat weapons,Lances,Frag lance,,35,Way-Brethren only,Frag lance () (Lances ← Close combat weapons)
Equipment List,Cawdor,Wargear,Personal equipment,Respirator,,15,,Respirator () (Personal equipment ← Wargear)
Equipment List,Goliath,Wargear,Personal equipment,Respirator,,20,,Respirator () (Personal equipment ← Wargear)
Equipment List,Goliath,Ranged weapons,Auto/stub weapons,Autogun,,20,,Autogun () (Auto/stub weapons ← Ranged weapons)
Equipment List,Goliath,Ranged weapons,Auto/stub weapons,Autogun,warp round,10,,Autogun (warp round) (Auto/stub weapons ← Ranged weapons)
Equipment List,Goliath,Close combat weapons,Exo weapons,Power fist,,105,Gunner specialist only,Power fist () (Exo weapons ← Close combat weapons)
"""

PROFILES_CSV = """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills (nb i have not listed skills applied by subtype),Default assignment,Primary Skill Sets,Secondary Skill Sets
Escher,Gang Queen,6",3+,3+,3,3,3,4,2,5+,8,8,7,7,Fighter,Leader,61,120,Witch,Catfall,,"Agility, Combat",Cunning
Cawdor,Way-Brethren,5",4+,4+,3,3,1,4,1,6+,6,6,6,6,Fighter,"Ganger, Specialist",13,45,,,,Combat,"Agility, Shooting"
Goliath,Sumpkroc,4",4+,-,4,4,2,2,1,5+,4,4,4,4,Fighter,"Beast, Pet",,65,,,Ferocious jaws,,
"""


def catalogue_key(kind, name, profile="", category="", section=""):
    """The plan key for a catalogue row — how the sheets identify a thing.

    Named here because the key carries the category: two of the fixture's
    weapons are called "Power fist", and only the category tells them
    apart.
    """
    return f"{kind}:{ItemId(name, profile, category, section).key}"


RANGED, CLOSE, GEAR = "Ranged weapons", "Close combat weapons", "Wargear"
AUTOGUN = catalogue_key(
    "Weapon", "Autogun", category="Auto/stub weapons", section=RANGED
)
WARP_ROUND = catalogue_key(
    "WeaponProfile", "Autogun", "warp round", "Auto/stub weapons", RANGED
)
AUTOGUN_OWN = catalogue_key("WeaponProfile", "Autogun", "", "Auto/stub weapons", RANGED)
FRAG_LANCE = catalogue_key("Weapon", "Frag lance", category="Lances", section=CLOSE)
LANCE_PRIMED = catalogue_key("WeaponProfile", "Frag lance", "primed", "Lances", CLOSE)
LANCE_SPENT = catalogue_key("WeaponProfile", "Frag lance", "spent", "Lances", CLOSE)
POWER_FIST = catalogue_key(
    "Weapon", "Power fist", category="Power weapons", section=CLOSE
)
EXO_FIST = catalogue_key("Weapon", "Power fist", category="Exo weapons", section=CLOSE)
JAWS = catalogue_key(
    "Weapon", "Ferocious jaws", category="Natural weapons", section=CLOSE
)
RESPIRATOR = catalogue_key(
    "Wargear", "Respirator", category="Personal equipment", section=GEAR
)
PHELYNX = catalogue_key("Wargear", "Phelynx", category="Pets", section=GEAR)
# Typed Wargear on the sheet, but it has a firing line — so a weapon.
FRAG_GRENADES = catalogue_key(
    "Weapon", "Frag grenades", category="Grenades", section=GEAR
)

ESCHER_LIST = "Collection:escher equipment list"
CAWDOR_LIST = "Collection:cawdor equipment list"
GOLIATH_LIST = "Collection:goliath equipment list"


def entry_key(collection_key, item_key):
    return f"CollectionEntry:{collection_key.split(':', 1)[1]}:{item_key}"


@pytest.fixture
def foundation(default_pack):
    """Standard content, sown exactly as the foundations page's buttons
    would sow it (library/standard_content.py)."""
    for item in STANDARD_CONTENT.values():
        item.create()


@pytest.fixture
def sheets():
    return {
        "equipment": read_csv(EQUIPMENT_CSV),
        "weapon_profiles": read_csv(WEAPON_PROFILES_CSV),
        "equipment_lists": read_csv(EQUIPMENT_LISTS_CSV),
        "profiles": read_csv(PROFILES_CSV),
    }


@pytest.fixture
def plan(foundation, sheets):
    return plan_ingest(pack=None, **sheets)


# --- Stage 0: standard content is the ground ---------------------------------


class TestStandardContentIsTheGround:
    def test_ingest_declares_what_it_stands_on(self):
        # The seeds ingest resolves against are STANDARD_CONTENT entries —
        # the generic seed contract in test_foundations.py covers their
        # behaviour; this pins that ingest's two are among them.
        assert {"progression-counters", "skills-collection"} <= set(STANDARD_CONTENT)

    def test_perform_names_the_missing_seed_rather_than_planting_it(
        self, default_pack, sheets
    ):
        plan = plan_ingest(pack=None, **sheets)  # nothing sown
        with pytest.raises(LookupError, match="sow standard content"):
            perform(plan)
        assert Weapon.objects.count() == 0  # and the transaction held


# --- Stage 1: file → plan ----------------------------------------------------


class TestPlanning:
    def test_a_file_becomes_rows(self):
        rows = read_csv(WEAPON_PROFILES_CSV)
        assert len(rows) == 8
        assert rows[0]["Name"] == "Autogun"
        assert rows[0]["SR"] == '8"'

    def test_the_plan_says_what_each_row_becomes(self, plan):
        # The equipment sheet fixes identity and price...
        autogun = plan.get(AUTOGUN)
        assert autogun.action == "create"
        assert autogun.fields["price"] == 20
        assert autogun.fields["is_exclusive"] is False
        assert autogun.fields["trade_point_price"] == 0  # 0 is a real TP price

        # ...and the profiles sheet supplies the statline. A weapon's own
        # line is unnamed, free and first: the card prints it as the
        # weapon itself.
        own = plan.get(AUTOGUN_OWN)
        assert own.name == ""
        assert own.fields["position"] == 0
        assert own.fields["price"] == 0
        assert own.fields["stats"]["SR"] == '8"'

        # A named line is priced by the equipment sheet, not this one.
        warp = plan.get(WARP_ROUND)
        assert warp.fields["position"] == 1
        assert warp.fields["price"] == 10
        assert warp.fields["trade_point_price"] == 4

        # A weapon with no own line starts at its first named one — the
        # lance is only ever primed or spent, and neither is a hole.
        lance = plan.get(FRAG_LANCE)
        assert lance.fields["price"] == 0  # "-": the lists price it
        assert lance.fields["is_exclusive"] is True
        assert plan.get(LANCE_PRIMED).fields["position"] == 0
        assert plan.get(LANCE_SPENT).fields["position"] == 1

    def test_one_printed_name_two_weapons_are_told_apart(self, plan):
        # A power fist is Exo kit and a Power weapon: two weapons wearing
        # one name, kept apart by the category the sheet files them under
        # and by the author-facing qualifier (§6a).
        assert plan.get(POWER_FIST).fields["qualifier"] == "Power weapons"
        assert plan.get(EXO_FIST).fields["qualifier"] == "Exo weapons"
        assert plan.get(POWER_FIST).fields["price"] == 0  # "-", list-priced
        assert plan.get(EXO_FIST).fields["price"] == 105

    def test_a_grenade_is_a_weapon_that_takes_no_slot(self, plan):
        """The sheet types grenades Wargear for one reason: they do not
        count against the weapons a fighter holds. But a thing with a
        firing line is a weapon, so it arrives as one — and slots 0
        carries the fact the typing was standing in for."""
        grenade = plan.get(FRAG_GRENADES)
        assert grenade.kind == "Weapon"
        assert grenade.fields["slots"] == 0
        assert grenade.fields["price"] == 30
        assert grenade.fields["trade_point_price"] == 2

        # Nothing was left behind as wargear under the same name...
        assert not [
            p for p in plan.planned if p.kind == "Wargear" and p.name == "Frag grenades"
        ]
        # ...and it still homes where the lists expect to find it.
        assert grenade.fields["category"] == "Category:wargear:grenades"

        # Its statline came across, on the weapon's own unnamed line.
        own = plan.get(
            f"WeaponProfile:{ItemId('Frag grenades', '', 'Grenades', GEAR).key}"
        )
        assert own.fields["stats"]["LR"] == '6"'
        assert own.fields["position"] == 0

    def test_ordinary_wargear_stays_wargear(self, plan):
        # Only a firing line makes the difference — a respirator has none.
        assert plan.get(RESPIRATOR).kind == "Wargear"
        assert plan.get(PHELYNX).kind == "Wargear"

    def test_the_tp_column_is_the_whole_trading_post_story(self, plan):
        # "E" is never-sold-there; a digit is its price there. Nothing
        # plans a Trading Post — membership is having the price.
        assert plan.get(RESPIRATOR).fields["trade_point_price"] == 1
        assert plan.get(RESPIRATOR).fields["is_exclusive"] is False
        assert plan.get(PHELYNX).fields["trade_point_price"] is None
        assert plan.get(PHELYNX).fields["is_exclusive"] is True
        assert not [p for p in plan.planned if p.name == "Trading Post"]

    def test_traits_are_planned_once_with_annotations(self, plan):
        melee = plan.get("Trait:melee:")
        assert melee.action == "create"
        knockback = plan.get("Trait:knockback:5+")
        assert knockback.fields["annotation"] == "5+"
        # Melee appears on four sheet rows; the plan holds one trait.
        assert sum(1 for p in plan.planned if p.key == "Trait:melee:") == 1

    def test_profiles_plan_price_statline_and_built_ins(self, plan):
        queen = plan.get("Profile:gang queen")
        assert queen.fields["price"] == 120  # Rating IS the price (§5a)
        assert queen.fields["stats"]["M"] == '6"'
        assert queen.fields["stats"]["Ld"] == "8"

        built_ins = plan.get(queen.fields["built_ins"])
        members = [member["item"] for member in built_ins.fields["members"]]
        assert "Subtype:leader" in members
        assert "Rule:witch:" in members
        assert "Skill:catfall" in members
        assert {"item": "Counter:xp", "amount": 61} in built_ins.fields["members"]

    def test_built_ins_resolve_against_the_catalogue(self, plan):
        croc = plan.get("Profile:sumpkroc")
        built_ins = plan.get(croc.fields["built_ins"])
        assert {"item": JAWS} in built_ins.fields["members"]

    def test_the_grid_columns_become_placement_modifiers(self, plan):
        primary = plan.get("Modifier:Profile:gang queen:agility:primary")
        assert primary.fields["attach_to"] == "Profile:gang queen"
        assert primary.fields["places"] == {
            "category": "Category:skills:agility",
            "section": "Primary",
        }
        assert plan.get("Modifier:Profile:gang queen:cunning:secondary")

    def test_list_lines_become_a_named_collection_of_entries(self, plan):
        # The sheet splits the kind from the name; the library holds one
        # row, so the two go back together.
        assert plan.get(CAWDOR_LIST).name == "Cawdor Equipment List"

        entry = plan.get(entry_key(CAWDOR_LIST, FRAG_LANCE))
        assert entry.fields["collection"] == CAWDOR_LIST
        restriction = plan.get(f"Restriction:{entry.key}")
        assert restriction.fields["profile"] == "Profile:way-brethren"

        # A listing that names a Profile sells one firing line of a gun.
        assert plan.get(entry_key(GOLIATH_LIST, WARP_ROUND))

    def test_an_entry_overrides_only_where_it_disagrees(self, plan):
        # The catalogue prices a respirator at 15. Escher agrees, so its
        # entry says nothing and a later correction flows through;
        # Goliath charges 20, which is this list's own fact.
        assert plan.get(RESPIRATOR).fields["price"] == 15
        assert (
            plan.get(entry_key(ESCHER_LIST, RESPIRATOR)).fields["price_override"]
            is None
        )
        assert (
            plan.get(entry_key(GOLIATH_LIST, RESPIRATOR)).fields["price_override"] == 20
        )

    def test_a_list_only_item_takes_its_price_from_the_list(self, plan):
        # "-" is no reference price at all, so the list price is the only
        # price the thing has ever had and is always written.
        assert plan.get(POWER_FIST).fields["price"] == 0
        assert (
            plan.get(entry_key(ESCHER_LIST, POWER_FIST)).fields["price_override"] == 25
        )

        # Ferocious jaws is on no list: a free built-in, and it stays 0.
        assert plan.get(JAWS).fields["price"] == 0


# --- Stage 2: plan → preview ---------------------------------------------------


class TestPreview:
    def test_the_preview_counts_what_the_upload_creates(self, plan):
        preview = plan.preview()
        assert preview["ok"] is True
        assert preview["counts"]["Weapon"] == 6  # two named "Power fist"; one a grenade
        assert preview["counts"]["WeaponProfile"] == 8
        assert preview["counts"]["Profile"] == 3
        assert preview["counts"]["Wargear"] == 2
        assert preview["counts"]["Collection"] == 3
        assert preview["counts"]["CollectionEntry"] == 10
        assert preview["actions"]["create"] == sum(
            1 for p in plan.planned if p.action == "create"
        )

    def test_examples_pair_sheet_rows_with_planned_objects(self, plan):
        preview = plan.preview(examples=1)
        by_sheet = {
            example["source"]["sheet"]: example for example in preview["examples"]
        }
        # The catalogue row makes the weapon; the statline row makes its
        # firing line and the traits on it. Two sheets, two halves.
        equipment_example = by_sheet["equipment"]
        assert equipment_example["row"]["Name"] == "Autogun"
        assert ("Weapon", "Autogun") in {
            (c["kind"], c["name"]) for c in equipment_example["creates"]
        }

        statline_example = by_sheet["weapon_profiles"]
        created = {(c["kind"], c["name"]) for c in statline_example["creates"]}
        assert ("WeaponProfile", "") in created  # the weapon's own, unnamed line
        assert ("Trait", "Rapid Fire") in created

        profiles_example = by_sheet["profiles"]
        assert profiles_example["row"]["Name"] == "Gang Queen"
        kinds = {c["kind"] for c in profiles_example["creates"]}
        assert {"Profile", "DefaultAssignmentSet", "Modifier"} <= kinds

    def test_examples_can_be_sampled(self, plan):
        preview = plan.preview(examples=2, sample=True, seed=26)
        assert (
            len([e for e in preview["examples"] if e["source"]["sheet"] == "equipment"])
            == 2
        )

    def test_the_preview_is_plain_data(self, plan):
        # JSON round-trips: the preview is a structure, not objects.
        parsed = json.loads(json.dumps(plan.preview()))
        assert parsed["counts"] == plan.preview()["counts"]

    def test_notes_are_said_but_do_not_block(self, plan):
        preview = plan.preview()
        notes = [p for p in preview["problems"] if p["severity"] == "note"]
        # A gang-wide cap is not a restriction on *use*, and a
        # specialisation is something usable-by has no arm for. Both are
        # said plainly and carried past, never bent into the wrong shape.
        assert any("not a restriction on use" in n["message"] for n in notes)
        assert any("names a specialisation" in n["message"] for n in notes)
        assert preview["ok"] is True


# --- Problems: what the plan refuses ------------------------------------------


class TestProblems:
    def test_an_unknown_weapon_on_a_list_is_a_problem_not_a_weapon(self, foundation):
        plan = plan_ingest(
            equipment_lists=read_csv(
                """
Collection,Title,Section,Category,Name,Profile,Credits,Restrictions,ID
Equipment List,Escher,Ranged weapons,Web weapons,Web pisol,,90,,x
"""
            )
        )
        assert not plan.ok
        assert "Web pisol" in plan.problems[0].message
        assert not [p for p in plan.planned if p.kind == "Weapon"]
        with pytest.raises(ValueError, match="Web pisol"):
            perform(plan)

    def test_a_priced_own_line_is_refused(self, foundation):
        # A weapon's own firing line is bought with the weapon, so it
        # cannot carry a price of its own. A catalogue row typed
        # "Weapon Profile" that names no profile is asking for exactly
        # that, and is sent back rather than guessed at.
        plan = plan_ingest(
            equipment=read_csv(
                """
Assignable,Section,Category,Name,Profile,Cost,TP,ID
Weapon,Close combat weapons,Lances,Frag lance,,-,E,x
Weapon Profile,Close combat weapons,Lances,Frag lance,,45,E,y
"""
            )
        )
        assert not plan.ok
        assert "names no Profile" in plan.problems[0].message

    def test_a_statline_for_nothing_the_catalogue_sells_is_ignored(self, foundation):
        # Nothing is created either way, so this is said and carried
        # past — it never invents the weapon (resolve, never create).
        plan = plan_ingest(
            weapon_profiles=read_csv(
                """
Section,Category,Name,Profile,Sub-profile,SR,LR,Str,AP,L,Traits,ID
Ranged weapons,Web weapons,Web pistol,,,8",16",3,-,1,Web,x
"""
            )
        )
        assert plan.ok  # a note, not an error
        assert "sells no such thing" in plan.problems[0].message
        assert not [p for p in plan.planned if p.kind == "Weapon"]

    def test_an_unresolvable_built_in_does_not_block_the_fighter(self, foundation):
        """Built-in-only kit — exo-suits, hunting rigs, natural weapons —
        is never sold, so no sheet defines it. The fighter is still worth
        having, so this is said and the fighter arrives without it."""
        plan = plan_ingest(
            profiles=read_csv(
                """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Escher,Wyld Runner,6",4+,4+,3,3,1,4,1,6+,6,7,7,6,Fighter,Prospect,4,25,,,Exo-suit,Agility,
"""
            )
        )
        assert plan.ok  # a note, not an error
        assert "imported without it" in plan.problems[0].message
        assert plan.get("Profile:wyld runner") is not None

    def test_a_rule_in_variants_is_several_rules(self, foundation):
        """A leash at two distances is two rules sharing a printed name,
        exactly as a trait is — the annotation is part of the identity."""
        plan = plan_ingest(
            profiles=read_csv(
                """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Delaque,Piscean Spektor,5",4+,5+,3,3,2,4,2,5+,7,7,7,7,Fighter,"Beast, Pet",,110,"Leash (3"")",,,,
Delaque,Psychoteric Wyrm,4",4+,6+,3,3,2,3,1,6+,7,7,7,7,Fighter,"Beast, Pet",,50,"Leash (6"")",,,,
"""
            )
        )
        assert plan.ok
        assert plan.get('Rule:leash:3"').fields["annotation"] == '3"'
        assert plan.get('Rule:leash:6"').fields["annotation"] == '6"'

        perform(plan)
        leashes = Rule.objects.filter(name="Leash").order_by("annotation")
        assert [r.annotation for r in leashes] == ['3"', '6"']

    def test_the_sheet_may_name_the_qualifier_itself(self, foundation):
        """Where the sheet says which qualifier a fighter takes, that is
        used verbatim — inference is only the fallback."""
        plan = plan_ingest(
            profiles=read_csv(
                """
Gang,Name,Qualifier,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Genestealer Cults,Alpha,Genestealer Cults,5",4+,4+,3,3,2,4,2,5+,7,7,7,7,Fighter,Leader,25,110,,,,,
Malstrain,Alpha,Malstrain,5",4+,4+,3,3,2,4,2,5+,7,7,7,7,Fighter,Leader,25,110,,,,,
"""
            )
        )
        assert plan.ok
        assert plan.get("Profile:alpha:genestealer cults").fields["qualifier"] == (
            "Genestealer Cults"
        )
        assert plan.get("Profile:alpha:malstrain").fields["qualifier"] == "Malstrain"

    def test_two_fighters_claiming_one_identity_are_refused(self, foundation):
        """Name and qualifier together are the identity. Two rows holding
        both would be one row — and the second would vanish into the
        first — so the plan says so rather than quietly losing a fighter."""
        plan = plan_ingest(
            profiles=read_csv(
                """
Gang,Name,Qualifier,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Genestealer Cults,Alpha,Genestealer Cults,5",4+,4+,3,3,2,4,2,5+,7,7,7,7,Fighter,Leader,25,110,,,,,
Malstrain,Alpha,Genestealer Cults,5",4+,4+,3,3,2,4,2,5+,7,7,7,7,Fighter,Leader,25,110,,,,,
"""
            )
        )
        assert not plan.ok
        assert "need different qualifiers" in plan.problems[0].message

    def test_a_row_with_no_type_is_sent_back_to_its_own_sheet(self, foundation):
        plan = plan_ingest(
            profiles=read_csv(
                """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Chaos Helot Cult,2-5,,4+,,4,5,2,3,2,5+,,,,,,,,,,,,,
"""
            )
        )
        assert not plan.ok
        assert "§6b" in plan.problems[0].message


# --- Stage 3: plan → rows ------------------------------------------------------


class TestPerform:
    def test_creates_exactly_what_the_preview_said(self, plan):
        preview = plan.preview()
        result = perform(plan)
        planned_creates = {}
        for row in plan.planned:
            if row.action == "create":
                planned_creates[row.kind] = planned_creates.get(row.kind, 0) + 1
        assert result.counts() == planned_creates
        assert sum(result.counts().values()) == preview["actions"]["create"]
        # exists rows (the standard-content subtypes, mostly) resolve to
        # already-there rows; nothing is both created and pre-existing.
        planned_exists = {row.key for row in plan.planned if row.action == "exists"}
        assert set(result.existing) <= planned_exists
        assert not set(result.created) & set(result.existing)

    def test_weapons_arrive_with_profiles_statlines_and_traits(self, plan):
        perform(plan)
        autogun = Weapon.objects.get(name="Autogun")
        assert autogun.price == 20
        own, warp = autogun.profiles.order_by("position")
        assert own.price == 0 and warp.price == 10
        assert warp.trade_point_price == 4
        assert own.name == ""  # the weapon's own line prints as the weapon
        assert own.statline.as_dict() == {
            "short_range": '8"',
            "long_range": '24"',
            "strength": "3",  # the one shared Strength row
            "armour_piercing": "-",
            "lethality": "1",
        }
        assert sorted(warp.trait_names) == ["Cursed", "Single Shot"]

        lance = Weapon.objects.get(name="Frag lance")
        assert lance.is_exclusive is True
        primed, spent = lance.profiles.order_by("position")
        assert primed.statline.as_dict()["strength"] == "4"
        assert spent.statline.as_dict()["strength"] == "S"

    def test_profiles_arrive_with_statline_built_ins_and_grid(self, plan):
        perform(plan)
        queen = Profile.objects.get(name="Gang Queen")
        assert queen.price == 120
        assert queen.stats()["movement"] == '6"'
        assert queen.stats()["weapon_skill"] == "3+"
        assert queen.stats()["leadership"] == "8"  # plain number, no plus

        members = {str(m.assignable) for m in queen.built_ins.members.all()}
        assert {"Leader", "Witch", "Catfall"} <= members
        xp_row = queen.built_ins.members.get(counter__isnull=False)
        assert xp_row.assignable.name == "XP"
        assert xp_row.amount == 61

        placement = queen.modifiers.get(name="Gang Queen: Agility is Primary")
        assert placement.places_category.category.name == "Agility"
        assert placement.places_category.section.name == "Primary"

    def test_built_ins_attach_at_price_zero_whatever_the_lists_say(self, plan):
        perform(plan)
        croc = Profile.objects.get(name="Sumpkroc")
        members = {str(m.assignable) for m in croc.built_ins.members.all()}
        assert members == {"Beast", "Pet", "Ferocious jaws"}
        jaws = croc.built_ins.members.get(weapon__isnull=False).assignable
        assert jaws.price == 0  # never priced from a list (§5a)

    def test_equipment_lists_arrive_with_overrides_and_restrictions(self, plan):
        perform(plan)
        respirator = Wargear.objects.get(name="Respirator")
        assert respirator.price == 15
        goliath_list = Collection.objects.get(name="Goliath Equipment List")
        entry = CollectionEntry.objects.get(collection=goliath_list, wargear=respirator)
        assert entry.price_override == 20
        assert entry.price.credits == 20

        escher_list = Collection.objects.get(name="Escher Equipment List")
        assert (
            CollectionEntry.objects.get(
                collection=escher_list, wargear=respirator
            ).price_override
            is None
        )

        lance = Weapon.objects.get(name="Frag lance")
        assert [p.name for p in lance.usable_by_profiles.all()] == ["Way-Brethren"]

    def test_categories_land_under_their_sections(self, plan):
        perform(plan)
        category = Category.objects.get(name="Auto/stub weapons")
        assert category.section.name == "Ranged weapons"

    def test_skill_sets_resolve_to_the_standard_ones(self, plan):
        """The sheet names Agility and Combat, and standard content
        already has them, so an upload joins those sets rather than
        founding a second Agility beside the first."""
        before = set(
            Category.objects.filter(section__name="Skills").values_list(
                "name", flat=True
            )
        )
        perform(plan)
        after = Category.objects.filter(section__name="Skills")

        assert {"Agility", "Combat"} <= before  # sown, not invented here
        assert set(after.values_list("name", flat=True)) == before
        assert after.filter(name="Agility").count() == 1

    def test_the_trading_post_fills_itself(self, plan):
        """Ingest builds no Trading Post, and the post is full anyway.

        Membership there is *having a trade point price*, swept in by
        standard content's two selectors — so setting the field from the
        sheet's TP column is ingest's whole part in it. "E" is the other
        half of the same fact: never sold there, equipment list only.
        """
        from n26.library.standard_content import TRADING_POST_COLLECTION

        perform(plan)
        post = Collection.objects.get(name=TRADING_POST_COLLECTION)
        assert post.entries.count() == 0  # nothing was listed by hand

        swept = {
            item.name
            for selector in post.selectors.all()
            for item in selector.contents(include_exclusive=False)
        }
        assert "Autogun" in swept  # TP 0 — free there, but offered
        assert "Respirator" in swept  # TP 1
        assert "Frag lance" not in swept  # TP "E" — list only
        assert "Phelynx" not in swept

        # And the two halves never both hold, which the database also
        # refuses (exclusive_has_no_trade_points).
        assert not Weapon.objects.filter(
            is_exclusive=True, trade_point_price__isnull=False
        ).exists()

    def test_one_name_two_weapons_both_arrive(self, plan):
        perform(plan)
        fists = Weapon.objects.filter(name="Power fist").order_by("qualifier")
        assert [w.qualifier for w in fists] == ["Exo weapons", "Power weapons"]
        # The qualifier is for authors; a card prints the name alone.
        assert {str(w) for w in fists} == {"Power fist"}

    def test_the_whole_upload_is_one_transaction(self, foundation, sheets, monkeypatch):
        import n26.library.ingest as ingest_module

        plan = plan_ingest(pack=None, **sheets)
        original = ingest_module._Performer._create_modifier

        def explode(self, planned):
            raise RuntimeError("boom mid-import")

        monkeypatch.setattr(ingest_module._Performer, "_create_modifier", explode)
        with pytest.raises(RuntimeError):
            perform(plan)
        monkeypatch.setattr(ingest_module._Performer, "_create_modifier", original)
        assert Weapon.objects.count() == 0
        assert Profile.objects.count() == 0


# --- Round two: the same file again --------------------------------------------


class TestIdempotency:
    def test_a_second_upload_plans_exists_and_creates_nothing(self, foundation, sheets):
        first = plan_ingest(pack=None, **sheets)
        perform(first)
        weapons, traits, profiles = (
            Weapon.objects.count(),
            Trait.objects.count(),
            Profile.objects.count(),
        )

        again = plan_ingest(pack=None, **sheets)
        assert again.ok
        assert {p.action for p in again.planned} == {"exists"}
        result = perform(again)
        assert result.created == {}
        assert Weapon.objects.count() == weapons
        assert Trait.objects.count() == traits
        assert Profile.objects.count() == profiles

    def test_the_same_name_from_another_gang_is_qualified_not_merged(
        self, foundation, sheets
    ):
        """Two gangs printing one fighter name is normal; the qualifier
        (§6a) holds both. Authors see it, players never do."""
        perform(plan_ingest(pack=None, **sheets))
        clash_sheet = read_csv(
            """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Corpse Grinder Cults,Gang Queen,5",3+,4+,3,3,2,4,2,5+,7,7,7,7,Fighter,Leader,61,140,,,,Combat,
"""
        )
        clash = plan_ingest(profiles=clash_sheet)
        assert clash.ok
        planned = clash.get("Profile:gang queen:corpse grinder cults")
        assert planned.action == "create"
        assert planned.fields["qualifier"] == "Corpse Grinder Cults"
        assert any(p.severity == "note" and "§6a" in p.message for p in clash.problems)

        perform(clash)
        both = Profile.objects.filter(name="Gang Queen").order_by("qualifier")
        assert [(p.qualifier, p.gang_type.name, p.price) for p in both] == [
            ("", "Escher", 120),
            ("Corpse Grinder Cults", "Corpse Grinder Cults", 140),
        ]

        # And a third upload of the same clash sheet changes nothing.
        again = plan_ingest(profiles=clash_sheet)
        assert {p.action for p in again.planned} == {"exists"}
        assert perform(again).created == {}
