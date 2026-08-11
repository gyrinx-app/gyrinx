"""Collections — views onto the assignables, with prices.

An equipment list, a trading post, later a hire list: a collection is a
browsing surface, never a permission system. Operations do not consult
collections; an entry merely *pre-fills* a purchase's price. The design is
in design/collections.md.

Two things matter structurally:

* **A collection is itself an assignable.** Having a list is an
  assignment: the profile's own list arrives via its built-ins at hire,
  the gang's shared list is a gang-hosted assignment, and a territory can
  grant one computedly through an ordinary modifier. No parallel access
  mechanism exists — a fighter's lists are read off their card.

* **Entries override the reference price; they never replace it.** An
  entry with neither override showing is just "this item, at what the
  catalogue prints". The two overrides are independent — a list may
  reprice credits without touching Trade Points, or vice versa. The
  agreed consequence stands: a reference-price fix does not flow through
  an override; each override is its own fact.

``price_of`` is the one effective-price function, used by curated
collections (entry override → reference) and derived ones (reference
alone: the default Trading Post has no rows at all) — one function, so
the two species cannot drift.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from n26.core.constraints import NamesAnAssignable, exactly_one_of
from n26.library.models.assignable import (
    Assignable,
    Family,
    exclusive_has_no_trade_points,
)
from n26.library.models.base import Content, ContentQuerySet

#: What a collection entry may name. Not traits or injuries — those are
#: never shopped for — and not collections (a list does not contain a list;
#: granting access is the modifier system's job).
ENTRY_ASSIGNABLE_FIELDS = (
    "weapon",
    "weapon_profile",
    "wargear",
    "weapon_accessory",
    "subtype",
    "skill",
    "specialisation",
    "profile",
    "power",
    # Chosen carriers (archetypes, affiliations) are listable too: a
    # pack collects its archetypes so a slot's offer can be narrowed to
    # exactly that list.
    "archetype",
    "affiliation",
)


@dataclass(frozen=True)
class Price:
    """What buying a thing asks for, effectively.

    ``trade_points`` is ``None`` for a thing not offered at the Trading
    Post at all — distinct from 0, which is a real (free) TP price, and
    from Exclusive, which is the equipment-list-only "E".
    """

    credits: int
    trade_points: int | None
    is_exclusive: bool

    def __str__(self):
        if self.is_exclusive:
            trade = "E"
        elif self.trade_points is None:
            trade = "-"
        else:
            trade = str(self.trade_points)
        return f"{self.credits}cr / TP {trade}"


def price_of(assignable, entry=None):
    """The effective price of a thing, through an entry or at reference.

    The one function both species of collection use: a curated entry's
    override wins where set and falls through where null; no entry means
    reference alone (how a derived collection prices everything).
    Exclusivity is always the item's own fact — a list cannot override it.

    **A blank override is an answer, not a gap.** It says "this list
    sells it at the usual price", which is the ordinary thing for an
    author to mean and by far the commonest thing they write. Read as
    missing data it looks like most of the library is unpriced; read as
    what it is, an override is the exception a list goes to the trouble
    of stating.
    """
    # An override replaces the item's *own* price; anything it comes with
    # still costs what it costs, so the composition happens after.
    override = entry.price_override if entry is not None else None
    credits = assignable.reference_price(base=override)
    trade_points = assignable.trade_point_price
    if entry is not None:
        if entry.trade_point_override is not None:
            trade_points = entry.trade_point_override
    if assignable.is_exclusive:
        trade_points = None
    return Price(
        credits=credits,
        trade_points=trade_points,
        is_exclusive=assignable.is_exclusive,
    )


#: Where a browse hangs a weapon's buyable profiles. One attribute name
#: for both species of collection, so a curated list and a sweep cannot
#: come to disagree about what rides under a gun.
TRADEABLE_PROFILES = "tradeable_profiles"


def paid_profiles(with_trade_point_price=False):
    """A weapon's named, paid profiles — the rows a listing prints under
    the gun.

    Named, because a blank profile is the weapon's own firing line rather
    than an alternative to it. Paid, because a free profile already rides
    along with the weapon wherever it goes: selling one would put the
    same ammo on the gun twice.

    ``with_trade_point_price`` narrows to what a trading trip deals in —
    membership at a Trading Post is having a TP price, and a sweep that
    said so means it of the ammo as well as of the gun.
    """
    from n26.library.models.assignable import WeaponProfile

    found = WeaponProfile.objects.filter(price__gt=0).exclude(name="")
    if with_trade_point_price:
        found = found.filter(trade_point_price__isnull=False)
    return found


def entryable_kinds():
    """The model classes a collection may hold, by the entry column that
    names each one.

    Read off ``CollectionEntry``'s own foreign keys rather than listed
    again here, so a kind that becomes listable becomes visible to
    everything asking what collections contain, with nothing to remember.
    """
    return {
        name: CollectionEntry._meta.get_field(name).related_model
        for name in ENTRY_ASSIGNABLE_FIELDS
    }


class CollectionQuerySet(ContentQuerySet):
    """Narrowing helpers for collections. Opt-in, like every other one."""

    def containing(self, *families):
        """Collections holding at least one assignable of these families.

        The question a surface asks to decide whether a collection belongs
        on it: a screen for buying kit wants the collections with gear in
        them, whoever holds them and however they were built. Asked by
        ``Family`` rather than by naming kinds, so a new sort of gear
        qualifies its collections the day it exists.

        Both ways a collection contains something are answered together:
        curated entries, where the family follows from which column is
        set, and sweeps, where it follows from the kind swept. Emptiness
        is an answer — a collection with neither holds nothing of any
        family, so it belongs on no surface that asks.

        One query wherever it is used, whatever the collections hold:
        the containment tests are subqueries against the entry and
        selector tables, not rows brought back to be counted.
        """
        from django.db.models import Exists, OuterRef

        wanted = [
            (name, model)
            for name, model in entryable_kinds().items()
            if model.family in families
        ]
        if not wanted:
            return self.none()

        entry_columns = models.Q()
        swept_kinds = models.Q()
        for name, model in wanted:
            entry_columns |= models.Q(**{f"{name}__isnull": False})
            swept_kinds |= models.Q(
                of_kind__app_label=model._meta.app_label,
                of_kind__model=model._meta.model_name,
            )

        return self.filter(
            Exists(
                CollectionEntry.objects.filter(entry_columns, collection=OuterRef("pk"))
            )
            | Exists(
                CollectionSelector.objects.filter(
                    swept_kinds, collection=OuterRef("pk")
                )
            )
        )


CollectionManager = models.Manager.from_queryset(CollectionQuerySet)


class Collection(Content, Assignable):
    """A named, directly addressable view onto the assignables.

    Directly addressable is the point: a Venator profile says "I use
    *this* equipment list" by putting the row in its built-ins; a filter
    or a grant names the same row rather than redefining it.

    A collection contains things two ways, and most use one or the other:

    * **entries** — curated rows, each naming one item, optionally at this
      collection's own price. An equipment list is usually all entries.
    * **selectors** — rows that sweep in whole swathes ("every weapon"),
      at reference prices. A trading post is usually a couple of selectors
      plus entries for the items it prices differently — an entry always
      wins over a selector for the same item, which is how the Nomad post
      marks Imperial equipment as harder to obtain than usual.

    Deliberately absent: anything about **charging**. How a purchase is
    paid — whether Trade Points are spent, from what budget, pooled or
    per-fighter, temporary or standing — is the shopping flow's concern,
    expressed as the ``Terms`` a browse is made on (``n26.core.browse``). The
    same collection can be shopped as a plain list or as a trading trip;
    it declares contents and prices, and nothing else.
    """

    family = Family.GANG

    #: What listing an entry here asks an author for, beyond the pick.
    #: A shop's entries state prices; a menu's — a pick list of
    #: affiliations behind a choice — have nothing to state, so its
    #: entry form asks for nothing and its preview prints no money.
    #: The seam every surface reads is ``entry_asks()`` below, so a
    #: further flag with further asks changes one function.
    prices_its_entries = models.BooleanField(
        default=True,
        verbose_name="Prices its entries",
        help_text=(
            "On for anything sold from — prices and Trade Points may be "
            "stated per entry. Off for a menu, like a pick list behind "
            "a choice: nothing is for sale, so listing an item asks "
            "for nothing but the item."
        ),
    )

    def entry_asks(self):
        """The extra fields an entry of *this* collection takes.

        The entry form shows exactly these, and the page's tables print
        columns for no more — one answer, read by both, so the form and
        the preview cannot disagree about whether money is involved.
        """
        return (
            ("price_override", "trade_point_override")
            if self.prices_its_entries
            else ()
        )

    objects = CollectionManager()

    class Meta:
        verbose_name = "collection"
        verbose_name_plural = "collections"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="collection_unique_per_pack",
            ),
            exclusive_has_no_trade_points("collection"),
        ]

    def default_section(self):
        """Where this collection's unplaced categories fall, if declared."""
        return next(
            (section for section in self.sections.all() if section.is_default),
            None,
        )


class CollectionSection(Content):
    """One named tier of a collection: "Primary" in Skills & Powers, at 0.

    Defined once per collection and picked by name everywhere — the
    section names, their order, and where the unplaced fall are the
    collection's **schema**, never conventions restated per placement.
    A ``PlacesCategory`` effect points at one of these rows, which is
    what makes placements collection-scoped and gives the admin a
    dropdown ("Primary (Skills & Powers)") instead of a string and a
    magic number.

    ``position`` orders the sections in the view and resolves placement
    conflicts (lowest wins). ``is_default`` marks where unplaced
    categories fall — an ordinary section in every other way.
    """

    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="sections"
    )
    name = models.CharField(max_length=200, help_text='The tier — "Primary".')
    position = models.PositiveIntegerField(
        default=0,
        help_text="Orders the sections; the lowest placement wins a conflict.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Unplaced categories fall here. At most one per collection.",
    )

    class Meta:
        verbose_name = "collection section"
        verbose_name_plural = "collection sections"
        ordering = ["collection", "position", "name"]
        constraints = [
            models.UniqueConstraint(
                "collection",
                Lower("name"),
                name="collection_section_unique_name",
            ),
            models.UniqueConstraint(
                fields=["collection"],
                condition=models.Q(is_default=True),
                name="one_default_section_per_collection",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.collection.name})"


#: What a selector row may sweep in, by ContentType model name. The same
#: kinds an entry may name — a collection contains shoppable things
#: however it lists them.
SELECTABLE_KIND_NAMES = tuple(name.replace("_", "") for name in ENTRY_ASSIGNABLE_FIELDS)


class CollectionSelector(Content):
    """One sweep of a collection's contents: a kind, optionally narrowed.

    "Every weapon", "every wargear", "every weapon homed in Auto/Stub
    Weapons". Swept-in items sell at reference price — a curated
    entry for the same item wins, which is where per-item customisation
    lives. ``of_kind`` is the ``OffersChoice`` pattern: a plain foreign
    key to the ContentType row, a typed reference to a model class.
    """

    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="selectors"
    )
    of_kind = models.ForeignKey(
        "contenttypes.ContentType",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The kind of assignable this sweeps in — every weapon, say.",
    )
    category = models.ForeignKey(
        "library.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Narrow the sweep to items homed in one category.",
    )
    with_trade_point_price = models.BooleanField(
        default=False,
        help_text=(
            "Sweep only items offered at the Trading Post — a trade "
            "point price set. This is what makes the Trading Post: "
            "membership is having a TP price, not being listed by hand."
        ),
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "collection selector"
        verbose_name_plural = "collection selectors"
        ordering = ["collection", "position"]

    def __str__(self):
        kind = self.of_kind.name
        said = f"every {kind}"
        if self.category_id:
            said += f" in {self.category.name}"
        if self.with_trade_point_price:
            said += " with a TP price"
        return said

    @classmethod
    def of(cls, collection, model, category=None, **kwargs):
        from django.contrib.contenttypes.models import ContentType

        return cls.objects.create(
            collection=collection,
            of_kind=ContentType.objects.get_for_model(model),
            category=category,
            **kwargs,
        )

    def as_selector(self):
        """What this row says, whole, in the selector vocabulary.

        The kind, the category narrowing and the TP-price narrowing —
        this stored shape is a dialect of the one grammar, compiled here
        and executed through it (see design/selectors.md). Exclusivity
        stays out: that is the browse's terms, not this row's meaning.
        """
        from n26.core import select

        parts = [select.OfKind(self.of_kind.model_class())]
        if self.category_id is not None:
            parts.append(select.HomedIn(self.category))
        if self.with_trade_point_price:
            parts.append(select.HasTradePointPrice())
        if len(parts) == 1:
            return parts[0]
        return select.All(*parts)

    def contents(self, include_exclusive=True):
        """The swept-in items, as a queryset — the selector, compiled.

        ``include_exclusive`` belongs to the *browse*, not the row: a
        trading trip has no Exclusive items in its listing ("E" means
        equipment list only), while the same sweep browsed as a plain
        list legitimately carries them.

        A TP-narrowed sweep over weapons also prefetches each weapon's
        paid, TP-priced profiles to ``tradeable_profiles`` — the ammo
        rows the Trading Post prints under the gun. One query for the
        whole sweep, so browsing stays a fixed number of queries.
        """
        from django.db.models import Prefetch

        from n26.library.models.assignable import (
            OPTION_OFFER_PATHS,
            USABLE_BY_LISTS,
            Optioned,
            UsableBy,
        )

        model = self.of_kind.model_class()
        found = model.objects.filter(self.as_selector().as_q(model)).select_related(
            "category__section"
        )
        if issubclass(model, UsableBy):
            # So marking a swept listing usable costs no extra queries.
            found = found.prefetch_related(*USABLE_BY_LISTS)
        if issubclass(model, Optioned):
            # So a swept thing that offers alternatives at the till — a
            # mount and its weapon swaps — puts them on screen without a
            # query per row.
            found = found.prefetch_related(*OPTION_OFFER_PATHS)
        if self.with_trade_point_price and hasattr(model, "profiles"):
            found = found.prefetch_related(
                Prefetch(
                    "profiles",
                    queryset=paid_profiles(with_trade_point_price=True),
                    to_attr=TRADEABLE_PROFILES,
                )
            )
        if not include_exclusive:
            found = found.filter(is_exclusive=False)
        return found

    def clean(self):
        if self.of_kind_id and self.of_kind.model not in SELECTABLE_KIND_NAMES:
            allowed = ", ".join(SELECTABLE_KIND_NAMES)
            raise ValidationError(
                f"A collection cannot sweep in {self.of_kind.name}s. "
                f"Sweepable kinds: {allowed}."
            )


class CollectionEntry(NamesAnAssignable, Content):
    """One item a collection lists, at this list's own price where an
    override says so and at the item's own otherwise.
    """

    # Same mixin as a player's Assignment and a profile's
    # DefaultAssignment — ``assignable=`` routes to the right column,
    # exactly one may be set. (A comment, not the docstring: the
    # docstring is shown to authors on the authoring pages.)
    ASSIGNABLE_FIELDS = ENTRY_ASSIGNABLE_FIELDS

    #: The key assignable kinds use in their ``ATTACHMENT_ASKS`` to say
    #: which of this row's columns matter when they are the thing named
    #: (library/offers.py).
    attachment_context = "entry"

    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="entries"
    )
    weapon = models.ForeignKey(
        "library.Weapon",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    weapon_profile = models.ForeignKey(
        "library.WeaponProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    weapon_accessory = models.ForeignKey(
        "library.WeaponAccessory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    wargear = models.ForeignKey(
        "library.Wargear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    subtype = models.ForeignKey(
        "library.Subtype",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    skill = models.ForeignKey(
        "library.Skill",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    specialisation = models.ForeignKey(
        "library.Specialisation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    profile = models.ForeignKey(
        "library.Profile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    power = models.ForeignKey(
        "library.Power",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    archetype = models.ForeignKey(
        "library.Archetype",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    affiliation = models.ForeignKey(
        "library.Affiliation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    price_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="This list's credit price. Blank means at reference price.",
    )
    trade_point_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="This list's TP price. Blank means at reference price.",
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "collection entry"
        verbose_name_plural = "collection entries"
        ordering = ["collection", "position"]
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(ENTRY_ASSIGNABLE_FIELDS),
                name="collection_entry_exactly_one",
            ),
        ]

    def __str__(self):
        return f"{self.assignable} in {self.collection.name}"

    @property
    def price(self):
        """This entry's effective price: overrides folded onto reference."""
        return price_of(self.assignable, entry=self)
