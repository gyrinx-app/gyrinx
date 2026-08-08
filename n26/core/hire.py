"""The hire view: what you would get, before you get it.

A gang sheet shows the models a player owns; a hire view shows the ones
they could buy. Both are lists of ``ModelCard`` — the same structure, from
the same renderer — because a preview is built by the same machinery that
builds a real card, just from library instead of stored rows.

That matters more than it sounds. The alternative is a second, parallel
"what you'd get" renderer, which drifts from the real card the first time
anyone changes either. Here they cannot drift: ``build_card_from_profile``
mirrors ``Operation.hire``, and a test asserts a preview card equals the
card of the model actually hired from it.

Options come grouped, so the view is *one card per option*, never one per
combination: each option's card shows that option taken against an
otherwise-default selection, and a specific combination's card is a
``build_card_from_profile(profile, option=[...])`` away. Enumerating the
combinations is exactly the explosion the groups exist to avoid.

Query budget, as everywhere: previewing a whole gang list is a fixed
number of queries whatever its length.
"""

from dataclasses import dataclass, field

from n26.core.card import build_card_from_profile, build_modifier_index
from n26.core.effects import compute
from n26.core.render import ModelCard, card_to_model_card

#: What an option is called when a profile offers no alternatives. Every
#: profile has at least one thing you can hire, so a UI always draws the
#: same shape rather than branching on whether choices exist.
STANDARD_OPTION_NAME = "As standard"


@dataclass
class HireOption:
    """One version of a fighter you could hire."""

    name: str
    #: What this option adds on its own — the surcharge, not the total.
    price: int
    #: What the hire costs with this option taken and all else default.
    total_price: int
    is_default: bool
    card: ModelCard
    #: None when the profile offers no alternatives and this is the
    #: synthesised standard one.
    default_set: object = None


@dataclass
class HireGroup:
    """One axis of the choice a profile offers.

    ``name`` is None for the default group — the plain options every
    profile may have. ``choose`` is "one" (radio: exactly one, the default
    marked) or "any" (checkboxes: take any number, none by default).
    """

    name: str | None
    choose: str
    options: list[HireOption] = field(default_factory=list)


@dataclass
class HireEntry:
    """One profile a player could hire, with every axis of the choice."""

    profile: object
    #: The default group first — never empty, "As standard" is synthesised
    #: when the profile offers no plain alternatives — then each named
    #: group in position order.
    groups: list[HireGroup] = field(default_factory=list)

    @property
    def name(self):
        return self.profile.name

    @property
    def profile_type(self):
        return self.profile.profile_type.name

    @property
    def options(self):
        """The default group's options — the axis every profile has."""
        return self.groups[0].options

    @property
    def base_price(self):
        """The advertised price — what the default selection costs."""
        return self.default_option.total_price

    @property
    def default_option(self):
        return next(option for option in self.options if option.is_default)

    @property
    def offers_a_choice(self):
        return len(self.options) > 1 or len(self.groups) > 1


def build_hire_entry(profile, index=None):
    """Every axis of this profile's hire, each option with the card you'd get.

    Pass ``index`` to share one modifier index across a whole list; without
    one it is built here, for a single entry.
    """
    grouped = profile.grouped_options()
    if not grouped or grouped[0][0] is not None:
        # Every entry has the default group, options or not.
        grouped = [(None, [])] + grouped

    cards = {None: build_card_from_profile(profile)}
    for _, sets in grouped:
        for default_set in sets:
            cards[default_set.pk] = build_card_from_profile(profile, option=default_set)

    if index is None:
        index = build_modifier_index(
            [node.assignable for card in cards.values() for node in card.all_nodes()]
        )

    def drawn(card):
        return card_to_model_card(
            card, computed=compute(card, index), name=profile.name
        )

    groups = []
    for group, sets in grouped:
        one_of = group is None or group.choose == "one"
        options = [
            HireOption(
                name=default_set.name,
                price=default_set.price,
                total_price=cards[default_set.pk].full_rating,
                is_default=(one_of and position == 0),
                default_set=default_set,
                card=drawn(cards[default_set.pk]),
            )
            for position, default_set in enumerate(sets)
        ]
        if group is None and not options:
            options = [
                HireOption(
                    name=STANDARD_OPTION_NAME,
                    price=0,
                    total_price=cards[None].full_rating,
                    is_default=True,
                    default_set=None,
                    card=drawn(cards[None]),
                )
            ]
        groups.append(
            HireGroup(
                name=group.name if group is not None else None,
                choose=group.choose if group is not None else "one",
                options=options,
            )
        )
    return HireEntry(profile=profile, groups=groups)


def build_hire_list(gang_type):
    """Every profile a gang of this type could hire — the whole screen.

    A fixed number of queries however many profiles there are: the content
    is fetched in one pass, one modifier index covers every card, and the
    cards themselves are assembled in memory.
    """
    profiles = list(hireable_profiles(gang_type))
    cards = []
    for profile in profiles:
        cards.append(build_card_from_profile(profile))
        for _, sets in profile.grouped_options():
            cards.extend(
                build_card_from_profile(profile, option=default_set)
                for default_set in sets
            )
    index = build_modifier_index(
        [node.assignable for card in cards for node in card.all_nodes()]
    )
    return [build_hire_entry(profile, index=index) for profile in profiles]


def shelve_hire_list(entries):
    """The hire list in sections of categories — the picker's shape.

    Groups by each profile's home category (``Section`` heading, then
    ``Category`` inside it), taxonomy order — the same derivation
    ``browse._sectioned`` does for collections. Profiles without a home
    gather at the end under empty headings: a content gap to show, not
    an error to hide.
    """

    def order(entry):
        category = entry.profile.category
        # Section, then category, then the entry — each level fully keyed,
        # so a category's entries stay contiguous and the grouping below
        # can work on runs.
        if category is None:
            return (1, 0, "", 0, "", entry.base_price, entry.name)
        return (
            0,
            category.section.position,
            category.section.name.lower(),
            category.position,
            category.name.lower(),
            entry.base_price,
            entry.name,
        )

    section_rows = []
    for entry in sorted(entries, key=order):
        category = entry.profile.category
        section_name = category.section.name if category else ""
        category_name = category.name if category else ""
        if not section_rows or section_rows[-1]["name"] != section_name:
            section_rows.append({"name": section_name, "categories": []})
        categories = section_rows[-1]["categories"]
        if not categories or categories[-1]["name"] != category_name:
            categories.append({"name": category_name, "entries": []})
        categories[-1]["entries"].append(entry)
    return section_rows


def hireable_profiles(gang_type):
    """The profiles of a gang type, with everything a preview card needs."""
    from n26.library.models import Profile
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

    members = [f"members__{name}" for name in DEFAULT_ASSIGNABLE_FIELDS]
    weapon_extras = (
        "members__weapon__profiles__traits",
        "members__weapon__profiles__statline__stats__statline_type_stat__stat",
        "members__weapon_profile__traits",
        "members__weapon_profile__statline__stats__statline_type_stat__stat",
    )
    return (
        Profile.objects.filter(gang_type=gang_type)
        # category__section rides along for the shelving — without it,
        # grouping a listing costs two queries per profile.
        .select_related("profile_type", "built_ins", "category__section")
        .prefetch_related(
            "statline__stats__statline_type_stat__stat",
            *(f"built_ins__{path}" for path in members),
            *(f"built_ins__{path}" for path in weapon_extras),
            "options__group",
            "options__default_set",
            *(f"options__default_set__{path}" for path in members),
            *(f"options__default_set__{path}" for path in weapon_extras),
        )
        .order_by("price", "name")
    )
