"""Modifiers — what an assignable does once assigned.

A modifier is a **scope** and an **effect**, each exactly one small typed
row hanging off it::

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
#: Effects worked out at read time by ``n26.effects.compute``.
COMPUTED_EFFECT_FIELDS = (
    "adds_assignable",
    "removes_assignable",
    "changes_stat",
    "offers_choice",
    "places_category",
    "requires_companions",
)

#: Effects that write rows, run by ``n26.operations`` when the carrier is
#: assigned. Prefixed ``Op`` so the distinction is visible at the call site.
STORED_EFFECT_FIELDS = ("op_adds_miniature",)

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
    CONDITIONS = ("has_subtypes", "counter_at_least")

    #: Positional, not factual — read off the carrier node, like
    #: ``TargetsAttachedWeapon``. An archetype's Champion row applies to
    #: a Champion who *picked* it, never to every Champion because the
    #: gang did: same carrier, and where it is hosted decides.
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
            # The gang's echo of this row reaches nobody; only the model
            # whose own row this is. A discovered (granted) carrier hangs
            # off no row at all, so it cannot be anyone's bearer.
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


class HasSubtypes(models.Model):
    """Condition: the model has one of these subtypes.

    "Leaders and Champions each select a skill" is one row naming both —
    any-of within the row. Wanting Mounted *and* Wyrd is two rows.
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

    class Meta:
        verbose_name = "has subtypes"
        verbose_name_plural = "has subtypes"

    def __str__(self):
        wanted = list(self.subtypes.all()) if self.pk else []
        return " or ".join(str(subtype) for subtype in wanted) + " models"

    def as_condition(self):
        from n26.core import select

        wanted = list(self.subtypes.all())
        if not wanted:
            # An empty row narrows nothing — never "matches nobody".
            return None
        return select.Any(*(select.Has(subtype) for subtype in wanted))


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
    """The model's weapons, optionally only those with a given trait."""

    with_trait = models.ForeignKey(
        "library.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Only weapons carrying this trait. Blank means all of them.",
    )

    class Meta:
        verbose_name = "targets weapons"
        verbose_name_plural = "target weapons"

    def __str__(self):
        return f"weapons with {self.with_trait}" if self.with_trait else "all weapons"

    @property
    def narrows(self):
        """Whether this scope reaches fewer than everything of its kind."""
        return bool(self.with_trait_id)

    def as_selector(self):
        """What this scope's filter says, in the selector vocabulary.

        Matching runs against the round snapshot ``compute`` provides —
        printed traits plus what earlier (less specific) rounds added.
        Compiled once per instance, as on ``TargetsMiniature``.
        """
        compiled = getattr(self, "_compiled_selector", None)
        if compiled is None:
            from n26.core import select

            compiled = (
                select.Has(self.with_trait)
                if self.with_trait_id is not None
                else select.Anything()
            )
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
    never swallows the other. Modifiers reaching *members* from a
    gang-hosted carrier keep using ``TargetsMiniature`` — the broadcast
    is unchanged.
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
        """Traits go on weapons; subtypes and skills go on models."""
        if self.trait_id is not None:
            return target_kind == WEAPON_PROFILE
        return target_kind == MODEL


class AddsAssignable(AssignableChoice):
    """Gives the target a subtype, skill or trait it would not otherwise have."""

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
    """Takes a subtype, skill or trait away, computed — Death of a Leader."""

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
    """The bearer may select one assignable of a given kind.

    Computed: the offer is a *slot* on the card, present while the carrier
    is; only the answer is ever stored (an assignment caused by the
    carrier's). Unresolved is simply the absence of a resolution — nothing
    pending is written, so nothing pending can go stale, and deferring the
    pick costs nothing.

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
            'Narrow the offer to one tier of a collection: "a Skill from a '
            'set that is Primary for this fighter". The tier is a row of '
            "the collection's schema, the same row a placement aims at, so "
            'the admin picks "Primary (Skills & Powers)" rather than '
            "restating a name. Blank offers the whole kind."
        ),
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            'What the card calls this slot — "skill tree 1". Blank derives '
            "a label from the kind and any section, which is usually right."
        ),
    )

    class AnswerHost(models.TextChoices):
        #: The model (or gang) whose row carries the question — the
        #: ordinary case: a Specialist's specialisation rides them.
        BEARER = "bearer", "the bearer"
        #: The Leader → Gang arrow:
        #: the Outcast Leader picks the archetype, but the pick belongs
        #: to the gang — the answer lands as a gang row, radiates to the
        #: members, and, being caused by the Leader's row, dies with the
        #: Leader.
        GANG = "gang", "the gang"

    answer_host = models.CharField(
        max_length=20,
        choices=AnswerHost,
        default=AnswerHost.BEARER,
        help_text=(
            "Which host the answer's assignment lands on. Almost always "
            "the bearer; a Leader's archetype pick is carried by the "
            "gang, not the Leader."
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
    def of(cls, model, from_section=None, label="", answer_host=AnswerHost.BEARER):
        from django.contrib.contenttypes.models import ContentType

        return cls.objects.create(
            of_kind=ContentType.objects.get_for_model(model),
            from_section=from_section,
            label=label,
            answer_host=answer_host,
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
    #: whatever category the carrier's answered choice is homed in. A
    #: Venator rank slot says "put *the chosen tree* under Primary" —
    #: which tree that is lives on the answer, not here. Unanswered, the
    #: placement simply does not happen, and the plan says why.
    the_chosen = models.BooleanField(
        default=False,
        help_text=(
            "Place whatever category the carrier's answered choice is "
            "homed in, instead of naming one."
        ),
    )
    section = models.ForeignKey(
        "library.CollectionSection",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The tier it appears under for the bearer — a row of the "
            "collection's schema, so the admin picks "
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
    """One scope plus one effect. Computed onto cards; never stored."""

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
    op_adds_miniature = models.OneToOneField(
        OpAddsMiniature,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier",
        verbose_name="adds model",
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
