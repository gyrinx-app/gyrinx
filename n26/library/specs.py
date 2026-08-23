"""Specs — what each authoring verb asks for, as data.

Step 1 of design/authoring-build-plan.md. A spec is a declarative
description of one verb's parameters: which model each names, whether
it's optional, what narrows it, what the admin should read next to it.
Forms are *generated* from specs (step 2), and a filled form **compiles
to the verb call** — so the form can never drift from the API, and a
verb without a spec is caught by a discovering guard
(tests/sandbox/test_specs.py, the money-words pattern).

Two rules keep specs honest:

* **Help is sourced, never written.** A field's words come from the
  model field it stores into — the ``help_text`` we have been writing
  carefully all along — referenced as ``(Model, "field_name")`` and
  resolved on read. A test pins the resolution literally, so a spec
  can't quietly paraphrase the model.
* **Every spec is tested against a named example object** — form-shaped
  data replicating something an example suite built (the Brawler leader
  row, the XP-75 promotion) compiles through the spec and must come out
  saying exactly what that object says.

Nothing here renders anything; a spec is the *structure* forms derive
from, the same structures-before-renderers rule as cards.
"""

import inspect
from dataclasses import dataclass
from dataclasses import field as dataclass_field

# --- Field kinds ------------------------------------------------------------
#
# Each describes one parameter. ``source`` is the (model, field name)
# whose help_text and choices the form will show — never a place to
# write new words.


@dataclass(frozen=True)
class _Sourced:
    source: tuple = None
    #: Asked when the thing is made and never again. Some answers are
    #: what the thing *is* rather than something about it — a choice's
    #: slot type decides which pickables could ever settle it, so
    #: changing it leaves a list and a pick that no longer belong to
    #: each other.
    #: Changing one of these is making a different thing. A form opened
    #: on a row that already exists does not offer the field, and so
    #: does not write it (``GeneratedForm.opened_on``).
    fixed: bool = False

    @property
    def help(self):
        """The model field's own words, resolved on read."""
        if self.source is None:
            return ""
        model, field_name = self.source
        return str(model._meta.get_field(field_name).help_text)

    @property
    def max_length(self):
        """The column's own limit, resolved on read — None where it has none.

        The form enforces this so an overlong value is a validation
        error with the field named, rather than the database refusing
        the INSERT and the author getting a 500 with nobody's name on it.
        """
        if self.source is None:
            return None
        model, field_name = self.source
        return getattr(model._meta.get_field(field_name), "max_length", None)

    @property
    def label(self):
        """What the model field calls itself, where it calls itself
        anything — ``None`` otherwise, leaving the form to derive one.

        Django names a field after its column unless told otherwise, so
        a field that says something different is a field whose author
        wanted a particular word in front of a reader: "Set" above a
        column called ``group``. Where nothing was said, the form's own
        derivation says the same thing and this stays out of the way.
        """
        if self.source is None:
            return None
        model, field_name = self.source
        stated = str(model._meta.get_field(field_name).verbose_name)
        return None if stated == field_name.replace("_", " ") else stated


@dataclass(frozen=True)
class One(_Sourced):
    """One row of a model — a foreign key pick.

    ``filtered_by`` names the relations a pick must respect —
    ``("collection",)`` on a section pick means "a section of *that*
    collection". It **refuses** in the generated form's ``clean()``, in
    words, and leaves the picker offering everything: the rows it turns
    away are still worth seeing, since a section of the wrong collection
    is a mistake an author can make and should be told about by name.

    ``within`` names the accessor on the thing a part is being added to
    that lists the only rows worth offering — ``"option_groups"`` on an
    set pick means "a set of *this* profile's". This one narrows the
    picker *and* refuses. The rows it excludes belong to other people's
    things, so there is nothing to be gained by offering them, and the
    refusal is what stops a submission naming one anyway.
    """

    model: type = None
    optional: bool = False
    filtered_by: tuple = ()
    within: str = ""


@dataclass(frozen=True)
class Many(_Sourced):
    """Several rows of a model — an M2M pick.

    ``replaced_by`` is the verb that owns replacing the set, for a form
    opened on a row that already exists. ``revise`` refuses a set,
    because what happens to a member the new value does not name is a
    decision; the verb is where that decision is stated, and naming it
    here is how an edit form finds it. A field without one may be filled
    in when the row is made and not changed afterwards.
    """

    model: type = None
    replaced_by: object = None


@dataclass(frozen=True)
class Int(_Sourced):
    pass


@dataclass(frozen=True)
class Bool(_Sourced):
    pass


@dataclass(frozen=True)
class Text(_Sourced):
    #: Paragraph-shaped — the form draws a textarea instead of an input.
    long: bool = False


@dataclass(frozen=True)
class Artwork(_Sourced):
    """The address of a drawing in the site's own storage.

    Two controls, one value: a box holding the address, and an upload
    that puts a file in the storage and fills the box in. Only the
    address is stored, so there is nothing for a reader to choose
    between (library/artwork.py).
    """


@dataclass(frozen=True)
class Choice(_Sourced):
    """One of a fixed set. ``options`` for a plain tuple (offerable
    kinds); otherwise the choices come off the sourced model field.
    ``coerce`` turns the submitted value into what the verb takes —
    an offerable kind name into its model class.

    ``reads`` is the way back: how a form opened on a stored row
    recovers what was chosen. Needed only where the column is not the
    parameter — a choice of kind is stored as a ContentType, and
    ``getattr(row, "model")`` would find nothing."""

    options: tuple = ()
    coerce: object = None
    reads: object = None

    @property
    def choices(self):
        if self.options:
            return tuple((option, option) for option in self.options)
        model, field_name = self.source
        return tuple(model._meta.get_field(field_name).choices)


@dataclass(frozen=True)
class Conditions:
    """The nested WHO conditions a scope verb takes — rendered as a
    formset of chips (step 2), compiled by each condition's own spec.
    ``kinds`` names which condition verbs may appear."""

    kinds: tuple = ()

    help = "Narrow who this reaches. No conditions means everyone."


@dataclass(frozen=True)
class Union:
    """One thing of any of several kinds — the ef_adds/ef_removes
    picker over ``GRANTABLE_FIELDS``, and ``attach_to``. ``over`` names
    the allowed kinds (field name → model label).

    ``through`` is the row the pick is written into, when there is one
    (a built-in's ``DefaultAssignment``). Naming it lets each kind's
    own ``ATTACHMENT_ASKS`` ride the form — a counter's opening value
    appears because the counter declares it, never because a form
    special-cased counters (library/offers.py)."""

    over: dict = dataclass_field(default_factory=dict)
    through: type = None

    help = ""


# --- The spec and its registry ----------------------------------------------


@dataclass(frozen=True)
class Spec:
    """One verb's parameters, as data. ``compile(data)`` performs the
    verb call a filled form amounts to."""

    verb: object
    fields: dict
    #: What the verb makes. Inferred from the ``name`` field's source
    #: where there is one, named here where there isn't — a stat has a
    #: short name and a full one, and a through row has neither.
    model: type = None
    #: The field an author reads as this thing's name, and so where a
    #: refusal about a duplicate belongs. Every creating kind but one
    #: calls it ``name``; a stat is told apart by its full name, which
    #: is what its uniqueness is derived from.
    identity: str = "name"
    #: What a verb picker calls this verb. Usually blank — the model's
    #: verbose name reads well and two names for one thing drift — but
    #: two verbs can write the same model (``ef_places`` and
    #: ``ef_places_choice`` both write a ``PlacesCategory``), and a
    #: picker labelling both from the model shows one choice twice. A
    #: verb that shares its model states its own label; a guard test
    #: refuses a picker with two choices reading alike.
    label: str = ""
    #: The line under the label on a kind-picker card: what the verb
    #: does, in one plain sentence an author can act on. The label is
    #: the name; this is the explanation the name cannot carry.
    blurb: str = ""
    #: A concrete case from the books, revealed on the card's hover —
    #: the fastest way to recognise "that is the one I need".
    example: str = ""
    #: Kept for existing content, steered away from for new: the picker
    #: draws a Deprecated pill on the card. Never removed while content
    #: uses the verb.
    deprecated: bool = False

    @property
    def name(self):
        return self.verb.__name__

    @property
    def creates(self):
        return self.model or self.fields["name"].source[0]

    def compile(self, data):
        """Call the verb with form-shaped ``data``.

        Keys absent from ``data`` fall back to the verb's own defaults.
        A ``Conditions`` value is a list of ``(verb_name, payload)``
        pairs, each compiled by that condition's spec and passed
        positionally — the nesting the grammar asks for.
        """
        signature = inspect.signature(self.verb)
        args, kwargs = [], {}
        for name, kind in self.fields.items():
            if name not in data:
                continue
            value = data[name]
            if isinstance(kind, Conditions):
                for condition_name, payload in value:
                    if condition_name not in kind.kinds:
                        allowed = ", ".join(kind.kinds)
                        raise ValueError(
                            f"{self.name} cannot take a {condition_name} "
                            f"condition. Allowed: {allowed}."
                        )
                    args.append(specs()[condition_name].compile(payload))
            elif signature.parameters[name].kind is inspect.Parameter.VAR_POSITIONAL:
                args.extend(value)
            elif isinstance(kind, Choice) and kind.coerce is not None:
                kwargs[name] = kind.coerce(value)
            else:
                kwargs[name] = value
        return self.verb(*args, **kwargs)


def _offerable_kind_to_model(kind_name):
    """ "skill" → the Skill class — the form speaks kinds, never
    ContentType rows; the verb takes the class."""
    from django.apps import apps

    return apps.get_model("library", kind_name)


def use_lists(model):
    """The four use lists of a kind carrying ``UsableBy``, as spec fields.

    Derived from the mixin's own fields rather than written out per kind,
    so a weapon's page and a skill's draw the same pickers, each picking
    what its own column points at — and a fifth list on the mixin
    reaches every form the day it exists. The same shape serves the
    collection entry, whose columns are the same four asking about one
    list's offer.
    """
    from n26.library import authoring
    from n26.library.models.assignable import USABLE_BY_LISTS

    return {
        name: Many(
            model=model._meta.get_field(name).related_model,
            source=(model, name),
            replaced_by=authoring.set_usable_by,
        )
        for name in USABLE_BY_LISTS
    }


def _build_registry():
    from n26.library import authoring
    from n26.library.models import (
        Affiliation,
        AllowsAtMost,
        Archetype,
        Category,
        ChangesCategory,
        ChangesStat,
        Collection,
        CollectionEntry,
        CollectionSection,
        Counter,
        CounterAtLeast,
        DefaultAssignment,
        DefaultAssignmentSet,
        GangType,
        HasPickable,
        HasSubtypes,
        HasTraits,
        Hidden,
        InCategories,
        IsOneOf,
        IsProfile,
        LastingEffect,
        OffersChoice,
        OpAddsMiniature,
        OpChangesCounter,
        Option,
        OptionGroup,
        Pickable,
        Picklist,
        PicklistMember,
        PlacesCategory,
        Power,
        Profile,
        ProfileType,
        RequiresCompanions,
        Rule,
        Section,
        Skill,
        SkillTree,
        Slot,
        SlotType,
        Specialisation,
        Stat,
        StatlineType,
        StatlineTypeStat,
        Subtype,
        Trait,
        Wargear,
        Weapon,
        WeaponAccessory,
        WeaponProfile,
    )
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS
    from n26.library.models.modifier import (
        COUNTABLE_FIELDS,
        GRANTABLE_FIELDS,
        OFFERABLE_KINDS,
    )

    # What a built-in may be, derived from the DefaultAssignment row
    # itself so the union can never drift from the model's own keys.
    # A kind declaring itself off the generic picker — a weapon's extra
    # profile, attached from its gun member's own row — is left out.
    built_in_kinds = {
        name: f"library.{DefaultAssignment._meta.get_field(name).related_model.__name__}"
        for name in DEFAULT_ASSIGNABLE_FIELDS
        if DefaultAssignment._meta.get_field(name).related_model.offered_as_built_in
    }
    # What a collection entry may list, derived the same way.
    entry_kinds = {
        name: f"library.{CollectionEntry._meta.get_field(name).related_model.__name__}"
        for name in CollectionEntry.ASSIGNABLE_FIELDS
    }

    specs = [
        # -- scopes, and the conditions that nest inside them ---------
        Spec(
            authoring.targets_model,
            {
                "conditions": Conditions(
                    kinds=(
                        "has_subtypes",
                        "is_profile",
                        "has_pickable",
                        "counter_at_least",
                    )
                ),
            },
            label="The model carrying it",
            blurb=(
                "Only the model this is directly assigned to — nothing is "
                "reached through the gang. Conditions can narrow it "
                "further."
            ),
            example=(
                "Mounted grants two skills: the fighter with the Mounted "
                "subtype gets them. An archetype assigned to a Champion "
                "applies to that Champion alone."
            ),
        ),
        Spec(
            authoring.targets_every_model,
            {
                "conditions": Conditions(
                    kinds=(
                        "has_subtypes",
                        "is_profile",
                        "has_pickable",
                        "counter_at_least",
                    )
                ),
            },
            label="All models in the gang",
            blurb=(
                "Every model in the gang, not just whoever carries this — "
                "the reach for things the gang holds: a chosen alliance, a "
                "founding rule. Conditions narrow it the same way."
            ),
            example=(
                "The leader's archetype sets the skills available to every "
                "model except Champions: one modifier, with a condition "
                "naming the exception."
            ),
        ),
        Spec(
            authoring.has_subtypes,
            {
                "subtypes": Many(model=Subtype, source=(HasSubtypes, "subtypes")),
                "negate": Bool(source=(HasSubtypes, "negate")),
            },
        ),
        Spec(
            authoring.is_profile,
            {
                "profiles": Many(model=Profile, source=(IsProfile, "profiles")),
                "negate": Bool(source=(IsProfile, "negate")),
            },
        ),
        Spec(
            authoring.has_pickable,
            {
                "pickables": Many(model=Pickable, source=(HasPickable, "pickables")),
                "negate": Bool(source=(HasPickable, "negate")),
            },
        ),
        Spec(
            authoring.counter_at_least,
            {
                "counter": One(model=Counter, source=(CounterAtLeast, "counter")),
                "at_least": Int(source=(CounterAtLeast, "at_least")),
            },
        ),
        Spec(
            authoring.has_traits,
            {"traits": Many(model=Trait, source=(HasTraits, "traits"))},
        ),
        Spec(
            authoring.in_categories,
            {"categories": Many(model=Category, source=(InCategories, "categories"))},
        ),
        Spec(
            authoring.is_one_of,
            {"weapons": Many(model=Weapon, source=(IsOneOf, "weapons"))},
        ),
        Spec(
            authoring.targets_weapons,
            {
                "conditions": Conditions(
                    kinds=("has_traits", "in_categories", "is_one_of")
                )
            },
            label="The model's weapons",
            blurb=("Every weapon that model holds — narrowable by trait or category."),
            example=(
                "Backstab: the fighter's Melee weapons all gain the Backstab trait."
            ),
        ),
        Spec(
            authoring.targets_attached_weapon,
            {},
            label="The weapon it's fitted to",
            blurb=(
                "For accessories: the one gun this item is bolted onto, nothing else."
            ),
            example=(
                "A telescopic sight improves the gun it's fitted to — not "
                "every gun the fighter owns."
            ),
        ),
        Spec(
            authoring.targets_gang,
            {},
            label="The gang carrying it and all models",
            blurb=(
                "Affects the gang and all models, in a different way per "
                "effect. Use with care."
            ),
            example=(
                "A rule given to the gang prints on the gang's sheet only, "
                "while what the rule does reaches every fighter. Prefer "
                "assigning a hidden item to the gang that carries “All "
                "models in the gang” modifiers."
            ),
            deprecated=True,
        ),
        Spec(
            authoring.targets_gang_alone,
            {},
            label="The gang carrying it",
            blurb="Applied only to the gang; does not reach the models.",
            example=(
                "A rule that prints on the gang sheet without touching the "
                "fighters, or a gang-level counter."
            ),
        ),
        # -- effects, worked out at read time --------------------------
        Spec(
            authoring.ef_adds,
            {"thing": Union(over=dict(GRANTABLE_FIELDS))},
            label="Gives something",
            blurb=(
                "The target gains a subtype, skill, power, rule, trait, "
                "list or weapon — or a hidden item, which brings whatever "
                "it gives. For as long as the item carrying this modifier "
                "stays."
            ),
            example=(
                "The Cutter grants Mounted; Mounted grants Nerves of "
                "Steel. Sell the Cutter and all of it goes."
            ),
        ),
        Spec(
            authoring.ef_removes,
            {"thing": Union(over=dict(GRANTABLE_FIELDS))},
            label="Takes something away",
            blurb=(
                "Cancels something granted or innate, and whatever that "
                "was itself giving. Hides built-in kit rather than "
                "deleting it; never un-buys what was paid for."
            ),
            example=(
                "Selected as Leader: loses the Loner subtype. Name a "
                "hidden item and everything it gives goes at once."
            ),
        ),
        Spec(
            authoring.ef_changes_stat,
            {
                "stat": One(model=Stat, source=(ChangesStat, "stat")),
                "mode": Choice(source=(ChangesStat, "mode")),
                "amount": Int(source=(ChangesStat, "amount")),
            },
            label="Changes a stat",
            blurb="Shifts or sets one cell of the statline, better or worse.",
            example="Eye Injury: −1 BS. A bionic eye cancels it out.",
        ),
        Spec(
            authoring.ef_offers_choice,
            {
                "model": Choice(
                    options=OFFERABLE_KINDS,
                    coerce=_offerable_kind_to_model,
                    reads=lambda row: row.of_kind.model,
                ),
                "from_section": One(
                    model=CollectionSection,
                    optional=True,
                    source=(OffersChoice, "from_section"),
                ),
                "label": Text(source=(OffersChoice, "label")),
                "will_be_assigned_to": Choice(
                    source=(OffersChoice, "will_be_assigned_to")
                ),
            },
            label="Offers a choice",
            blurb=(
                "Puts an open question on the card; the player chooses one "
                "thing of a kind."
            ),
            example=(
                "A Leader starts with a Primary skill — the card says "
                "“Choose” until they pick."
            ),
        ),
        Spec(
            authoring.ef_changes_category,
            {
                "category": One(model=Category, source=(ChangesCategory, "category")),
            },
            label="Changes the model's category",
            blurb=(
                "Where the model files on the gang sheet — under a heading "
                "you name instead of their entry's own."
            ),
            example=("A fighter selected as Outcast Leader sorts with the Leaders."),
        ),
        Spec(
            authoring.ef_places,
            {
                "category": One(model=Category, source=(PlacesCategory, "category")),
                "section": One(
                    model=CollectionSection,
                    source=(PlacesCategory, "section"),
                    filtered_by=("collection",),
                ),
            },
            label="Puts a category into a section",
            blurb=(
                "For that model, a category you name counts under a "
                "section of a collection."
            ),
            example=(
                "Wyrd: the Wyrd Powers category of the Skills & Powers "
                "collection counts as one of their Secondary sets."
            ),
        ),
        Spec(
            authoring.ef_places_choice,
            {
                "section": One(
                    model=CollectionSection,
                    source=(PlacesCategory, "section"),
                    filtered_by=("collection",),
                ),
            },
            label="Puts the player's choice into a section",
            blurb=(
                "Pair with “Offers a choice” on the same item: whatever "
                "the player picks, the category it belongs to goes into "
                "the section."
            ),
            example=(
                "A Venator's “skill tree 1”: pick Ferocity and Ferocity "
                "becomes a Primary set."
            ),
        ),
        Spec(
            authoring.ef_requires_companions,
            {
                "for_each": One(model=Subtype, source=(RequiresCompanions, "for_each")),
                "at_least": Int(source=(RequiresCompanions, "at_least")),
                "of": One(model=Subtype, source=(RequiresCompanions, "of")),
            },
            label="Notes a composition rule",
            blurb=(
                "Says what the gang should field alongside what — written "
                "on the sheet, never enforced."
            ),
            example="For each Champion, at least three Hive Scum.",
        ),
        Spec(
            authoring.ef_allows_at_most,
            {
                "at_most": Int(source=(AllowsAtMost, "at_most")),
                "thing": Union(over=dict(COUNTABLE_FIELDS)),
            },
            label="Notes a limit",
            blurb=(
                "Says how many of something the gang — or one model — "
                "should hold at most. Written on the sheet, never "
                "enforced; nought is a ban."
            ),
            example=(
                "At most 2 Aberrants on the roster; no Brutes from the "
                "gang's own list; one Familiar each."
            ),
        ),
        # -- effects written once, at purchase time ---------------------
        Spec(
            authoring.op_adds_model,
            {"profile": One(model=Profile, source=(OpAddsMiniature, "profile"))},
            label="Brings a model",
            blurb=(
                "Buying the item carrying this modifier adds a whole new "
                "model to the gang, free. It goes if the item goes."
            ),
            example=(
                "Cyber-mastiff wargear brings the mastiff itself, XP and "
                "injuries of its own."
            ),
        ),
        Spec(
            authoring.op_changes_counter,
            {
                "counter": One(model=Counter, source=(OpChangesCounter, "counter")),
                "mode": Choice(source=(OpChangesCounter, "mode")),
                "amount": Int(source=(OpChangesCounter, "amount")),
            },
            label="Moves a counter",
            blurb=(
                "When the item carrying this modifier arrives, set, add "
                "to, or subtract from a counter the model keeps — recorded "
                "on the ledger."
            ),
            example="Selected as Outcast Leader: starts with 61 XP.",
        ),
        # -- the leaves: what the authoring views create ----------------
        # Name-only (and nearly-so) kinds, the ground everything else
        # references. Help is sourced from the Assignable mixin's own
        # fields; a blank help is a blank on the model, not an omission
        # here.
        Spec(
            authoring.create_subtype,
            {
                "name": Text(source=(Subtype, "name")),
                "qualifier": Text(source=(Subtype, "qualifier")),
                "library_author_help": Text(
                    source=(Subtype, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_rule,
            {
                "name": Text(source=(Rule, "name")),
                "annotation": Text(source=(Rule, "annotation")),
                "qualifier": Text(source=(Rule, "qualifier")),
                "library_author_help": Text(
                    source=(Rule, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_trait,
            {
                "name": Text(source=(Trait, "name")),
                "annotation": Text(source=(Trait, "annotation")),
                "qualifier": Text(source=(Trait, "qualifier")),
                "library_author_help": Text(
                    source=(Trait, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_skill,
            {
                "name": Text(source=(Skill, "name")),
                "category": One(
                    model=Category, optional=True, source=(Skill, "category")
                ),
                **use_lists(Skill),
                "qualifier": Text(source=(Skill, "qualifier")),
                "library_author_help": Text(
                    source=(Skill, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_power,
            {
                "name": Text(source=(Power, "name")),
                "annotation": Text(source=(Power, "annotation")),
                "category": One(
                    model=Category, optional=True, source=(Power, "category")
                ),
                **use_lists(Power),
                "qualifier": Text(source=(Power, "qualifier")),
                "library_author_help": Text(
                    source=(Power, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_lasting_effect,
            {
                "name": Text(source=(LastingEffect, "name")),
                "qualifier": Text(source=(LastingEffect, "qualifier")),
                "library_author_help": Text(
                    source=(LastingEffect, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_counter,
            {
                "name": Text(source=(Counter, "name")),
                "qualifier": Text(source=(Counter, "qualifier")),
                "library_author_help": Text(
                    source=(Counter, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_wargear,
            {
                "name": Text(source=(Wargear, "name")),
                "price": Int(source=(Wargear, "price")),
                "trade_point_price": Int(source=(Wargear, "trade_point_price")),
                "category": One(
                    model=Category, optional=True, source=(Wargear, "category")
                ),
                **use_lists(Wargear),
                "qualifier": Text(source=(Wargear, "qualifier")),
                "library_author_help": Text(
                    source=(Wargear, "library_author_help"), long=True
                ),
            },
        ),
        # The foundations: not assignables, but nothing stands without
        # them. Statline *types* are seeded or composed in the Django
        # admin — a multi-select cannot express print order.
        Spec(
            authoring.create_stat,
            {
                "short_name": Text(source=(Stat, "short_name")),
                "full_name": Text(source=(Stat, "full_name")),
                "is_inches": Bool(source=(Stat, "is_inches")),
                "is_target": Bool(source=(Stat, "is_target")),
                "is_inverted": Bool(source=(Stat, "is_inverted")),
                "is_modifier": Bool(source=(Stat, "is_modifier")),
            },
            model=Stat,
            identity="full_name",
        ),
        Spec(
            authoring.create_statline_type,
            {"name": Text(source=(StatlineType, "name"))},
        ),
        Spec(
            authoring.add_stat_to_statline_type,
            {
                "stat": One(model=Stat, source=(StatlineTypeStat, "stat")),
                "short_name_override": Text(
                    source=(StatlineTypeStat, "short_name_override")
                ),
                "is_highlighted": Bool(source=(StatlineTypeStat, "is_highlighted")),
                "is_first_of_group": Bool(
                    source=(StatlineTypeStat, "is_first_of_group")
                ),
            },
            model=StatlineTypeStat,
        ),
        Spec(
            authoring.create_weapon_accessory,
            {
                "name": Text(source=(WeaponAccessory, "name")),
                "price": Int(source=(WeaponAccessory, "price")),
                "trade_point_price": Int(source=(WeaponAccessory, "trade_point_price")),
                "category": One(
                    model=Category,
                    optional=True,
                    source=(WeaponAccessory, "category"),
                ),
                "fits_category": One(
                    model=Category,
                    optional=True,
                    source=(WeaponAccessory, "fits_category"),
                ),
                "fits_asterisked": Bool(source=(WeaponAccessory, "fits_asterisked")),
                **use_lists(WeaponAccessory),
                "qualifier": Text(source=(WeaponAccessory, "qualifier")),
                "library_author_help": Text(
                    source=(WeaponAccessory, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_weapon,
            {
                "name": Text(source=(Weapon, "name")),
                "slots": Int(source=(Weapon, "slots")),
                "statline_type": One(
                    model=StatlineType, optional=True, source=(Weapon, "statline_type")
                ),
                "price": Int(source=(Weapon, "price")),
                "trade_point_price": Int(source=(Weapon, "trade_point_price")),
                "is_exclusive": Bool(source=(Weapon, "is_exclusive")),
                "category": One(
                    model=Category, optional=True, source=(Weapon, "category")
                ),
                **use_lists(Weapon),
                "qualifier": Text(source=(Weapon, "qualifier")),
                "library_author_help": Text(
                    source=(Weapon, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.add_weapon_profile,
            {
                "name": Text(source=(WeaponProfile, "name")),
                # Beside the name, because the two are one answer: a
                # named line prints "Warp round (Autogun)", and the
                # bracket is this. Left blank on a new line the verb
                # fills in the weapon's name, which is what the book
                # prints.
                "annotation": Text(source=(WeaponProfile, "annotation")),
                "price": Int(source=(WeaponProfile, "price")),
                "trade_point_price": Int(source=(WeaponProfile, "trade_point_price")),
                "is_exclusive": Bool(source=(WeaponProfile, "is_exclusive")),
                "traits": Many(
                    model=Trait,
                    source=(WeaponProfile, "traits"),
                    replaced_by=authoring.set_traits,
                ),
                "qualifier": Text(source=(WeaponProfile, "qualifier")),
                "library_author_help": Text(
                    source=(WeaponProfile, "library_author_help"), long=True
                ),
            },
        ),
        # The carriers: things whose whole payload is the modifiers hung
        # on them later. The page makes the thing; the composer arms it.
        Spec(
            authoring.create_hidden,
            {
                "name": Text(source=(Hidden, "name")),
                "qualifier": Text(source=(Hidden, "qualifier")),
                "library_author_help": Text(
                    source=(Hidden, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_specialisation,
            {
                "name": Text(source=(Specialisation, "name")),
                "qualifier": Text(source=(Specialisation, "qualifier")),
                "library_author_help": Text(
                    source=(Specialisation, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_archetype,
            {
                "name": Text(source=(Archetype, "name")),
                "qualifier": Text(source=(Archetype, "qualifier")),
                "library_author_help": Text(
                    source=(Archetype, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_affiliation,
            {
                "name": Text(source=(Affiliation, "name")),
                "qualifier": Text(source=(Affiliation, "qualifier")),
                "library_author_help": Text(
                    source=(Affiliation, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_skill_tree,
            {
                "name": Text(source=(SkillTree, "name")),
                "category": One(model=Category, source=(SkillTree, "category")),
                "qualifier": Text(source=(SkillTree, "qualifier")),
                "library_author_help": Text(
                    source=(SkillTree, "library_author_help"), long=True
                ),
            },
        ),
        # Slots and picks: a slot type, its pickables, the picklist they
        # are offered on, and the slot itself. Four pages and no code,
        # which is the whole point of the shape.
        Spec(
            authoring.create_slot_type,
            {
                "name": Text(source=(SlotType, "name")),
                "plural_name": Text(source=(SlotType, "plural_name")),
                "allows_repeats": Bool(source=(SlotType, "allows_repeats")),
            },
        ),
        Spec(
            authoring.create_pickable,
            {
                "name": Text(source=(Pickable, "name")),
                # The slot type is what this pickable belongs to:
                # settled when it is made and not afterwards, or a list
                # would be left offering something no choice of its slot
                # type could take.
                "slot_type": One(
                    model=SlotType, source=(Pickable, "slot_type"), fixed=True
                ),
                "category": One(
                    model=Category, source=(Pickable, "category"), optional=True
                ),
                "qualifier": Text(source=(Pickable, "qualifier")),
                "library_author_help": Text(
                    source=(Pickable, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_picklist,
            {
                "name": Text(source=(Picklist, "name")),
                # One slot type throughout, settled when the list is
                # made: every pickable on it and every choice drawing on
                # it were accepted against this.
                "slot_type": One(
                    model=SlotType, source=(Picklist, "slot_type"), fixed=True
                ),
            },
        ),
        Spec(
            authoring.add_picklist_member,
            {
                # A list offers one slot type's pickables, so the picker
                # on its page offers that slot type's and nothing else.
                "pickable": One(
                    model=Pickable,
                    source=(PicklistMember, "pickable"),
                    within="may_offer",
                ),
                "label_override": Text(source=(PicklistMember, "label_override")),
                "position": Int(source=(PicklistMember, "position")),
            },
            model=PicklistMember,
        ),
        Spec(
            authoring.create_slot,
            {
                "name": Text(source=(Slot, "name")),
                # The slot type a choice is in, settled when it is made.
                # Changed afterwards, the list behind it would offer
                # pickables the choice could not take and the picks
                # already made would answer nothing.
                "slot_type": One(
                    model=SlotType, source=(Slot, "slot_type"), fixed=True
                ),
                # Narrowed where the slot type is already settled — on
                # its own page, where a slot is added to it. The page
                # that makes a slot from scratch has no slot type to
                # narrow by and offers every list there is.
                "picklist": One(
                    model=Picklist,
                    source=(Slot, "picklist"),
                    within="picklists",
                ),
                "label": Text(source=(Slot, "label")),
                "min_picks": Int(source=(Slot, "min_picks")),
                "max_picks": Int(source=(Slot, "max_picks")),
                "assigned_to": Choice(source=(Slot, "assigned_to")),
                "hidden": Bool(source=(Slot, "hidden")),
                "position": Int(source=(Slot, "position")),
                "qualifier": Text(source=(Slot, "qualifier")),
                "library_author_help": Text(
                    source=(Slot, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_section,
            {
                "name": Text(source=(Section, "name")),
                "position": Int(source=(Section, "position")),
            },
        ),
        Spec(
            authoring.create_category,
            {
                "section": One(model=Section, source=(Category, "section")),
                "name": Text(source=(Category, "name")),
                "position": Int(source=(Category, "position")),
            },
        ),
        # The gang surface: the type, the entries hired off its list,
        # and the named lists those entries use.
        Spec(
            authoring.create_gang_type,
            {
                "name": Text(source=(GangType, "name")),
                "starting_credits": Int(source=(GangType, "starting_credits")),
                # Nothing on an ingest sheet carries artwork, so a badge is
                # authored here and only here.
                "icon_url": Artwork(source=(GangType, "icon_url")),
                "foundable": Bool(source=(GangType, "foundable")),
                "qualifier": Text(source=(GangType, "qualifier")),
                "library_author_help": Text(
                    source=(GangType, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_profile,
            {
                "name": Text(source=(Profile, "name")),
                "profile_type": One(
                    model=ProfileType, source=(Profile, "profile_type")
                ),
                "gang_type": One(model=GangType, source=(Profile, "gang_type")),
                "price": Int(source=(Profile, "price")),
                "category": One(
                    model=Category, optional=True, source=(Profile, "category")
                ),
                "hireable": Bool(source=(Profile, "hireable")),
                "qualifier": Text(source=(Profile, "qualifier")),
                "library_author_help": Text(
                    source=(Profile, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.create_collection,
            {
                "name": Text(source=(Collection, "name")),
                "prices_its_entries": Bool(source=(Collection, "prices_its_entries")),
                "qualifier": Text(source=(Collection, "qualifier")),
                "library_author_help": Text(
                    source=(Collection, "library_author_help"), long=True
                ),
            },
        ),
        # One curated row. What listing each kind asks for — the price
        # and trade-point overrides — comes from the kind's own
        # ATTACHMENT_ASKS, resolved through the union. The use lists are
        # named here instead, because narrowing is not the kind's
        # knowledge but the row's: any offer may be narrowed, whatever
        # sort of thing it offers. Which collections ask for either is
        # ``Collection.entry_asks``, applied by the page.
        Spec(
            authoring.add_entry,
            {
                "thing": Union(over=entry_kinds, through=CollectionEntry),
                **use_lists(CollectionEntry),
            },
            model=CollectionEntry,
        ),
        # One of a collection's own sections — where placements point
        # and where a pick-list's options live.
        Spec(
            authoring.add_section,
            {
                "name": Text(source=(CollectionSection, "name")),
                "is_default": Bool(source=(CollectionSection, "is_default")),
            },
            model=CollectionSection,
        ),
        Spec(
            authoring.add_built_in,
            # No flat extras here: what attaching each kind asks for —
            # a counter's opening value — comes from the kind's own
            # ATTACHMENT_ASKS, resolved through the union.
            {"thing": Union(over=built_in_kinds, through=DefaultAssignment)},
            model=DefaultAssignment,
        ),
        # One more thing inside a set that already exists — how an
        # option comes to bring two items. Same union as a built-in,
        # because both write the same row.
        Spec(
            authoring.add_default_member,
            {"thing": Union(over=built_in_kinds, through=DefaultAssignment)},
            model=DefaultAssignment,
        ),
        # The choice a thing offers when it is acquired. No set appears
        # here: the author says what the option is called, what it is
        # priced at and what it brings, and the verb founds the set that
        # holds it.
        Spec(
            authoring.offer_option,
            {
                "name": Text(source=(Option, "name")),
                "price": Int(source=(DefaultAssignmentSet, "price")),
                "thing": Union(over=built_in_kinds, through=DefaultAssignment),
                "group": One(
                    model=OptionGroup,
                    optional=True,
                    within="option_groups",
                    source=(Option, "group"),
                ),
            },
            model=Option,
        ),
        Spec(
            authoring.create_option_group,
            {
                "name": Text(source=(OptionGroup, "name")),
                "choose": Choice(source=(OptionGroup, "choose")),
            },
        ),
    ]
    return {spec.name: spec for spec in specs}


_REGISTRY = None


def specs():
    """Every authored verb's spec, keyed by verb name.

    Built on first ask, so importing this module never touches the app
    registry before Django is ready.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY
