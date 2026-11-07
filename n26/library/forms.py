"""Generate authoring forms from specs and compile validated data into API calls.

Verb signatures determine required fields and defaults. Specs provide field
help, choices and relation restrictions. Conditions use formsets whose
payloads are compiled by their own specs. Rule and subtype union fields
also support creating name-only content.

``ModifierComposerForm`` combines the generated scope and effect forms,
conditions and modifier naming. See design/authoring-build-plan.md.
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

#: Target kinds produced by scope functions, checked against modifier._possible_kinds.
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
    "ef_excludes_campaign_assets": "ExcludesCampaignAssets",
    "ef_changes_stat": "ChangesStat",
    "ef_contributes_to_counter": "ContributesToCounter",
    "ef_changes_category": "ChangesCategory",
    "ef_hides_categories": "HidesCategories",
    "ef_randomises_skill_advancements": "RandomisesSkillAdvancements",
    "ef_offers_choice": "OffersChoice",
    "ef_places": "PlacesCategory",
    "ef_places_choice": "PlacesCategory",
    "ef_draws_pick": "DrawsPick",
    "ef_requires_companions": "RequiresCompanions",
    "ef_allows_at_most": "AllowsAtMost",
    "op_adds_model": "OpAddsMiniature",
    "op_changes_counter": "OpChangesCounter",
    "op_sets_status": "OpSetsStatus",
}

#: Kinds the union picker may create inline: name-only leaves. The help
#: is the copyright guardrail, written once.
CREATABLE_INLINE = ("rule", "subtype")
NAME_ONLY_HELP = (
    "Name only. The rule's wording stays in the book. A bracket becomes "
    'the annotation, so "Leash (3\\")" is Leash at 3" — the same row the '
    "importer would make."
)


class StagedForm(forms.Form):
    """Choose whether newly authored content is staged, defaulting to staged.

    This separate form is shared by creation and ingest pages; staging is not
    a parameter on each content creation spec.
    """

    staged = forms.BooleanField(
        required=False,
        initial=True,
        label="Staged",
        help_text="Players cannot add staged content to gangs until you put it live. Existing gangs keep what they already hold.",
    )


class PendingCreate:
    """A name-only rule or subtype to create after form validation."""

    def __init__(self, kind, name):
        self.kind = kind
        self.name = name


def _is_required(spec, name):
    """Derive required fields from parameters without defaults, excluding ``*args``."""
    parameter = inspect.signature(spec.verb).parameters[name]
    return (
        parameter.default is inspect.Parameter.empty
        and parameter.kind is not inspect.Parameter.VAR_POSITIONAL
    )


def _switch_default(spec, name):
    """Read a Boolean parameter's default from the authoring function.

    Create forms use it as the initial value. An unchecked box can omit the
    parameter only when its default is false.
    """
    return inspect.signature(spec.verb).parameters[name].default


def _model_class(label):
    from django.apps import apps

    return apps.get_model("library", label)


class _AuthoringChoiceField(forms.ModelChoiceField):
    """Show authoring labels to distinguish same-named content with qualifiers."""

    def label_from_instance(self, obj):
        return getattr(obj, "authoring_label", None) or str(obj)


class _AuthoringMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return getattr(obj, "authoring_label", None) or str(obj)


def _labelled(model):
    """Join forward relations used by option labels to avoid a query per choice."""
    related = [
        field.name
        for field in model._meta.get_fields()
        if field.concrete and (field.many_to_one or field.one_to_one)
    ]
    return model.objects.select_related(*related)


def _form_fields(spec, name, kind):
    """Build Django fields for one spec parameter."""
    if isinstance(kind, One):
        return {
            name: _AuthoringChoiceField(
                queryset=_labelled(kind.model).filter(**kind.filters),
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
                # Apply the model field's minimum before attempting a database write.
                min_value=kind.min_value,
                max_value=kind.max_value,
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
                # Apply the model field's length limit before attempting a database write.
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
                queryset=_labelled(_model_class(label.split(".")[-1])).filter(
                    **kind.filters.get(option, {})
                ),
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
    """Map attachment fields to the union kinds declaring them."""
    from n26.library.offers import attachment_asks

    if kind.through is None:
        return {}
    asked = {}
    for option, label in kind.over.items():
        for ask in attachment_asks(_model_class(label.split(".")[-1]), kind.through):
            asked.setdefault(ask.name, []).append(option)
    return {name: tuple(options) for name, options in asked.items()}


def _initial_from(spec, row):
    """Read initial form values from existing content.

    Union fields need both a kind and an object control. Choices whose stored
    field differs from the function parameter use their ``reads`` accessor.
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
            # Restore attachment parameters too, so saving an unchanged grant preserves its starting pick.
            for ask_name, options in _union_asks(kind).items():
                if chosen in options and getattr(row, ask_name, None) is not None:
                    initial[ask_name] = getattr(row, ask_name)
        elif isinstance(kind, Choice) and kind.reads is not None:
            initial[name] = kind.reads(row)
        elif not hasattr(row, name):
            continue
        elif isinstance(kind, Many):
            initial[name] = getattr(row, name).all()
        else:
            initial[name] = getattr(row, name)
    return initial


def cross_pack_refusal(writing_into, referenced):
    """Explain a forbidden cross-pack reference, or return no message.

    System content may reference only system content. Otherwise every gang
    using it could depend on a user's private or deleted pack. Owned content
    may reference any content visible to its author. Forms enforce this rule;
    models do not. See design/campaign-assets.md.
    """
    pack = getattr(referenced, "pack", None)
    if pack is None or writing_into.owner_id is not None or pack.owner_id is None:
        return None
    label = getattr(referenced, "authoring_label", None) or str(referenced)
    return (
        f"{label} is in the {pack.name} pack, which has an owner. Content in "
        f"the {writing_into.name} pack can only reference content in packs "
        f"that nobody owns."
    )


def picks_in(spec_fields, cleaned):
    """Map form field names to the selected content they must validate.

    Union errors belong on the selected kind's object field.
    """
    from n26.library.models.base import Content

    picked = {}
    for name, kind in spec_fields.items():
        value = cleaned.get(name)
        if isinstance(kind, Many) and value is not None:
            picked[name] = [row for row in value if isinstance(row, Content)]
        elif isinstance(kind, One) and isinstance(value, Content):
            picked[name] = [value]
        elif isinstance(kind, Union) and isinstance(value, Content):
            picked[f"{name}_{cleaned.get(f'{name}_kind')}"] = [value]
    return picked


def refuse_cross_pack_references(form, writing_into, picks):
    """Add errors for selected content incompatible with the destination pack.

    ``picks`` maps field names to content. Prefetching packs avoids a query
    for each selection.
    """
    for name, rows in picks.items():
        for row in rows:
            refusal = cross_pack_refusal(writing_into, row)
            if refusal is not None:
                form.add_error(name, refusal)


class GeneratedForm(forms.Form):
    """Validate spec fields and compile their values into an authoring API call."""

    spec = None
    #: ``{union field: {through column: (kinds that declare it)}}`` —
    #: which extra inputs ride each union, so clean() can keep only the
    #: chosen kind's and verb_data() can pass them on.
    union_asks = {}

    def __init__(self, *args, collection=None, carrier=None, editing=None, **kwargs):
        super().__init__(*args, **kwargs)
        #: The containing collection used to validate filtered_by fields.
        self.collection = collection
        #: The carrier whose related records constrain within pickers.
        self.carrier = carrier
        #: The row this form was opened on, when it edits one that already
        #: exists — whose pack an edit stays in.
        self.editing = editing
        if carrier is None:
            return
        for name, kind in self.spec.fields.items():
            if isinstance(kind, One) and kind.within:
                self.fields[name].queryset = getattr(carrier, kind.within).all()
            if isinstance(kind, Union) and kind.through is not None:
                self._offer_the_carriers_kinds(name, kind, carrier)

    def _offer_the_carriers_kinds(self, name, kind, carrier):
        """Restrict built-in selectors to the carrier's declared kinds.

        Choose the first allowed kind initially. A carrier declaring no restrictions
        keeps every kind.
        """
        offered = getattr(carrier, "built_in_kinds", None)
        if offered is None:
            return
        offered = [option for option in offered if option in kind.over]
        kind_field = self.fields[f"{name}_kind"]
        labels = dict(kind_field.choices)
        # In the carrier's order, so the default reads first in the list.
        kind_field.choices = [("", labels[""])] if "" in labels else []
        kind_field.choices += [(option, labels[option]) for option in offered]
        kind_field.initial = offered[0] if offered else None
        for option in kind.over:
            if option not in offered:
                self.fields.pop(f"{name}_{option}", None)
                self.fields.pop(f"{name}_new_{option}", None)

    def clean(self):
        cleaned = super().clean()
        for name, kind in self.spec.fields.items():
            if isinstance(kind, One) and kind.within and self.carrier is not None:
                picked = cleaned.get(name)
                # Validate against the same accessor used to narrow choices.
                # Use an existence query instead of loading the whole related set.
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
        writing_into = self.writes_into()
        refuse_cross_pack_references(
            self, writing_into, picks_in(self.spec.fields, cleaned)
        )
        # A part names the thing it is added to, so the carrier is a
        # reference the row will hold as surely as any pick.
        carrier_refusal = cross_pack_refusal(writing_into, self.carrier)
        if carrier_refusal is not None:
            self.add_error(None, carrier_refusal)
        return cleaned

    def writes_into(self):
        """Resolve the destination pack for creation or editing.

        Edits retain their pack. Parts marked ``joins_carrier_pack`` use the carrier's
        pack. Other creations use the default pack, matching the authoring API.
        """
        from n26.library.models.pack import get_default_pack

        pack = getattr(self.editing, "pack", None)
        if pack is None and self.spec.joins_carrier_pack:
            pack = getattr(self.carrier, "pack", None)
        return pack if pack is not None else get_default_pack()

    def _clean_union(self, name, kind, cleaned):
        """Resolve exactly one existing or newly named object of the selected kind."""
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
        asks = {}
        for ask_name, options in self.union_asks.get(name, {}).items():
            if chosen not in options:
                cleaned[ask_name] = None
            elif cleaned.get(ask_name) is not None:
                asks[ask_name] = cleaned[ask_name]
        if asks and not isinstance(picked, PendingCreate):
            self._refuse_as_the_row_would(name, kind, chosen, picked, asks)

    def _refuse_as_the_row_would(self, name, kind, chosen, picked, asks):
        """Validate attachment parameters using an unsaved through record.

        Map its ``clean()`` errors to the corresponding form fields.
        Name-only creations skip this check and are resolved by ``verb_data()``.
        """
        try:
            kind.through(**{chosen: picked}, **asks).clean()
        except ValidationError as refused:
            picker = f"{name}_{chosen}"
            if not hasattr(refused, "error_dict"):
                self.add_error(picker, refused)
                return
            for field, errors in refused.error_dict.items():
                self.add_error(field if field in self.fields else picker, errors)

    def verb_data(self):
        """Return validated API parameters, resolving union controls and inline creations.

        Omit empty optional values so the function's defaults apply. Inline creation
        runs after validation and before the main function call.
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
        """Call the spec with validated fields and uncompiled condition pairs.

        ``conditions`` contains ``(verb_name, payload)`` pairs compiled by the
        spec.
        """
        data = self.verb_data()
        if conditions:
            data["conditions"] = list(conditions)
        return self.spec.compile(data)

    @classmethod
    def opened_on(cls, thing, data=None, files=None, prefix="edit"):
        """Populate an edit form from an existing record and remove fixed fields.

        Prefix the form to prevent field names and HTML identifiers colliding with
        part-creation forms on the same page. Removed fixed fields cannot be changed
        by submitting extra keys because ``apply_to`` writes only form fields.
        """
        initial = _initial_from(cls.spec, thing)
        form = cls(data, files, initial=initial, prefix=prefix, editing=thing)
        for name, kind in cls.spec.fields.items():
            if getattr(kind, "fixed", False):
                form.fields.pop(name, None)
                continue
            if not (isinstance(kind, Choice) and name in initial):
                continue
            current = str(initial[name])
            offered = {str(value) for value, _label in form.fields[name].choices}
            if current not in offered:
                form.fields[name].choices = [
                    *form.fields[name].choices,
                    (current, f"{current.replace('_', ' ')} (retired)"),
                ]
        return form

    def apply_to(self, thing):
        """Update existing content through ``authoring.revise`` and set-replacement
        functions.

        Preserve fields absent from the form. ``Many.replaced_by`` defines
        replacement for multi-select fields; combine fields sharing a replacement
        function into one call. Values cleaned to ``None`` leave non-nullable
        scalar fields unchanged. Empty strings clear text fields; entering zero
        explicitly stores zero.
        """
        from n26.library.authoring import revise

        columns, sets, verbs = {}, {}, {}
        for name in self.spec.fields:
            if name not in self.fields:
                continue
            value = self.cleaned_data.get(name)
            written_by = getattr(self.spec.fields[name], "written_by", None)
            if written_by is not None:
                # No column to write: the verb that owns the parameter
                # writes it, after the row's own columns are saved. An
                # empty box says nothing here as it does below.
                if value is not None:
                    verbs[written_by] = value
                continue
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
        for write, value in verbs.items():
            write(thing, value)
        return thing


def generate_form(spec):
    """Create a Django Form subclass from a spec.

    Conditions use ``condition_formset_for`` separately. Pass uncompiled
    ``(verb_name, payload)`` pairs into the form's ``compile()`` call.
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
    """Build one condition selector containing every allowed kind's fields.

    Fields are individually optional; ``clean()`` requires the chosen kind's
    parameters. ``payload()`` returns values for the scope form to compile.
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
        # A condition is part of a modifier, and the composer writes
        # modifiers into the default pack.
        from n26.library.models.pack import get_default_pack

        refuse_cross_pack_references(
            self, get_default_pack(), picks_in(specs()[chosen].fields, cleaned)
        )
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
    """Build condition chips, or return ``None`` when the scope takes none.

    ``initial`` holds existing conditions; ``extra`` adds empty chips.
    The view stores the count in the URL and removes submitted chips through
    ``without_condition_chip`` before redirecting with the remaining form state.
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
    """Remove a submitted condition and renumber the remaining formset entries.

    Update management counts to match. An out-of-range index leaves data unchanged.
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
    """Read every declared scope condition into initial formset data.

    Omitting a condition here would remove it when the modifier is saved.
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
    """Build optional fields for ``SUGGESTED_BUILT_INS``, or return ``None``.

    Fixed suggestions ask only for attachment values; open suggestions also
    ask for content. Blank suggestions are skipped. ``apply(created)`` adds the
    selected built-ins within the creation view's transaction.
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

    def clean(self):
        """A suggestion's pick is written into the new row's own pack,
        which is the default pack; the same rule the generated forms
        hold applies to it."""
        from n26.library.models.base import Content
        from n26.library.models.pack import get_default_pack

        # Call the base explicitly because dynamically generated methods lack a __class__ cell.
        cleaned = forms.Form.clean(self)
        picks = {}
        for suggestion in self.offer:
            value = cleaned.get(suggestion.slug)
            rows = list(value) if suggestion.many and value is not None else [value]
            picks[suggestion.slug] = [row for row in rows if isinstance(row, Content)]
        refuse_cross_pack_references(self, get_default_pack(), picks)
        return cleaned

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
    attrs["clean"] = clean
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
    """Use a spec label, model verbose name or function name for a kind choice.

    Spec labels distinguish functions that create the same model.
    """
    spec = specs().get(name)
    if spec is not None and spec.label:
        return spec.label
    if model_label is None:
        return name
    model = _model_class(model_label)
    return str(model._meta.verbose_name)


def _scope_verb(scope):
    """Resolve a stored scope to its creation function, including its reach variant."""
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
    """Resolve an effect's creation function, distinguishing placement variants."""
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


#: Accepted target kinds used to disable incompatible effect choices.
#: List grant targets explicitly because they depend on selected content.
#: Tests compare accepts() using bare grants and grants naming a trait or rule.
EFFECT_CAN_TARGET = {
    "ef_adds": ("model", "weapon_profile", "gang"),
    "ef_removes": ("model", "weapon_profile", "gang"),
    "ef_excludes_campaign_assets": ("gang",),
    "ef_changes_stat": ("model", "weapon_profile"),
    "ef_contributes_to_counter": ("model", "gang"),
    "ef_changes_category": ("model",),
    "ef_hides_categories": ("model",),
    "ef_randomises_skill_advancements": ("model",),
    "ef_offers_choice": ("model", "gang"),
    "ef_places": ("model",),
    "ef_places_choice": ("model",),
    "ef_draws_pick": ("model",),
    "ef_requires_companions": ("gang",),
    "ef_allows_at_most": ("model", "gang"),
    "op_adds_model": ("model", "gang"),
    "op_changes_counter": ("model", "gang"),
    "op_sets_status": ("model",),
}

#: The target kinds as an author reads them, for a greyed card's reason.
_TARGET_WORDS = {
    "model": "a model",
    "weapon_profile": "a weapon",
    "gang": "the gang",
}


def scope_kind_cards(picked="", carrier=None):
    """Build scope cards with labels, examples and target kinds.

    When a carrier is supplied, disable incompatible scopes and include a reason.
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
    """Return labels and descriptions for a modifier's fixed scope and effect kinds."""
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
    """Build effect cards with accepted target kinds for compatibility filtering.

    The server validates compatibility again on submission.
    """
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
    """Compose or edit a modifier using generated scope and effect forms.

    The panes use ``who-`` and ``what-`` prefixes; conditions use ``conditions-``.
    An optional carrier controls attachment. ``make_reusable`` changes automatic
    naming, while attachment still follows ``attach_to``.

    ``opened_on`` fixes the existing kinds and populates their fields.
    Saving an edit updates the modifier used by every carrier.
    """

    scope_kind = forms.ChoiceField(choices=_scope_choices, label="Who it reaches")
    effect_kind = forms.ChoiceField(choices=_effect_choices, label="What it does")
    name = forms.CharField(
        required=False,
        help_text="Blank writes the modifier's own sentence as its name.",
        # Validate names against the model field's length limit.
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
        """Build panes from URL-selected kinds before submission.

        ``chips`` adds empty condition forms and is also URL state.
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
        """Populate an existing modifier's fixed kinds, fields and condition chips.

        ``chips`` appends empty conditions to those already stored.
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
        """Restore submitted or URL-carried form data without displaying validation errors.

        Validation must run to construct the panes. Clear errors afterwards because
        restoring an unfinished form is not a save attempt.
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
        """Validate scope targets against an unsaved effect before any writes."""
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
                # An unsaved Rule or Subtype needs only its prospective field value for accepts().
                # Rules may target gangs; subtypes cannot.
                return model(**{f"{thing.kind}_id": 1})
            field = next(
                name
                for name, label in GRANTABLE_FIELDS.items()
                if isinstance(thing, _model_class(label.split(".")[-1]))
            )
            return model(**{field: thing})
        if effect_kind == "ef_excludes_campaign_assets":
            return model(asset_type=self.what_form.cleaned_data.get("asset_type"))
        return model()

    def _written_name(self, scope, effect):
        """Generate a name from the modifier's behaviour and optional carrier.

        Reusable names include the scope. Carrier-specific names replace the generic
        scope with the carrier but retain conditions, which distinguish modifiers
        that otherwise have identical effects and would violate name uniqueness.
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
        """Create or recompose a modifier and attach it to the supplied carrier.

        Reusable naming does not change attachment. Editing recomposes the existing
        modifier so every current carrier receives the correction.
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
    """Generate characteristic fields from the statline type's content.

    A spec cannot enumerate ``set_statline(**values)`` because the type defines
    the parameter names. All fields are optional and accept textual values such
    as ``S`` and ``E`` as well as numbers.
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
        """Validate storage length and reject separators from pasted multi-cell data.

        Textual characteristics such as ``S`` and ``D6`` remain valid.
        """
        from n26.library.models import StatlineStat

        # Call the base explicitly because this generated method lacks a __class__ cell.
        cleaned = forms.Form.clean(self)
        # Read the storage limit from the model field to keep validation consistent.
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
        """Populate the editor with canonical stored characteristic values.

        Retain units such as the Movement inch mark. Prefix the form to prevent
        collisions with the neighbouring content form.
        """
        statline = getattr(owner, "statline", None)
        initial = (
            {stat.field_name: stat.value for stat in statline.ordered_stats()}
            if statline is not None
            else {}
        )
        return cls(data, initial=initial, prefix=prefix)

    def cells(self, placeholders=None):
        """Return bound characteristic controls in type order.

        Bound fields preserve submitted values after validation errors.
        ``placeholders`` can show the values retained when controls are left blank.
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
        """Save supplied characteristic values; leave an entirely blank owner without a statline."""
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
        """Replace displayed characteristic values, including cleared controls.

        Blank values display as dashes. Preserve an absent statline when all controls
        remain blank, so merely saving the page does not create an empty statline.
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


def trading_post_visit_settings_form(*args, **kwargs):
    """A global configuration has no owning pack to constrain its references."""

    class TradingPostVisitSettingsForm(
        generate_form(specs()["configure_trading_post_visit"])
    ):
        def clean(self):
            # Field validation enforces the library-only queryset. Global settings
            # can reference owned library packs as well as system packs.
            return forms.Form.clean(self)

    return TradingPostVisitSettingsForm(*args, **kwargs)
