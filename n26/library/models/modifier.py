"""Modifiers — what an assignable does once assigned.

A modifier is attached to a specific assignable — its **carrier** —
asserting who it reaches (its **scope**) and what it does (its
**effect**). The thing an effect lands on is the **bearer**. Each of the
two parts is exactly one small typed row hanging off the modifier::

    TargetsWeapons(with_trait=Melee)  +  AddsAssignable(trait=Backstab)
    TargetsMiniature()                +  AddsAssignable(subtype=Mounted)
    TargetsMiniature()                +  ChangesStat(BS, worsen, 1)

Splitting them means a new way of *selecting* things is a new scope model
with its own ``targets()``, and nothing else in the system learns anything
about it. The foreign keys point out of ``Modifier`` so both
exactly-one rules are real database check constraints, the way assignment
hosts and statline owners are.

Nothing here stores rules text — see CLAUDE.md.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils.text import capfirst

from n26.core.constraints import exactly_one_of
from n26.library.models.base import Content

#: The kinds of thing a scope can select.
MODEL = "model"
WEAPON_PROFILE = "weapon_profile"
GANG = "gang"

#: Modifier columns holding a scope, and holding an effect.
SCOPE_FIELDS = (
    "targets_miniature",
    "targets_weapons",
    "targets_attached_weapon",
    "targets_gang",
)
#: Effects re-derived on every read by ``n26.effects.compute``, which
#: vanish with their carrier.
COMPUTED_EFFECT_FIELDS = (
    "adds_assignable",
    "removes_assignable",
    "changes_stat",
    "changes_category",
    "offers_choice",
    "places_category",
    "requires_companions",
    "allows_at_most",
)

#: Effects that write player data — an assignment, a ledger event — run
#: once by ``n26.operations`` when the carrier arrives, and never undone
#: by its removal. Prefixed ``Op`` so the distinction is visible at the
#: call site.
STORED_EFFECT_FIELDS = ("op_adds_miniature", "op_changes_counter")

#: Kinds an OffersChoice may name. Growing this is one line plus deliberate
#: thought — clean() refuses anything else, and the boot check screams if a
#: kind named here has no Assignment column to resolve into.
#: ``skilltree`` is a token whose home names the set (Venators);
#: ``archetype`` and ``affiliation`` are chosen carriers whose whole
#: payload rides them as modifiers (Outcasts, design/outcasts.md);
#: ``subtype`` because some *types* are chosen — an Enforcer Haunt
#: selects Psyrender or Bonecrusher, and the pick is a fact other rules
#: may match on.
OFFERABLE_KINDS = (
    "specialisation",
    "power",
    "skill",
    "skilltree",
    "archetype",
    "affiliation",
    "subtype",
)

EFFECT_FIELDS = (*COMPUTED_EFFECT_FIELDS, *STORED_EFFECT_FIELDS)

#: Which assignable kinds an AddsAssignable/RemovesAssignable can name.
GRANTABLE_FIELDS = {
    "subtype": "library.Subtype",
    "skill": "library.Skill",
    "trait": "library.Trait",
    # Granting a collection grants access to browse it — Tech Bazaar's
    # standing Trading Post access; an alliance opening another list.
    "collection": "library.Collection",
    # A named special rule the bearer gains — "all Escher fighters may…",
    # carried by the gang type and reaching each member.
    "rule": "library.Rule",
    # A power the bearer knows without having learned it — a psyker entry
    # whose sheet says it manifests something from the start. Skill-like:
    # a fact on the card, gone when the granter goes.
    "power": "library.Power",
    # Free kit: a beast's claws, a vehicle's fixed gun. The weapon and its
    # firing lines are worked out at read time, so they add nothing to the
    # gang's rating, are never paid for, cannot be sold, and go when the
    # thing that granted them goes. The only grantable kind with a price
    # and with children of its own — see ``n26.core.effects``, which
    # builds the card nodes a granted weapon needs.
    "weapon": "library.Weapon",
    # A carrier that draws no row, so naming one is naming a *bundle*:
    # everything the hidden thing does arrives or departs together. What
    # a gang's own rules hang off, so that one "takes away" can cancel
    # the lot — see recipes.md, the corrupted gang.
    "hidden": "library.Hidden",
    # A further choice: picking Clan House opens the House choice.
    # Un-choosing the first retracts the second and its pick through the
    # ordinary cause chain. The *pickable* is deliberately not here — a
    # pickable handed over with no slot to answer shows nothing and does
    # nothing, so giving one could only be a mistake.
    "slot": "library.Slot",
}

#: What an ``AllowsAtMost`` may count. The books limit ranks ("no
#: Brutes"), fighter entries ("0–2 Aberrants") and gear ("one Familiar
#: each") and nothing else, so the three are named rather than the whole
#: run of assignable kinds.
COUNTABLE_FIELDS = {
    "subtype": "library.Subtype",
    "profile": "library.Profile",
    "wargear": "library.Wargear",
}


@dataclass(frozen=True)
class Target:
    """One thing a scope selected.

    ``kind`` is ``MODEL`` or ``WEAPON_PROFILE``. ``node`` is the card node
    for a weapon profile, and ``None`` for the model itself.
    """

    kind: str
    node: object = None


# --- Scopes: what a modifier reaches ------------------------------------


class TargetsMiniature(models.Model):
    """The model carrying the assignable — optionally only some models.

    Unfiltered, this is the ordinary case: whatever carries the modifier
    is what it affects. Narrowing is done by **condition rows** hanging
    off this scope (``HasSubtypes``, ``CounterAtLeast``) — one row per
    condition, so a new way of narrowing is a new small model, never a
    new column here. No rows means everyone, the same default-open rule
    ``UsableBy`` uses.

    The stored shape is this scope's own — a tailored admin form,
    PROTECTed references — but it is a *dialect*: ``as_selector()``
    compiles it to the one grammar (``n26.core.select``) and matching runs
    through that engine, as every persisted selector's does. See
    design/selectors.md.
    """

    #: Reverse relations ``as_selector()`` folds, in order. The boot
    #: check (n26.E003/E004) verifies this names exactly the condition
    #: models that FK this scope — a condition nothing folds would be
    #: silently dead.
    CONDITIONS = ("has_subtypes", "is_profile", "has_pickable", "counter_at_least")

    #: Positional, not factual — read off the carrier node, like
    #: ``TargetsAttachedWeapon``. An archetype assigned to a Champion
    #: applies to that Champion, never to every Champion because the gang
    #: holds one: same carrier, and the host decides.
    when_directly_assigned = models.BooleanField(
        default=False,
        help_text=(
            "Only the model this is directly assigned to — never reached "
            "through the gang's broadcast."
        ),
    )

    class Meta:
        verbose_name = "targets the model"
        verbose_name_plural = "target the model"

    def __str__(self):
        parts = [str(row) for row in self._condition_rows()] if self.pk else []
        described = ", ".join(parts) if parts else "the model"
        if self.when_directly_assigned:
            described += " (bearer only)"
        return described

    @property
    def narrows(self):
        """Whether this scope reaches fewer than everything of its kind."""
        return bool(self.pk and self._condition_rows()) or self.when_directly_assigned

    def _condition_rows(self):
        return [
            row for related in self.CONDITIONS for row in getattr(self, related).all()
        ]

    def as_selector(self):
        """What this scope's filter says, compiled once per instance.

        Scope rows are shared across every card in a render via the
        modifier index, so the compiled tree is built once and reused —
        content edits arrive on fresh instances, never mid-render.
        """
        compiled = getattr(self, "_compiled_selector", None)
        if compiled is None:
            from n26.core import select

            conditions = [
                folded
                for row in self._condition_rows()
                if (folded := row.as_condition()) is not None
            ]
            if not conditions:
                compiled = select.Anything()
            elif len(conditions) == 1:
                compiled = conditions[0]
            else:
                compiled = select.All(*conditions)
            self._compiled_selector = compiled
        return compiled

    def targets(self, card, facts, carrier=None):
        """The model, when the fighter matches.

        ``facts`` is the round snapshot ``compute`` hands in — printed
        facts plus everything settled by earlier rounds. It is required:
        there is exactly one way scopes are asked, and anything wanting
        "who would this reach?" should run compute and read the plan.

        On a gang's own card this targets nothing: the unfiltered case
        compiles to ``Anything``, which must not swallow the gang. The
        symmetric rule lives on ``TargetsGang``.
        """
        if getattr(card, "host_kind", MODEL) != MODEL:
            return []
        if self.when_directly_assigned and (carrier is None or carrier.broadcast):
            # The gang's broadcast of this assignment reaches nobody; only
            # the model it is hosted on. A discovered (granted) carrier
            # hangs off no assignment at all, so it has no bearer.
            return []
        if self.as_selector().matches(facts.model()):
            return [Target(kind=MODEL)]
        return []


# --- Conditions: how a scope narrows -------------------------------------
#
# One row per condition, FK'ing the scope it narrows. Each knows how to
# fold itself into the selector grammar (``as_condition``) and how to say
# itself (``__str__`` — plan traces and auto-names compose these). All of
# a scope's rows are ANDed; alternatives live inside a row (a
# ``HasSubtypes`` with several subtypes is any-of).


#: The words a negated condition reads with, and the words a plain one
#: does. A condition names alternatives and then says whether it wants
#: them or wants everything else — "Leader or Champion models", "every
#: model except Champions" — so the two readings share one shape.
_EXCEPT = "every model except "
_THESE = " models"


def _negatable():
    """The column a condition carries to mean "everything but these".

    Most scoping names the ranks it reaches, and naming a further one is
    a value on the row. This is for the rule easier to state the other
    way round, where writing out everyone else would be a list that goes
    stale the day a subtype is added. It sits on the conditions naming a
    *membership* (a subtype, an entry, a pick); a threshold's opposite
    is a different question and is not written this way.
    """
    return models.BooleanField(
        default=False,
        help_text=(
            "Reach everything this does not name — every model except "
            "these. Other conditions still narrow it further."
        ),
    )


def _some_of(rows):
    """A few names said whole, a crowd said by its size.

    Condition strings ride into plan traces and auto-composed modifier
    names, and a row naming twenty profiles would write a name no column
    holds and no reader finishes. Three names is where a list stops
    reading as alternatives and starts reading as an inventory.
    """
    names = [str(row) for row in rows]
    if len(names) <= 3:
        return " or ".join(names)
    return f"{names[0]}, {names[1]} or {len(names) - 2} more"


class HasSubtypes(models.Model):
    """Condition: the model has one of these subtypes.

    "Leaders and Champions each select a skill" is one row naming both —
    any-of within the row. Wanting Mounted *and* Wyrd is two rows.
    Negated, it is the same row read the other way: everyone the row
    does not name.
    """

    scope = models.ForeignKey(
        TargetsMiniature,
        on_delete=models.CASCADE,
        related_name="has_subtypes",
    )
    subtypes = models.ManyToManyField(
        "library.Subtype",
        related_name="+",
        help_text="The model must have at least one of these subtypes.",
    )
    negate = _negatable()

    class Meta:
        verbose_name = "has subtypes"
        verbose_name_plural = "has subtypes"

    def __str__(self):
        wanted = list(self.subtypes.all()) if self.pk else []
        if self.negate:
            return _EXCEPT + _some_of(wanted)
        return _some_of(wanted) + _THESE

    def as_condition(self):
        from n26.core import select

        wanted = list(self.subtypes.all())
        if not wanted:
            # An empty row narrows nothing — never "matches nobody", and
            # never "matches everybody but nobody" when negated either.
            return None
        matched = select.Any(*(select.Has(subtype) for subtype in wanted))
        return select.Not(matched) if self.negate else matched


class IsProfile(models.Model):
    """Condition: the model is one of these profiles, named outright.

    For a row about particular entries where no subtype picks them out —
    an archetype's Champion row reaches "Outcast Champion" the profile,
    not everything ranked champion. Being an entry is identity, not a
    possession: the fighter matchable's thing is their profile, so this
    folds to ``Exactly`` where ``HasSubtypes`` folds to ``Has``.
    """

    scope = models.ForeignKey(
        TargetsMiniature,
        on_delete=models.CASCADE,
        related_name="is_profile",
    )
    profiles = models.ManyToManyField(
        "library.Profile",
        related_name="+",
        help_text="The model must be one of these profiles.",
    )
    negate = _negatable()

    class Meta:
        verbose_name = "is the profile"
        verbose_name_plural = "is the profile"

    def __str__(self):
        wanted = list(self.profiles.all()) if self.pk else []
        if self.negate:
            return _EXCEPT + _some_of(wanted)
        return _some_of(wanted) + _THESE

    def as_condition(self):
        from n26.core import select

        wanted = list(self.profiles.all())
        if not wanted:
            # An empty row narrows nothing — never "matches nobody".
            return None
        matched = select.Any(*(select.Exactly(profile) for profile in wanted))
        return select.Not(matched) if self.negate else matched


class HasPickable(models.Model):
    """Condition: the model has one of these picked.

    "Models with the Cawdor legacy" — one condition serving every slot
    type ever authored, because what was picked is an ordinary
    assignment and picking it is an ordinary possession. Any-of within
    the row; negated, it is everyone who picked something else.

    A pick with no slot behind it is not a possession, so it is not
    matched here either: a pickable nobody was offered says nothing about
    the model holding it.
    """

    scope = models.ForeignKey(
        TargetsMiniature,
        on_delete=models.CASCADE,
        related_name="has_pickable",
    )
    pickables = models.ManyToManyField(
        "library.Pickable",
        related_name="+",
        help_text="The model must have picked at least one of these.",
    )
    negate = _negatable()

    class Meta:
        verbose_name = "has pickable"
        verbose_name_plural = "has pickable"

    def __str__(self):
        wanted = list(self.pickables.all()) if self.pk else []
        if self.negate:
            return _EXCEPT + _some_of(wanted)
        return _some_of(wanted) + _THESE

    def as_condition(self):
        from n26.core import select

        wanted = list(self.pickables.all())
        if not wanted:
            return None
        matched = select.Any(*(select.Has(pickable) for pickable in wanted))
        return select.Not(matched) if self.negate else matched


class CounterAtLeast(models.Model):
    """Condition: the model's counter has reached a threshold.

    The "at 5 XP" in a promotion offer. Stored dialect of the selector
    leaf of the same name (``n26.core.select.CounterAtLeast``), which
    ``as_condition`` folds it into.
    """

    scope = models.ForeignKey(
        TargetsMiniature,
        on_delete=models.CASCADE,
        related_name="counter_at_least",
    )
    counter = models.ForeignKey(
        "library.Counter",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The counter whose value is checked.",
    )
    at_least = models.PositiveIntegerField(
        default=0,
        help_text="The value the counter must have reached.",
    )

    class Meta:
        verbose_name = "counter at least"
        verbose_name_plural = "counter at least"

    def __str__(self):
        return f"at {self.counter} {self.at_least}+"

    def as_condition(self):
        from n26.core import select

        return select.CounterAtLeast(self.counter, self.at_least)


class TargetsWeapons(models.Model):
    """The bearer's weapons — optionally only some of them.

    Narrowing is done by **condition rows**, as on ``TargetsMiniature``:
    one row per way of narrowing, each naming as many values as it likes.
    Within a row the values are alternatives; across rows they stack. So
    "any Las or Plasma weapon that also has Unstable" is two rows, and
    "all Las weapons" is one row naming one category.

    No rows means every weapon the bearer has — the same default-open
    rule the model scope uses.
    """

    #: Reverse relations ``as_selector()`` folds, in the order their
    #: sentences read. The boot check (n26.E003/E004) verifies this names
    #: exactly the condition models that FK this scope.
    CONDITIONS = ("is_one_of", "in_categories", "has_traits")

    class Meta:
        verbose_name = "targets weapons"
        verbose_name_plural = "target weapons"

    def __str__(self):
        parts = [str(row) for row in self._condition_rows()] if self.pk else []
        return f"weapons {', '.join(parts)}" if parts else "all weapons"

    @property
    def narrows(self):
        """Whether this scope reaches fewer than everything of its kind."""
        return bool(self.pk and self._condition_rows())

    def _condition_rows(self):
        return [
            row for related in self.CONDITIONS for row in getattr(self, related).all()
        ]

    def as_selector(self):
        """What this scope's conditions say, in the selector vocabulary.

        Rows stack: a scope naming a category and a trait reaches the
        weapons answering both. Matching runs against the round snapshot
        ``compute`` provides — printed traits plus what earlier (less
        specific) rounds added. Compiled once per instance, as on
        ``TargetsMiniature``.
        """
        compiled = getattr(self, "_compiled_selector", None)
        if compiled is None:
            from n26.core import select

            conditions = [
                folded
                for row in self._condition_rows()
                if (folded := row.as_condition()) is not None
            ]
            if not conditions:
                compiled = select.Anything()
            elif len(conditions) == 1:
                compiled = conditions[0]
            else:
                compiled = select.All(*conditions)
            self._compiled_selector = compiled
        return compiled

    def targets(self, card, facts, carrier=None):
        from n26.core import select

        chosen = self.as_selector()
        return [
            Target(kind=WEAPON_PROFILE, node=node)
            for node in card.weapon_profile_nodes()
            if chosen.matches(
                facts.weapon(node)
                if facts is not None
                else select.matchable(node.assignable)
            )
        ]


# --- Conditions on the weapon scope ---------------------------------------
#
# The same grammar the model scope's conditions use: one row per way of
# narrowing, any-of within a row, all rows ANDed. Each says itself as a
# clause, because the scope's sentence is those clauses joined and that
# sentence becomes a modifier's name.


class IsOneOf(models.Model):
    """Condition: the weapon is one of these.

    Naming guns outright, for a rule about a particular weapon rather
    than about a kind of weapon — "Helamite claws gain Additional
    Attacks (1)", where no trait or category picks the claws out
    reliably.
    """

    scope = models.ForeignKey(
        TargetsWeapons,
        on_delete=models.CASCADE,
        related_name="is_one_of",
    )
    weapons = models.ManyToManyField(
        "library.Weapon",
        related_name="+",
        help_text="The weapon must be one of these. Any one of them matching is enough.",
    )

    class Meta:
        verbose_name = "is one of"
        verbose_name_plural = "is one of"

    def __str__(self):
        wanted = list(self.weapons.all()) if self.pk else []
        return "named " + " or ".join(str(weapon) for weapon in wanted)

    def as_condition(self):
        from n26.core import select

        wanted = list(self.weapons.all())
        if not wanted:
            # An empty row narrows nothing — never "matches nothing".
            return None
        return select.Any(*(select.LineOf(weapon) for weapon in wanted))


class InCategories(models.Model):
    """Condition: the weapon is homed in one of these categories.

    "Van Saar gangs get an AP improvement of 1 on all Las weapons" is
    one row naming the Las Weapons category.
    """

    scope = models.ForeignKey(
        TargetsWeapons,
        on_delete=models.CASCADE,
        related_name="in_categories",
    )
    categories = models.ManyToManyField(
        "library.Category",
        related_name="+",
        help_text=(
            "The weapon must be homed in one of these categories. Any one "
            "of them matching is enough."
        ),
    )

    class Meta:
        verbose_name = "in categories"
        verbose_name_plural = "in categories"

    def __str__(self):
        # Each category's own name, as every other sentence naming one
        # says it. Two categories sharing a name across sections read
        # alike here; the composer refuses the duplicate name in words.
        wanted = list(self.categories.all()) if self.pk else []
        return "in " + " or ".join(category.name for category in wanted)

    def as_condition(self):
        from n26.core import select

        wanted = list(self.categories.all())
        if not wanted:
            return None
        return select.Any(*(select.HomedIn(category) for category in wanted))


class HasTraits(models.Model):
    """Condition: the weapon carries one of these traits.

    Matched against the round snapshot, so a trait an earlier modifier
    added counts — a scope naming Melee reaches a knife that was given
    Melee, not only one printed with it.
    """

    scope = models.ForeignKey(
        TargetsWeapons,
        on_delete=models.CASCADE,
        related_name="has_traits",
    )
    traits = models.ManyToManyField(
        "library.Trait",
        related_name="+",
        help_text=(
            "The weapon must carry one of these traits. Any one of them "
            "matching is enough."
        ),
    )

    class Meta:
        verbose_name = "has traits"
        verbose_name_plural = "has traits"

    def __str__(self):
        wanted = list(self.traits.all()) if self.pk else []
        return "with " + " or ".join(str(trait) for trait in wanted)

    def as_condition(self):
        from n26.core import select

        wanted = list(self.traits.all())
        if not wanted:
            return None
        return select.Any(*(select.Has(trait) for trait in wanted))


class TargetsAttachedWeapon(models.Model):
    """The weapon this modifier's carrier is attached to.

    The weapon accessories: a telescopic sight is a wargear hung off a
    weapon's assignment, and its effects land on *that* weapon's
    profiles — not the model, not every weapon. Positional rather than
    factual, so its selector is ``Anything`` (round 0) and the thing it
    needs is the ``carrier`` node compute hands every scope: two
    identical sights on two guns each reach their own gun.
    """

    class Meta:
        verbose_name = "targets the attached weapon"
        verbose_name_plural = "target the attached weapon"

    def __str__(self):
        return "the weapon this is attached to"

    #: Positional, with nothing to filter: it reaches the one weapon it hangs
    #: off, and there is no narrower version of that.
    narrows = False

    def as_selector(self):
        from n26.core import select

        return select.Anything()

    def targets(self, card, facts, carrier=None):
        if carrier is None:
            return []  # a discovered (computed) carrier hangs off nothing
        for node in card.all_nodes():
            if carrier in node.children:
                return [
                    Target(kind=WEAPON_PROFILE, node=child)
                    for child in node.children
                    if child.is_weapon_profile
                ]
        return []


class TargetsGang(models.Model):
    """The gang carrying the assignable — the gang itself, not its members.

    The gang-level choices: a Venator gang ranks its skill trees once,
    for everyone, so the offer belongs on the *gang's* card and must not
    echo onto ten fighters (design/gang-sheet.md). Symmetric with
    ``TargetsMiniature``'s guard: each targets only its own kind of
    card, read off ``card.host_kind``, so an unfiltered selector on one
    never swallows the other. A modifier reaching *members* from a
    gang-hosted carrier uses ``TargetsMiniature`` instead; that is the
    broadcast.
    """

    class Meta:
        verbose_name = "targets the gang"
        verbose_name_plural = "target the gang"

    def __str__(self):
        return "the gang"

    #: There is one gang, so this scope has nothing to narrow to.
    narrows = False

    def as_selector(self):
        from n26.core import select

        return select.Anything()

    def targets(self, card, facts, carrier=None):
        if getattr(card, "host_kind", MODEL) != GANG:
            return []
        return [Target(kind=GANG)]


# --- Effects: what a modifier does to them ------------------------------


class AssignableChoice(models.Model):
    """Shared shape for effects that name one assignable."""

    is_stored = False

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
    trait = models.ForeignKey(
        "library.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    collection = models.ForeignKey(
        "library.Collection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    rule = models.ForeignKey(
        "library.Rule",
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
    weapon = models.ForeignKey(
        "library.Weapon",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    hidden = models.ForeignKey(
        "library.Hidden",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    slot = models.ForeignKey(
        "library.Slot",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True

    def __str__(self):
        return str(self.thing) if self.thing else "nothing"

    @property
    def thing(self):
        for name in GRANTABLE_FIELDS:
            if getattr(self, f"{name}_id") is not None:
                return getattr(self, name)
        return None

    def accepts(self, target_kind):
        """A trait goes on a firing line; most things go on a model; a
        rule, a collection or a hidden carrier may also land on the gang
        itself.

        A weapon goes on a model only: it is the model that carries a
        gun, and the gun's own firing lines are what a weapon-scoped
        modifier reaches once the grant has put them on the card. The
        gang's card carries named rules, standing lists, and the hidden
        carriers its own rules hang off — an alliance's "the gang
        gains…" — but has no type line, no skills row, and holds no
        weapons, so nothing else can land there. A slot may land on
        either: a gang is asked its affiliation, a fighter their legacy.
        """
        if self.trait_id is not None:
            return target_kind == WEAPON_PROFILE
        if target_kind == GANG:
            return (
                self.rule_id is not None
                or self.collection_id is not None
                or self.hidden_id is not None
                or self.slot_id is not None
            )
        return target_kind == MODEL


class AddsAssignable(AssignableChoice):
    """Gives the target something it would not otherwise have.

    A subtype, skill, trait, collection, rule — or a weapon, which is the
    one grantable kind that has a price and firing lines of its own. A
    granted weapon is free kit: it and its lines are worked out at read
    time, so nothing is bought, nothing is worth anything, and it lasts
    exactly as long as whatever granted it.

    Naming a hidden carrier gives a *bundle*: it draws no row, so what
    arrives is everything it in turn does.
    """

    class Meta:
        verbose_name = "adds assignable"
        verbose_name_plural = "adds assignables"
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(GRANTABLE_FIELDS),
                name="adds_assignable_exactly_one",
            ),
        ]

    def __str__(self):
        return f"adds {super().__str__()}"


class RemovesAssignable(AssignableChoice):
    """Takes one away, computed — Death of a Leader.

    It reaches what another modifier **granted** and what the card holds
    **innately**: a built-in gun, a rule that arrived with the gang type.
    A granted thing simply stops being given; an innate assignment is
    hidden — nothing is deleted, and dropping whatever cancelled it
    brings it straight back on the next read.

    Never what was paid for. A purchase is parted with by an operation,
    not by reading a card, so an assignment carrying credits or a rating
    of its own stays exactly where it is — and so does a free assignment
    with a purchase hanging beneath it, because an accessory somebody
    bought for a built-in gun must not be stranded.

    What the cancelled thing was itself doing goes with it, down the
    chain: name a hidden carrier and every rule it hands out departs
    together, which is how one of these takes away a whole bundle. A
    thing two carriers give survives losing one of them.
    """

    class Meta:
        verbose_name = "removes assignable"
        verbose_name_plural = "removes assignables"
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(GRANTABLE_FIELDS),
                name="removes_assignable_exactly_one",
            ),
        ]

    def __str__(self):
        return f"removes {super().__str__()}"


class OffersChoice(models.Model):
    """Puts an open question on the card: the bearer chooses one
    assignable of a given kind.

    Computed: the offer is a *slot* on the card, present while the carrier
    is; only what was chosen is ever stored (an assignment caused by the
    carrier's own). Unresolved is simply the absence of a resolution —
    nothing pending is written, so nothing pending can go stale, and
    deferring the pick costs nothing.

    ``of_kind`` is a plain foreign key to the ContentType row — a typed
    reference to a model *class*. This is not the content_type+object_id
    generic-FK pattern; there is no object id and nothing polymorphic to
    resolve at read time.
    """

    is_stored = False

    of_kind = models.ForeignKey(
        "contenttypes.ContentType",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "What kind of assignable may be chosen — a Specialisation, "
            "a Wyrd Power, a Skill."
        ),
    )
    from_section = models.ForeignKey(
        "library.CollectionSection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            'Narrow the offer to one section of a collection: "a Skill '
            'from a set that is Primary for this fighter". That section is '
            "part of the collection's own schema, the same row a placement "
            'aims at, so the admin picks "Primary (Skills & Powers)" rather '
            "than restating a name. Blank offers the whole kind."
        ),
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            'What the card calls this slot — "skill tree 1". Blank derives '
            "a label from the kind and any section, which is usually right. "
            'The label also picks the row: "Skills" or "Powers" files the '
            "question in that row of the card, beside what the fighter "
            "already has; any other wording is a row of its own. Unlabelled, "
            "the kind decides the same way."
        ),
    )

    class WillBeAssignedTo(models.TextChoices):
        #: The model (or gang) whose assignment carries the offered choice
        #: — the ordinary case: a Specialist's specialisation rides them.
        BEARER = "bearer", "the bearer"
        #: The Leader → Gang arrow:
        #: the Outcast Leader picks the archetype, but the pick belongs
        #: to the gang — what is chosen lands as a gang-hosted
        #: assignment, is broadcast to the members, and, being caused by
        #: the Leader's assignment, dies with the Leader.
        GANG = "gang", "the gang"

    will_be_assigned_to = models.CharField(
        max_length=20,
        choices=WillBeAssignedTo,
        default=WillBeAssignedTo.BEARER,
        help_text=(
            "Where the chosen thing's assignment will land. Almost always "
            "the bearer; a Leader's archetype pick is carried by the gang, "
            "not the Leader."
        ),
    )

    class Meta:
        verbose_name = "offers a choice"
        verbose_name_plural = "offers choices"

    def __str__(self):
        if self.from_section_id is not None:
            return f"offers a choice of {self.of_kind.name} from {self.from_section}"
        return f"offers a choice of {self.of_kind.name}"

    def save(self, *args, **kwargs):
        """Store the label the way a card has to show it.

        An author types "favoured archetype" and the slot beside it reads
        "Favoured archetype": a label is sentence case, and the surfaces
        drawing it should not each have to say so. Only the first
        character is touched — ``str.capitalize`` would lowercase the
        rest and flatten a name or an acronym the author meant. In
        ``save`` and not ``clean`` because ``objects.create`` never calls
        ``full_clean``: the authoring verbs and any importer must land
        the same value a form does.
        """
        self.label = capfirst(self.label)
        super().save(*args, **kwargs)

    @classmethod
    def of(
        cls,
        model,
        from_section=None,
        label="",
        will_be_assigned_to=WillBeAssignedTo.BEARER,
    ):
        from django.contrib.contenttypes.models import ContentType

        return cls.objects.create(
            of_kind=ContentType.objects.get_for_model(model),
            from_section=from_section,
            label=label,
            will_be_assigned_to=will_be_assigned_to,
        )

    @property
    def kind_label(self):
        """What the card calls this slot — "Primary skill", or "Skill".

        Sentence case whichever branch answers it, so every surface can
        draw what it is given: a stored label is canonicalised on the way
        in, and a derived one is built from a kind's verbose name, which
        is lowercase. One rule, stated here, is what lets the renderers
        hold none of their own.
        """
        if self.label:
            return self.label
        if self.from_section_id is not None:
            return capfirst(f"{self.from_section.name} {self.of_kind.name}")
        return capfirst(self.of_kind.name)

    def accepts(self, target_kind):
        # A model picks its specialisation; a gang picks its ranked
        # skill trees. Same slot machinery, two kinds of bearer.
        return target_kind in (MODEL, GANG)

    def selector(self):
        """What may be chosen, in the selector vocabulary.

        Kind only, deliberately. A section narrowing is *not* expressible
        here and should not be: which sets are Primary is a fact about the
        fighter, folded from their card, and a selector matches a thing in
        isolation. The narrowing shapes the pickable list instead — see
        ``n26.core.browse.offered_by`` — which is the right place for it,
        because a shorter list informs while a stricter selector would
        police.
        """
        from n26.core import select

        return select.OfKind(self.of_kind.model_class())

    def choosables(self):
        """Every pickable of the kind, ignoring any section narrowing.

        The whole-kind fallback, and what a fighterless context can
        answer. Ask ``n26.core.browse.offered_by`` for the list a *particular*
        fighter should see.
        """
        return self.selector().choosables()

    def clean(self):
        if self.of_kind_id and self.of_kind.model not in OFFERABLE_KINDS:
            allowed = ", ".join(OFFERABLE_KINDS)
            raise ValidationError(
                f"A choice of {self.of_kind.name} cannot be offered. "
                f"Offerable kinds: {allowed}."
            )


class PlacesCategory(models.Model):
    """For the bearer, one category of the taxonomy sits under a section.

    A skill set's *category* is fundamental — Agility is Agility for
    everyone. Its *section* is dynamic: the fighter's profile places
    Agility under "Primary", the Wyrd subtype places the powers family
    under "Secondary" ("Wyrds treat the Wyrd Powers as a Secondary Skill
    Set"), and anything unplaced falls back to "Other" at browse time.
    There is no access table and no grade vocabulary — just where a
    category appears for this fighter.

    Computed, so a placement appears and disappears with its carrier and
    knows its source. When two carriers place the same category, the
    **lowest section position wins** — ordering, the same rule as
    everywhere else — and those positions are the collection's own
    schema (``CollectionSection``), agreed once, not restated here.
    """

    is_stored = False

    category = models.ForeignKey(
        "library.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The skill set or power family being placed. Blank only when "
            "``the_chosen`` carries the naming instead."
        ),
    )
    #: The carrier-relative mode (design/venator-skill-trees.md): place
    #: whatever category the carrier's chosen thing is homed in. A
    #: Venator rank slot says "put *the chosen tree* under Primary" —
    #: which tree that is lives on what was chosen, not here. With
    #: nothing chosen, the placement simply does not happen, and the
    #: plan says why.
    the_chosen = models.BooleanField(
        default=False,
        help_text=(
            "Place whatever category the carrier's chosen thing is "
            "homed in, instead of naming one."
        ),
    )
    section = models.ForeignKey(
        "library.CollectionSection",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The collection section it appears under for the bearer — one "
            "of the collection's own sections, so the admin picks "
            '"Primary (Skills & Powers)" rather than restating a string '
            "and a number. Scopes the placement to that collection."
        ),
    )

    class Meta:
        verbose_name = "places category"
        verbose_name_plural = "places categories"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(the_chosen=False, category__isnull=False)
                    | models.Q(the_chosen=True, category__isnull=True)
                ),
                name="places_category_names_one_or_the_chosen",
            ),
        ]

    def __str__(self):
        named = "the chosen set" if self.the_chosen else self.category.name
        return f"puts {named} under {self.section}"

    def accepts(self, target_kind):
        return target_kind == MODEL


class RequiresCompanions(models.Model):
    """The gang keeps companions in ratio — "Lead the Masses": at least
    three Outcast Hive Scum on the roster for each Outcast Champion.

    Computed onto the **gang's** card as a note, never enforced: the
    book removes Champions from the roster; we say the roster is short
    and leave the gang to its owner. Counts are of members' printed
    hierarchy subtypes — a rank is hire-time built-in fact, not
    something modifiers grant mid-read.
    """

    is_stored = False

    for_each = models.ForeignKey(
        "library.Subtype",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The rank that must be propped up — each Champion.",
    )
    at_least = models.PositiveIntegerField(default=1)
    of = models.ForeignKey(
        "library.Subtype",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The companions required — three Hive Scum.",
    )

    class Meta:
        verbose_name = "requires companions"
        verbose_name_plural = "requires companions"

    def __str__(self):
        return f"needs {self.at_least} {self.of} for each {self.for_each}"

    def accepts(self, target_kind):
        return target_kind == GANG


class AllowsAtMost(models.Model):
    """The ceiling half of composition — "0–2 Genestealer Cult
    Aberrants", "up to one Psychic Familiar each", "no Brutes,
    Hangers-on or Pets from the gang's own list".

    The mirror of ``RequiresCompanions`` and computed the same way: a
    note on the sheet, never a refusal. **Nought is how a ban is
    written**, so a limit and a ban are one mechanism and an author never
    has to decide which of two they are writing.

    What gets counted follows the scope. Aimed at the gang it is a census
    of the roster — members by rank, by entry, and the gear they hold
    between them. Aimed at a model it is that model's own assignments,
    which is what "each" means in "up to one Familiar each".
    """

    is_stored = False

    at_most = models.PositiveIntegerField(
        default=0,
        help_text='How many may be held — the 2 in "0–2 Aberrants". Nought is a ban.',
    )
    subtype = models.ForeignKey(
        "library.Subtype",
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
    wargear = models.ForeignKey(
        "library.Wargear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "allows at most"
        verbose_name_plural = "allow at most"
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(COUNTABLE_FIELDS),
                name="allows_at_most_counts_exactly_one",
            ),
        ]

    def __str__(self):
        if not self.at_most:
            return f"none of {self.thing}"
        return f"at most {self.at_most} of {self.thing}"

    @property
    def thing(self):
        for name in COUNTABLE_FIELDS:
            if getattr(self, f"{name}_id") is not None:
                return getattr(self, name)
        return None

    def accepts(self, target_kind):
        # A census over the roster, or a count of one model's own
        # assignments.
        return target_kind in (MODEL, GANG)


class OpAddsMiniature(models.Model):
    """Brings another model into the gang — a pet, an exotic beast.

    A **stored** effect: a pet has XP, injuries and gear of its own, so it
    cannot be computed into existence on every read. ``n26.operations``
    runs this when the carrier is assigned, inside the same transaction,
    stamping the new membership as caused by the purchase — so selling the
    wargear takes the pet with it through the ordinary cascade.

    The pet's own price is carried by the wargear that brought it, so its
    membership is ledgered at full list price with a full discount: the
    entry says what the pet is worth and that nothing was paid for it here.
    """

    is_stored = True

    profile = models.ForeignKey(
        "library.Profile",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The profile the new model is hired as.",
    )

    class Meta:
        verbose_name = "adds model"
        verbose_name_plural = "adds models"

    def __str__(self):
        return f"adds a {self.profile}"

    def accepts(self, target_kind):
        # A pet collar brings a pet to its bearer's gang; a Justicar
        # alliance brings the delegation to the gang itself. Both write
        # once, at assignment — the scope says where the *note* belongs.
        return target_kind in (MODEL, GANG)

    def perform(self, operation, assignment):
        """Hire the model, free, caused by the purchase that brought it."""
        from n26.core.models import Reason

        price = self.profile.price
        return operation.hire(
            self.profile,
            str(self.profile),
            paid=0,
            list_price=price,
            discount=price,
            rating=0,
            reason=Reason.GRANTED,
            caused_by=assignment,
        )


class OpChangesCounter(models.Model):
    """Moves a counter the bearer keeps — "starts with 61 XP" on a
    selection made after hire, a Kill Count bump a title confers.

    A **stored** effect: a counter's value is player-side state written
    only by ``op.tally``, one ledger event per change — so a rule that
    moves one writes once, when its carrier is assigned, and the change
    is on the ledger like any other. Taking the carrier away does not
    move the value back: the ledger is append-only, and what a rule
    tallied is something that happened.

    A hire's printed Starting XP does not need this — a built-in counter
    member carries its opening value. This is for the value a *later*
    assignment sets or shifts: the carrier arrives, the counter moves.
    """

    is_stored = True

    class Mode(models.TextChoices):
        ADD = "add", "add"
        SUBTRACT = "subtract", "subtract"
        SET = "set", "set"

    counter = models.ForeignKey(
        "library.Counter",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The counter to move.",
    )
    mode = models.CharField(
        max_length=10,
        choices=Mode,
        default=Mode.SET,
        help_text=(
            "How the amount is applied: added to the value, subtracted "
            "from it (never below zero), or becomes it outright."
        ),
    )
    amount = models.PositiveIntegerField(
        default=0,
        help_text='The figure — the 61 in "starts with 61 XP".',
    )

    class Meta:
        verbose_name = "changes counter"
        verbose_name_plural = "changes counters"

    def __str__(self):
        if self.mode == self.Mode.ADD:
            return f"adds {self.amount} to {self.counter}"
        if self.mode == self.Mode.SUBTRACT:
            return f"takes {self.amount} from {self.counter}"
        return f"sets {self.counter} to {self.amount}"

    def accepts(self, target_kind):
        # A model's counter, or the gang's own — both keep tallies.
        return target_kind in (MODEL, GANG)

    def perform(self, operation, assignment):
        """Tally the bearer's counter, assigning one if they keep none.

        The bearer is whoever the carrier landed on. A counter assigned
        here is caused by the carrier's assignment, so a counter that
        only exists because of this rule leaves when the rule's carrier
        does — but its tallies, like all tallies, are history and stay
        written.
        """
        from n26.core.models import Assignment, Reason

        miniature = assignment.miniature or assignment.miniature_root
        if miniature is not None:
            host = {"miniature": miniature}
        else:
            host = {"gang": assignment.gang or assignment.gang_root}
        row = Assignment.objects.filter(
            counter=self.counter, archived=False, **host
        ).first()
        if row is None:
            row = operation.assign(
                self.counter,
                paid=0,
                reason=Reason.GRANTED,
                caused_by=assignment,
                **host,
            )
        if self.mode == self.Mode.ADD:
            change = self.amount
        elif self.mode == self.Mode.SUBTRACT:
            change = -self.amount
        else:
            held = getattr(row, "counter_value", None)
            change = self.amount - (held.value if held else 0)
        operation.tally(row, change, note=str(assignment.assignable))


class ChangesCategory(models.Model):
    """Re-files the bearer on the gang sheet: they sort under this
    category's heading rather than their entry's own.

    Computed, so it can only ever move a model that exists. The hire
    list and a collection's contents sort by the stored home category
    before any bearer does, and stay untouched — which is why this
    speaks of sorting and not of what the profile is.
    """

    is_stored = False

    category = models.ForeignKey(
        "library.Category",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The heading the model sorts under on the gang sheet.",
    )

    class Meta:
        verbose_name = "changes category"
        verbose_name_plural = "changes categories"

    def __str__(self):
        return f"sorts under {self.category}"

    def accepts(self, target_kind):
        # Only a model has a place in the gang sheet's order.
        return target_kind == MODEL


class ChangesStat(models.Model):
    """Shifts or sets one characteristic.

    ``improve``/``worsen`` are direction-aware: worsening a roll target goes
    up (4+ becomes 5+), worsening a plain number goes down. The stat's own
    ``is_inverted`` flag decides which.
    """

    is_stored = False

    class Mode(models.TextChoices):
        IMPROVE = "improve", "Improve"
        WORSEN = "worsen", "Worsen"
        SET = "set", "Set to"

    stat = models.ForeignKey("library.Stat", on_delete=models.PROTECT, related_name="+")
    mode = models.CharField(max_length=20, choices=Mode, default=Mode.WORSEN)
    amount = models.IntegerField(default=1)

    class Meta:
        verbose_name = "changes stat"
        verbose_name_plural = "changes stats"

    def __str__(self):
        return (
            f"{self.get_mode_display().lower()} {self.stat.short_name} by {self.amount}"
        )

    def accepts(self, target_kind):
        """A statline is a statline — models and weapons both have one."""
        return target_kind in (MODEL, WEAPON_PROFILE)


# --- The modifier itself -------------------------------------------------


class Modifier(Content):
    """One scope — who it reaches — plus one effect — what it does.

    Shared by design: the same modifier may be carried by any number of
    assignables, and editing it changes it everywhere it is carried. A
    computed effect is re-derived on every read and vanishes with its
    carrier; a written one runs once when the carrier arrives and is
    never undone by removal.
    """

    name = models.CharField(max_length=200)

    targets_miniature = models.OneToOneField(
        TargetsMiniature,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
        verbose_name="targets the model",
    )
    targets_attached_weapon = models.OneToOneField(
        TargetsAttachedWeapon,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    targets_weapons = models.OneToOneField(
        TargetsWeapons,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    targets_gang = models.OneToOneField(
        TargetsGang,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
        verbose_name="targets the gang",
    )

    adds_assignable = models.OneToOneField(
        AddsAssignable,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    removes_assignable = models.OneToOneField(
        RemovesAssignable,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    changes_stat = models.OneToOneField(
        ChangesStat,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    changes_category = models.OneToOneField(
        ChangesCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    offers_choice = models.OneToOneField(
        OffersChoice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    places_category = models.OneToOneField(
        PlacesCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    requires_companions = models.OneToOneField(
        RequiresCompanions,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    allows_at_most = models.OneToOneField(
        AllowsAtMost,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
    )
    op_adds_miniature = models.OneToOneField(
        OpAddsMiniature,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
        verbose_name="adds model",
    )
    op_changes_counter = models.OneToOneField(
        OpChangesCounter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
        verbose_name="changes counter",
    )

    class Meta:
        verbose_name = "modifier"
        verbose_name_plural = "modifiers"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("name"), name="modifier_unique_per_pack"
            ),
            models.CheckConstraint(
                condition=exactly_one_of(SCOPE_FIELDS),
                name="modifier_exactly_one_scope",
            ),
            models.CheckConstraint(
                condition=exactly_one_of(EFFECT_FIELDS),
                name="modifier_exactly_one_effect",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def scope(self):
        for name in SCOPE_FIELDS:
            if getattr(self, f"{name}_id") is not None:
                return getattr(self, name)
        return None

    @property
    def effect(self):
        for name in EFFECT_FIELDS:
            if getattr(self, f"{name}_id") is not None:
                return getattr(self, name)
        return None

    def clean(self):
        """One scope, one effect, and the two must make sense together."""
        if sum(getattr(self, f"{f}_id") is not None for f in SCOPE_FIELDS) != 1:
            raise ValidationError("A modifier must have exactly one scope.")
        if sum(getattr(self, f"{f}_id") is not None for f in EFFECT_FIELDS) != 1:
            raise ValidationError("A modifier must have exactly one effect.")

        scope, effect = self.scope, self.effect
        kinds = {target.kind for target in _possible_kinds(scope)}
        if not any(effect.accepts(kind) for kind in kinds):
            raise ValidationError(
                f"{effect} cannot apply to {scope} — a trait goes on a weapon, "
                f"a subtype or skill goes on a model."
            )


def _possible_kinds(scope):
    """What kinds of target a scope can ever produce, without a card."""
    if isinstance(scope, (TargetsWeapons, TargetsAttachedWeapon)):
        return [Target(kind=WEAPON_PROFILE)]
    if isinstance(scope, TargetsGang):
        return [Target(kind=GANG)]
    return [Target(kind=MODEL)]
