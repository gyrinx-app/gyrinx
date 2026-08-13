"""Four printed cards, represented end to end — the four-card challenge.

The challenge: prove the system can represent four real rulebook
profiles, exactly as the book prints them. Each one leans on
a different corner of the machinery:

* **Van Saar Ash Wastes 'Arachni-Rig'** — a vehicle; an any-of option
  group ("may select any of the below"); each gun knocking a point off
  Attacks via a ``Hidden`` carrier, stacking when both are taken.
* **Enforcer 'Sanctioner' Pattern Automata** — three sets summing: a
  one-of melee group (replace claw and/or baton with one pick), and an
  any-of group of extra grenade types that are **weapon profiles**
  stacking onto the launcher array from the built-ins.
* **Ironhead Squat Vartijan Exo-Driller** — a granted skill and a named
  ``Rule`` side by side (the book prints them apart), plus a plain
  weapon swap.
* **Goliath 'Zerker** — two subtypes, a fists swap, an any-of stash.

Everything below is content authoring plus assertions — no special
casing anywhere. Rule names only, never rules text (CLAUDE.md).
"""

import pytest

from n26.core.card import build_card, build_card_from_profile, build_modifier_index
from n26.core.effects import compute
from n26.core.hire import build_hire_entry, build_hire_list
from n26.core.render import build_model_card, card_to_model_card
from n26.library.models import Profile, ProfileType, StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    changes_stat,
    create_default_set,
    create_hidden,
    create_option_group,
    create_rule,
    create_skill,
    create_wargear,
    create_weapon,
    found_gang,
    hire_with_option,
    offer_option,
    set_statline,
)

pytestmark = pytest.mark.django_db


# --- The printed statlines -------------------------------------------------
#
# Both cards print the same thirteen columns; Fighter and Vehicle are still
# two StatlineTypes because the *shape* belongs to the profile type — pack
# data, not code.

STAT_DEFINITIONS = [
    ("M", "Movement", {"is_inches": True}),
    ("WS", "Weapon Skill", {"is_target": True, "is_inverted": True}),
    ("BS", "Ballistic Skill", {"is_target": True, "is_inverted": True}),
    ("S", "Strength", {}),
    ("T", "Toughness", {}),
    ("W", "Wounds", {}),
    ("I", "Initiative", {}),
    ("A", "Attacks", {}),
    ("Sv", "Save", {"is_target": True, "is_inverted": True}),
    ("Ld", "Leadership", {"is_highlighted": True, "is_first_of_group": True}),
    ("Cl", "Cool", {"is_highlighted": True}),
    ("Wil", "Willpower", {"is_highlighted": True}),
    ("Int", "Intelligence", {"is_highlighted": True}),
]


@pytest.fixture
def stats(make_stat):
    made = {}
    for short, full, flags in STAT_DEFINITIONS:
        row_flags = {
            k: v
            for k, v in flags.items()
            if k in ("is_inches", "is_target", "is_inverted")
        }
        made[short] = make_stat(short, full, **row_flags)
    return made


def _statline_type(name, stats):
    statline_type = StatlineType.objects.create(name=name)
    for position, (short, _, flags) in enumerate(STAT_DEFINITIONS):
        StatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=stats[short],
            position=position,
            is_highlighted=flags.get("is_highlighted", False),
            is_first_of_group=flags.get("is_first_of_group", False),
        )
    return statline_type


@pytest.fixture
def fighter_type(stats, default_pack):
    return ProfileType.objects.create(
        name="Fighter", statline_type=_statline_type("Fighter statline", stats)
    )


@pytest.fixture
def vehicle_type(stats, default_pack):
    return ProfileType.objects.create(
        name="Vehicle", statline_type=_statline_type("Vehicle statline", stats)
    )


@pytest.fixture
def gang(gang_type):
    from django.contrib.auth.models import User

    return found_gang(
        "The Showcase",
        gang_type,
        owner=User.objects.create_user("tom"),
        budget=2000,
    )


def full_card(miniature):
    """A hired model's card with its computed effects folded in."""
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def preview(profile, option=None):
    card = build_card_from_profile(profile, option=option)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return card_to_model_card(card, computed=compute(card, index), name=profile.name)


def weapon_names(card):
    return [w.name for w in card.weapons]


def ammo_names(weapon_line):
    """Profile names without the weapon-name annotation each carries."""
    return [p.name.split(" (")[0] for p in weapon_line.profiles]


def _subtype(name):
    """Brute appears on three of the four cards; subtypes are unique rows."""
    from n26.library.models import Subtype

    return Subtype.objects.get_or_create(name=name)[0]


# --- Van Saar Ash Wastes 'Arachni-Rig' — 275 credits -----------------------


@pytest.fixture
def arachni_rig(vehicle_type, gang_type, default_pack):
    profile = Profile.objects.create(
        name="Van Saar Ash Wastes 'Arachni-Rig'",
        profile_type=vehicle_type,
        gang_type=gang_type,
        price=275,
    )
    set_statline(
        profile,
        movement=5,
        weapon_skill=4,
        ballistic_skill=4,
        strength=5,
        toughness=4,
        wounds=4,
        initiative=3,
        attacks=4,
        save=4,
        leadership=7,
        cool=7,
        willpower=6,
        intelligence=7,
    )
    profile.built_ins = create_default_set(
        "Arachni-Rig built-ins",
        members=[
            _subtype("Flying"),
            _subtype("Walker"),
            create_weapon("Twin-linked heavy las carbine", profiles=[("Standard", 0)]),
            create_weapon("Servo-arm array", profiles=[("Strike", 0)]),
        ],
    )
    profile.save()

    # The asterisked footnote as data: taking a gun costs an Attack. The
    # carrier is Hidden — no card row, no shop will ever sweep it in — but
    # the shifted Attacks cell names it, so nothing it does is secret.
    attacks = profile.statline_type.stats.get(stat__short_name="A").stat
    conversion = create_hidden(
        "Hardpoint conversion",
        effects=[(_targets_model(), changes_stat(attacks, "worsen", 1))],
    )

    # "It may select any of the below options" — one any-of set; taking
    # both is two sets, two conversions, minus two Attacks.
    hardpoints = create_option_group(profile, "Weapon hardpoints", choose="any")
    for position, (name, cost) in enumerate([("Rad gun", 35), ("Plasma gun", 75)]):
        offer_option(
            profile,
            name,
            default_set=create_default_set(
                name,
                members=[create_weapon(name, profiles=[("Standard", 0)]), conversion],
                price=cost,
            ),
            group=hardpoints,
            position=position,
        )
    return profile


def _targets_model():
    from n26.library.models import TargetsMiniature

    return TargetsMiniature.objects.create()


def _sets_of(profile, *names):
    return [profile.options.get(default_set__name=name).default_set for name in names]


class TestTheArachniRig:
    def test_the_card_as_printed(self, gang, arachni_rig):
        rig = hire_with_option(gang, arachni_rig, "Rig One")
        card = full_card(rig)

        assert card.rating == 275
        assert card.type_line == "Vehicle (Flying, Walker)"
        assert weapon_names(card) == [
            "Servo-arm array",
            "Twin-linked heavy las carbine",
        ]
        assert card.statline.get("M").value == '5"'
        assert card.statline.get("Sv").value == "4+"
        assert card.statline.get("A").value == "4"

    def test_one_gun_costs_35_credits_and_one_attack(self, gang, arachni_rig):
        selection = _sets_of(arachni_rig, "Rad gun")
        rig = hire_with_option(gang, arachni_rig, "Rig Two", option=selection)
        card = full_card(rig)

        assert card.rating == 310
        assert "Rad gun" in weapon_names(card)
        attacks = card.statline.get("A")
        assert attacks.value == "3"
        (source,) = attacks.modified_by
        assert source.source == "Hardpoint conversion"
        # A hidden carrier's name is written to be read; its kind is the
        # library's plumbing, and a player's tooltip never says it.
        assert source.source_kind == ""

    def test_both_guns_stack_to_minus_two(self, gang, arachni_rig):
        selection = _sets_of(arachni_rig, "Rad gun", "Plasma gun")
        rig = hire_with_option(gang, arachni_rig, "Rig Three", option=selection)
        card = full_card(rig)

        assert card.rating == 275 + 35 + 75
        assert card.statline.get("A").value == "2"
        assert [p.source for p in card.statline.get("A").modified_by] == [
            "Hardpoint conversion",
            "Hardpoint conversion",
        ]

    def test_the_carrier_draws_no_row(self, gang, arachni_rig):
        selection = _sets_of(arachni_rig, "Rad gun")
        rig = hire_with_option(gang, arachni_rig, "Rig Four", option=selection)
        card = full_card(rig)

        drawn = [
            line.name
            for bucket in (card.equipment, card.skills, card.rules, card.subtypes)
            for line in bucket
        ] + weapon_names(card)
        assert "Hardpoint conversion" not in drawn

    def test_the_preview_promises_the_same_rig(self, gang, arachni_rig):
        selection = _sets_of(arachni_rig, "Rad gun", "Plasma gun")

        promised = preview(arachni_rig, option=selection)
        rig = hire_with_option(gang, arachni_rig, "Rig Five", option=selection)
        delivered = full_card(rig)

        assert promised.rating == delivered.rating
        assert weapon_names(promised) == weapon_names(delivered)
        assert promised.statline.get("A").value == delivered.statline.get("A").value


# --- Enforcer 'Sanctioner' Pattern Automata — 235 credits -------------------


@pytest.fixture
def sanctioner(fighter_type, gang_type, default_pack):
    profile = Profile.objects.create(
        name="Enforcer 'Sanctioner' Pattern Automata",
        profile_type=fighter_type,
        gang_type=gang_type,
        price=235,
    )
    set_statline(
        profile,
        movement=5,
        weapon_skill=4,
        ballistic_skill=4,
        strength=4,
        toughness=5,
        wounds=3,
        initiative=3,
        attacks=2,
        save=4,
        leadership=7,
        cool=7,
        willpower=7,
        intelligence=7,
    )

    # The launcher array arrives with smoke; choke and stun exist as its
    # further, priced ammo types — exactly the rows a mid-campaign
    # ``buy_weapon_profile`` would use.
    launcher = create_weapon(
        "Grenade launcher array",
        profiles=[
            ("Smoke grenades", 0),
            ("Choke gas grenades", 50),
            ("Stun grenades", 15),
        ],
    )
    claw = create_weapon("Pacifier assault claw", profiles=[("Strike", 0)])
    baton = create_weapon("Heavy shock baton", profiles=[("Strike", 0)])
    replacements = {
        "Concussion cannon": (
            create_weapon("Concussion cannon", profiles=[("Blast", 0)]),
            25,
        ),
        "Sanction pattern man-catcher": (
            create_weapon("Sanction pattern man-catcher", profiles=[("Grab", 0)]),
            10,
        ),
        "SLHG pattern assault ram": (
            create_weapon(
                "SLHG pattern assault ram 'sledge hammer'",
                profiles=[
                    ("Ram", 0),
                    ("Auxiliary launcher: choke gas", 0),
                    ("Auxiliary launcher: frag", 0),
                ],
            ),
            80,
        ),
    }

    profile.built_ins = create_default_set(
        "Sanctioner built-ins",
        members=[
            _subtype("Brute"),
            create_rule("Automated Repair Systems"),
            create_rule("Mobile Bulwark"),
            launcher,
        ],
    )
    profile.save()

    # The melee set: "replace their pacifier assault claw and/or heavy
    # shock baton with ONE of the following" — a one-of, so its states are
    # enumerated: keep both, or drop either or both for the one pick.
    # Ten sets, not forty: the grenade picks below multiply outside it.
    position = iter(range(100))
    offer_option(
        profile,
        "Claw and baton",
        default_set=create_default_set("Claw and baton", members=[claw, baton]),
        position=next(position),
    )
    for name, (weapon, price) in replacements.items():
        for kept, kept_name in [
            ((baton,), "keeps baton"),
            ((claw,), "keeps claw"),
            ((), "replaces both"),
        ]:
            offer_option(
                profile,
                f"{name} ({kept_name})",
                default_set=create_default_set(
                    f"{name} ({kept_name})", members=[weapon, *kept], price=price
                ),
                position=next(position),
            )

    # The additional grenade types: an any-of set whose members are
    # weapon profiles, stacking onto the array the built-ins bring.
    grenades = create_option_group(
        profile, "Additional grenade types", choose="any", position=1
    )
    for position, name in enumerate(["Choke gas grenades", "Stun grenades"]):
        ammo = launcher.profiles.get(name=name)
        offer_option(
            profile,
            name,
            default_set=create_default_set(name, members=[ammo], price=ammo.price),
            group=grenades,
            position=position,
        )
    return profile


class TestTheSanctioner:
    def test_the_card_as_printed(self, gang, sanctioner):
        automata = hire_with_option(gang, sanctioner, "Unit 10919")
        card = full_card(automata)

        assert card.rating == 235
        assert card.type_line == "Fighter (Brute)"
        assert [r.name for r in card.rules] == [
            "Automated Repair Systems",
            "Mobile Bulwark",
        ]
        assert weapon_names(card) == [
            "Grenade launcher array",
            "Heavy shock baton",
            "Pacifier assault claw",
        ]
        launcher = next(w for w in card.weapons if w.name == "Grenade launcher array")
        assert ammo_names(launcher) == ["Smoke grenades"]

    def test_the_sets_sum_instead_of_multiplying(self, sanctioner):
        # Ten melee states plus two grenade toggles: twelve authored sets
        # where flat one-of combinations would need forty.
        assert sanctioner.options.count() == 12
        groups = sanctioner.grouped_options()
        assert [(g.name if g else None, len(sets)) for g, sets in groups] == [
            (None, 10),
            ("Additional grenade types", 2),
        ]

    def test_a_fully_loaded_sanctioner(self, gang, sanctioner):
        selection = _sets_of(
            sanctioner,
            "Concussion cannon (keeps baton)",
            "Choke gas grenades",
            "Stun grenades",
        )
        automata = hire_with_option(gang, sanctioner, "Unit 5", option=selection)
        card = full_card(automata)

        assert card.rating == 235 + 25 + 50 + 15
        assert weapon_names(card) == [
            "Concussion cannon",
            "Grenade launcher array",
            "Heavy shock baton",
        ]
        launcher = next(w for w in card.weapons if w.name == "Grenade launcher array")
        assert ammo_names(launcher) == [
            "Smoke grenades",
            "Choke gas grenades",
            "Stun grenades",
        ]
        # The ammo says it came with the array, like the free profile does.
        choke = next(
            p for p in launcher.profiles if p.name.startswith("Choke gas grenades")
        )
        assert choke.provenance.source == "Grenade launcher array"
        assert [
            c.default_set.name for c in automata.membership.chosen_options.all()
        ] == [
            "Concussion cannon (keeps baton)",
            "Choke gas grenades",
            "Stun grenades",
        ]

    def test_the_preview_promises_the_same_automata(self, gang, sanctioner):
        selection = _sets_of(
            sanctioner, "SLHG pattern assault ram (replaces both)", "Stun grenades"
        )

        promised = preview(sanctioner, option=selection)
        automata = hire_with_option(gang, sanctioner, "Unit 6", option=selection)
        delivered = full_card(automata)

        assert promised.rating == delivered.rating == 235 + 80 + 15
        assert weapon_names(promised) == weapon_names(delivered)
        promised_launcher = next(
            w for w in promised.weapons if w.name == "Grenade launcher array"
        )
        delivered_launcher = next(
            w for w in delivered.weapons if w.name == "Grenade launcher array"
        )
        assert [p.name for p in promised_launcher.profiles] == [
            p.name for p in delivered_launcher.profiles
        ]

    def test_naming_two_melee_states_is_refused(self, gang, sanctioner):
        selection = _sets_of(
            sanctioner,
            "Concussion cannon (keeps baton)",
            "Sanction pattern man-catcher (keeps claw)",
        )
        with pytest.raises(ValueError, match="at most one"):
            hire_with_option(gang, sanctioner, "Unit 7", option=selection)


# --- Ironhead Squat Vartijan Exo-Driller — 280 credits ----------------------


@pytest.fixture
def exo_driller(fighter_type, gang_type, default_pack):
    profile = Profile.objects.create(
        name="Ironhead Squat Vartijan Exo-Driller",
        profile_type=fighter_type,
        gang_type=gang_type,
        price=280,
    )
    set_statline(
        profile,
        movement=4,
        weapon_skill=4,
        ballistic_skill=3,
        strength=4,
        toughness=5,
        wounds=3,
        initiative=3,
        attacks=2,
        save=4,
        leadership=7,
        cool=7,
        willpower=6,
        intelligence=6,
    )
    profile.built_ins = create_default_set(
        "Exo-Driller built-ins",
        members=[
            _subtype("Brute"),
            create_rule("Sensor Suite"),
            create_skill("Bulging Biceps"),
            create_weapon("Power fist", profiles=[("Strike", 0)]),
            create_weapon("Seismic crusher", profiles=[("Crush", 0)]),
        ],
    )
    profile.save()
    offer_option(
        profile,
        "Heavy flamer",
        default_set=create_default_set(
            "Heavy flamer",
            members=[create_weapon("Heavy flamer", profiles=[("Flame", 0)])],
        ),
        position=0,
    )
    offer_option(
        profile,
        "Heavy bolter",
        default_set=create_default_set(
            "Heavy bolter",
            members=[create_weapon("Heavy bolter", profiles=[("Burst", 0)])],
            price=10,
        ),
        position=1,
    )
    return profile


class TestTheExoDriller:
    def test_the_card_as_printed(self, gang, exo_driller):
        driller = hire_with_option(gang, exo_driller, "Old Reliable")
        card = full_card(driller)

        assert card.rating == 280
        assert card.type_line == "Fighter (Brute)"
        # The book prints Skills and the named rule apart; so does the card.
        assert [s.name for s in card.skills] == ["Bulging Biceps"]
        assert [r.name for r in card.rules] == ["Sensor Suite"]
        assert weapon_names(card) == [
            "Heavy flamer",
            "Power fist",
            "Seismic crusher",
        ]

    def test_the_heavy_bolter_swap(self, gang, exo_driller):
        selection = _sets_of(exo_driller, "Heavy bolter")
        driller = hire_with_option(gang, exo_driller, "Loud Reliable", option=selection)
        card = full_card(driller)

        assert card.rating == 290
        assert "Heavy bolter" in weapon_names(card)
        assert "Heavy flamer" not in weapon_names(card)


# --- Goliath 'Zerker — 175 credits ------------------------------------------


@pytest.fixture
def zerker(fighter_type, gang_type, default_pack):
    profile = Profile.objects.create(
        name="Goliath 'Zerker",
        profile_type=fighter_type,
        gang_type=gang_type,
        price=175,
    )
    set_statline(
        profile,
        movement=4,
        weapon_skill=3,
        ballistic_skill=6,
        strength=6,
        toughness=5,
        wounds=4,
        initiative=2,
        attacks=3,
        save=6,
        leadership=6,
        cool=7,
        willpower=6,
        intelligence=4,
    )
    profile.built_ins = create_default_set(
        "'Zerker built-ins",
        members=[
            _subtype("Brute"),
            _subtype("Loner"),
            create_rule("Combat Chems Stash"),
        ],
    )
    profile.save()
    offer_option(
        profile,
        "Open fists",
        default_set=create_default_set(
            "Open fists",
            members=[create_weapon("Open fists", profiles=[("Pummel", 0)])],
        ),
        position=0,
    )
    offer_option(
        profile,
        "Mutated fists & bone spurs",
        default_set=create_default_set(
            "Mutated fists & bone spurs",
            members=[
                create_weapon("Mutated fists & bone spurs", profiles=[("Gouge", 0)])
            ],
            price=45,
        ),
        position=1,
    )
    stash = create_option_group(profile, "Stimm-slug stash", choose="any", position=1)
    offer_option(
        profile,
        "Stimm-slug stash",
        default_set=create_default_set(
            "Stimm-slug stash", members=[create_wargear("Stimm-slug stash")], price=25
        ),
        group=stash,
    )
    return profile


class TestTheZerker:
    def test_the_card_as_printed(self, gang, zerker):
        brute = hire_with_option(gang, zerker, "Grendel")
        card = full_card(brute)

        assert card.rating == 175
        assert card.type_line == "Fighter (Brute, Loner)"
        assert [r.name for r in card.rules] == ["Combat Chems Stash"]
        assert weapon_names(card) == ["Open fists"]
        assert card.statline.get("BS").value == "6+"
        assert card.statline.get("Sv").value == "6+"

    def test_everything_selected(self, gang, zerker):
        selection = _sets_of(zerker, "Mutated fists & bone spurs", "Stimm-slug stash")
        brute = hire_with_option(gang, zerker, "Grendel's Mother", option=selection)
        card = full_card(brute)

        assert card.rating == 175 + 45 + 25
        assert weapon_names(card) == ["Mutated fists & bone spurs"]
        assert [e.name for e in card.equipment] == ["Stimm-slug stash"]


# --- The whole zoo on one hire screen ---------------------------------------


class TestTheHireScreen:
    @pytest.fixture
    def roster(self, gang_type, arachni_rig, sanctioner, exo_driller, zerker):
        return gang_type

    def test_every_card_is_offered_with_its_sets(self, roster):
        entries = build_hire_list(roster)
        by_name = {entry.name: entry for entry in entries}

        rig = by_name["Van Saar Ash Wastes 'Arachni-Rig'"]
        assert rig.base_price == 275
        # Two sets: the main pick, then the hardpoints. What the
        # author calls the second one is not here to be asserted on —
        # a player is shown the answers, never the question.
        assert [g.choose for g in rig.groups] == ["one", "any"]
        assert [o.name for o in rig.groups[1].options] == ["Rad gun", "Plasma gun"]

        automata = by_name["Enforcer 'Sanctioner' Pattern Automata"]
        assert automata.base_price == 235
        assert [len(g.options) for g in automata.groups] == [10, 2]

    def test_each_option_card_shows_that_option_taken(self, roster):
        entry = build_hire_entry(
            Profile.objects.get(name="Van Saar Ash Wastes 'Arachni-Rig'")
        )
        rad_gun = next(o for o in entry.groups[1].options if o.name == "Rad gun")
        assert rad_gun.total_price == 310
        assert rad_gun.card.statline.get("A").value == "3"
        assert entry.default_option.card.statline.get("A").value == "4"

    def test_the_whole_zoo_costs_a_fixed_number_of_queries(self, roster, gang_type):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert build_hire_list(gang_type)
            return len(captured.captured_queries)

        few = measure()
        # Double the roster: clone the 'Zerker three times.
        zerker = Profile.objects.get(name="Goliath 'Zerker")
        for index in range(3):
            clone = Profile.objects.create(
                name=f"Goliath 'Zerker {index}",
                profile_type=zerker.profile_type,
                gang_type=gang_type,
                price=175,
                built_ins=zerker.built_ins,
            )
            for option in zerker.options.all():
                group = (
                    create_option_group(
                        clone, option.group.name, choose=option.group.choose
                    )
                    if option.group
                    else None
                )
                offer_option(
                    clone,
                    option.name,
                    default_set=option.default_set,
                    position=option.position,
                    group=group,
                )

        assert len(build_hire_list(gang_type)) == 7
        assert measure() == few


# --- A squad, printed --------------------------------------------------------


class TestTheSquadOnPaper:
    """A living demo: the same two profiles, equipped four different ways,
    with the gang sheet and the ledger printed side by side. Run it to
    look at it:

        uv run pytest tests/sandbox/test_screenshot_profiles.py -s -k Squad
    """

    def test_it_all_renders(self, gang, arachni_rig, sanctioner):
        from n26.core.reconcile import assert_reconciled
        from n26.core.render_text import gang_to_text, ledger_to_text

        hire_with_option(gang, arachni_rig, "Spinneret")
        hire_with_option(
            gang,
            arachni_rig,
            "Widowmaker",
            option=_sets_of(arachni_rig, "Rad gun", "Plasma gun"),
        )
        hire_with_option(gang, sanctioner, "Unit Primus")
        hire_with_option(
            gang,
            sanctioner,
            "Unit Secundus",
            option=_sets_of(
                sanctioner,
                "SLHG pattern assault ram (replaces both)",
                "Choke gas grenades",
                "Stun grenades",
            ),
        )

        sheet = gang_to_text(gang)
        ledger = ledger_to_text(gang)
        print("\n" + sheet)
        print(ledger)

        # The two rigs differ only in what was chosen, and it shows.
        assert "Spinneret — 275cr" in sheet
        assert "Widowmaker — 385cr" in sheet
        assert "Unit Primus — 235cr" in sheet
        assert "Unit Secundus — 380cr" in sheet
        # Everything the ledger says still adds up.
        assert_reconciled(gang)
