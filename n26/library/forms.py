"""Forms generated from specs — the admin surface of the authoring verbs.

Step 2 of design/authoring-build-plan.md. ``generate_form(spec)`` turns
one verb's spec into a plain Django ``Form``; a valid form **compiles to
the verb call** (``form.compile()``), so what the admin can build and
what the API can express are the same thing by construction. On top sits
``ModifierComposerForm``, the hand-written shell for the one assembly
that is always three rows: pick a WHO, pick a WHAT, and say where the
modifier hangs.

The rules the forms keep:

* **Requiredness comes from the verb's signature** — a parameter with a
  default is optional, one without is required. Nothing is declared
  twice.
* **Help is the spec's help**, which is the model field's own words.
* **Refusals are words at form level, never database errors**: a
  section of the wrong collection, an effect that cannot apply to a
  scope — each is a ``ValidationError`` that says why, in the same
  words the models use.
* **Conditions are a formset of chips**: each chip picks a condition
  kind and fills that kind's fields, compiled by that condition's own
  spec.
* **The union picker can create name-only leaves inline** (a Rule, a
  Subtype) — a name and nothing else, because the wording stays in the
  book.

Templates are deliberately absent (merge-time); everything here is
asserted through form data in tests, the structures-before-renderers
rule again.
"""

import inspect

from django import forms
from django.core.exceptions import ValidationError

from n26.library import artwork
from n26.library.specs import (
    Artwork,
    Bool,
    Choice,
    Conditions,
    Int,
    Many,
    One,
    Text,
    Union,
    specs,
)

#: What each scope verb's targets can ever be — the form-level mirror of
#: ``n26.library.models.modifier._possible_kinds``, checked against it by a
#: drift test rather than trusted.
SCOPE_PRODUCES = {
    "targets_model": "model",
    "targets_weapons": "weapon_profile",
    "targets_attached_weapon": "weapon_profile",
    "targets_gang": "gang",
}

#: Which model each effect verb creates — for the compatibility check,
#: which runs ``accepts()`` on an unsaved instance so no row is written
#: before the form is known good. Guarded by a drift test.
EFFECT_MODELS = {
    "ef_adds": "AddsAssignable",
    "ef_removes": "RemovesAssignable",
    "ef_changes_stat": "ChangesStat",
    "ef_offers_choice": "OffersChoice",
    "ef_places": "PlacesCategory",
    "ef_places_choice": "PlacesCategory",
    "ef_requires_companions": "RequiresCompanions",
    "op_adds_model": "OpAddsMiniature",
}

#: Kinds the union picker may create inline: name-only leaves. The help
#: is the copyright guardrail, written once.
CREATABLE_INLINE = ("rule", "subtype")
NAME_ONLY_HELP = (
    "Name only. The rule's wording stays in the book. A bracket becomes "
    'the annotation, so "Leash (3\\")" is Leash at 3" — the same row the '
    "importer would make."
)


class PendingCreate:
    """A name-only leaf the form will create at compile time — typed
    into the union picker instead of picked."""

    def __init__(self, kind, name):
        self.kind = kind
        self.name = name


def _is_required(spec, name):
    """A parameter without a default must be filled; one with a default
    may be left alone. Read off the verb, never declared twice."""
    parameter = inspect.signature(spec.verb).parameters[name]
    return (
        parameter.default is inspect.Parameter.empty
        and parameter.kind is not inspect.Parameter.VAR_POSITIONAL
    )


def _model_class(label):
    from django.apps import apps

    return apps.get_model("library", label)


class _AuthoringChoiceField(forms.ModelChoiceField):
    """A picker that reads as an author needs it to.

    Two things may print the same name — the books give Delaque's and
    Goliath's beasts the same Ferocious jaws — so a picker showing only
    what a card shows would offer the same row twice. It labels with
    ``authoring_label`` where a kind has one.
    """

    def label_from_instance(self, obj):
        return getattr(obj, "authoring_label", None) or str(obj)


class _AuthoringMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return getattr(obj, "authoring_label", None) or str(obj)


def _labelled(model):
    """A picker's option queryset, with what the labels read joined in.

    Several kinds say themselves through a foreign key — a category
    names its section, a section its collection — so a picker labelling
    each option one row at a time costs a query per choice. Joining
    every forward relation keeps the option list to one query whatever
    the kind.
    """
    related = [
        field.name
        for field in model._meta.get_fields()
        if field.concrete and (field.many_to_one or field.one_to_one)
    ]
    return model.objects.select_related(*related)


def _form_fields(spec, name, kind):
    """The Django form field(s) one spec field becomes."""
    if isinstance(kind, One):
        return {
            name: _AuthoringChoiceField(
                queryset=_labelled(kind.model),
                required=_is_required(spec, name),
                help_text=kind.help,
            )
        }
    if isinstance(kind, Many):
        return {
            name: _AuthoringMultipleChoiceField(
                queryset=_labelled(kind.model),
                required=_is_required(spec, name),
                help_text=kind.help,
            )
        }
    if isinstance(kind, Int):
        return {
            name: forms.IntegerField(
                required=_is_required(spec, name), help_text=kind.help
            )
        }
    if isinstance(kind, Bool):
        return {name: forms.BooleanField(required=False, help_text=kind.help)}
    if isinstance(kind, Text):
        return {
            name: forms.CharField(
                required=_is_required(spec, name),
                help_text=kind.help,
                widget=forms.Textarea(attrs={"rows": 3})
                if getattr(kind, "long", False)
                else forms.TextInput(),
            )
        }
    if isinstance(kind, Artwork):
        # Two controls, one stored value. The upload is not a spec field —
        # nothing about it is kept — so it never reaches the verb; clean()
        # turns it into the address the box holds.
        return {
            name: forms.CharField(
                required=_is_required(spec, name),
                help_text=kind.help,
            ),
            f"{name}_upload": forms.FileField(
                required=False,
                label="Upload a drawing",
                help_text=(
                    "An SVG file. Uploading one stores it and fills in the "
                    "address above, replacing whatever is there."
                ),
                widget=forms.ClearableFileInput(attrs={"accept": ".svg,image/svg+xml"}),
            ),
        }
    if isinstance(kind, Choice):
        return {
            name: forms.ChoiceField(
                choices=kind.choices,
                required=_is_required(spec, name),
                help_text=kind.help,
            )
        }
    if isinstance(kind, Union):
        # Each control says which kind it belongs to, so the page can
        # show only the chosen kind's picker (base.html reads the
        # markers). Without the script every control shows and the form
        # still works — the markers are hints, not structure.
        # The field names carry the spec field's stem ("thing_subtype")
        # so a form can hold several unions; the labels never show it —
        # Django would otherwise write "Thing new subtype".
        def spoken(option):
            return option.replace("_", " ")

        fields = {
            f"{name}_kind": forms.ChoiceField(
                choices=[(option, spoken(option)) for option in kind.over],
                label="Kind",
                widget=forms.Select(attrs={"data-union-kind": name}),
            )
        }

        def member_attrs(*options):
            return {"data-union-of": name, "data-union-member": " ".join(options)}

        for option, label in kind.over.items():
            fields[f"{name}_{option}"] = _AuthoringChoiceField(
                queryset=_labelled(_model_class(label.split(".")[-1])),
                required=False,
                label=spoken(option).capitalize(),
                widget=forms.Select(attrs=member_attrs(option)),
            )
            if option in CREATABLE_INLINE:
                fields[f"{name}_new_{option}"] = forms.CharField(
                    required=False,
                    label=f"New {spoken(option)}",
                    help_text=NAME_ONLY_HELP,
                    widget=forms.TextInput(attrs=member_attrs(option)),
                )
        # What attaching each kind asks for, beyond the pick — declared
        # by the kinds themselves, never enumerated here. One form field
        # per distinct through column, marked with every kind that
        # declares it, always optional: whether it applies is decided in
        # clean(), by the chosen kind.
        for ask_name, options in _union_asks(kind).items():
            field = kind.through._meta.get_field(ask_name).formfield(required=False)
            field.widget.attrs.update(member_attrs(*options))
            fields[ask_name] = field
        return fields
    raise ValueError(f"No form field for {type(kind).__name__}")


def _union_asks(kind):
    """``{through column: (kinds that declare it)}`` for one union —
    each kind's own ATTACHMENT_ASKS, folded across the union's kinds."""
    from n26.library.offers import attachment_asks

    if kind.through is None:
        return {}
    asked = {}
    for option, label in kind.over.items():
        for ask in attachment_asks(_model_class(label.split(".")[-1]), kind.through):
            asked.setdefault(ask.name, []).append(option)
    return {name: tuple(options) for name, options in asked.items()}


class GeneratedForm(forms.Form):
    """Base for spec-generated forms: filtered_by and unions in clean,
    and ``compile()`` performing the verb call."""

    spec = None
    #: ``{union field: {through column: (kinds that declare it)}}`` —
    #: which extra inputs ride each union, so clean() can keep only the
    #: chosen kind's and verb_data() can pass them on.
    union_asks = {}

    def __init__(self, *args, collection=None, **kwargs):
        super().__init__(*args, **kwargs)
        #: The collection this form is being filled *within*, when the
        #: flow knows one — what filtered_by checks against.
        self.collection = collection

    def clean(self):
        cleaned = super().clean()
        for name, kind in self.spec.fields.items():
            if isinstance(kind, One) and "collection" in kind.filtered_by:
                picked = cleaned.get(name)
                if (
                    picked is not None
                    and self.collection is not None
                    and picked.collection != self.collection
                ):
                    self.add_error(
                        name,
                        f"That section belongs to {picked.collection.name}, "
                        f"not {self.collection.name}.",
                    )
            if isinstance(kind, Union):
                self._clean_union(name, kind, cleaned)
            if isinstance(kind, Artwork):
                artwork.clean_onto(self, cleaned, name, f"{name}_upload")
        return cleaned

    def _clean_union(self, name, kind, cleaned):
        """Exactly one thing, picked or newly named, of the chosen kind."""
        chosen = cleaned.get(f"{name}_kind")
        if not chosen:
            return
        picked = cleaned.get(f"{name}_{chosen}")
        named = (cleaned.get(f"{name}_new_{chosen}") or "").strip()
        if picked is not None and named:
            self.add_error(
                f"{name}_{chosen}",
                f"Pick an existing {chosen} or name a new one, not both.",
            )
        elif picked is not None:
            cleaned[name] = picked
        elif named:
            cleaned[name] = PendingCreate(chosen, named)
        else:
            self.add_error(f"{name}_{chosen}", f"Pick or name a {chosen}.")
        # An ask typed for one kind must not survive switching to a
        # kind that never asked — the value only means what the chosen
        # kind says it means.
        for ask_name, options in self.union_asks.get(name, {}).items():
            if chosen not in options:
                cleaned[ask_name] = None

    def verb_data(self):
        """The spec-field values a valid form holds, ready for the verb:
        helper fields (a union's ``_kind`` and per-kind pickers) are
        gone, empties fall back to the verb's defaults, and name-only
        creations happen here — after validation, before the verb.
        """
        from n26.library import authoring

        def _new_rule(typed):
            # A rule's annotation is part of its identity, so a bracket
            # the author typed has to land in the annotation — otherwise
            # this makes a rule *named* "Leash (3\")" that prints exactly
            # like the real one and matches nothing.
            name, annotation = authoring.split_annotation(typed)
            return authoring.create_rule(name, annotation=annotation)

        creators = {
            "rule": _new_rule,
            "subtype": authoring.create_subtype,
        }
        data = {}
        for name in self.spec.fields:
            value = self.cleaned_data.get(name)
            if value in (None, "", []) or (
                value is False and not _is_required(self.spec, name)
            ):
                continue
            if isinstance(value, PendingCreate):
                value = creators[value.kind](value.name)
            data[name] = value
        # The asks that survived clean() — only the chosen kind's, so
        # the verb sees a counter's amount and never a collection's.
        for asks in self.union_asks.values():
            for ask_name in asks:
                value = self.cleaned_data.get(ask_name)
                if value not in (None, ""):
                    data[ask_name] = value
        return data

    def compile(self, conditions=()):
        """The verb call this valid form amounts to.

        ``conditions`` are ``(verb_name, payload)`` pairs from the
        condition formset, passed through to the spec.
        """
        data = self.verb_data()
        if conditions:
            data["conditions"] = list(conditions)
        return self.spec.compile(data)

    @classmethod
    def opened_on(cls, thing, data=None, files=None, prefix="edit"):
        """The same form, filled in from a row that already exists.

        A creating spec describes its verb's parameters, and for the
        leaf kinds every one of those names a column on the thing the
        verb makes — so the spec reads both ways, and editing needs no
        second description of a kind. A guard holds that true
        (tests/sandbox/test_authoring_views.py).

        Prefixed, because a thing's page carries the form that adds a
        part as well as this one, and the two specs name fields alike:
        unprefixed, a weapon's page draws two inputs called
        ``is_exclusive`` sharing one id, and the switches cross-wire —
        saving the weapon marks it exclusive because the other form's
        control answered for it.
        """
        initial = {
            name: getattr(thing, name)
            for name in cls.spec.fields
            if hasattr(thing, name)
        }
        return cls(data, files, initial=initial, prefix=prefix)

    def apply_to(self, thing):
        """Write this valid form's fields onto an existing row.

        The verb is for making things; changing one is a write to the
        columns the spec already names, which is ``authoring.revise`` —
        one write path, shared with a re-import of a changed
        spreadsheet. Values the form does not carry are left alone
        rather than blanked.

        A many-to-many field is the exception the shared verb refuses,
        and rightly: replacing a set is a decision. Here the decision is
        already made — a multi-select carries the whole set, so what it
        does not name has been taken off.
        """
        from n26.library.authoring import revise

        columns, sets = {}, {}
        for name in self.spec.fields:
            if name not in self.fields:
                continue
            value = self.cleaned_data.get(name)
            if thing._meta.get_field(name).many_to_many:
                sets[name] = value
            else:
                columns[name] = value
        revise(thing, **columns)
        for name, value in sets.items():
            getattr(thing, name).set(value or ())
        return thing


def generate_form(spec):
    """A plain Django ``Form`` subclass for one verb, from its spec.

    ``Conditions`` fields do not become flat form fields — they ride a
    formset built by :func:`condition_formset_for`, and the compiled
    payloads are handed to ``compile()``.
    """
    attrs = {"spec": spec, "union_asks": {}}
    for name, kind in spec.fields.items():
        if isinstance(kind, Conditions):
            continue
        if isinstance(kind, Union) and kind.through is not None:
            asks = _union_asks(kind)
            taken = [ask for ask in asks if ask in spec.fields]
            assert not taken, (
                f"{spec.name}'s {name} union asks for {taken}, which the "
                f"spec already names — an ask and a spec field cannot "
                f"share a name."
            )
            attrs["union_asks"] = {**attrs["union_asks"], name: asks}
        attrs.update(_form_fields(spec, name, kind))
    return type(f"{_camel(spec.name)}Form", (GeneratedForm,), attrs)


def _camel(verb_name):
    return "".join(part.title() for part in verb_name.split("_"))


# --- The condition formset ---------------------------------------------------


def condition_chip_form(kinds):
    """One chip: pick a condition kind, fill that kind's fields.

    The chip carries the union of every allowed kind's fields, all
    optional at the field level; ``clean()`` requires exactly the chosen
    kind's, in words. ``payload()`` is what the scope form's
    ``compile()`` wants.
    """
    attrs = {
        "kinds": kinds,
        "kind": forms.ChoiceField(choices=[(kind, kind) for kind in kinds]),
    }
    for kind_name in kinds:
        spec = specs()[kind_name]
        for field_name, field_kind in spec.fields.items():
            for name, field in _form_fields(spec, field_name, field_kind).items():
                field.required = False
                attrs[name] = field

    def clean(self):
        cleaned = forms.Form.clean(self)
        chosen = cleaned.get("kind")
        if not chosen:
            return cleaned
        for field_name in specs()[chosen].fields:
            if field_name in self.errors:
                continue
            value = cleaned.get(field_name)
            # Empty is none, blank, or an exhausted iterable (an empty
            # queryset) — but never a legitimate zero.
            empty = (
                value is None
                or value == ""
                or (hasattr(value, "__iter__") and not any(True for _ in value))
            )
            if empty:
                self.add_error(field_name, f"A {chosen} condition needs {field_name}.")
        return cleaned

    def payload(self):
        chosen = self.cleaned_data["kind"]
        return (
            chosen,
            {
                field_name: self.cleaned_data[field_name]
                for field_name in specs()[chosen].fields
            },
        )

    attrs["clean"] = clean
    attrs["payload"] = payload
    return type("ConditionChipForm", (forms.Form,), attrs)


def condition_formset_for(spec, data=None, prefix="conditions", extra=0):
    """The formset of condition chips a scope form carries, or ``None``
    for scopes that take no conditions. ``extra`` is how many empty
    chips to draw — the composer page carries it in the URL, so "add a
    condition" is a link and the state survives a refresh."""
    kinds = next(
        (kind.kinds for kind in spec.fields.values() if isinstance(kind, Conditions)),
        None,
    )
    if kinds is None:
        return None
    formset_class = forms.formset_factory(condition_chip_form(kinds), extra=extra)
    return formset_class(data, prefix=prefix)


# --- Suggested built-ins: the create page's quick build-out -------------------


def suggestion_form_for(kind_model):
    """The form for what a new ``kind_model`` usually comes with, or
    ``None`` when it suggests nothing (``SUGGESTED_BUILT_INS``, resolved
    by library/offers.py).

    One field group per suggestion, everything optional — blank means
    skipped. A fixed suggestion asks only for its extra values (Starting
    XP is one number field); an open one is a picker over the
    pre-queried candidates. ``apply(created)`` performs ``add_built_in``
    for whatever was taken, in the create view's own transaction.
    """
    from n26.library.offers import built_in_offer

    offer = built_in_offer(kind_model)
    if not offer:
        return None

    attrs = {"offer": offer}
    for suggestion in offer:
        lone_ask = suggestion.fixed is not None and len(suggestion.asks) == 1
        if suggestion.fixed is None:
            if not suggestion.candidates:
                continue  # nothing to offer yet; apply() skips it too
            field_class = (
                _AuthoringMultipleChoiceField
                if suggestion.many
                else _AuthoringChoiceField
            )
            attrs[suggestion.slug] = field_class(
                queryset=suggestion.model.objects.filter(
                    pk__in=[row.pk for row in suggestion.candidates]
                ),
                required=False,
                label=suggestion.label,
            )
        elif not suggestion.asks:
            attrs[suggestion.slug] = forms.BooleanField(
                required=False, label=suggestion.label
            )
        for ask in suggestion.asks:
            field_class = (
                forms.IntegerField if ask.input == "number" else forms.CharField
            )
            attrs[f"{suggestion.slug}_{ask.name}"] = field_class(
                required=False,
                label=suggestion.label
                if lone_ask
                else f"{suggestion.label}: {ask.name}",
                help_text=ask.help,
            )

    def apply(self, created):
        """The built-ins the author took, made against ``created``."""
        from n26.library import authoring

        made = []
        for suggestion in self.offer:
            values = {
                ask.name: value
                for ask in suggestion.asks
                if (value := self.cleaned_data.get(f"{suggestion.slug}_{ask.name}"))
                not in (None, "")
            }
            if suggestion.fixed is not None:
                taken = (
                    bool(values)
                    if suggestion.asks
                    else bool(self.cleaned_data.get(suggestion.slug))
                )
                things = [suggestion.fixed] if taken else []
            elif suggestion.many:
                things = list(self.cleaned_data.get(suggestion.slug) or ())
            else:
                picked = self.cleaned_data.get(suggestion.slug)
                things = [picked] if picked is not None else []
            for thing in things:
                made.append(authoring.add_built_in(created, thing, **values))
        return made

    attrs["apply"] = apply
    return type("SuggestedBuiltInsForm", (forms.Form,), attrs)


# --- The modifier composer ----------------------------------------------------


#: Which model each scope verb writes — the label source for the
#: composer's WHO select. SCOPE_PRODUCES guards the key set by drift
#: test, so a new scope verb shows up here or shows up loudly.
SCOPE_MODELS = {
    "targets_model": "TargetsMiniature",
    "targets_weapons": "TargetsWeapons",
    "targets_attached_weapon": "TargetsAttachedWeapon",
    "targets_gang": "TargetsGang",
}


def _verb_label(name, model_label):
    """A verb choice as an author reads it — the model's own verbose
    name ("targets the model"), the verb name when nothing better is
    known."""
    if model_label is None:
        return name
    model = _model_class(model_label)
    return str(model._meta.verbose_name)


def _scope_choices():
    return [
        (name, _verb_label(name, SCOPE_MODELS.get(name)))
        for name in specs()
        if name.startswith("targets_")
    ]


def _effect_choices():
    return [
        (name, _verb_label(name, EFFECT_MODELS.get(name)))
        for name in specs()
        if name.startswith(("ef_", "op_"))
    ]


class ModifierComposerForm(forms.Form):
    """One form for the three-row assembly: a WHO pane, a WHAT pane,
    and where the modifier hangs.

    The panes are spec-generated forms bound from the same data under
    the ``who-`` and ``what-`` prefixes, picked by ``scope_kind`` and
    ``effect_kind``; conditions ride the ``conditions-`` formset. The
    composer opens from an assignable's page ("attach here" —
    ``attach_to=``) or standalone; ``keep_reusable`` leaves the modifier
    unattached either way, for ``attach_modifiers_to`` later.

    ``save()`` is ``modifier(auto_name, scope, effect, attach_to=…)``
    where the auto-name is the modifier's own sentence.
    """

    scope_kind = forms.ChoiceField(choices=_scope_choices, label="Who it reaches")
    effect_kind = forms.ChoiceField(choices=_effect_choices, label="What it does")
    name = forms.CharField(
        required=False,
        help_text="Blank writes the modifier's own sentence as its name.",
    )
    keep_reusable = forms.BooleanField(
        required=False,
        label="Keep reusable",
        help_text=(
            "Save without attaching here, so it can be attached to "
            "several carriers later."
        ),
    )

    def __init__(self, data=None, *, attach_to=None, collection=None, **kwargs):
        super().__init__(data, **kwargs)
        self.attach_to = attach_to
        self.collection = collection
        self.who_form = None
        self.what_form = None
        self.condition_formset = None

    @classmethod
    def unbound(cls, scope_kind, effect_kind, *, attach_to=None, chips=0):
        """The composer ready to draw, before anything is submitted.

        The bound path builds its panes in ``clean()`` from the posted
        kinds; a page rendering step two of the flow has no data yet,
        only the kinds carried in the URL. ``chips`` is how many empty
        condition rows to offer — also URL state, so "add a condition"
        is a plain link.
        """
        form = cls(
            attach_to=attach_to,
            initial={"scope_kind": scope_kind, "effect_kind": effect_kind},
        )
        form.who_form = generate_form(specs()[scope_kind])(prefix="who")
        form.what_form = generate_form(specs()[effect_kind])(prefix="what")
        form.condition_formset = condition_formset_for(specs()[scope_kind], extra=chips)
        return form

    def clean(self):
        cleaned = super().clean()
        scope_kind = cleaned.get("scope_kind")
        effect_kind = cleaned.get("effect_kind")
        if not scope_kind or not effect_kind:
            return cleaned

        self.who_form = generate_form(specs()[scope_kind])(
            self.data, prefix="who", collection=self.collection
        )
        self.what_form = generate_form(specs()[effect_kind])(
            self.data, prefix="what", collection=self.collection
        )
        self.condition_formset = condition_formset_for(specs()[scope_kind], self.data)

        for pane, sub in (("who", self.who_form), ("what", self.what_form)):
            if not sub.is_valid():
                for field, errors in sub.errors.items():
                    for error in errors:
                        self.add_error(None, f"{pane} {field}: {error}")
        if self.condition_formset is not None and not self.condition_formset.is_valid():
            for index, errors in enumerate(self.condition_formset.errors):
                for field, messages in errors.items():
                    for message in messages:
                        self.add_error(
                            None, f"condition {index + 1} {field}: {message}"
                        )

        if not self.errors:
            self._check_compatibility(scope_kind, effect_kind)
        return cleaned

    def _check_compatibility(self, scope_kind, effect_kind):
        """The Modifier.clean() check, before anything is written.

        Runs ``accepts()`` on an *unsaved* effect instance, so a trait
        aimed at a model is a form error in words — never a database
        constraint tripping after rows exist.
        """
        effect = self._transient_effect(effect_kind)
        target_kind = SCOPE_PRODUCES[scope_kind]
        if not effect.accepts(target_kind):
            raise ValidationError(
                f"{effect_kind} cannot apply to {scope_kind} — a trait goes "
                f"on a weapon, a subtype or skill goes on a model, and only "
                f"the gang can be asked for companions."
            )

    def _transient_effect(self, effect_kind):
        from n26.library.models.modifier import GRANTABLE_FIELDS

        model = _model_class(EFFECT_MODELS[effect_kind])
        if effect_kind in ("ef_adds", "ef_removes"):
            thing = self.what_form.cleaned_data.get("thing")
            if isinstance(thing, PendingCreate):
                # A new-named Rule or Subtype: both live on models, which
                # an empty instance (no trait set) already says.
                return model()
            field = next(
                name
                for name, label in GRANTABLE_FIELDS.items()
                if isinstance(thing, _model_class(label.split(".")[-1]))
            )
            return model(**{field: thing})
        return model()

    def save(self):
        """Compile both panes, glue with the modifier verb, attach."""
        from n26.library import authoring

        payloads = (
            [chip.payload() for chip in self.condition_formset.forms]
            if self.condition_formset is not None
            else []
        )
        scope = self.who_form.compile(conditions=payloads)
        effect = self.what_form.compile()
        name = self.cleaned_data.get("name") or f"{scope}: {effect}"
        target = None if self.cleaned_data.get("keep_reusable") else self.attach_to
        return authoring.modifier(name, scope, effect, attach_to=target)


# --- Statlines: a form whose fields are data ---------------------------------


def statline_form_for(statline_type):
    """One field per stat of a statline type — the one form the spec
    system deliberately cannot generate.

    A spec describes a *verb's parameters*, and ``set_statline`` takes
    ``**values`` whose names come from content: the stats of whichever
    statline type the owner uses. So this reads the shape off the data
    instead, and compiles to the same verb. Every field is optional —
    a blank cell is a stat the book leaves blank, drawn as a dash — and
    every value is stored as typed, since ``S`` (the wielder's Strength)
    and ``E`` (engaged only) are as legitimate as ``4``.
    """
    attrs = {"statline_type": statline_type}
    for type_stat in statline_type.stats.select_related("stat"):
        stat = type_stat.stat
        attrs[stat.field_name] = forms.CharField(
            required=False,
            label=stat.short_name,
            help_text=stat.full_name,
            widget=forms.TextInput(attrs={"placeholder": stat.placeholder, "size": 6}),
        )

    def save(self, owner):
        from n26.library import authoring

        values = {
            name: value
            for name, value in self.cleaned_data.items()
            if str(value).strip()
        }
        if not values:
            return None
        return authoring.set_statline(owner, **values)

    attrs["save"] = save
    return type("StatlineForm", (forms.Form,), attrs)
