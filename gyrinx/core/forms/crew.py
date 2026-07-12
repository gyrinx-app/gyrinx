"""Forms for battle crews (#1346).

The recipe form (:class:`CrewForm`) captures a crew's chosen fighters and its
random-draw spec while the crew is a draft. Loadout and extras forms edit a
crew after it has been locked (drawn). None of these touch the gang's canonical
cost, credits, or audit — a crew is a virtual overlay.
"""

from django import forms

from gyrinx.core.handlers.crew import eligible_crew_fighters
from gyrinx.core.models.crew import Crew, CrewLineItem, CrewMember
from gyrinx.core.models.list import ListFighter


class CrewForm(forms.ModelForm):
    """Create or edit a crew's selection recipe.

    The gang is fixed by the view (from the URL), not chosen here — so this only
    edits the crew's name, chosen fighters, and random-draw spec. ``chosen_fighters``
    is a declared field (not a Meta field) so the view sets the M2M explicitly
    after saving with the acting user.
    """

    chosen_fighters = forms.ModelMultipleChoiceField(
        queryset=ListFighter.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Chosen fighters",
        help_text="Fighters you specifically pick for this crew.",
    )

    class Meta:
        model = Crew
        fields = ["name", "random_spec"]
        labels = {
            "name": "Crew name",
            "random_spec": "Random draw",
        }
        help_texts = {
            "name": "Optional — a label for this crew.",
            "random_spec": (
                "How many extra fighters to draw at random at battle start, on "
                "top of the chosen ones. A number (6), a die (D3), or die + "
                "number (D3+4). Leave blank for no random draw."
            ),
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "random_spec": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. D3+4"}
            ),
        }

    def __init__(self, *args, gang=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Gang comes from the view on create, or the instance on edit.
        self.gang = gang or getattr(self.instance, "list", None)
        if self.gang is not None:
            self.fields["chosen_fighters"].queryset = eligible_crew_fighters(self.gang)
        if self.instance and self.instance.pk:
            self.fields["chosen_fighters"].initial = self.instance.chosen_fighters.all()


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
            "reason": "Optional — note why, when free or by patronage.",
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
