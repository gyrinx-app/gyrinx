"""Forms for battle crews (#1346).

The recipe form (:class:`CrewForm`) captures a crew's selection method and the
numbers it needs while the crew is a draft. The method is URL-driven (see
``views/crew.py``) and the form prunes itself to the fields that method
actually uses — that is what makes a contradictory recipe, such as an entirely
random selection that also names fighters, impossible to express. The extras
form adds credit-consuming line items. None of these touch the gang's canonical
cost, credits, or audit — a crew is a virtual overlay.
"""

from django import forms
from django.utils.html import format_html

from gyrinx.core.handlers.crew import eligible_crew_fighters
from gyrinx.core.models.crew import (
    Crew,
    CrewLineItem,
    CrewMember,
    build_selection_spec,
    split_selection_spec,
)
from gyrinx.core.models.list import ListFighter

# The implicit "everything the fighter owns" card, which has no row of its own.
# Same wording as the fighter card's set switcher.
DEFAULT_SET_LABEL = "Default (all equipment)"

# The dice offered for a random draw. The model still stores/validates any
# ``DX`` for data integrity; the UI offers the ones scenarios actually use.
DICE_CHOICES = [("", "No dice"), ("D3", "D3"), ("D6", "D6")]

# One sentence per method, shown above the fields it applies to.
METHOD_INTRO = {
    Crew.CUSTOM: "You choose which fighters take part.",
    Crew.RANDOM: (
        "The fighters are drawn at random when the crew is rolled at battle start."
    ),
    Crew.HYBRID: (
        "You choose some of the fighters; the rest are drawn at random when the "
        "crew is rolled at battle start."
    ),
}

CUSTOM_COUNT_HELP = {
    Crew.CUSTOM: (
        "The number in brackets, e.g. Custom Selection (10). Leave blank if the "
        "scenario shows no number — the whole gang may take part."
    ),
    Crew.HYBRID: (
        "Hybrid Selection (X+Y): you choose the first number, the second is "
        "drawn at random."
    ),
}

RANDOM_GROUP = {
    Crew.RANDOM: (
        "How many fighters are drawn at random",
        "The number in brackets, e.g. Random Selection (D3+4).",
    ),
    Crew.HYBRID: (
        "How many are drawn at random",
        "Hybrid Selection (X+Y): you choose the first number, the second is "
        "drawn at random.",
    ),
}


class CrewFighterChoiceField(forms.ModelMultipleChoiceField):
    """Fighter checkboxes labelled ``**name** · category (rating)`` instead of
    the raw ``__str__``. The queryset should be loaded via ``with_related_data``
    so the category and cached cost read from the prefetch cache."""

    def label_from_instance(self, obj):
        return format_html(
            "<strong>{}</strong> · {} ({}¢)",
            obj.name,
            obj.content_fighter.get_category_display(),
            obj.cost_int_cached,
        )


def equipment_set_field_name(fighter_id):
    """The per-fighter equipment-set field on :class:`CrewForm`."""
    return f"equipment_set_{fighter_id}"


class CrewEquipmentSetField(forms.ModelChoiceField):
    """One fighter's "which card does this model use?" picker.

    Custom Selection lets the player choose the equipment set each chosen model
    brings, so the crew form carries one of these per eligible fighter that has
    named sets. The empty choice is the implicit Default card.

    The choices are set from the sets already loaded by ``with_related_data()``
    rather than left to ``ModelChoiceIterator``, which calls
    ``queryset.iterator()`` — that bypasses the prefetch cache and would cost a
    query per fighter on a form that lists the whole gang. The queryset is still
    the fighter's own sets, so validation can't accept another fighter's card.
    """

    def __init__(self, *, fighter, sets, **kwargs):
        super().__init__(
            queryset=fighter.equipment_sets.all(),
            required=False,
            empty_label=DEFAULT_SET_LABEL,
            label=f"Equipment set for {fighter.name}",
            widget=forms.Select(
                attrs={
                    "class": "form-select form-select-sm",
                    "aria-label": f"Equipment set for {fighter.name}",
                }
            ),
            **kwargs,
        )
        self.choices = [("", self.empty_label)] + [(s.pk, s.name) for s in sets]


class CrewForm(forms.ModelForm):
    """Create or edit a crew's selection recipe for one selection method.

    The gang is fixed by the view (from the URL), and so is the ``method`` —
    changing method is a navigation, not a client-side toggle. The form keeps
    only the fields that method uses:

    ==========  ==========================================
    Custom      how many you choose + which fighters
    Random      how many are drawn at random
    Hybrid      both
    ==========  ==========================================

    The random draw is entered as a structured (dice, number) pair rather than
    free text and recombined into ``Crew.random_spec``. Nothing here is written
    to the crew: the view hands the cleaned recipe to
    ``handle_crew_recipe_save``, which also clears the other methods' fields.
    """

    chosen_fighters = CrewFighterChoiceField(
        queryset=ListFighter.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Fighters",
        help_text="Choose the fighters for this crew.",
    )
    custom_count = forms.IntegerField(
        min_value=1,
        max_value=99,
        required=False,
        label="How many fighters you choose",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "style": "width:6rem"}
        ),
    )
    random_dice = forms.ChoiceField(
        choices=DICE_CHOICES,
        required=False,
        label="Dice",
        widget=forms.Select(attrs={"class": "form-select", "style": "width:auto"}),
    )
    random_number = forms.IntegerField(
        min_value=0,
        max_value=99,
        required=False,
        label="Number",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "style": "width:6rem", "placeholder": "0"}
        ),
    )

    class Meta:
        model = Crew
        fields = ["name"]
        labels = {"name": "Crew name"}
        help_texts = {"name": "Optional — a label for this crew."}
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}

    def __init__(self, *args, gang=None, method=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Gang comes from the view on create, or the instance on edit.
        self.gang = gang or getattr(self.instance, "list", None)
        self.method = (
            method or getattr(self.instance, "selection_method", None) or (Crew.CUSTOM)
        )

        # with_related_data() so the checkbox labels (category + cached cost)
        # and each fighter's equipment sets render without a query per fighter.
        self.eligible = (
            eligible_crew_fighters(self.gang).with_related_data()
            if self.gang is not None
            else ListFighter.objects.none()
        )

        # Prune to the current method's fields. A Random Selection form has no
        # fighter checkboxes at all, so "all random, but also these three" is
        # not a state a user can get into.
        if self.method == Crew.RANDOM:
            del self.fields["custom_count"]
            del self.fields["chosen_fighters"]
        elif self.method == Crew.CUSTOM:
            del self.fields["random_dice"]
            del self.fields["random_number"]

        self.shows_picks = "chosen_fighters" in self.fields
        self.shows_count = "custom_count" in self.fields
        self.shows_random = "random_dice" in self.fields
        self.method_intro = METHOD_INTRO[self.method]

        if self.shows_picks:
            picks_field = self.fields["chosen_fighters"]
            picks_field.queryset = self.eligible
            # Evaluate the eligible fighters once, through the field's own
            # queryset: the checkboxes, the count, and the equipment-set selects
            # below then all read from that single load.
            self.eligible_fighters = list(picks_field.queryset)
            self.eligible_count = len(self.eligible_fighters)
            # A fighter with named sets gets a select for which one they bring;
            # a fighter with only the Default card has nothing to choose.
            for fighter in self.eligible_fighters:
                sets = list(fighter.equipment_sets.all())
                if not sets:
                    continue
                self.fields[equipment_set_field_name(fighter.pk)] = (
                    CrewEquipmentSetField(fighter=fighter, sets=sets)
                )
        else:
            self.eligible_fighters = []
            self.eligible_count = self.eligible.count()
        self.has_eligible_fighters = self.eligible_count > 0

        if self.shows_count:
            self.fields["custom_count"].help_text = CUSTOM_COUNT_HELP[self.method]
        if self.shows_random:
            self.random_group_label, self.random_group_help = RANDOM_GROUP[self.method]

        if self.instance and self.instance.pk:
            if self.shows_picks:
                chosen = list(self.instance.members.filter(source=CrewMember.CHOSEN))
                self.fields["chosen_fighters"].initial = [
                    m.list_fighter_id for m in chosen
                ]
                for member in chosen:
                    field = self.fields.get(
                        equipment_set_field_name(member.list_fighter_id)
                    )
                    if field is not None:
                        field.initial = member.equipment_set_id
            if self.shows_count:
                self.fields["custom_count"].initial = self.instance.custom_count
            if self.shows_random:
                dice, number = split_selection_spec(self.instance.random_spec)
                self.fields["random_dice"].initial = dice
                self.fields["random_number"].initial = number

    def fighter_rows(self):
        """One row per eligible fighter for the template: the checkbox, and the
        equipment-set select for fighters that have named sets (``None``
        otherwise). Pairing the two here keeps the template free of dynamic
        field-name lookups."""
        if not self.shows_picks:
            return []
        rows = []
        for checkbox in self["chosen_fighters"]:
            name = equipment_set_field_name(checkbox.data["value"])
            rows.append(
                {
                    "checkbox": checkbox,
                    "set_field": self[name] if name in self.fields else None,
                }
            )
        return rows

    def clean(self):
        cleaned = super().clean()
        # Recombine the structured widgets into the stored spec string. Blank
        # for Custom, which has no random component at all.
        spec = (
            build_selection_spec(
                cleaned.get("random_dice"), cleaned.get("random_number")
            )
            if self.shows_random
            else ""
        )
        cleaned["random_spec"] = spec

        picks = list(cleaned.get("chosen_fighters") or [])
        count = cleaned.get("custom_count")

        # Which card each chosen fighter brings. Only the ticked fighters count:
        # a select left set on a fighter the player then unticked is ignored.
        cleaned["equipment_sets"] = {
            fighter.pk: cleaned.get(equipment_set_field_name(fighter.pk))
            for fighter in picks
        }

        if self.method == Crew.RANDOM:
            if not spec:
                self.add_error(
                    "random_number",
                    "Enter how many fighters are drawn at random — Random "
                    "Selection always shows a number in brackets.",
                )
            return cleaned

        if self.method == Crew.HYBRID:
            if not count:
                self.add_error(
                    "custom_count",
                    "Enter how many fighters you choose — the first number in "
                    "brackets.",
                )
            if not spec:
                self.add_error(
                    "random_number",
                    "Enter how many fighters are drawn at random — the second "
                    "number in brackets.",
                )

        # Custom Selection with no number in brackets is unbounded: any number
        # of picks is fine, and none at all means the whole gang takes part.
        if count is None:
            return cleaned

        # A scenario can ask for more fighters than the gang can field; then the
        # most it can send is everyone.
        required = min(count, self.eligible_count)
        if len(picks) != required:
            message = (
                f"Choose exactly {required} fighters — you've chosen {len(picks)}."
            )
            if count > self.eligible_count:
                message += (
                    f" This gang only has {self.eligible_count} fighters available."
                )
            self.add_error("chosen_fighters", message)

        return cleaned


class CrewLineItemForm(forms.ModelForm):
    """Add or edit a crew extra (tactics card, etc.) with its payment method."""

    class Meta:
        model = CrewLineItem
        fields = ["label", "cost", "payment", "reason"]
        labels = {
            "label": "What is it?",
            "cost": "Credits value",
            "payment": "Paid for with",
            "reason": "Reason",
        }
        help_texts = {
            "reason": "Optional — note why, when free or from an allowance.",
        }
        widgets = {
            "label": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Tactics card: Ambush",
                }
            ),
            "cost": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "payment": forms.Select(attrs={"class": "form-select"}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
        }
