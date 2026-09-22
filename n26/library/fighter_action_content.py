"""Standard progression content supplied by Foundations.

The recipes name rulebook content. The installer resolves their targets and
creates ordinary grants; runtime progression reads the resulting content.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BindingRecipe:
    key: str
    kind: str
    preview_rule: str
    scope_label: str
    filters: dict = field(default_factory=dict)
    exclusions: tuple = ()
    subtypes: tuple = ()
    opening_counters: tuple = ()


BINDINGS = (
    BindingRecipe(
        key="profiles",
        kind="profile",
        preview_rule="Fighter progression",
        scope_label="Models using this profile",
        exclusions=(
            ({"category__section__name__iexact": "Allies"}, "Alliance delegation"),
            ({"category__section__name__iexact": "Dramatis Personae"}, "Hired gun"),
            ({"category__name__iexact": "Hired Guns"}, "Hired gun"),
            ({"category__name__iexact": "Hired Gun"}, "Hired gun"),
        ),
        opening_counters=(("XP", 0),),
    ),
    BindingRecipe(
        key="outcast-leaders",
        kind="gang-type",
        preview_rule="Outcast leader progression",
        scope_label="Leaders in this gang",
        filters={"name__iexact": "Outcast"},
        subtypes=("Leader",),
    ),
)

SPECIALISATIONS = (
    ("Heavy", "Bulging Biceps"),
    ("Gunner", "Hip-shooting"),
    ("Gunslinger", "Gunfighter"),
    ("Scout", "Clamber"),
    ("Sniper", "Precision Shot"),
    ("Brawler", "Berserker"),
    ("Medic", "Medicate"),
    ("Tech", "Munitioneer"),
)


@dataclass(frozen=True)
class PromotionResult:
    name: str
    adds: tuple
    removes: tuple
    skill: str
    rating: int = 0
    choice_name: str = ""


@dataclass(frozen=True)
class PromotionRecipe:
    name: str
    from_subtype: str
    threshold: int
    replaces_advancement: bool
    results: tuple
    optional_profiles: tuple = ()
    stash_weapons_for: tuple = ()
    keep_weapon_trait: str = ""
    suppress_slots: tuple = ()
    choice_type: str = ""
    exclude_from_offers: tuple = ()


INITIATES = (
    {"name__iexact": "Initiate", "gang_type__name__iexact": "Corpse Grinder Cults"},
    {"name__iexact": "Initiate", "gang_type__name__iexact": "Corpse Grinder Cult"},
    {"name__iexact": "Initiate", "gang_type__name__iexact": "Corpse Grinders"},
)

PROMOTIONS = (
    PromotionRecipe(
        name="Prospect promotion",
        from_subtype="Prospect",
        threshold=13,
        replaces_advancement=True,
        results=tuple(
            PromotionResult(
                f"Ganger specialist: {label}",
                ("Ganger", "Specialist"),
                ("Prospect",),
                skill,
                15,
                choice_name=label,
            )
            for label, skill in SPECIALISATIONS
        ),
        optional_profiles=INITIATES,
        stash_weapons_for=INITIATES,
        keep_weapon_trait="Melee",
        suppress_slots=({"name__iexact": "Specialisation", "qualifier": ""},),
        choice_type="Specialisation",
    ),
    PromotionRecipe(
        name="Ganger promotion",
        from_subtype="Ganger",
        threshold=37,
        replaces_advancement=False,
        exclude_from_offers=("Offer Primary Skill to Leader/Champion",),
        results=(
            PromotionResult(
                "Champion promotion", ("Champion",), ("Ganger",), "Inspiring"
            ),
        ),
    ),
)
