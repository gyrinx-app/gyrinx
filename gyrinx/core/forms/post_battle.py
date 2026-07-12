"""Form for the bulk post-battle updates editor.

One dynamic form builds a set of per-fighter fields (XP, per-counter deltas,
injury + reason, private notes) plus a single battle selector. Every field is
optional; the view acts only on the ones that were filled in or changed. Field
names are prefixed by fighter pk so a single ``request.POST`` carries the whole
grid.
"""

from django import forms

from gyrinx.core.forms.list import available_injuries_for_fighter
from gyrinx.core.models.battle import Battle
from gyrinx.forms import group_select


class PostBattleUpdatesForm(forms.Form):
    """Bulk per-fighter post-battle edits for one list.

    Pass the list's fighters via ``fighters`` and the campaign's selectable
    battles via ``battles``. For each fighter the form gains:

    - ``xp_<pk>`` — XP to add (optional, positive).
    - ``counter_<pk>_<counter_pk>`` — one per applicable counter, a delta.
    - ``injury_<pk>`` — an injury to apply (optional), filtered per fighter.
    - ``injury_reason_<pk>`` — required reason when an injury is chosen.
    - ``private_notes_<pk>`` — pre-filled private notes (rich text).

    Plus a single ``battle`` selector that links every logged action to a battle.
    """

    def __init__(self, *args, fighters=None, battles=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighters = list(fighters or [])

        self.fields["battle"] = forms.ModelChoiceField(
            required=False,
            queryset=battles if battles is not None else Battle.objects.none(),
            empty_label="---",
            widget=forms.Select(attrs={"class": "form-select"}),
            label="Link to a battle",
        )

        for fighter in self.fighters:
            pk = fighter.pk

            self.fields[f"xp_{pk}"] = forms.IntegerField(
                required=False,
                min_value=1,
                widget=forms.NumberInput(
                    attrs={
                        "class": "form-control form-control-sm",
                        "min": 1,
                        "placeholder": "+XP",
                        "aria-label": f"XP to add for {fighter.name}",
                    }
                ),
            )

            for entry in fighter.applicable_counters:
                counter = entry.counter
                self.fields[f"counter_{pk}_{counter.pk}"] = forms.IntegerField(
                    required=False,
                    widget=forms.NumberInput(
                        attrs={
                            "class": "form-control form-control-sm",
                            "placeholder": "±0",
                            "aria-label": f"{counter.name} change for {fighter.name}",
                        }
                    ),
                )

            injury_field = f"injury_{pk}"
            self.fields[injury_field] = forms.ModelChoiceField(
                required=False,
                queryset=available_injuries_for_fighter(fighter),
                empty_label="—",
                widget=forms.Select(
                    attrs={
                        "class": "form-select form-select-sm",
                        "aria-label": f"Injury for {fighter.name}",
                    }
                ),
            )
            group_select(
                self,
                injury_field,
                key=lambda x: x.injury_group.name if x.injury_group else "Other",
            )

            self.fields[f"injury_reason_{pk}"] = forms.CharField(
                required=False,
                max_length=255,
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control form-control-sm",
                        "placeholder": "Reason",
                        "aria-label": f"Injury reason for {fighter.name}",
                    }
                ),
            )

            self.fields[f"private_notes_{pk}"] = forms.CharField(
                required=False,
                initial=fighter.private_notes,
                widget=forms.Textarea(
                    attrs={
                        "class": "form-control",
                        "rows": 4,
                        "placeholder": "Private notes (only visible to you)",
                        "aria-label": f"Private notes for {fighter.name}",
                    }
                ),
            )

    def clean(self):
        cleaned = super().clean()
        # An injury must come with a reason.
        for fighter in self.fighters:
            pk = fighter.pk
            if (
                cleaned.get(f"injury_{pk}")
                and not (cleaned.get(f"injury_reason_{pk}") or "").strip()
            ):
                self.add_error(f"injury_reason_{pk}", "Add a reason for this injury.")
        return cleaned
