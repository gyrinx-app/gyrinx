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

Not every fighter on offer is on a gang list. A collection the gang
carries can list profiles too — a corruption's Aberrants and Chaos
Spawn arrive that way — and it offers them at its own prices. Such a
collection becomes a section of its own, built from the same entries by
the same functions, with the collection's price standing in for the
fighter's own (``Offer``, ``collection_offers``).

Query budget, as everywhere: previewing a whole gang list is a fixed
number of queries whatever its length, and so is a gang's carried
collections however many it carries.
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
    #: The collection entry that offered this row, where a collection did.
    #: Its price is the one the row quotes and the one the hire charges, so
    #: a click has to say which entry offered it — hence ``key``.
    entry: object = None
    #: Where a card for this row is fetched from before any option is
    #: named — what the offer is priced by, and nothing about the
    #: selection. A surface following every control adds the ticked
    #: options to it; empty means the row carries its cards inline.
    card_url: str = ""

    @property
    def name(self):
        return self.profile.name

    @property
    def key(self):
        """What a click submits to name this row — the profile, and the
        offer it was made under when a collection made it.

        A profile can be on this screen twice: once on the gang's own list
        at reference price and once in a carried collection at the
        collection's. The two rows are different offers of the same
        fighter, so the identity a click carries is both halves. Neither
        half is a price: the server looks the entry up and reads the
        price off it, the way an equip page's listing submits a line's
        identity.
        """
        if self.entry is None:
            return str(self.profile.pk)
        return f"{self.profile.pk}-{self.entry.pk}"

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


@dataclass(frozen=True)
class Offer:
    """One profile on the hire screen, and what put it there.

    A plain row of a gang's own list is an offer with no collection behind
    it. A collection the gang carries offers its own rows: the entry
    naming a profile prices it this collection's way, while a sweep
    ("every profile homed in Corrupted Beasts") offers it at reference
    like any listing.
    """

    profile: object
    #: The curated row that offered this, when one did. A swept profile
    #: has none, exactly as a swept line in a browse has none.
    entry: object = None
    #: Which collection is offering. None for the gang's own list, whose
    #: rows answer to no collection.
    collection: object = None

    @property
    def base(self):
        """The price this offer puts in place of the profile's own, if any.

        A blank override is an answer rather than a gap — it says "at the
        usual price" — so it falls through to the profile's own price, the
        same reading ``price_of`` gives every other listing.
        """
        return self.entry.price_override if self.entry is not None else None


def build_hire_entry(profile, index=None, with_cards=True, base=None, entry=None):
    """Every set of this profile's options, each with the card you'd get.

    Pass ``index`` to share one modifier index across a whole list; without
    one it is built here, for a single entry.

    ``with_cards=False`` prices the options without drawing their cards —
    the internal cards are still built, because an option's total is its
    card's rating, but nothing runs the effects engine or shapes a
    ``ModelCard`` for a card the caller will not show. A surface that
    serves cards on demand asks ``preview_model_card`` for each instead.

    ``base`` prices the fighter as an offering collection does, and
    ``entry`` is the row that made the offer — carried on the entry so a
    click can say which offer it answered.
    """
    grouped = profile.grouped_offers()
    if not grouped or grouped[0][0] is not None:
        # Every entry has the default group, options or not.
        grouped = [(None, [])] + grouped

    cards = {None: build_card_from_profile(profile, base=base)}
    for _, options in grouped:
        for option in options:
            cards[option.default_set.pk] = build_card_from_profile(
                profile, option=option.default_set, base=base
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
    return HireEntry(profile=profile, groups=groups, entry=entry)


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
    return build_offer_entries(
        [Offer(profile=profile) for profile in profiles], with_cards=with_cards
    )


def build_offer_entries(offers, with_cards=True):
    """Hire entries for offers already fetched — the one build on this screen.

    A row priced by a collection and a row priced by the catalogue differ
    only in what replaces the fighter's own price, so both come through
    here: one modifier index covers every card, and the cards are
    assembled in memory.
    """
    index = None
    if with_cards:
        cards = []
        for offer in offers:
            profile = offer.profile
            cards.append(build_card_from_profile(profile, base=offer.base))
            for _, sets in profile.grouped_options():
                cards.extend(
                    build_card_from_profile(
                        profile, option=default_set, base=offer.base
                    )
                    for default_set in sets
                )
        index = build_modifier_index(
            [node.assignable for card in cards for node in card.all_nodes()]
        )
    return [
        build_hire_entry(
            offer.profile,
            index=index,
            with_cards=with_cards,
            base=offer.base,
            entry=offer.entry,
        )
        for offer in offers
    ]


def collection_offers(collections):
    """Every fighter these collections offer, as they offer it.

    Both ways a collection contains something, answered together: curated
    entries naming a profile, at this collection's own price, and
    selectors sweeping profiles in at reference. An entry wins over a
    sweep for the same profile, as wherever else a collection is read
    (``n26.core.browse``) — that is where per-item pricing lives.

    Emptiness is the answer to whether a collection belongs on the hire
    screen: one holding no profiles offers nothing here and gets no
    section. A profile nobody may hire directly is left out too — a pet
    arrives behind its collar, and drawing a row whose button cannot work
    is the harm.

    A fixed number of queries however many collections, entries or
    profiles: the entries and the sweeps come back one query each, the
    profiles in a single fetch carrying everything a preview row needs,
    and each sweep is then decided in memory.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q

    from n26.core import select
    from n26.library.models import CollectionEntry, CollectionSelector, Profile

    ids = [collection.pk for collection in collections]
    if not ids:
        return []

    entries = list(
        CollectionEntry.objects.filter(
            collection_id__in=ids, profile__isnull=False
        ).order_by("position")
    )
    sweeps = list(
        CollectionSelector.objects.filter(
            collection_id__in=ids,
            of_kind=ContentType.objects.get_for_model(Profile),
        )
        .select_related("category")
        .order_by("position")
    )
    if not entries and not sweeps:
        return []

    wanted = Q(pk__in=[entry.profile_id for entry in entries])
    for sweep in sweeps:
        wanted |= sweep.as_selector().as_q(Profile)
    found = {profile.pk: profile for profile in hireable_profiles().filter(wanted)}

    offers = []
    for collection in collections:
        taken = set()
        for entry in entries:
            profile = found.get(entry.profile_id)
            if entry.collection_id != collection.pk or profile is None:
                continue
            if profile.pk in taken:
                continue
            taken.add(profile.pk)
            offers.append(Offer(profile=profile, entry=entry, collection=collection))
        for sweep in sweeps:
            if sweep.collection_id != collection.pk:
                continue
            # The sweep is decided against the rows already fetched rather
            # than by a query of its own, so a gang carrying six swept
            # lists costs what one costs. A selector row can only ask
            # about a profile's kind, its home and its Trade Point price
            # — facts printed on the row — so no possession is needed to
            # answer it.
            selector = sweep.as_selector()
            for profile in found.values():
                if profile.pk in taken:
                    continue
                if selector.matches(select.Matchable(thing=profile)):
                    taken.add(profile.pk)
                    offers.append(Offer(profile=profile, collection=collection))
    return offers


def collection_sections(offers, with_cards=True):
    """One section per collection that offers fighters, named after it.

    The collection is the heading because the collection is the offer: a
    reader knows these fighters by what brought them ("Genestealer Cult
    Corrupted"), not by which gang type authored them. Inside, the
    categories are the profiles' own homes, in taxonomy order, cheapest
    first — the same shape every other section on this screen takes.
    """
    grouped = {}
    for offer in offers:
        grouped.setdefault(offer.collection.pk, (offer.collection, []))[1].append(offer)
    sections = []
    for collection, rows in grouped.values():
        sections.append(
            _section_of(
                str(collection), build_offer_entries(rows, with_cards=with_cards)
            )
        )
    return sections


def preview_model_card(profile, option=None, base=None):
    """The drawn card a row shows for what it is currently set to.

    The single card a hire page serves on demand, and the same
    derivation ``build_hire_entry`` draws inline: the card a selection
    would produce, its effects computed, shaped for a renderer.

    ``option`` is one set or a list of them, as everywhere a selection is
    named. A list is the whole configuration — one pick per group,
    composed — which is what a listing following all of its controls asks
    for; the per-option cards a list builds are that with one group
    picked and the rest left at their defaults.

    ``base`` prices it as an offering collection does, so the card behind
    a collection's row carries the same number the row quotes.
    """
    card = build_card_from_profile(profile, option=option, base=base)
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

    return group_by_home(
        ((entry.profile.category, entry) for entry in entries),
        section=lambda heading, categories: HireSection(
            name=heading or UNCATEGORISED, categories=categories
        ),
        category=lambda heading, entries: HireCategory(name=heading, entries=entries),
        order=_entry_order,
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


def _entry_order(entry):
    # Cheapest first within a category: a gang list is read to find what
    # this many credits will buy.
    return (entry.base_price, entry.name)


def _section_of(name, entries):
    """One section under a heading the taxonomy did not provide.

    A gang type on the all-profiles scope, a collection a gang carries:
    the heading is the thing that gathered these fighters, and the
    categories inside keep the taxonomy's own homes and order. Rows the
    content gave no home gather last, under no heading — the picker draws
    those straight inside the section.
    """
    homes = {}
    for entry in entries:
        home = entry.profile.category
        key = (
            (0, home.section.position, home.position, home.name)
            if home is not None
            else (1, 0, 0, "")
        )
        homes.setdefault(key, []).append(entry)
    return HireSection(
        name=name,
        categories=[
            HireCategory(name=key[3], entries=sorted(rows, key=_entry_order))
            for key, rows in sorted(homes.items())
        ],
    )


def section_by_gang_type(entries):
    """The hire list in sections of gang types — the all-profiles scope.

    Every gang list at once is found by whose list it is, so the
    sections are the gang types and the categories inside keep the
    taxonomy's own homes. Cheapest first within a category, as
    everywhere on this screen.
    """
    by_type = {}
    for entry in entries:
        by_type.setdefault(entry.profile.gang_type, []).append(entry)

    return [
        _section_of(gang_type.name, by_type[gang_type])
        for gang_type in sorted(by_type, key=lambda found: found.name.casefold())
    ]
