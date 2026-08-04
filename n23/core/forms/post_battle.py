"""Form for the bulk post-battle updates editor.

One dynamic form builds a set of per-fighter fields (XP, per-counter deltas,
injuries, captured-by) plus gang-level fields (battle selector, credits gained,
per-resource deltas, assets claimed). Every field is optional; the view acts
only on the ones that were filled in. Field names are prefixed by fighter pk so
a single ``request.POST`` carries the whole grid.
"""

from django import forms
from django.utils.html import format_html, format_html_join

from n23.core.forms.list import available_injuries_for_fighter
from n23.core.models.battle import Battle
from n23.core.models.campaign import CampaignAsset
from n23.core.models.list import List, ListFighter
from gyrinx.forms import group_select
from gyrinx.models import FighterCategoryChoices


class RepeatedSelect(forms.SelectMultiple):
    """A ``<select>`` whose name may appear multiple times in the payload.

    Renders one single-value select (no ``multiple`` attribute) per submitted
    value — each wrapped in a ``data-pb-repeat-item`` row so a bound re-render
    (validation error) keeps every selection visible. The page's JS clones a
    row so users can add more; values are collected with ``getlist``. Without
    JS it degrades to one select.
    """

    allow_multiple_selected = False

    def render(self, name, value, attrs=None, renderer=None):
        values = [v for v in (value or []) if v not in (None, "")]
        if not values:
            values = [None]
        parts = []
        for i, v in enumerate(values):
            item_attrs = None if attrs is None else dict(attrs)
            if i and item_attrs:
                # Only the first select keeps the id the label points at.
                item_attrs.pop("id", None)
            parts.append(
                format_html(
                    '<div class="d-flex gap-1 align-items-center" data-pb-repeat-item>{}</div>',
                    super().render(name, v, item_attrs, renderer),
                )
            )
        return format_html_join("", "{}", ((p,) for p in parts))


class RepeatedModelChoiceField(forms.ModelMultipleChoiceField):
    """Collects repeated single-selects into a list of model instances.

    Unlike the parent, blank rows (untouched cloned selects) are ignored
    rather than rejected, and duplicates + submission order are preserved —
    a fighter really can suffer the same lasting injury twice in one battle.
    """

    widget = RepeatedSelect

    def clean(self, value):
        values = [v for v in (value or []) if v]
        by_pk = {str(obj.pk): obj for obj in super().clean(values)}
        return [by_pk[str(v)] for v in values]


def can_be_captured(fighter):
    """Whether the capture flow applies: alive and not already captured/sold."""
    return not fighter.is_dead and fighter.captured_state is None


class PostBattleUpdatesForm(forms.Form):
    """Bulk post-battle edits for one list.

    Pass the list's fighters via ``fighters``, the campaign's selectable
    battles via ``battles``, gangs that could capture a fighter via
    ``capture_lists``, the list's campaign resources via ``resources`` and
    claimable campaign assets via ``assets``. Gang-level fields:

    - ``battle`` — links every logged action to a battle.
    - ``credits_gained`` — credits to add to the gang (optional, positive).
    - ``resource_<pk>`` — one per campaign resource, a delta.
    - ``assets_captured`` — campaign assets to claim (repeated select).

    For each fighter the form gains:

    - ``xp_<pk>`` — XP to add (optional, positive).
    - ``counter_<pk>_<counter_pk>`` — one per applicable counter, a delta.
    - ``injury_<pk>`` — injuries to apply (repeated select), filtered per
      fighter (only present for fighters not already dead).
    - ``state_<pk>`` — explicit state to put the fighter into (recovery,
      convalescence, dead; in repair for vehicles; only present for fighters
      not already dead).
    - ``captured_by_<pk>`` — gang that captured the fighter (only present for
      fighters that can be captured).
    """

    def __init__(
        self,
        *args,
        fighters=None,
        battles=None,
        capture_lists=None,
        resources=None,
        assets=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fighters = list(fighters or [])
        self.resources = list(resources or [])
        capture_lists = (
            capture_lists if capture_lists is not None else List.objects.none()
        )
        has_capture_lists = capture_lists.exists()
        assets = assets if assets is not None else CampaignAsset.objects.none()

        self.fields["battle"] = forms.ModelChoiceField(
            required=False,
            queryset=battles if battles is not None else Battle.objects.none(),
            empty_label="---",
            widget=forms.Select(attrs={"class": "form-select"}),
            label="Link to a battle",
        )

        self.fields["credits_gained"] = forms.IntegerField(
            required=False,
            min_value=1,
            widget=forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "min": 1,
                    "placeholder": "+¢",
                    "aria-label": "Credits gained by the gang",
                }
            ),
        )

        for resource in self.resources:
            self.fields[f"resource_{resource.pk}"] = forms.IntegerField(
                required=False,
                widget=forms.NumberInput(
                    attrs={
                        "class": "form-control form-control-sm",
                        "placeholder": "±0",
                        "aria-label": f"{resource.resource_type.name} change",
                    }
                ),
            )

        assets_field = RepeatedModelChoiceField(
            required=False,
            queryset=assets,
            label="Assets claimed",
        )
        assets_field.widget.attrs.update(
            {
                "class": "form-select form-select-sm",
                "aria-label": "Asset claimed by the gang",
            }
        )
        assets_field.label_from_instance = _asset_label
        self.fields["assets_captured"] = assets_field
        group_select(
            self,
            "assets_captured",
            key=lambda a: a.asset_type.name_plural,
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
                        "data-pb-xp": "",
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

            if not fighter.is_dead:
                # Dead fighters get no injury or state fields: a further
                # injury would re-run (or bypass) the kill flow, and leaving
                # DEAD must go through the resurrect flow (cost restoration).
                injury_field = f"injury_{pk}"
                self.fields[injury_field] = RepeatedModelChoiceField(
                    required=False,
                    queryset=available_injuries_for_fighter(fighter),
                )
                self.fields[injury_field].widget.attrs.update(
                    {
                        "class": "form-select form-select-sm",
                        "aria-label": f"Injury for {fighter.name}",
                    }
                )
                group_select(
                    self,
                    injury_field,
                    key=lambda x: x.injury_group.name if x.injury_group else "Other",
                )

                # Mirror EditFighterStateForm: vehicles repair, they don't
                # recover, convalesce or die.
                if fighter.content_fighter.category == FighterCategoryChoices.VEHICLE:
                    state_choices = [
                        (ListFighter.ACTIVE, "Active"),
                        (ListFighter.IN_REPAIR, "In Repair"),
                    ]
                else:
                    state_choices = [
                        (ListFighter.ACTIVE, "Active"),
                        (ListFighter.RECOVERY, "Recovery"),
                        (ListFighter.CONVALESCENCE, "Convalescence"),
                        (ListFighter.DEAD, "Dead"),
                    ]
                self.fields[f"state_{pk}"] = forms.ChoiceField(
                    required=False,
                    choices=[("", "—")] + state_choices,
                    widget=forms.Select(
                        attrs={
                            "class": "form-select form-select-sm",
                            "aria-label": f"State for {fighter.name}",
                        }
                    ),
                )

            if can_be_captured(fighter) and has_capture_lists:
                self.fields[f"captured_by_{pk}"] = forms.ModelChoiceField(
                    required=False,
                    queryset=capture_lists,
                    empty_label="—",
                    widget=forms.Select(
                        attrs={
                            "class": "form-select form-select-sm",
                            "aria-label": f"Gang that captured {fighter.name}",
                        }
                    ),
                )

        # A stronger border on every input, matching the steppers' outline
        # buttons so the grid's controls read as one set.
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            if "border-secondary" not in css:
                field.widget.attrs["class"] = f"{css} border-secondary".strip()

    def clean(self):
        cleaned = super().clean()
        # Resource losses can't take a resource below zero; validate here so
        # the whole submit fails cleanly instead of half-applying.
        for resource in self.resources:
            field = f"resource_{resource.pk}"
            delta = cleaned.get(field)
            if delta and delta < 0 and resource.amount + delta < 0:
                self.add_error(
                    field,
                    f"Cannot reduce {resource.resource_type.name} below zero "
                    f"(current: {resource.amount}).",
                )
        return cleaned


def _asset_label(asset):
    if asset.holder:
        return f"{asset.name} (held by {asset.holder.name})"
    return f"{asset.name} (unclaimed)"
