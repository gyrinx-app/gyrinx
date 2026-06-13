from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.content.models import ContentSkillCategory
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListSkillTreeAssignment


class ListSkillTreeForm(forms.Form):
    """
    Form for picking a gang's ranked skill trees (gang-wide skills).

    Renders one ranked dropdown per slot (1..``gang_skill_tree_count``). Each
    dropdown lists the available pool of skill trees. Restricted trees are
    hidden unless ``include_restricted`` is set.
    """

    def __init__(self, *args, **kwargs):
        self.list_obj = kwargs.pop("list_obj")
        self.request = kwargs.pop("request", None)
        self.include_restricted = kwargs.pop("include_restricted", False)
        super().__init__(*args, **kwargs)

        house = self.list_obj.content_house
        self.slot_count = house.gang_skill_tree_count or 0

        pool = self._pool_queryset(house)

        # Current picks: slot -> category id
        current = {
            a.slot: a.skill_category_id
            for a in ListSkillTreeAssignment.objects.filter(
                list=self.list_obj, archived=False
            )
        }

        for slot in range(1, self.slot_count + 1):
            self.fields[f"slot_{slot}"] = forms.ModelChoiceField(
                queryset=pool,
                required=False,
                label=f"Tree {slot}",
                initial=current.get(slot),
                empty_label="—",
                widget=forms.Select(attrs={"class": "form-select"}),
            )

    def _pool_queryset(self, house):
        """The set of skill trees a gang may pick from.

        Always pack-aware (so pack-authored trees are pickable), and the
        ``include_restricted`` toggle is applied uniformly — including when the
        house defines an explicit ``gang_skill_tree_choices`` pool, which only
        narrows the pack-aware queryset rather than replacing it.
        """
        packs = self.list_obj.packs.all()
        qs = ContentSkillCategory.objects.with_packs(packs, include_archived_items=True)

        # Read the explicit pool membership straight from the M2M through table:
        # the related manager uses the pack-excluding ContentManager, which would
        # silently drop pack-authored categories that the house added to its pool.
        explicit_ids = list(
            house.gang_skill_tree_choices.through.objects.filter(
                contenthouse=house
            ).values_list("contentskillcategory_id", flat=True)
        )
        if explicit_ids:
            qs = qs.filter(id__in=explicit_ids)

        if not self.include_restricted:
            qs = qs.filter(restricted=False)

        return qs.order_by("name")

    @property
    def slot_fields(self):
        """Bound fields for each slot, in order (for template iteration)."""
        return [self[f"slot_{slot}"] for slot in range(1, self.slot_count + 1)]

    def clean(self):
        cleaned_data = super().clean()

        if self.list_obj.archived:
            raise ValidationError("Cannot modify skill trees for an archived list.")

        # Chosen trees must be distinct across slots.
        picks = [
            cleaned_data.get(f"slot_{slot}") for slot in range(1, self.slot_count + 1)
        ]
        chosen = [p for p in picks if p is not None]
        if len(chosen) != len(set(chosen)):
            raise ValidationError("Each skill tree can only be picked once.")

        return cleaned_data

    def save(self):
        """Archive existing picks and create the new ranked selection."""
        with transaction.atomic():
            ListSkillTreeAssignment.objects.filter(
                list=self.list_obj, archived=False
            ).update(archived=True)

            chosen_names = []
            for slot in range(1, self.slot_count + 1):
                category = self.cleaned_data.get(f"slot_{slot}")
                if category is None:
                    continue
                ListSkillTreeAssignment.objects.create(
                    list=self.list_obj,
                    slot=slot,
                    skill_category=category,
                )
                chosen_names.append(f"{slot}. {category.name}")

            if (
                self.list_obj.is_campaign_mode
                and self.list_obj.campaign
                and self.request
            ):
                action_text = "Updated gang skill trees: " + (
                    ", ".join(chosen_names) if chosen_names else "None"
                )
                CampaignAction.objects.create(
                    campaign=self.list_obj.campaign,
                    list=self.list_obj,
                    user=self.request.user,
                    description=action_text,
                )
