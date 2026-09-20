"""One ordinary form for a whole gang's crew and selected model cards."""

from dataclasses import dataclass

from django import forms

from n26.core.crews import CrewSelection, saved_card_key
from n26.core.models.crew import CrewMember
from n26.core.status import Status


@dataclass(frozen=True)
class CrewFormModel:
    miniature: object
    role: forms.BoundField
    card: forms.BoundField
    override: forms.BoundField
    warning: str
    saved_source: str
    search: str
    may_override: bool
    available: bool


class CrewForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    random_count = forms.IntegerField(
        label="Models to draw", min_value=1, required=False, initial=2
    )
    random_role = forms.ChoiceField(label="Draw into", choices=CrewMember.Role.choices)

    def __init__(self, *args, roster, crew=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.roster = roster
        self.initial["revision"] = crew.revision if crew else 0
        self.initial["random_role"] = CrewMember.Role.STARTING
        self.models = []
        for item in roster:
            model, saved = item.miniature, item.saved
            suffix = str(model.pk)
            role_name, card_name, override_name = (
                f"role_{suffix}",
                f"card_{suffix}",
                f"override_{suffix}",
            )
            self.fields[role_name] = forms.ChoiceField(
                label=f"Crew role for {model.name}",
                choices=[("out", "Not selected"), *CrewMember.Role.choices],
                initial=saved.role if saved else "out",
            )
            choices = [(c.key, c.name) for c in item.cards]
            if saved:
                choices.insert(
                    0, (saved_card_key(saved), f"{saved.card_name} — saved selection")
                )
            self.fields[card_name] = forms.ChoiceField(
                label=f"Model card for {model.name}",
                choices=choices,
                initial=saved_card_key(saved) if saved else item.cards[0].key,
            )
            self.fields[override_name] = forms.BooleanField(
                label="Allow for this battle",
                required=False,
                initial=saved.eligibility_override if saved else False,
            )
            warning = (
                "This model is no longer available. Remove it from the crew."
                if not item.available
                else f"{model.get_status_display()}. Usually unavailable for selection."
                if model.status != Status.ACTIVE
                else ""
            )
            self.models.append(
                CrewFormModel(
                    model,
                    self[role_name],
                    self[card_name],
                    self[override_name],
                    warning,
                    saved.get_source_display() if saved else "",
                    f"{model.name} {model.membership.profile if model.membership else ''}".lower(),
                    item.available and model.status != Status.ACTIVE,
                    item.available,
                )
            )

    def clean(self):
        cleaned = super().clean()
        for name in self.data:
            if (
                name.startswith("role_")
                and name not in self.fields
                and self.data[name] != "out"
            ):
                raise forms.ValidationError(
                    "A selected model is no longer on this roster. Reload the crew before saving."
                )
        selections = []
        for item in self.roster:
            suffix = str(item.miniature.pk)
            role = cleaned.get(f"role_{suffix}")
            if not role or role == "out":
                continue
            override = cleaned.get(f"override_{suffix}", False)
            if not item.available:
                self.add_error(
                    f"role_{suffix}",
                    "This model is no longer available. Remove it from the crew.",
                )
            elif item.miniature.status != Status.ACTIVE and not override:
                self.add_error(
                    f"override_{suffix}",
                    "Allow this model for this battle or remove it from the crew.",
                )
            selections.append(
                CrewSelection(suffix, role, cleaned.get(f"card_{suffix}", ""), override)
            )
        cleaned["selections"] = selections
        return cleaned
