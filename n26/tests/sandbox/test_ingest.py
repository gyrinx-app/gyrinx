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

The fixture sheets are miniatures of the real pre-ingest worksheets —
the rows are drawn from the worked examples in design/ingest.md.
"""

import json

import pytest

from n26.library.ingest import perform, plan_ingest, read_csv
from n26.library.models import (
    Category,
    Profile,
    Trait,
    Wargear,
    Weapon,
)
from n26.library.models.collection import Collection, CollectionEntry
from n26.library.standard_content import STANDARD_CONTENT

# --- The upload: three small sheets in the real sheets' shape ---------------

WEAPONS_CSV = """
Gang,Type,Subtype,Name,SR,LR,Str,AP,L,Traits,Credits,TP
Trading Post,Ranged,Auto/stub,Autogun,8",24",3,-,1,Rapid Fire (1),20,0
Trading Post,Ranged,Auto/stub,- warp round,8",24",3,-,1,"Cursed, Single Shot",10,4
Cawdor,Close Combat,Lances,Frag lance,,,,,,,35,E
Cawdor,Close Combat,Lances,- primed,E,-,4,-1,1,"Heavy, Knockback (5+), Melee",,
Cawdor,Close Combat,Lances,- spent,E,-,S,-,1,"Heavy, Melee",,
Escher,Close Combat,Power,Power knife,E,-,S+1,-2,1,Melee,-,E
Goliath,Ranged,Natural,Ferocious jaws,E,-,S,-1,1,"Melee, Rending (6+)",-,E
"""

EQUIPMENT_CSV = """
Gang,Type,Subtype,Name,Credits,Restrictions
Escher,Ranged,Auto/stub,Autogun,20,
Escher,Close Combat,Power,Power knife,25,
Escher,Wargear,Personal equipment,Respirator,15,
Escher,Wargear,Pets,Phelynx,60,maximum one per gang
Cawdor,Close Combat,Lances,Frag lance,35,Way-Brethren only
Cawdor,Wargear,Personal equipment,Respirator,15,
Goliath,Wargear,Personal equipment,Respirator,20,
Goliath,Ranged,Auto/stub,Autogun,20,
Goliath,Ranged,Auto/stub,- warp round,10,
"""

PROFILES_CSV = """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills (nb i have not listed skills applied by subtype),Default assignment,Primary Skill Sets,Secondary Skill Sets
Escher,Gang Queen,6",3+,3+,3,3,3,4,2,5+,8,8,7,7,Fighter,Leader,61,120,Witch,Catfall,,"Agility, Combat",Cunning
Cawdor,Way-Brethren,5",4+,4+,3,3,1,4,1,6+,6,6,6,6,Fighter,"Ganger, Specialist",13,45,,,,Combat,"Agility, Shooting"
Goliath,Sumpkroc,4",4+,-,4,4,2,2,1,5+,4,4,4,4,Fighter,"Beast, Pet",,65,,,Ferocious jaws,,
"""


@pytest.fixture
def foundation(default_pack):
    """Standard content, sown exactly as the foundations page's buttons
    would sow it (library/standard_content.py)."""
    for item in STANDARD_CONTENT.values():
        item.create()


@pytest.fixture
def sheets():
    return {
        "weapons": read_csv(WEAPONS_CSV),
        "equipment_lists": read_csv(EQUIPMENT_CSV),
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
        rows = read_csv(WEAPONS_CSV)
        assert len(rows) == 7
        assert rows[0]["Name"] == "Autogun"
        assert rows[0]["SR"] == '8"'

    def test_the_plan_says_what_each_row_becomes(self, plan):
        autogun = plan.get("Weapon:autogun")
        assert autogun.action == "create"
        assert autogun.fields["price"] == 20
        assert autogun.fields["is_exclusive"] is False

        # Shape A: a weapon with stats is its own first, free profile —
        # unnamed, because the card prints it as the weapon itself.
        own = plan.get("WeaponProfile:autogun:")
        assert own.name == ""
        assert own.fields["position"] == 0
        assert own.fields["price"] == 0
        assert own.fields["stats"]["SR"] == '8"'

        # The dash row beneath it is a further, priced profile.
        warp = plan.get("WeaponProfile:autogun:warp round")
        assert warp.fields["position"] == 1
        assert warp.fields["price"] == 10
        assert warp.fields["trade_point_price"] == 4

        # Shape B: a stat-less header weapon; all profiles are dash rows.
        lance = plan.get("Weapon:frag lance")
        assert lance.fields["price"] == 35
        assert lance.fields["is_exclusive"] is True
        assert plan.get("WeaponProfile:frag lance:primed").fields["position"] == 0
        assert plan.get("WeaponProfile:frag lance:spent").fields["position"] == 1

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

    def test_built_ins_resolve_against_the_weapons_sheet(self, plan):
        croc = plan.get("Profile:sumpkroc")
        built_ins = plan.get(croc.fields["built_ins"])
        assert {"item": "Weapon:ferocious jaws"} in built_ins.fields["members"]

    def test_the_grid_columns_become_placement_modifiers(self, plan):
        primary = plan.get("Modifier:Profile:gang queen:agility:primary")
        assert primary.fields["attach_to"] == "Profile:gang queen"
        assert primary.fields["places"] == {
            "category": "Category:skills:agility",
            "section": "Primary",
        }
        assert plan.get("Modifier:Profile:gang queen:cunning:secondary")

    def test_equipment_lines_become_entries_and_restrictions(self, plan):
        entry = plan.get("CollectionEntry:cawdor:Weapon:frag lance")
        assert entry.fields["collection"] == "Collection:cawdor equipment list"
        restriction = plan.get(f"Restriction:{entry.key}")
        assert restriction.fields["profile"] == "Profile:way-brethren"

        # The dash line under Goliath's autogun is a profile entry.
        assert plan.get("CollectionEntry:goliath:WeaponProfile:autogun:warp round")

    def test_prices_reference_and_override(self, plan):
        # Respirator is 15, 15, 20 across three lists: 15 is the
        # reference, Goliath's 20 an override, the others none (§5b).
        assert plan.get("Wargear:respirator").fields["price"] == 15
        goliath = plan.get("CollectionEntry:goliath:Wargear:respirator")
        assert goliath.fields["price_override"] == 20
        escher = plan.get("CollectionEntry:escher:Wargear:respirator")
        assert escher.fields["price_override"] is None

        # Power knife is printed "-": its reference comes from the one
        # list that sells it. Ferocious jaws is on no list: a free
        # built-in, price 0.
        assert plan.get("Weapon:power knife").fields["price"] == 25
        assert plan.get("Weapon:ferocious jaws").fields["price"] == 0

    def test_the_new_sheet_shape_plans_identically(self, foundation):
        explicit = read_csv(
            """
Gang,Type,Subtype,Weapon,Profile,SR,LR,Str,AP,L,Traits,Credits,TP
Trading Post,Ranged,Auto/stub,Autogun,,8",24",3,-,1,Rapid Fire (1),20,0
Trading Post,Ranged,Auto/stub,Autogun,warp round,8",24",3,-,1,"Cursed, Single Shot",10,4
"""
        )
        positional = read_csv(
            """
Gang,Type,Subtype,Name,SR,LR,Str,AP,L,Traits,Credits,TP
Trading Post,Ranged,Auto/stub,Autogun,8",24",3,-,1,Rapid Fire (1),20,0
Trading Post,Ranged,Auto/stub,- warp round,8",24",3,-,1,"Cursed, Single Shot",10,4
"""
        )
        keys = lambda plan: {  # noqa: E731
            (p.kind, p.key, p.fields.get("price")) for p in plan.planned
        }
        assert keys(plan_ingest(weapons=explicit)) == keys(
            plan_ingest(weapons=positional)
        )


# --- Stage 2: plan → preview ---------------------------------------------------


class TestPreview:
    def test_the_preview_counts_what_the_upload_creates(self, plan):
        preview = plan.preview()
        assert preview["ok"] is True
        assert preview["counts"]["Weapon"] == 4
        assert preview["counts"]["WeaponProfile"] == 6
        assert preview["counts"]["Profile"] == 3
        assert preview["counts"]["Wargear"] == 2
        assert preview["counts"]["Collection"] == 3
        assert preview["counts"]["CollectionEntry"] == 9
        assert preview["actions"]["create"] == sum(
            1 for p in plan.planned if p.action == "create"
        )

    def test_examples_pair_sheet_rows_with_planned_objects(self, plan):
        preview = plan.preview(examples=1)
        by_sheet = {
            example["source"]["sheet"]: example for example in preview["examples"]
        }
        weapons_example = by_sheet["weapons"]
        assert weapons_example["row"]["Name"] == "Autogun"
        created = {(c["kind"], c["name"]) for c in weapons_example["creates"]}
        assert ("Weapon", "Autogun") in created
        assert ("WeaponProfile", "") in created  # the weapon's own, unnamed line
        assert ("Trait", "Rapid Fire") in created

        profiles_example = by_sheet["profiles"]
        assert profiles_example["row"]["Name"] == "Gang Queen"
        kinds = {c["kind"] for c in profiles_example["creates"]}
        assert {"Profile", "DefaultAssignmentSet", "Modifier"} <= kinds

    def test_examples_can_be_sampled(self, plan):
        preview = plan.preview(examples=2, sample=True, seed=26)
        assert (
            len([e for e in preview["examples"] if e["source"]["sheet"] == "weapons"])
            == 2
        )

    def test_the_preview_is_plain_data(self, plan):
        # JSON round-trips: the preview is a structure, not objects.
        parsed = json.loads(json.dumps(plan.preview()))
        assert parsed["counts"] == plan.preview()["counts"]

    def test_notes_are_said_but_do_not_block(self, plan):
        preview = plan.preview()
        notes = [p for p in preview["problems"] if p["severity"] == "note"]
        assert any("maximum one per gang" in n["message"] for n in notes)
        assert preview["ok"] is True


# --- Problems: what the plan refuses ------------------------------------------


class TestProblems:
    def test_an_unknown_weapon_on_a_list_is_a_problem_not_a_weapon(self, foundation):
        plan = plan_ingest(
            equipment_lists=read_csv(
                """
Gang,Type,Subtype,Name,Credits,Restrictions
Escher,Ranged,Web,Web pisol,90,
"""
            )
        )
        assert not plan.ok
        assert "Web pisol" in plan.problems[0].message
        assert plan.get("Weapon:web pisol") is None
        with pytest.raises(ValueError, match="Web pisol"):
            perform(plan)

    def test_a_priced_first_profile_is_refused(self, foundation):
        plan = plan_ingest(
            weapons=read_csv(
                """
Gang,Type,Subtype,Name,SR,LR,Str,AP,L,Traits,Credits,TP
Cawdor,Close Combat,Lances,Frag lance,,,,,,,35,E
Cawdor,Close Combat,Lances,- primed,E,-,4,-1,1,Melee,45,
"""
            )
        )
        assert not plan.ok
        assert "mandatory and free" in plan.problems[0].message

    def test_an_unresolvable_built_in_is_a_problem(self, foundation):
        plan = plan_ingest(
            profiles=read_csv(
                """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Escher,Wyld Runner,6",4+,4+,3,3,1,4,1,6+,6,7,7,6,Fighter,Prospect,4,25,,,Exo-suit,Agility,
"""
            )
        )
        assert not plan.ok
        assert "resolve, never create" in plan.problems[0].message

    def test_two_rules_sharing_a_name_hit_the_5d_wall(self, foundation):
        plan = plan_ingest(
            profiles=read_csv(
                """
Gang,Name,M,WS,BS,S,T,W,I,A,Sv,Ld,Cl,Wil,Int,Type,Subtype(s),Starting XP,Rating,Special Rules,Default skills,Default assignment,Primary Skill Sets,Secondary Skill Sets
Delaque,Piscean Spektor,5",4+,5+,3,3,2,4,2,5+,7,7,7,7,Fighter,"Beast, Pet",,110,"Leash (3"")",,,,
Delaque,Psychoteric Wyrm,4",4+,6+,3,3,2,3,1,6+,7,7,7,7,Fighter,"Beast, Pet",,50,"Leash (6"")",,,,
"""
            )
        )
        assert not plan.ok
        assert "§5d" in plan.problems[0].message

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
        goliath_list = Collection.objects.get(name="Goliath equipment list")
        entry = CollectionEntry.objects.get(collection=goliath_list, wargear=respirator)
        assert entry.price_override == 20
        assert entry.price.credits == 20

        escher_list = Collection.objects.get(name="Escher equipment list")
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
        category = Category.objects.get(name="Auto/stub")
        assert category.section.name == "Ranged"

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
