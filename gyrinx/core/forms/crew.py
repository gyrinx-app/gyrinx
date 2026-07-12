"""Forms for battle crews (#1346).

The recipe form (:class:`CrewForm`) captures a crew's chosen fighters and its
random-draw spec while the crew is a draft. Loadout and extras forms edit a
crew after it has been locked (drawn). None of these touch the gang's canonical
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

# The dice offered for a random draw. The model still stores/validates any
# ``DX`` for data integrity; the UI offers the ones scenarios actually use.
DICE_CHOICES = [("", "No dice"), ("D3", "D3"), ("D6", "D6")]


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


class CrewForm(forms.ModelForm):
    """Create or edit a crew's selection recipe.

    The gang is fixed by the view (from the URL), not chosen here — so this only
    edits the crew's name, chosen fighters, and random-draw spec. The random
    draw is entered as a structured (dice, number) pair rather than free text,
    then recombined into ``Crew.random_spec``. ``chosen_fighters`` is a declared
    field (not a Meta field) so the view sets the M2M explicitly after saving
    with the acting user.
    """

    chosen_fighters = CrewFighterChoiceField(
        queryset=ListFighter.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Chosen fighters",
        help_text="Tick the fighters you're hand-picking for this battle.",
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

    def __init__(self, *args, gang=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Gang comes from the view on create, or the instance on edit.
        self.gang = gang or getattr(self.instance, "list", None)
        if self.gang is not None:
            # with_related_data() so the checkbox labels (category + cached cost)
            # render without a query per fighter.
            self.fields["chosen_fighters"].queryset = eligible_crew_fighters(
                self.gang
            ).with_related_data()
        self.has_eligible_fighters = self.fields["chosen_fighters"].queryset.exists()

        if self.instance and self.instance.pk:
            self.fields["chosen_fighters"].initial = self.instance.chosen_fighters.all()
            dice, number = split_selection_spec(self.instance.random_spec)
            self.fields["random_dice"].initial = dice
            self.fields["random_number"].initial = number

    def clean(self):
        cleaned = super().clean()
        # Recombine the structured widgets into the stored spec string.
        self.instance.random_spec = build_selection_spec(
            cleaned.get("random_dice"), cleaned.get("random_number")
        )
        return cleaned


class CrewMemberLoadoutForm(forms.ModelForm):
    """Pick the equipment set (battle loadout) a crew member brings.

    Choices are the member's fighter's own equipment sets; the empty choice
    means their full kit. The chosen set scopes this member's contribution to
    crew rating.
    """

    class Meta:
        model = CrewMember
        fields = ["equipment_set"]
        labels = {"equipment_set": "Battle loadout"}
        widgets = {"equipment_set": forms.Select(attrs={"class": "form-select"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["equipment_set"]
        field.required = False
        field.empty_label = "Full kit (all equipment)"
        field.queryset = self.instance.list_fighter.equipment_sets.all()


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
