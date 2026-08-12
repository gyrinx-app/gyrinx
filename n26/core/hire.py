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
from n26.core.taxonomy import UNCATEGORISED, group_by_home

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
    #: None when the caller asked for a list without drawn cards — a
    #: page that fetches each card on demand instead of shipping every
    #: one. ``preview_model_card`` is the single card such a page serves.
    card: ModelCard | None
    #: None when the profile offers no alternatives and this is the
    #: synthesised standard one.
    default_set: object = None
    #: Where a drawn card for exactly this option can be fetched, when
    #: the surface serves them on demand. A display address, so the view
    #: that knows its URLs fills it in; empty means the card is inline.
    card_url: str = ""


@dataclass
class HireGroup:
    """One set of the options a profile offers.

    ``choose`` is "one" (radio: exactly one, the default marked) or
    "any" (checkboxes: take any number, none by default).

    A set has no name here, deliberately. The one the content carries
    is the author's label for their own page — a player is shown the
    options, and a heading naming the set would be a second vocabulary
    they never agreed to. What a reader needs is that these options go
    together, which is the grouping itself.
    """

    choose: str
    options: list[HireOption] = field(default_factory=list)

    @property
    def offers_a_choice(self):
        """Whether this set is worth putting in front of anyone.

        A pick-one set with a single option is not a choice: the head
        is taken unasked and there is nothing else to pick. An any-of
        or one-or-none set with one option is — taking it or not is
        the choice.
        """
        return len(self.options) > 1 or self.choose != "one"


@dataclass
class HireEntry:
    """One profile a player could hire, with every set of its options."""

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
        """The default group's options — the set every profile has."""
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


@dataclass
class HireCategory:
    """One category heading and the entries filed under it.

    An empty name means the content filed nothing here, and the entries
    sit straight inside the section.
    """

    name: str
    entries: list[HireEntry] = field(default_factory=list)


@dataclass
class HireSection:
    """One section heading and its categories."""

    name: str
    categories: list[HireCategory] = field(default_factory=list)

    def all_entries(self):
        for category in self.categories:
            yield from category.entries


def build_hire_entry(profile, index=None, with_cards=True):
    """Every set of this profile's options, each with the card you'd get.

    Pass ``index`` to share one modifier index across a whole list; without
    one it is built here, for a single entry.

    ``with_cards=False`` prices the options without drawing their cards —
    the internal cards are still built, because an option's total is its
    card's rating, but nothing runs the effects engine or shapes a
    ``ModelCard`` for a card the caller will not show. A surface that
    serves cards on demand asks ``preview_model_card`` for each instead.
    """
    grouped = profile.grouped_offers()
    if not grouped or grouped[0][0] is not None:
        # Every entry has the default group, options or not.
        grouped = [(None, [])] + grouped

    cards = {None: build_card_from_profile(profile)}
    for _, options in grouped:
        for option in options:
            cards[option.default_set.pk] = build_card_from_profile(
                profile, option=option.default_set
            )

    if with_cards and index is None:
        index = build_modifier_index(
            [node.assignable for card in cards.values() for node in card.all_nodes()]
        )

    def drawn(card):
        if not with_cards:
            return None
        return card_to_model_card(
            card, computed=compute(card, index), name=profile.name
        )

    groups = []
    for group, offered in grouped:
        one_of = group is None or group.choose == "one"
        options = [
            HireOption(
                name=option.name,
                price=option.default_set.price,
                total_price=cards[option.default_set.pk].full_rating,
                is_default=(one_of and position == 0),
                default_set=option.default_set,
                card=drawn(cards[option.default_set.pk]),
            )
            for position, option in enumerate(offered)
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
                choose=group.choose if group is not None else "one",
                options=options,
            )
        )
    return HireEntry(profile=profile, groups=groups)


def build_hire_list(gang_type, with_cards=True):
    """Every profile a gang of this type could hire — the whole screen.

    A fixed number of queries however many profiles there are: the content
    is fetched in one pass, one modifier index covers every card, and the
    cards themselves are assembled in memory.
    """
    return build_entries(list(hireable_profiles(gang_type)), with_cards=with_cards)


def build_entries(profiles, with_cards=True):
    """Hire entries for profiles already fetched — the shared build.

    The scopes differ only in which profiles they fetch; everything
    after the fetch is this."""
    index = None
    if with_cards:
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
    return [
        build_hire_entry(profile, index=index, with_cards=with_cards)
        for profile in profiles
    ]


def preview_model_card(profile, option=None):
    """The drawn card one option's row shows — built alone.

    The single card a hire page serves on demand, and the same
    derivation ``build_hire_entry`` draws inline: the card an option
    would produce, its effects computed, shaped for a renderer.
    """
    card = build_card_from_profile(profile, option=option)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return card_to_model_card(card, computed=compute(card, index), name=profile.name)


def section_hire_list(entries):
    """The hire list in sections of categories — the picker's shape.

    Grouped by each profile's home category, the taxonomy's own way —
    the same derivation a browsed collection gets, so a heading means
    the same thing on both screens.

    The homeless section is named here rather than left blank, which is
    what tells this surface apart from a browse. The picker draws its
    sections as tabs, a tab needs a word on it, and a nameless one would
    cost that section every way of reaching its rows. The *category*
    stays unnamed: the content really did file nothing, and such rows
    sit straight inside the section.
    """

    def entry_order(entry):
        # Cheapest first within a category: a gang list is read to find
        # what this many credits will buy.
        return (entry.base_price, entry.name)

    return group_by_home(
        ((entry.profile.category, entry) for entry in entries),
        section=lambda heading, categories: HireSection(
            name=heading or UNCATEGORISED, categories=categories
        ),
        category=lambda heading, entries: HireCategory(name=heading, entries=entries),
        order=entry_order,
    )


def hireable_profiles(gang_type=None):
    """Hireable profiles with everything a preview card needs.

    ``gang_type`` narrows to one gang list; without it, every hireable
    profile in the library — the all-profiles scope.
    """
    from n26.library.models import Profile
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

    members = [f"members__{name}" for name in DEFAULT_ASSIGNABLE_FIELDS]
    weapon_extras = (
        "members__weapon__profiles__traits",
        "members__weapon__profiles__statline__stats__statline_type_stat__stat",
        "members__weapon_profile__traits",
        "members__weapon_profile__statline__stats__statline_type_stat__stat",
    )
    # A profile that is not hireable is not a secret — its card still
    # previews wherever it is granted — it just is not for sale here:
    # a pet arrives behind its collar, not off the hire screen.
    found = Profile.objects.filter(hireable=True)
    if gang_type is not None:
        found = found.filter(gang_type=gang_type)
    return (
        # category__section rides along for the section headings — without
        # it, grouping a listing costs two queries per profile. gang_type
        # for the all-profiles scope, whose sections are the gang types.
        found.select_related(
            "profile_type", "built_ins", "category__section", "gang_type"
        )
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


def supplementary_profiles():
    """The profiles every gang may hire, whichever gang type authored them.

    Being supplementary is a fact of the taxonomy: a profile whose home
    category sits under the supplementary section is on offer to every
    gang, and moving a profile in or out of the scope is an authoring
    act, never a code change.
    """
    from n26.library.standard_content import SUPPLEMENTARY_SECTION

    return hireable_profiles().filter(category__section__name=SUPPLEMENTARY_SECTION)


def section_by_gang_type(entries):
    """The hire list in sections of gang types — the all-profiles scope.

    Every gang list at once is found by whose list it is, so the
    sections are the gang types and the categories inside keep the
    taxonomy's own homes. Cheapest first within a category, as
    everywhere on this screen.
    """

    def entry_order(entry):
        return (entry.base_price, entry.name)

    by_type = {}
    for entry in entries:
        by_type.setdefault(entry.profile.gang_type, []).append(entry)

    sections = []
    for gang_type in sorted(by_type, key=lambda found: found.name.casefold()):
        homes = {}
        for entry in by_type[gang_type]:
            home = entry.profile.category
            key = (
                (0, home.section.position, home.position, home.name)
                if home is not None
                else (1, 0, 0, "")
            )
            homes.setdefault(key, []).append(entry)
        sections.append(
            HireSection(
                name=gang_type.name,
                categories=[
                    HireCategory(name=key[3], entries=sorted(rows, key=entry_order))
                    for key, rows in sorted(homes.items())
                ],
            )
        )
    return sections
