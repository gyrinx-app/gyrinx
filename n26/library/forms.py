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
    "targets_every_model": "model",
    "targets_weapons": "weapon_profile",
    "targets_attached_weapon": "weapon_profile",
    "targets_gang": "gang",
    "targets_gang_alone": "gang",
}

#: Which model each effect verb creates — for the compatibility check,
#: which runs ``accepts()`` on an unsaved instance so no row is written
#: before the form is known good. Guarded by a drift test.
EFFECT_MODELS = {
    "ef_adds": "AddsAssignable",
    "ef_removes": "RemovesAssignable",
    "ef_changes_stat": "ChangesStat",
    "ef_contributes_to_counter": "ContributesToCounter",
    "ef_changes_category": "ChangesCategory",
    "ef_offers_choice": "OffersChoice",
    "ef_places": "PlacesCategory",
    "ef_places_choice": "PlacesCategory",
    "ef_requires_companions": "RequiresCompanions",
    "ef_allows_at_most": "AllowsAtMost",
    "op_adds_model": "OpAddsMiniature",
    "op_changes_counter": "OpChangesCounter",
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


def _switch_default(spec, name):
    """What the verb does with a switch nobody says anything about.

    ``True`` or ``False`` where the parameter has a default, and neither
    where it has none — that switch is the author's to answer. Two things
    read it: a create form draws the switch where the verb starts it, and an
    unchecked box may only be dropped as "say nothing" where saying nothing
    means off.
    """
    return inspect.signature(spec.verb).parameters[name].default


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
                label=kind.label,
            )
        }
    if isinstance(kind, Many):
        return {
            name: _AuthoringMultipleChoiceField(
                queryset=_labelled(kind.model),
                required=_is_required(spec, name),
                help_text=kind.help,
                label=kind.label,
            )
        }
    if isinstance(kind, Int):
        return {
            name: forms.IntegerField(
                required=_is_required(spec, name),
                help_text=kind.help,
                label=kind.label,
            )
        }
    if isinstance(kind, Bool):
        return {
            name: forms.BooleanField(
                required=False,
                initial=_switch_default(spec, name) is True,
                help_text=kind.help,
                label=kind.label,
            )
        }
    if isinstance(kind, Text):
        return {
            name: forms.CharField(
                required=_is_required(spec, name),
                help_text=kind.help,
                label=kind.label,
                # The column's own limit, so an overlong value is this
                # field's error rather than the database refusing the
                # INSERT as a 500.
                max_length=kind.max_length,
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
        # A choice the verb defaults may be left alone, and a select
        # with no empty entry submits its first option — so the blank
        # has to be offered, or "none of these" is unsayable and every
        # form quietly picks the first.
        wanted = _is_required(spec, name)
        blank = [] if wanted else [("", "—")]
        return {
            name: forms.ChoiceField(
                choices=blank + list(kind.choices),
                required=wanted,
                help_text=kind.help,
                label=kind.label,
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

        # A union whose parameter has a default may be left alone, like
        # any other. The blank choice has to be offered for that to be
        # possible: a select with no empty entry submits its first
        # option, so "nothing" would be unsayable.
        wanted = _is_required(spec, name)
        blank = [] if wanted else [("", "Nothing")]
        fields = {
            f"{name}_kind": forms.ChoiceField(
                choices=blank + [(option, spoken(option)) for option in kind.over],
                required=wanted,
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


def _initial_from(spec, row):
    """A form's opening values, read off a row that already exists.

    Straight off the columns, which is what nearly every spec field
    names. The two shapes that are not: a union fills two controls (the
    kind, and that kind's picker), and a choice whose stored column is
    not the parameter says how it reads itself back.
    """
    initial = {}
    for name, kind in spec.fields.items():
        if isinstance(kind, Conditions):
            # Conditions are rows of their own, drawn as a formset.
            continue
        if isinstance(kind, Union):
            chosen = next(
                (
                    option
                    for option in kind.over
                    if getattr(row, f"{option}_id", None) is not None
                ),
                None,
            )
            if chosen is not None:
                initial[f"{name}_kind"] = chosen
                initial[f"{name}_{chosen}"] = getattr(row, chosen)
        elif isinstance(kind, Choice) and kind.reads is not None:
            initial[name] = kind.reads(row)
        elif not hasattr(row, name):
            continue
        elif isinstance(kind, Many):
            initial[name] = getattr(row, name).all()
        else:
            initial[name] = getattr(row, name)
    return initial


class GeneratedForm(forms.Form):
    """Base for spec-generated forms: filtered_by and unions in clean,
    and ``compile()`` performing the verb call."""

    spec = None
    #: ``{union field: {through column: (kinds that declare it)}}`` —
    #: which extra inputs ride each union, so clean() can keep only the
    #: chosen kind's and verb_data() can pass them on.
    union_asks = {}

    def __init__(self, *args, collection=None, carrier=None, **kwargs):
        super().__init__(*args, **kwargs)
        #: The collection this form is being filled *within*, when the
        #: flow knows one — what filtered_by checks against.
        self.collection = collection
        #: The thing this part is being added to, when the flow knows
        #: one — what ``within`` narrows a picker to.
        self.carrier = carrier
        if carrier is None:
            return
        for name, kind in self.spec.fields.items():
            if isinstance(kind, One) and kind.within:
                self.fields[name].queryset = getattr(carrier, kind.within).all()

    def clean(self):
        cleaned = super().clean()
        for name, kind in self.spec.fields.items():
            if isinstance(kind, One) and kind.within and self.carrier is not None:
                picked = cleaned.get(name)
                # Asked of the same accessor that narrowed the picker, so
                # what is offered and what is accepted are one statement
                # rather than two that can come to disagree — and one that
                # holds for any kind, not only the ones whose rows can name
                # what they belong to. Asked of the database rather than of
                # a list, so a wide accessor costs one row and not all of
                # them.
                if (
                    picked is not None
                    and not getattr(self.carrier, kind.within)
                    .filter(pk=picked.pk)
                    .exists()
                ):
                    self.add_error(name, f"That does not belong to {self.carrier}.")
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
                value is False and _switch_default(self.spec, name) is False
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

        What the spec calls **fixed** is left out: those answers are
        what the thing is, and the way to a different answer is a
        different thing. Left out rather than refused, and taken off the
        form rather than only hidden — ``apply_to`` writes the fields the
        form carries, so a submission naming one anyway writes nothing.
        """
        form = cls(data, files, initial=_initial_from(cls.spec, thing), prefix=prefix)
        for name, kind in cls.spec.fields.items():
            if getattr(kind, "fixed", False):
                form.fields.pop(name, None)
        return form

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
        does not name has been taken off — and the spec field names the
        verb that owns saying so (``Many.replaced_by``), so this writes
        through the same verb an importer does. Sets sharing a verb are
        handed over together, because facts stated together are stated
        together: the four use lists are one answer about one row.

        An empty box over a column that cannot hold nothing says nothing,
        so the stored value stands. A number field left blank cleans to no
        value at all, and writing that would have the database refuse the
        whole save — with a message about whatever the caller guessed a
        refusal means. Nought is said by typing nought.
        """
        from n26.library.authoring import revise

        columns, sets = {}, {}
        for name in self.spec.fields:
            if name not in self.fields:
                continue
            value = self.cleaned_data.get(name)
            column = thing._meta.get_field(name)
            if column.many_to_many:
                sets[name] = value
            elif value is None and not column.null:
                continue
            else:
                columns[name] = value
        # The row's own sense check runs before anything is written, so
        # two boxes that make no sense together are refused in words on
        # the form — the database would refuse them too, but the page
        # can only read that as a name already taken. Only clean(): the
        # form has checked each field, and uniqueness and constraints
        # are the database's, whose refusals the pages already put into
        # words of their own.
        for name, value in columns.items():
            setattr(thing, name, value)
        thing.clean()
        revise(thing, **columns)
        owned = {}
        for name, value in sets.items():
            replace = self.spec.fields[name].replaced_by
            if replace is None:
                raise ValueError(
                    f"{name} is a set this form can edit with no verb that "
                    f"owns replacing it — give its spec field a replaced_by "
                    f"saying what leaving the set means"
                )
            owned.setdefault(replace, {})[name] = value or ()
        for replace, values in owned.items():
            replace(thing, **values)
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


def condition_formset_for(spec, data=None, prefix="conditions", extra=0, initial=None):
    """The formset of condition chips a scope form carries, or ``None``
    for scopes that take no conditions. ``extra`` is how many empty
    chips to draw — the composer page carries it in the URL, so "add a
    condition" is a link and the state survives a refresh. ``initial``
    is the narrowing a scope already has, one entry per chip.

    A scope narrowed too far is corrected by taking a condition off it,
    and the chip goes there and then: the click posts the form,
    the view drops that chip from what arrived
    (``without_condition_chip``) and sends the rest back as an address.
    There is no delete field, because a tickbox that only takes effect
    on the next save reads as a control that does nothing.
    """
    kinds = next(
        (kind.kinds for kind in spec.fields.values() if isinstance(kind, Conditions)),
        None,
    )
    if kinds is None:
        return None
    formset_class = forms.formset_factory(condition_chip_form(kinds), extra=extra)
    return formset_class(data, prefix=prefix, initial=initial)


def without_condition_chip(data, index, prefix="conditions"):
    """Posted form data with one condition chip taken out of it.

    A formset addresses its forms by position, so dropping one means
    renumbering every chip after it and telling the management form
    there is one fewer. Left as a gap, the missing position reads as a
    chip the author emptied and the last chip is read twice.

    An index naming no chip leaves the data alone — a click cannot be
    allowed to rewrite a form on the strength of a number that came
    from the page.
    """
    try:
        total = int(data.get(f"{prefix}-TOTAL_FORMS", 0))
    except TypeError, ValueError:
        return data
    if not 0 <= index < total:
        return data

    def fields_of(position):
        start = f"{prefix}-{position}-"
        return [(key, key[len(start) :]) for key in data if key.startswith(start)]

    reduced = data.copy()
    for position in range(index, total):
        for key, _ in fields_of(position):
            del reduced[key]
    for position in range(index + 1, total):
        for key, field in fields_of(position):
            reduced.setlist(f"{prefix}-{position - 1}-{field}", data.getlist(key))
    reduced[f"{prefix}-TOTAL_FORMS"] = str(total - 1)
    return reduced


def _conditions_of(scope):
    """The narrowing a scope already carries, as chips a formset opens on.

    Every scope states its narrowing the same way — rows hung off it —
    so one loop reads them all back. A narrowing missing from here is one
    the composer drops the moment an author saves the modifier for any
    other reason.
    """
    # A condition's relation on its scope and the verb that builds it
    # are the same word, which is what lets rows be read back without a
    # second table saying so. A guard in the suite holds that true.
    chips = []
    for relation in getattr(scope, "CONDITIONS", ()):
        for row in getattr(scope, relation).all():
            chips.append({"kind": relation, **_initial_from(specs()[relation], row)})
    return chips


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
    "targets_every_model": "TargetsMiniature",
    "targets_weapons": "TargetsWeapons",
    "targets_attached_weapon": "TargetsAttachedWeapon",
    "targets_gang": "TargetsGang",
    "targets_gang_alone": "TargetsGang",
}


def _verb_label(name, model_label):
    """A verb choice as an author reads it — the spec's own label where
    it states one, the model's verbose name otherwise, the verb name
    when nothing better is known.

    The spec speaks first because two verbs can write one model, and a
    picker labelling both from the model shows one choice twice — the
    author cannot tell which of the two "places category" rows carries
    the category field.
    """
    spec = specs().get(name)
    if spec is not None and spec.label:
        return spec.label
    if model_label is None:
        return name
    model = _model_class(model_label)
    return str(model._meta.verbose_name)


def _scope_verb(scope):
    """Which verb builds this scope row — SCOPE_MODELS read backwards,
    for a composer opened on a modifier that already exists.

    Two scope models each carry two verbs, told apart by the row: the
    reach an author picked is which verb they picked.
    """
    name = type(scope).__name__
    if name == "TargetsMiniature":
        return (
            "targets_every_model"
            if scope.reach == scope.Reach.EVERY_MODEL
            else "targets_model"
        )
    if name == "TargetsGang":
        return "targets_gang" if scope.echoes else "targets_gang_alone"
    return next(verb for verb, model in SCOPE_MODELS.items() if model == name)


def _effect_verb(effect):
    """Which verb builds this effect row.

    One model can have two verbs where both write the same columns and
    mean different things: a placement either names a category or takes
    whatever the carrier chose, and the flag is which.
    """
    name = type(effect).__name__
    if name == "PlacesCategory":
        return "ef_places_choice" if effect.the_chosen else "ef_places"
    return next(verb for verb, model in EFFECT_MODELS.items() if model == name)


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


#: What each effect verb can ever apply to — the kind pickers' own copy
#: of the models' ``accepts()``, for greying an effect card the moment a
#: scope is picked. Stated rather than derived, because ``ef_adds`` and
#: ``ef_removes`` reach a weapon's line only through a trait, which a
#: bare instance's ``accepts()`` cannot see; a drift test holds the rest
#: of the table to the models.
EFFECT_CAN_TARGET = {
    "ef_adds": ("model", "weapon_profile", "gang"),
    "ef_removes": ("model", "weapon_profile", "gang"),
    "ef_changes_stat": ("model", "weapon_profile"),
    "ef_contributes_to_counter": ("model", "gang"),
    "ef_changes_category": ("model",),
    "ef_offers_choice": ("model", "gang"),
    "ef_places": ("model",),
    "ef_places_choice": ("model",),
    "ef_requires_companions": ("gang",),
    "ef_allows_at_most": ("model", "gang"),
    "op_adds_model": ("model", "gang"),
    "op_changes_counter": ("model", "gang"),
}

#: The target kinds as an author reads them, for a greyed card's reason.
_TARGET_WORDS = {
    "model": "a model",
    "weapon_profile": "a weapon",
    "gang": "the gang",
}


def scope_kind_cards(picked="", carrier=None):
    """The WHO picker as cards: label, blurb and example off each verb's
    spec, plus what the scope produces (for the client-side effect gate)
    and — when the composer hangs on a carrier — whether this scope can
    ever speak for it. "The weapon it's fitted to" is greyed on anything
    that is never bolted to a weapon, with the reason on the card.
    """
    cards = []
    for name in specs():
        if not name.startswith("targets_"):
            continue
        spec = specs()[name]
        disabled, reason = False, ""
        if (
            name == "targets_attached_weapon"
            and carrier is not None
            and not getattr(carrier, "attaches_to_weapons", False)
        ):
            disabled = True
            reason = f"A {carrier._meta.verbose_name} is never fitted to a weapon."
        cards.append(
            {
                "value": name,
                "label": _verb_label(name, SCOPE_MODELS.get(name)),
                "blurb": spec.blurb,
                "example": spec.example,
                "produces": SCOPE_PRODUCES[name],
                "checked": name == picked,
                "disabled": disabled,
                "reason": reason,
                "deprecated": spec.deprecated,
            }
        )
    return cards


def chosen_kind_cards(modifier):
    """The two cards this modifier's kinds were picked from — label and
    blurb only, for a page that shows the settled kinds rather than
    offering them again. The kinds are what a modifier *is*, so the page
    that corrects one states them and never asks."""
    scope_kind, effect_kind = _scope_verb(modifier.scope), _effect_verb(modifier.effect)
    return (
        {
            "label": _verb_label(scope_kind, SCOPE_MODELS.get(scope_kind)),
            "blurb": specs()[scope_kind].blurb,
        },
        {
            "label": _verb_label(effect_kind, EFFECT_MODELS.get(effect_kind)),
            "blurb": specs()[effect_kind].blurb,
        },
    )


def effect_kind_cards(picked=""):
    """The WHAT picker as cards, each carrying the target kinds it can
    apply to — the client greys it the moment the picked scope produces
    something outside them, and the compose submit refuses the pair in
    words either way."""
    cards = []
    for name in specs():
        if not name.startswith(("ef_", "op_")):
            continue
        spec = specs()[name]
        can = EFFECT_CAN_TARGET[name]
        cards.append(
            {
                "value": name,
                "label": _verb_label(name, EFFECT_MODELS.get(name)),
                "blurb": spec.blurb,
                "example": spec.example,
                "accepts": " ".join(can),
                "reason": "Applies to "
                + " or ".join(_TARGET_WORDS[kind] for kind in can)
                + ".",
                "checked": name == picked,
            }
        )
    return cards


class ModifierComposerForm(forms.Form):
    """One form for the three-row assembly: a WHO pane, a WHAT pane,
    and where the modifier hangs.

    The panes are spec-generated forms bound from the same data under
    the ``who-`` and ``what-`` prefixes, picked by ``scope_kind`` and
    ``effect_kind``; conditions ride the ``conditions-`` formset. The
    composer opens from an assignable's page ("attach here" —
    ``attach_to=``) or standalone; ``make_reusable`` decides what an
    unnamed modifier is called, never where it goes.

    ``save()`` is ``modifier(auto_name, scope, effect, attach_to=…)``
    where the auto-name is the modifier's own sentence, or the carrier
    and what it does where the author wants a name of this carrier's
    own — see ``_written_name``.

    Opened on a modifier that already exists (``opened_on``) the same
    form edits it: the panes start filled, the kinds are fixed, and
    ``save()`` rewrites the row every carrier is already holding.
    """

    scope_kind = forms.ChoiceField(choices=_scope_choices, label="Who it reaches")
    effect_kind = forms.ChoiceField(choices=_effect_choices, label="What it does")
    name = forms.CharField(
        required=False,
        help_text="Blank writes the modifier's own sentence as its name.",
        # The column's own limit, so an overlong name is this field's
        # error in words rather than the database refusing the INSERT.
        max_length=200,
    )
    make_reusable = forms.BooleanField(
        required=False,
        label="Make reusable",
        help_text=(
            "Name this modifier generically, so it can be attached to "
            "several carriers later. Without this enabled the modifier "
            "will be named specifically for the thing that it's attached "
            "to."
        ),
    )

    def __init__(
        self, data=None, *, attach_to=None, collection=None, editing=None, **kwargs
    ):
        if editing is not None and data is not None:
            # Editing keeps the modifier's own kinds, whatever was
            # posted: a submission naming another kind would give every
            # carrier holding this a behaviour none of them asked for.
            data = data.copy()
            data["scope_kind"] = _scope_verb(editing.scope)
            data["effect_kind"] = _effect_verb(editing.effect)
        super().__init__(data, **kwargs)
        self.attach_to = attach_to
        self.collection = collection
        self.editing = editing
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

    @classmethod
    def opened_on(cls, row, *, chips=0):
        """The composer filled in from a modifier that already exists.

        The kinds are not offered again. What a modifier reaches and
        what it does are what it *is*; swapping either is composing a
        different one, and the effect may not even accept the other
        scope's targets. Everything inside the two kinds is filled from
        the rows, conditions included — they arrive as chips already
        written, and ``chips`` adds empty ones after them.
        """
        scope_kind, effect_kind = _scope_verb(row.scope), _effect_verb(row.effect)
        form = cls(
            editing=row,
            initial={
                "name": row.name,
                "scope_kind": scope_kind,
                "effect_kind": effect_kind,
            },
        )
        form.who_form = generate_form(specs()[scope_kind]).opened_on(
            row.scope, prefix="who"
        )
        form.what_form = generate_form(specs()[effect_kind]).opened_on(
            row.effect, prefix="what"
        )
        form.condition_formset = condition_formset_for(
            specs()[scope_kind], extra=chips, initial=_conditions_of(row.scope)
        )
        return form

    @classmethod
    def carried(cls, data, *, attach_to=None, editing=None):
        """The composer as the author left it, filled in from data that
        has travelled — a post being redrawn, or an address a removed
        condition redirected to.

        Bound rather than opened on initial values, so everything typed
        into the chips and both panes comes back exactly as it was sent.
        Then quietened: what arrives here is a form mid-edit, not an
        attempt to save one, and a pane the author has not reached yet
        is not a refusal yet either.

        Validation has to run before it can be set aside, because the
        panes are built in ``clean()`` — an unvalidated composer has no
        panes to draw.
        """
        form = cls(data, attach_to=attach_to, editing=editing)
        form.full_clean()
        form._errors.clear()
        for pane in (form.who_form, form.what_form):
            if pane is not None:
                pane._errors.clear()
        if form.condition_formset is not None:
            for chip in form.condition_formset.forms:
                chip._errors.clear()
            form.condition_formset._non_form_errors = (
                form.condition_formset.error_class()
            )
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
                f"on a weapon, a subtype or skill goes on a model, a rule or "
                f"a list may also go to the gang, and only the gang can be "
                f"asked for companions."
            )

    def _transient_effect(self, effect_kind):
        from n26.library.models.modifier import GRANTABLE_FIELDS

        model = _model_class(EFFECT_MODELS[effect_kind])
        if effect_kind in ("ef_adds", "ef_removes"):
            thing = self.what_form.cleaned_data.get("thing")
            if isinstance(thing, PendingCreate):
                # A new-named Rule or Subtype, not yet a row — its kind
                # names the column, and the raw id is enough for
                # accepts(), which reads nothing else: a rule may land
                # on the gang where a subtype may not.
                return model(**{f"{thing.kind}_id": 1})
            field = next(
                name
                for name, label in GRANTABLE_FIELDS.items()
                if isinstance(thing, _model_class(label.split(".")[-1]))
            )
            return model(**{field: thing})
        return model()

    def _written_name(self, scope, effect):
        """The name a modifier gets when the author leaves the box empty.

        Reusable means named for what it does and nothing else, so the
        same row reads true on every carrier it is later given to. The
        scope stays in that name: two reusable modifiers doing one thing
        to different people are different modifiers, and a list of them
        all called "adds Catfall" says nothing about which is which.

        Named specifically, the carrier takes the scope's place at the
        front — for a modifier hanging on one profile, that profile *is*
        who it reaches, and "targets the model" beside its name is a
        sentence about the machinery rather than about the fighter.

        A scope that narrows keeps its say. Only the generic half of a
        scope is machinery; the narrowing half is the one fact telling
        two otherwise identical rows on one carrier apart. A skill grid
        hangs a row per rank off a single affiliation and several ranks
        put the same category in the same collection section, so dropping the rank
        would name both rows the same thing — and the second one would
        be refused by the unique-name constraint rather than merely read
        oddly.
        """
        from django.utils.text import Truncator

        from n26.library.models import Modifier

        if self.attach_to is None or self.cleaned_data.get("make_reusable"):
            written = f"{scope}: {effect}"
        elif getattr(scope, "narrows", False):
            written = f"{self.attach_to}, {scope}: {effect}"
        else:
            written = f"{self.attach_to}: {effect}"
        # A derived name must fit its column by construction — the author
        # never typed it, so no field error can reach them, and the
        # database's refusal would land as a broken page.
        limit = Modifier._meta.get_field("name").max_length
        return Truncator(written).chars(limit)

    def save(self):
        """Compile both panes, glue with the modifier verb, attach.

        Attaching happens either way. The reusable flag decides what the
        row is *called*, never where it goes: an author composing on a
        carrier wants it on that carrier, and one that saved itself
        somewhere else would be a click that appeared to do nothing.

        Editing takes the same two compiled parts to
        ``recompose_modifier``, which puts them on the row the carriers
        already hold — so a correction reaches every one of them and
        none of them is re-attached.
        """
        from n26.library import authoring

        # A chip nobody filled in is an offer that was not taken, not a
        # condition narrowing nothing.
        payloads = [
            chip.payload()
            for chip in (
                self.condition_formset.forms
                if self.condition_formset is not None
                else []
            )
            if chip.cleaned_data.get("kind")
        ]
        scope = self.who_form.compile(conditions=payloads)
        effect = self.what_form.compile()
        name = self.cleaned_data.get("name") or self._written_name(scope, effect)
        if self.editing is not None:
            return authoring.recompose_modifier(self.editing, name, scope, effect)
        return authoring.modifier(name, scope, effect, attach_to=self.attach_to)


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
    type_stats = list(statline_type.stats.select_related("stat"))
    attrs = {"statline_type": statline_type, "type_stats": type_stats}
    # Kept out of the class body and attached afterwards, because these
    # names come from content and the class has names of its own. A Save
    # characteristic derives the field name ``save``, which as a class
    # attribute is overwritten by this form's ``save`` method — the field
    # then does not exist, and drawing the row raises on the stat that
    # named it. ``clean`` and ``data`` are the same shape of collision.
    fields = {
        type_stat.stat.field_name: forms.CharField(
            required=False,
            label=type_stat.short_name,
            help_text=type_stat.stat.full_name,
            widget=forms.TextInput(
                attrs={"placeholder": type_stat.stat.placeholder, "size": 6}
            ),
        )
        for type_stat in type_stats
    }

    def clean(self):
        """Refuse what cannot be stored, and nothing else.

        A characteristic is not always a number: ``S`` stands for the
        wielder's own Strength, ``D6`` is rolled, ``-`` is none. Turning
        those away would make this editor refuse content the spreadsheet
        importer accepts, so the only refusals are about storage —
        something too long for the column, and something with a
        separator in it, which is a whole row pasted into one box.
        """
        from n26.library.models import StatlineStat

        # Named base rather than a bare super(): this form is built by
        # type() rather than declared, so there is no class cell for the
        # no-argument form to find.
        cleaned = forms.Form.clean(self)
        # Read off the column rather than written down here, so the
        # refusal cannot come to disagree with what will actually fit.
        limit = StatlineStat._meta.get_field("value").max_length
        for type_stat in self.type_stats:
            value = (cleaned.get(type_stat.field_name) or "").strip()
            if len(value) > limit:
                self.add_error(
                    type_stat.field_name,
                    f"{type_stat.full_name} is longer than {limit} characters — "
                    f"a statline cell holds a short value like 4, 3+ or S.",
                )
            elif "," in value or "\n" in value:
                self.add_error(
                    type_stat.field_name,
                    f"{type_stat.full_name} holds one characteristic — give "
                    f"each of them its own box.",
                )
        return cleaned

    def opened_on(cls, owner, data=None, prefix="statline"):
        """The same form, filled in from the characteristics already stored.

        The values shown are the stored ones, which are canonical: an
        author who typed 4 for a Movement is shown the ``4"`` a card
        prints. Stripping the mark for display would leave the editor and
        the card disagreeing about what the value is, with no way to tell
        whose quote mark it was.

        Prefixed, because a thing's page carries its own generated form
        beside this one and the two can name a field alike.
        """
        statline = getattr(owner, "statline", None)
        initial = (
            {stat.field_name: stat.value for stat in statline.ordered_stats()}
            if statline is not None
            else {}
        )
        return cls(data, initial=initial, prefix=prefix)

    def cells(self, placeholders=None):
        """The characteristics as the editor draws them, in type order.

        Values come off the bound field rather than the database, so a
        form redrawn after a refusal shows what was typed — a complaint
        about a value no longer on the screen is one nobody can act on.

        ``placeholders``, keyed by field name, replaces what an empty box
        suggests. An editor where empty means "keep what is already
        printed" has something truer to show there than an example: the
        value that stands if nothing is typed.
        """
        from n26.core.render import EditableStatCell

        placeholders = placeholders or {}
        return [
            EditableStatCell(
                short_name=type_stat.short_name,
                full_name=type_stat.full_name,
                name=self[type_stat.field_name].html_name,
                value=self[type_stat.field_name].value() or "",
                placeholder=placeholders.get(
                    type_stat.field_name, type_stat.stat.placeholder
                ),
                highlighted=type_stat.is_highlighted,
                first_of_group=type_stat.is_first_of_group,
                error=" ".join(self.errors.get(type_stat.field_name, [])),
            )
            for type_stat in self.type_stats
        ]

    def save(self, owner):
        """Record the characteristics that were typed.

        Nothing typed means nothing to record: a firing line added with
        every box empty is a line with no statline, not a statline of
        blanks.
        """
        from n26.library import authoring

        values = {
            name: value
            for name, value in self.cleaned_data.items()
            if str(value).strip()
        }
        if not values:
            return None
        return authoring.set_statline(owner, **values)

    def save_every_value(self, owner):
        """Record every characteristic the form drew, blanks included.

        Editing means something different by an empty box than adding
        does. ``set_statline`` leaves a characteristic it is not told
        about alone, which is right for a spreadsheet whose column is
        missing and wrong for a person looking at a box they have just
        cleared — an author who cannot empty one is stuck with a typo
        for good. A blank is stored as a blank, which every surface
        prints as a dash.

        An owner with no statline and nothing typed keeps none: a
        profile whose page was opened and saved has not thereby been
        given a row of dashes.
        """
        from n26.library import authoring

        typed = any(str(value).strip() for value in self.cleaned_data.values())
        if getattr(owner, "statline", None) is None and not typed:
            return None
        return authoring.set_statline(
            owner,
            **{
                type_stat.field_name: self.cleaned_data.get(type_stat.field_name, "")
                for type_stat in self.type_stats
            },
        )

    attrs.update(
        clean=clean,
        opened_on=classmethod(opened_on),
        cells=cells,
        save=save,
        save_every_value=save_every_value,
    )
    form_class = type("StatlineForm", (forms.Form,), attrs)
    form_class.base_fields = fields
    form_class.declared_fields = fields
    return form_class
