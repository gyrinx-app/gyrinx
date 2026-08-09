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

    @property
    def help(self):
        """The model field's own words, resolved on read."""
        if self.source is None:
            return ""
        model, field_name = self.source
        return str(model._meta.get_field(field_name).help_text)


@dataclass(frozen=True)
class One(_Sourced):
    """One row of a model — a foreign key pick.

    ``filtered_by`` names the relations the form must respect when
    narrowing the queryset — ``("collection",)`` on a section pick means
    "a section of *that* collection", enforced in the generated form's
    ``clean()`` in words (step 2).
    """

    model: type = None
    optional: bool = False
    filtered_by: tuple = ()


@dataclass(frozen=True)
class Many(_Sourced):
    """Several rows of a model — an M2M pick."""

    model: type = None


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


def _build_registry():
    from n26.library import authoring
    from n26.library.models import (
        Affiliation,
        Archetype,
        Category,
        ChangesStat,
        Collection,
        CollectionSection,
        Counter,
        CounterAtLeast,
        DefaultAssignment,
        GangType,
        HasSubtypes,
        Hidden,
        LastingEffect,
        OffersChoice,
        OpAddsMiniature,
        PlacesCategory,
        Power,
        Profile,
        ProfileType,
        RequiresCompanions,
        Rule,
        Section,
        Skill,
        SkillTree,
        Specialisation,
        Stat,
        StatlineType,
        StatlineTypeStat,
        Subtype,
        TargetsMiniature,
        TargetsWeapons,
        Trait,
        Wargear,
        Weapon,
        WeaponAccessory,
        WeaponProfile,
    )
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS
    from n26.library.models.modifier import GRANTABLE_FIELDS, OFFERABLE_KINDS

    # What a built-in may be, derived from the DefaultAssignment row
    # itself so the union can never drift from the model's own keys.
    built_in_kinds = {
        name: f"library.{DefaultAssignment._meta.get_field(name).related_model.__name__}"
        for name in DEFAULT_ASSIGNABLE_FIELDS
    }

    specs = [
        # -- scopes, and the conditions that nest inside them ---------
        Spec(
            authoring.targets_model,
            {
                "conditions": Conditions(kinds=("has_subtypes", "counter_at_least")),
                "when_directly_assigned": Bool(
                    source=(TargetsMiniature, "when_directly_assigned")
                ),
            },
        ),
        Spec(
            authoring.has_subtypes,
            {"subtypes": Many(model=Subtype, source=(HasSubtypes, "subtypes"))},
        ),
        Spec(
            authoring.counter_at_least,
            {
                "counter": One(model=Counter, source=(CounterAtLeast, "counter")),
                "at_least": Int(source=(CounterAtLeast, "at_least")),
            },
        ),
        Spec(
            authoring.has_trait,
            {"trait": One(model=Trait, source=(TargetsWeapons, "with_trait"))},
        ),
        Spec(
            authoring.in_category,
            {"category": One(model=Category, source=(TargetsWeapons, "with_category"))},
        ),
        Spec(
            authoring.targets_weapons,
            {"conditions": Conditions(kinds=("has_trait", "in_category"))},
        ),
        Spec(authoring.targets_attached_weapon, {}),
        Spec(authoring.targets_gang, {}),
        # -- effects, worked out at read time --------------------------
        Spec(authoring.ef_adds, {"thing": Union(over=dict(GRANTABLE_FIELDS))}),
        Spec(authoring.ef_removes, {"thing": Union(over=dict(GRANTABLE_FIELDS))}),
        Spec(
            authoring.ef_changes_stat,
            {
                "stat": One(model=Stat, source=(ChangesStat, "stat")),
                "mode": Choice(source=(ChangesStat, "mode")),
                "amount": Int(source=(ChangesStat, "amount")),
            },
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
                "answer_host": Choice(source=(OffersChoice, "answer_host")),
            },
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
            label="places the chosen category",
        ),
        Spec(
            authoring.ef_requires_companions,
            {
                "for_each": One(model=Subtype, source=(RequiresCompanions, "for_each")),
                "at_least": Int(source=(RequiresCompanions, "at_least")),
                "of": One(model=Subtype, source=(RequiresCompanions, "of")),
            },
        ),
        # -- effects that write rows at purchase time -------------------
        Spec(
            authoring.op_adds_model,
            {"profile": One(model=Profile, source=(OpAddsMiniature, "profile"))},
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
                "price": Int(source=(WeaponProfile, "price")),
                "trade_point_price": Int(source=(WeaponProfile, "trade_point_price")),
                "is_exclusive": Bool(source=(WeaponProfile, "is_exclusive")),
                "traits": Many(model=Trait, source=(WeaponProfile, "traits")),
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
                "qualifier": Text(source=(Collection, "qualifier")),
                "library_author_help": Text(
                    source=(Collection, "library_author_help"), long=True
                ),
            },
        ),
        Spec(
            authoring.add_built_in,
            # No flat extras here: what attaching each kind asks for —
            # a counter's opening value — comes from the kind's own
            # ATTACHMENT_ASKS, resolved through the union.
            {"thing": Union(over=built_in_kinds, through=DefaultAssignment)},
            model=DefaultAssignment,
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
