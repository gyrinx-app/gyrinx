from django import forms
from django.db.models import Case, When

from gyrinx.content.models.equipment import ContentEquipment, ContentEquipmentCategory
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.house import ContentHouse
from gyrinx.content.models.metadata import ContentRule
from gyrinx.models import FighterCategoryChoices, equipment_category_groups
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, TinyMCEWithUpload

# Fighter categories excluded from pack creation.
_EXCLUDED_FIGHTER_CATEGORIES = {
    FighterCategoryChoices.STASH,
    FighterCategoryChoices.VEHICLE,
    FighterCategoryChoices.GANG_TERRAIN,
}


class PackForm(forms.ModelForm):
    class Meta:
        model = CustomContentPack
        fields = ["name", "summary", "description", "listed"]
        labels = {
            "name": "Name",
            "summary": "Summary",
            "description": "Description",
            "listed": "Listed",
        }
        help_texts = {
            "name": "The name of your content pack.",
            "summary": "A brief summary displayed on the pack index page.",
            "description": "A detailed description displayed on the pack detail page.",
            "listed": "If checked, this pack will appear in search results. Unlisted packs are still shareable via link.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "summary": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 5},
                mce_attrs={"height": "150px", **TINYMCE_EXTRA_ATTRS},
            ),
            "description": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20},
                mce_attrs=TINYMCE_EXTRA_ATTRS,
            ),
            "listed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ContentFighterPackForm(forms.ModelForm):
    """Form for adding/editing fighters in a content pack.

    On create (no instance): shows type, category, house, base_cost.
    On edit (has instance): adds skills, skill categories, and rules.

    Accepts an optional ``pack`` kwarg to filter house/rules querysets
    to include both base library content and pack-specific content.
    """

    class Meta:
        model = ContentFighter
        fields = [
            "type",
            "category",
            "house",
            "base_cost",
            "skills",
            "primary_skill_categories",
            "secondary_skill_categories",
            "rules",
        ]
        labels = {
            "type": "Name",
            "category": "Category",
            "house": "House",
            "base_cost": "Base cost",
            "skills": "Default skills",
            "primary_skill_categories": "Primary skill trees",
            "secondary_skill_categories": "Secondary skill trees",
            "rules": "Rules",
        }
        help_texts = {
            "type": "The fighter's name (e.g. 'Gang Leader').",
            "category": "The fighter's category.",
            "house": "The house or faction this fighter belongs to.",
            "base_cost": "The credit cost to hire this fighter.",
        }
        widgets = {
            "type": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "house": forms.Select(attrs={"class": "form-select"}),
            "base_cost": forms.NumberInput(attrs={"class": "form-control"}),
            "skills": forms.SelectMultiple(attrs={"class": "form-select", "size": 8}),
            "primary_skill_categories": forms.SelectMultiple(
                attrs={"class": "form-select", "size": 6}
            ),
            "secondary_skill_categories": forms.SelectMultiple(
                attrs={"class": "form-select", "size": 6}
            ),
            "rules": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter category choices.
        self.fields["category"].choices = [("", "---------")] + [
            (value, label)
            for value, label in FighterCategoryChoices.choices
            if value not in _EXCLUDED_FIGHTER_CATEGORIES
        ]

        # House is required for pack fighters.
        self.fields["house"].required = True

        # Filter house queryset: base library + pack houses.
        if pack is not None:
            self.fields["house"].queryset = ContentHouse.objects.with_packs([pack])
            # Default to the first house defined in the pack.
            if self.instance._state.adding and not self.initial.get("house"):
                from django.contrib.contenttypes.models import ContentType

                from gyrinx.core.models.pack import CustomContentPackItem

                house_ct = ContentType.objects.get_for_model(ContentHouse)
                first_pack_house = (
                    CustomContentPackItem.objects.filter(
                        pack=pack, content_type=house_ct, archived=False
                    )
                    .values_list("object_id", flat=True)
                    .first()
                )
                if first_pack_house:
                    self.initial["house"] = first_pack_house
        else:
            self.fields["house"].queryset = ContentHouse.objects.all()

        # Filter rules queryset: base library + pack rules.
        if pack is not None:
            self.fields["rules"].queryset = ContentRule.objects.with_packs([pack])
        else:
            self.fields["rules"].queryset = ContentRule.objects.all()

        # Fix initial values for the rules M2M field when editing.
        # model_to_dict() uses instance.rules.all() which goes through
        # ContentManager.get_queryset() and excludes pack content, so
        # pack rules assigned to this fighter are not pre-selected.
        # Use the field queryset to stay consistent with available choices.
        if not self.instance._state.adding:
            self.initial["rules"] = list(
                self.fields["rules"]
                .queryset.filter(contentfighter=self.instance)
                .values_list("pk", flat=True)
            )

        # On create (no saved instance yet), hide M2M fields.
        # Note: can't use `not self.instance.pk` because UUID pk is
        # auto-generated before save.
        if self.instance._state.adding:
            for field_name in [
                "skills",
                "primary_skill_categories",
                "secondary_skill_categories",
                "rules",
            ]:
                del self.fields[field_name]


class ContentHouseForm(forms.ModelForm):
    class Meta:
        model = ContentHouse
        fields = ["name"]
        labels = {
            "name": "Name",
        }
        help_texts = {
            "name": "The name of the house or faction.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }


class ContentRuleForm(forms.ModelForm):
    class Meta:
        model = ContentRule
        fields = ["name", "description"]
        labels = {
            "name": "Name",
            "description": "Description",
        }
        help_texts = {
            "name": "The name of the rule.",
            "description": "An optional description of what this rule does.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class ContentEquipmentPackForm(forms.ModelForm):
    """Form for adding/editing equipment in a content pack."""

    class Meta:
        model = ContentEquipment
        fields = ["name", "category", "cost", "rarity"]
        labels = {
            "name": "Name",
            "category": "Category",
            "cost": "Cost",
            "rarity": "Availability",
        }
        help_texts = {
            "name": "The name of the equipment.",
            "category": "The equipment category (e.g. Pistols, Wargear).",
            "cost": "The credit cost at the Trading Post.",
            "rarity": "The availability of this equipment.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "cost": forms.TextInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        # Accept and discard the pack kwarg for consistency with other forms.
        kwargs.pop("pack", None)
        super().__init__(*args, **kwargs)

        # Order categories by group, then by name within each group.
        self.fields[
            "category"
        ].queryset = ContentEquipmentCategory.objects.all().order_by(
            Case(
                *[
                    When(group=group, then=i)
                    for i, group in enumerate(equipment_category_groups)
                ],
                default=99,
            ),
            "name",
        )

        # Group the category dropdown by equipment group.
        from gyrinx.forms import group_select

        group_select(self, "category", key=lambda x: x.group)
