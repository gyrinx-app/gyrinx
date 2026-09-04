"""Assignable — a mixin, not a table.

Being attachable is a *property* of a content model, not an entity of its
own. A weapon is assignable; a skill is assignable; there is no separate
"assignable" row shadowing them. The model class is the kind — there is no
``AssignableType`` content row to mistype.

Two consequences follow, both deliberate:

* Because the mixin is abstract, the modifier relationship declared here
  gives every concrete kind its own join table. Modifiers never need to
  point back polymorphically.
* Because there is no shared table, ``n26.Assignment`` cannot hold a
  single foreign key. It holds one nullable key per kind, with a database
  constraint that exactly one is set, and a startup check that no kind has
  been forgotten. See ``n26.core.models.assignment``.
"""

from django.db import models
from django.db.models.functions import Lower

from n26.library.models.base import Content
from n26.library.models.modifier import Modifier


class Family(models.TextChoices):
    """How the authoring UI groups the kinds.

    Set per model class (``family = Family.GEAR``), never per row: it
    says what *sort* of thing a kind is, so the menu can read as the
    author thinks — the plumbing, the model's own qualities, the kit it
    carries, the gang-scale picks, the slot types. A discovering
    test refuses any authorable kind without one.
    """

    #: The plumbing everything references: rules, counters, the taxonomy.
    BASE = "base", "Base"
    #: What a model is and selects: subtypes, skills, powers, effects.
    MODEL = "model", "Model"
    #: What a model carries: weapons, wargear, traits.
    GEAR = "gear", "Gear"
    #: The gang-scale things: gang types, profiles, chosen carriers, lists.
    GANG = "gang", "Gang"
    #: A slot type and its parts: the type itself, its pickables, the
    #: picklists that contain them, and the slots that display them.
    CHOICE = "choice", "Slots & Pickables"
    #: Not assignables at all — the shapes content is built from.
    FOUNDATION = "foundation", "Foundation"


def exclusive_has_no_trade_points(class_name):
    """The check every priced kind carries: TP "E" and a TP price are
    mutually exclusive facts, so authoring both is refused at the database.
    Content integrity, not player policing."""
    return models.CheckConstraint(
        condition=models.Q(is_exclusive=False)
        | models.Q(trade_point_price__isnull=True),
        name=f"{class_name}_exclusive_has_no_tp",
    )


class Assignable(models.Model):
    """Mixin for anything that can be attached to a gang, model or assignment.

    Combine with ``Content``::

        class Wargear(Content, Assignable):
            ...

    Every assignable is **priced** — credits and Trade Points together, the
    pair the rulebook prints in every catalogue row — because anything may
    turn out to be purchasable (pets are wargear; powers and subtypes can be
    bought). No kind is special-cased; most things just stay at zero. The
    reference price is the item's own data; collections *override* it per
    entry, never replace it (see ``n26.library.models.collection``).

    Every assignable also has a **home category**: where it sorts in any
    collection that shows it. Fixed per item, whatever list it appears on.
    """

    name = models.CharField(max_length=200)
    # As long as a name: a weapon profile's annotation defaults to its
    # weapon's name, so a shorter column here would refuse a name the
    # name column accepted.
    annotation = models.CharField(
        max_length=200,
        blank=True,
        help_text="Shown in brackets after the name, e.g. Ammo (5+).",
    )
    #: How two things that print the same name are told apart — the
    #: books give Delaque's and Goliath's beasts the same "Ferocious
    #: jaws" with different profiles, and both must exist. **Author
    #: facing only**: unlike ``annotation``, which a card prints, this
    #: never reaches a player. ``authoring_label`` is the one place it
    #: appears, and a guard test keeps it out of everything else.
    qualifier = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Only to tell apart two things the books give the same name — "
            "Ferocious jaws (Sumpkroc) and Ferocious jaws (Psychoteric "
            "Wyrm). Seen by authors, never by players: the card prints "
            "the name alone. For words a card should print, use the "
            "annotation instead."
        ),
    )
    #: Authoring help: pack-author-owned words for whoever wields this
    #: while building *other* content. Addable and editable at any time —
    #: and the copyright line stays absolute: the book's rules text never
    #: lives here (CLAUDE.md).
    #:
    #: Never shown to players, which is why it is absent
    #: from ``n26.core.render.AssignableLine`` and ``n26.core.browse.PricedLine`` and
    #: should stay absent: the render layer carries what a player reads, and
    #: the surest way to keep this off a card is to give the UI no way to
    #: reach it.
    library_author_help = models.TextField(
        blank=True,
        default="",
        help_text=(
            "For content authors: what this is for and how to use it when "
            "building other content."
        ),
    )
    modifiers = models.ManyToManyField(
        Modifier,
        blank=True,
        related_name="%(app_label)s_%(class)s_set",
        help_text="What this does once assigned.",
    )
    price = models.PositiveIntegerField(
        default=0,
        help_text="Credit price at reference — what the catalogue prints.",
    )
    trade_point_price = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Trade Points to buy this at the Trading Post. Blank means "
            "not offered there at all; 0 is a real price."
        ),
    )
    is_exclusive = models.BooleanField(
        default=False,
        help_text=(
            'TP "E": never offered at the Trading Post — equipment list only. '
            "Wins over any trade point price."
        ),
    )
    category = models.ForeignKey(
        "library.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)ss",
        help_text="Where this sorts in any collection that shows it.",
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Order within its home category — a skill's D6 number in its "
            "set. Ties fall back to name."
        ),
    )
    built_ins = models.ForeignKey(
        "library.DefaultAssignmentSet",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_built_into",
        help_text=(
            "Always granted when this is acquired. No choice is offered "
            "for these — a thing that may be swapped for something else "
            "is an option, not a built-in."
        ),
    )

    #: What attaching something of this kind asks for, beyond the pick:
    #: the through row's columns that matter for this kind, keyed by the
    #: through row's ``attachment_context`` (library/offers.py). The
    #: kind's own knowledge — no form enumerates kinds by hand. The
    #: default: anything purchasable may be repriced where a collection
    #: lists it, and nothing extra when built in.
    ATTACHMENT_ASKS = {"entry": ("price_override", "trade_point_override")}

    #: The model card's named row this kind's lines join — the card's own
    #: vocabulary ("skills", "powers"), declared once here and read by
    #: everything that files a line, a computed grant, or an open
    #: question. None is the general run: lines draw as gear, questions
    #: as rows of their own. Kinds a card draws some other way entirely —
    #: a weapon block, a counter's cell — also say None and keep their
    #: bespoke handling.
    card_row = None

    #: Whether assignments of this kind hang off a weapon's own
    #: assignment — what makes "the weapon it's fitted to" a scope this
    #: kind's modifiers can speak. The composer greys that scope on
    #: everything else, with the reason on the card.
    attaches_to_weapons = False

    #: Whether a set of built-ins on this kind would ever come to
    #: anything. A set is materialised when an assignment *arrives* — a
    #: model hired, a gang founded, something bought — so a kind that
    #: only ever arrives by being **chosen** runs nothing, and items
    #: built into one would sit in the library unread. Such a kind says
    #: False, and what it brings rides it as modifiers instead. The
    #: authoring pages read this to decide whether to offer the
    #: attachment at all, and ``add_built_in`` refuses one however it is
    #: written.
    takes_built_ins = True

    #: Whether the generic built-in picker offers this kind. A kind that
    #: only means something beside one particular row of another kind —
    #: a weapon's extra profile beside its gun — says False and is
    #: attached from that row's own page instead, so the picker never
    #: offers an act whose meaning it cannot ask for.
    offered_as_built_in = True

    class Meta:
        abstract = True

    def __str__(self):
        """What a player reads. Never the qualifier — see below."""
        return f"{self.name} ({self.annotation})" if self.annotation else self.name

    @property
    def authoring_label(self):
        """What an *author* reads: the printed name, plus the qualifier
        that tells two same-named things apart. The only place the
        qualifier surfaces, so the guard has one thing to watch."""
        if self.qualifier:
            return f"{self} — {self.qualifier}"
        return str(self)

    @property
    def built_in_members(self):
        """What this always comes with, as the members of its built-ins
        set — empty when it has none yet, so a page can list without
        checking first. An archived member is one an author took off:
        it no longer materialises, so no surface lists it, though what
        it already granted keeps standing."""
        from n26.library.models.defaults import DefaultAssignment

        if self.built_ins_id is None:
            return DefaultAssignment.objects.none()
        return self.built_ins.members.filter(archived=False)

    def reference_price(self, base=None):
        """The credit price a catalogue prints, before any override.

        A plain field for most things; ``base`` replaces it where a
        collection prices this its own way.

        A kind that comes with kit composes instead (``price_with``): a
        mount advertises the package — itself, its built-ins and whatever
        comes as standard — because that is what buying it takes. Asked
        of the price rather than left to a subclass override: an
        assignable is a stack of mixins, and one further down the stack
        cannot replace a method one further up.
        """
        own = self.price if base is None else base
        composed = getattr(self, "price_with", None)
        return own if composed is None else composed(base=own)


class UsableBy(models.Model):
    """Who may use this — "(Fighter Or Walker Only)" as data, not prose.

    The rulebook prints applicability in every skill heading, and it
    gates even the advancement table's roll-12 free pick ("a model may
    still not select a skill that is unavailable to their Type or
    Subtype"). The list is an OR: a profile type matches, or a subtype
    matches. **Empty means everyone** — default open, the house rule.

    A mixin, so a kind opts in (skills and powers today) and anything
    without it is simply usable by all. And it informs, never polices:
    an unusable skill still shows in the listing, marked, and nothing
    stops the owner assigning it anyway.

    A collection entry carries the same four lists for its own line
    (``n26.library.models.collection``), which divides the two facts:
    what is true of the item wherever it appears belongs on the item,
    what one list narrows belongs on that list's entry.
    """

    # Two of the four say what they call themselves, because their
    # column names read as something else in front of an author: a
    # profile type is a type, and "profiles" on a weapon's page would be
    # taken for its firing lines. The other two are named what they are.
    usable_by_profile_types = models.ManyToManyField(
        "library.ProfileType",
        blank=True,
        related_name="+",
        verbose_name="Usable by types",
        help_text='The "Fighter" in "(Fighter Or Walker Only)".',
    )
    usable_by_subtypes = models.ManyToManyField(
        "library.Subtype",
        blank=True,
        related_name="+",
        help_text='The "Walker" in "(Fighter Or Walker Only)".',
    )
    usable_by_profiles = models.ManyToManyField(
        "library.Profile",
        blank=True,
        related_name="+",
        verbose_name="Usable by fighter entries",
        help_text=(
            'The "Wyld Runner" in "Wyld bow (Wyld Runner only)" — a whole '
            "fighter entry, which is neither a type nor a subtype. This "
            "holds wherever the item is listed; a restriction only one "
            "list prints goes on that list's entry instead."
        ),
    )

    class Meta:
        abstract = True

    def usable_by_selector(self):
        """Who may use this, in the selector vocabulary.

        The stored shape stays this mixin's own dialect — three
        tailored M2Ms — and compiles here to the one grammar: being an
        allowed *entry* is an ``Exactly`` (the fighter matchable's thing
        is their profile); having an allowed type or subtype is a
        ``Has``. Empty is ``Anything()``, the default-open rule.

        Prefetch-aware: reads the lists with ``.all()``, so a browse that
        prefetched them compiles a whole listing without extra queries.
        """
        from n26.core import select

        possessed = [
            *self.usable_by_profile_types.all(),
            *self.usable_by_subtypes.all(),
        ]
        entries = list(self.usable_by_profiles.all())
        if not possessed and not entries:
            return select.Anything()
        return select.Any(
            *(select.Has(allowed) for allowed in possessed),
            *(select.Exactly(allowed) for allowed in entries),
        )

    def is_usable_by(self, fighter):
        """Whether this fighter may use this. ``fighter`` is a matchable —
        ``n26.core.browse.usability_for`` builds it from a computed card."""
        return self.usable_by_selector().matches(fighter)

    def usable_by_words(self):
        """Who is allowed, as a phrase — empty where anyone is.

        The one place the three lists are read out for a reader, so a
        note on a listing's line, a mark on a card and a row on an
        authoring page name them the same way and in the same order.
        Prefetch-aware, like the selector.
        """
        allowed = [
            *self.usable_by_profiles.all(),
            *self.usable_by_profile_types.all(),
            *self.usable_by_subtypes.all(),
        ]
        return " or ".join(str(item) for item in allowed)


#: The lists ``usable_by_selector`` reads, derived from the mixin's own
#: fields: a listing that prefetches these for every kind carrying the
#: mixin marks usability without a query per line, and stays complete
#: if the mixin ever grows a fourth list.
USABLE_BY_LISTS = tuple(field.name for field in UsableBy._meta.local_many_to_many)


class Optioned(models.Model):
    """Mixin for things that offer alternatives when you acquire them.

    A profile offers them at hire; a mount in the wargear list offers
    them when bought ("replace its grenade launchers with plasma guns,
    +15 credits"). Same grammar, so the same code — which is why this is
    a mixin and not a feature of ``Profile``, where it started.

    The options themselves are ``Option`` rows naming their carrier, so a
    kind opts in here and gains ``options`` and ``option_groups``
    accessors. ``built_ins`` needs no opting in: it is on ``Assignable``,
    because coming with something is universal while being *swappable* is
    not.
    """

    class Meta:
        abstract = True

    @property
    def offers_a_choice(self):
        """Whether the offer holds anything worth putting in front of anyone.

        The same test each drawn group makes of itself: a pick-one set —
        the default group included — with a single option is not a
        choice, where an any-of or one-or-none set with one option is,
        because taking it or not is the choice. A surface deciding
        whether to offer a way to the options at all asks this rather
        than whether options merely exist.
        """
        for group, options in self.grouped_offers():
            exclusive = group is None or group.choose == "one"
            if len(options) > 1 or not exclusive:
                return True
        return False

    @property
    def default_option(self):
        """The default group's head — what taking this takes unasked."""
        sets = self.option_sets()
        return sets[0] if sets else None

    def option_sets(self):
        """The default group's sets, default first.

        The main pick anything may have: options an author created
        without naming a group. Further sets live in ``option_groups()``.

        Ordered by ``Option``'s own Meta rather than an ``order_by``
        here, so a prefetched list is used as-is: re-ordering would issue a
        fresh query per carrier and undo a hire list's query budget.
        """
        return [
            option.default_set
            for option in self.options.all()
            if option.group_id is None
        ]

    def grouped_offers(self):
        """Every set of the offer, in order: ``[(group, [options])]``.

        The default group comes first as ``(None, [options])``, present
        only when ungrouped options exist; then each named group by
        position. Built from the prefetched options alone — the group
        rows ride in on ``options__group`` — so a hire list pays no
        query per carrier.
        """
        heads, by_group = [], {}
        for option in self.options.all():
            key = option.group_id
            if key not in by_group:
                heads.append(option.group)
                by_group[key] = []
            by_group[key].append(option)
        heads.sort(key=lambda g: (g is not None, g.position if g else 0))
        return [(group, by_group[group.pk if group else None]) for group in heads]

    def grouped_options(self):
        """The same sets, as the default-sets a selection is made of.

        A selection names sets, because a set is what materialises;
        what the option offering it is called is a question for whatever
        puts the choice in front of a player.
        """
        return [
            (group, [option.default_set for option in options])
            for group, options in self.grouped_offers()
        ]

    def resolve_selection(self, selection=None):
        """The sets a hire takes, given what the player named.

        ``selection`` is a single set, a list of sets, or ``None``. It
        lists only what was *chosen*: a one-of group not named falls
        back to its head; any-of and one-or-none groups take exactly
        what was named, which may be nothing. Naming two sets from an
        exclusive group, or a set this does not offer, is refused —
        that is a caller bug, not a player choice.
        """
        named = list(
            selection
            if isinstance(selection, (list, tuple))
            else [selection]
            if selection is not None
            else []
        )
        named_pks = [chosen.pk for chosen in named]
        taken = []
        for group, sets in self.grouped_options():
            named_here = [s for s in sets if s.pk in named_pks]
            for chosen in named_here:
                named_pks.remove(chosen.pk)
            exclusive = group is None or group.choose in ("one", "one-or-none")
            if exclusive and len(named_here) > 1:
                raise ValueError(
                    f"{group.name if group else 'The options'} of {self.name} "
                    f"offer at most one choice; {len(named_here)} were named."
                )
            if not named_here and (group is None or group.choose == "one"):
                named_here = sets[:1]
            taken.extend(named_here)
        if named_pks:
            strays = [c.name for c in named if c.pk in named_pks]
            raise ValueError(f"{self.name} does not offer: {', '.join(strays)}.")
        return taken

    def options_taken(self, recorded_sets):
        """The options something was acquired with, in the offer's own order.

        ``recorded_sets`` is the ids of the sets recorded against it,
        because a set is what materialises. Acquiring something records
        every set it took, each pick-one group's head included, so what
        comes back is what the thing actually has. Nothing is inferred
        where nothing was recorded: something that arrived by another
        road than a purchase — kit built into a profile, say — took no
        options and had none materialised, and naming a group's head
        would credit it with a weapon nobody ever gave it.

        Groups offering no choice are left out, the same test the buying
        screen makes: a pick-one set with a single option is taken
        unasked, and naming it would tell a reader about a decision
        nobody made.

        Nothing stops two options bringing the same set, and a taking
        records the set rather than the wording that reached it. Each
        recorded set is therefore spent on the first option offering it,
        exactly as ``resolve_selection`` spends what a player named — a
        set taken once is named once, however many ways there were to
        ask for it.
        """
        unspent = set(recorded_sets)
        taken = []
        for group, offered in self.grouped_offers():
            one_of = (group.choose if group is not None else "one") == "one"
            if one_of and len(offered) < 2:
                continue
            for option in offered:
                if option.default_set_id in unspent:
                    unspent.discard(option.default_set_id)
                    taken.append(option)
        return taken

    def price_with(self, selection=None, base=None):
        """This, its built-ins, and every set taken with it.

        The advertised price is this with nothing named — composed rather
        than read, because acquiring this buys its built-ins and whichever
        option comes as standard, so the stored ``price`` is only the
        first term. ``Assignable.reference_price`` asks for exactly that.

        ``selection`` as in ``resolve_selection`` — a set, a list of sets,
        or ``None`` for the advertised price (each one-of group's default;
        nothing from the any-of groups).

        ``base`` replaces the item's *own* price and nothing else, which
        is what an equipment list's override means: a house pricing a
        mount at 140 has not made its 15-credit weapon swap free.
        """
        own = self.price if base is None else base
        taken = self.resolve_selection(selection)
        return (
            own
            + (self.built_ins.price if self.built_ins else 0)
            + sum(chosen.price for chosen in taken)
        )


#: What ``grouped_offers`` reads, as prefetch paths. A listing that
#: prefetches these for every kind carrying ``Optioned`` puts the choices
#: in front of a buyer without a query per line — the option rows, the
#: group each belongs to, and the set each would materialise, which is
#: also where an option's price is stored.
OPTION_OFFER_PATHS = ("options__group", "options__default_set")


class Wargear(Content, Assignable, UsableBy, Optioned):
    """Equipment that isn't a weapon — armour, grenades, pets, field gear.

    Carried by a model, and priced like anything else. A thing that
    bolts onto a *weapon* is not this: see ``WeaponAccessory``, which
    hangs off the weapon's assignment and carries the bracket saying
    what it fits.
    """

    family = Family.GEAR

    class Meta:
        verbose_name = "wargear"
        verbose_name_plural = "wargear"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="wargear_unique_per_pack",
            ),
            exclusive_has_no_trade_points("wargear"),
        ]


class WeaponAccessory(Content, Assignable, UsableBy):
    """Something bolted onto a weapon — a sight, suspensors, a crystal.

    Its own kind, because it behaves like nothing else does. It is
    assigned to a *weapon* rather than to a model, so it hangs off that
    weapon's assignment and its effects land on that weapon's profiles
    (``TargetsAttachedWeapon``). And the book restricts many of them in
    the name's brackets — "Focusing Crystal (Las Weapons Only)",
    "Suspensors (Weapons Marked With * Only)" — a fact about accessories
    that would be nonsense on a suit of armour.

    The ``fits_*`` fields are that bracket as data: another dialect of
    the one selector grammar, informing at browse and attach, policing
    nothing.
    """

    family = Family.GEAR
    attaches_to_weapons = True

    fits_category = models.ForeignKey(
        "library.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            'Fits weapons homed in this category only — the "Las Weapons" '
            'in "(Las Weapons Only)". Blank fits anything.'
        ),
    )
    fits_asterisked = models.BooleanField(
        default=False,
        help_text=(
            'Fits two-slot weapons only — "(Weapons Marked With * Only)", '
            "the Suspensors rule."
        ),
    )

    class Meta:
        verbose_name = "weapon accessory"
        verbose_name_plural = "weapon accessories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="weapon_accessory_unique_per_pack",
            ),
            exclusive_has_no_trade_points("weapon_accessory"),
        ]

    def fits_selector(self):
        """Which weapons this may be fitted to, in the one grammar."""
        from n26.core import select

        conditions = []
        if self.fits_category_id is not None:
            conditions.append(select.HomedIn(self.fits_category))
        if self.fits_asterisked:
            conditions.append(select.TakesSlots(2))
        if not conditions:
            return select.Anything()
        return conditions[0] if len(conditions) == 1 else select.All(*conditions)

    def fits(self, weapon):
        """Whether this belongs on that weapon. Information, never a gate."""
        from n26.core import select

        return self.fits_selector().matches(select.matchable(weapon))


class Trait(Content, Assignable):
    """A weapon trait: Melee, Rapid Fire (1), Knockback (6+).

    The parameter is the annotation, so Knockback (5+) and Knockback (6+) are
    two rows. No rules text — the rulebook's words are copyrighted and must
    never be stored in content (see CLAUDE.md).
    """

    family = Family.GEAR

    class Meta:
        verbose_name = "trait"
        verbose_name_plural = "traits"
        ordering = ["name", "annotation"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("annotation"),
                Lower("qualifier"),
                name="trait_unique_per_pack",
            ),
            exclusive_has_no_trade_points("trait"),
        ]


class Weapon(Content, Assignable, UsableBy):
    """A weapon. Always has at least one profile, the first of which is free.

    ``UsableBy`` because a shared house list narrows a few of its lines to
    one fighter entry — "Wyld bow (Wyld Runner only)".
    """

    family = Family.GEAR

    slots = models.PositiveIntegerField(
        default=1,
        help_text="Weapon slots used on a card. Asterisked weapons take 2.",
    )
    statline_type = models.ForeignKey(
        "library.StatlineType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="weapons",
        help_text=(
            "The shape of this weapon's profiles — SR, LR, Str, AP, L. Set it "
            "once on the weapon; every profile's statline reads it from here."
        ),
    )

    class Meta:
        verbose_name = "weapon"
        verbose_name_plural = "weapons"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="weapon_unique_per_pack",
            ),
            exclusive_has_no_trade_points("weapon"),
        ]

    def has_trait(self, name):
        """Whether any of this weapon's profiles carries the trait.

        The weapon-level question rules ask — "a weapon with the Heavy or
        Paired trait" (Mounted) — derived from the profiles, where traits
        actually live.
        """
        return any(
            trait.name.lower() == name.lower()
            for profile in self.profiles.all()
            for trait in profile.traits.all()
        )


class WeaponProfile(Content, Assignable):
    """One of a weapon's profiles. Assignable in its own right — buying an
    extra ammo type is an assignment hung off the weapon's assignment."""

    family = Family.GEAR
    attaches_to_weapons = True

    #: A profile means nothing apart from its gun, so the generic
    #: built-in picker never offers one cold: it is built in from a
    #: weapon member's own row, where which gun it rides is already
    #: settled.
    offered_as_built_in = False

    #: Overrides the mixin's: most profiles have no name of their own.
    #: The book prints the weapon's first line as the weapon — "Autogun"
    #: — and names only the lines beneath it, "- warp round". A blank
    #: name means this *is* the weapon's line.
    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Only for a line the book names — an ammo type like warp "
            "round. Leave blank for the weapon's own line, which prints "
            "as the weapon."
        ),
    )
    weapon = models.ForeignKey(
        Weapon, on_delete=models.CASCADE, related_name="profiles"
    )
    # ``price`` comes from the Assignable mixin — a weapon's first profile is
    # free (0, the default); paid ammo prices its own row, as the book does.
    # ``position`` overrides the mixin's: here it orders profiles within
    # their weapon rather than within a category.
    position = models.PositiveIntegerField(default=0)
    traits = models.ManyToManyField(
        Trait,
        blank=True,
        related_name="weapon_profiles",
        help_text=(
            "The traits this profile has by default. Computed onto cards, "
            "never copied player-side, so a content fix reaches every "
            "existing weapon."
        ),
    )

    class Meta:
        verbose_name = "weapon profile"
        verbose_name_plural = "weapon profiles"
        ordering = ["weapon", "position"]
        constraints = [
            exclusive_has_no_trade_points("weapon_profile"),
            # A weapon has one line that *is* the weapon; everything
            # else the book names. Two unnamed lines would print as the
            # weapon twice, with no way to tell them apart.
            models.UniqueConstraint(
                fields=["weapon"],
                condition=models.Q(name=""),
                name="one_unnamed_profile_per_weapon",
            ),
        ]

    def __str__(self):
        """What a card's line reads.

        Named, it is the ammo type and the gun it belongs to — "Warp
        round (Autogun)". Unnamed, it is simply the gun, because that
        is the line the book prints.
        """
        if not self.name:
            return self.annotation or "—"
        return super().__str__()

    @property
    def is_free(self):
        """Priced at nothing in the catalogue — true of every weapon's
        first profile. A *card* line cannot ask this: a zero there is a
        rating contribution, which says nothing about worth."""
        return self.price == 0

    @property
    def statline_type(self):
        """The shape of this profile's stats — fixed by the weapon."""
        return self.weapon.statline_type

    @property
    def trait_names(self):
        """Display strings, in name order. Uses prefetched rows if present."""
        return sorted(str(trait) for trait in self.traits.all())


class Subtype(Content, Assignable):
    """A model subtype: Leader, Ganger, Specialist, Mounted, Wyrd."""

    family = Family.MODEL
    card_row = "subtypes"

    class Meta:
        verbose_name = "subtype"
        verbose_name_plural = "subtypes"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="subtype_unique_per_pack",
            ),
            exclusive_has_no_trade_points("subtype"),
        ]


class Skill(Content, Assignable, UsableBy):
    """A skill a fighter has selected, homed in the set it comes from.

    That set is its home category — the taxonomy every collection
    shares — and its D6 number in the book is its position within it."""

    family = Family.MODEL
    card_row = "skills"

    class Meta:
        verbose_name = "skill"
        verbose_name_plural = "skills"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="skill_unique_per_pack",
            ),
            exclusive_has_no_trade_points("skill"),
        ]


class Rule(Content, Assignable):
    """A named special rule on a fighter's card — "Automated Repair
    Systems", "Combat Chems Stash".

    The card prints these apart from Skills (an Exo-Driller has both, under
    separate headings), so they are their own kind. Name and annotation
    only — the rule's text is copyrighted and is never stored (CLAUDE.md).
    A rule that also *does* something the app can compute carries ordinary
    modifiers.

    The annotation is part of the identity, exactly as it is for a
    ``Trait``: a rule that comes in variants — a leash at several
    distances — is several rows sharing one printed name, not one row
    that cannot decide.

    Normally it arrives built into something (a profile's kit, a gang
    type) or given by a modifier. Reach follows the host: built into a
    profile it prints on that model's card; held by the gang it is
    broadcast to every member's card.
    """

    family = Family.BASE
    card_row = "rules"

    class Meta:
        verbose_name = "special rule"
        verbose_name_plural = "special rules"
        ordering = ["name", "annotation"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("annotation"),
                Lower("qualifier"),
                name="rule_unique_per_pack",
            ),
            exclusive_has_no_trade_points("rule"),
        ]


class Affiliation(Content, Assignable):
    """Who the gang sides with, chosen once when the gang is created.

    A chosen carrier: the whole of what it means rides it as ordinary
    modifiers, and it is its own kind so the card says "Affiliation:".
    An affiliation's payload is typically *access* —
    equipment lists opened to some ranks, so its gives are scoped while
    the affiliation itself rides gang-wide — and an affiliation may
    itself offer a further choice (Clan House's "choose one of the six
    Houses"): what is chosen is an ordinary assignment hosted on the
    gang, so a choice carried on it simply computes into another slot.
    """

    family = Family.GANG
    # Chosen, never acquired: nothing would materialise items built in.
    takes_built_ins = False

    class Meta:
        verbose_name = "affiliation"
        verbose_name_plural = "affiliations"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="affiliation_unique_per_pack",
            ),
            exclusive_has_no_trade_points("affiliation"),
        ]


class Hidden(Content, Assignable):
    """A carrier for effects that draws no row of its own.

    Some printed rules are a side effect with no item behind them — the
    Arachni-Rig's guns each knock a point off its Attacks. The change
    belongs to *taking that option*, not to the gun (rad guns elsewhere
    cost no Attacks), so the option's set includes one of these
    carrying the modifier.

    Being its own kind is the whole mechanism: no collection sweeps it in
    (a sweep names kinds, and no listing stocks Hidden), and card
    renderers skip its row. Its *effects* still show — a shifted stat
    names it in the cell's provenance — so nothing it does is secret,
    only its row. Fully visible in the content library.

    Both givable and takeable-away, so one take-away cancels a whole
    bundle.
    """

    family = Family.BASE

    class Meta:
        verbose_name = "hidden assignable"
        verbose_name_plural = "hidden assignables"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="hidden_unique_per_pack",
            ),
            exclusive_has_no_trade_points("hidden"),
        ]


class Counter(Content, Assignable):
    """A named tally a model keeps: XP, Kill Count, Loot.

    The *definition* is content — who has one is ordinary assignment
    (XP rides every fighter entry's built-ins, with its opening value on
    the set's member). The running value is player-side state on the
    assignment (``n26.core.models.CounterValue``), changed only through
    ``op.tally``, which writes ledger events.

    The point of counters is that **effects hang off values**: a scope
    conditioned ``when_counter=xp, at_least=5`` reveals a promotion
    choice or confers a title the moment the threshold is crossed, and
    withdraws it if the value drops — computed, like everything else.
    """

    family = Family.BASE

    #: Building a counter in is what carries its opening value — the 61
    #: in "Starting XP 61" — so that is what attaching one asks for.
    ATTACHMENT_ASKS = {"built-in": ("amount",)}

    drawn = models.BooleanField(
        default=True,
        help_text=(
            "Drawn on the model card and editable on the fighter page. "
            "Turn off for a counter that is only there for conditions "
            "to check."
        ),
    )

    class Meta:
        verbose_name = "counter"
        verbose_name_plural = "counters"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="counter_unique_per_pack",
            ),
            exclusive_has_no_trade_points("counter"),
        ]


class Power(Content, Assignable, UsableBy):
    """A Wyrd power — manifested, not taught.

    Not a skill, but its family is a category, so it shows up in the
    same fighter-sectioned views as the skill sets, with no special
    casing (the rulebook: Wyrds treat the powers list as a Secondary
    Skill Set).

    The annotation carries what the book prints in brackets after the
    name — "(Free), Continuous Effect" — action type and upkeep, never
    rules text. Powers that manifest as weapons will reference ordinary
    weapon content when battle rendering wants them.
    """

    family = Family.MODEL
    card_row = "powers"

    class Meta:
        verbose_name = "power"
        verbose_name_plural = "powers"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="power_unique_per_pack",
            ),
            exclusive_has_no_trade_points("power"),
        ]


# Selector lookup paths: how "has trait X" compiles when filtering these
# models in the database. In-memory matching does not use these.
def _register_selector_lookups():
    from n26.core import select

    select.register_lookup(WeaponProfile, Trait, "traits")
    select.register_lookup(Weapon, Trait, "profiles__traits")


_register_selector_lookups()
