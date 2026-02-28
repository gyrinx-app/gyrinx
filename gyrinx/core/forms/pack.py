from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Case, When

from gyrinx.content.models.equipment import ContentEquipment, ContentEquipmentCategory
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.house import ContentHouse
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.weapon import ContentWeaponProfile, ContentWeaponTrait
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

        # On create (no saved instance yet), hide M2M fields that only
        # make sense after the fighter exists — except rules, which users
        # should be able to set when creating a fighter.
        # Note: can't use `not self.instance.pk` because UUID pk is
        # auto-generated before save.
        if self.instance._state.adding:
            for field_name in [
                "skills",
                "primary_skill_categories",
                "secondary_skill_categories",
            ]:
                del self.fields[field_name]

    def clean_type(self):
        value = self.cleaned_data["type"]
        qs = ContentFighter.objects.filter(type__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A fighter with this name already exists in the content library."
            )
        return value


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

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentHouse.objects.filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A house with this name already exists in the content library."
            )
        return value


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

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentRule.objects.filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A rule with this name already exists in the content library."
            )
        return value


class ContentWeaponTraitPackForm(forms.ModelForm):
    """Form for adding/editing weapon traits in a content pack."""

    class Meta:
        model = ContentWeaponTrait
        fields = ["name", "description"]
        labels = {
            "name": "Name",
            "description": "Description",
        }
        help_texts = {
            "name": "The name of the weapon trait (e.g. 'Plasma').",
            "description": "An optional description of what this trait does.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack

    def clean_name(self):
        value = self.cleaned_data["name"]
        # Check uniqueness among base (non-pack) traits.
        qs = ContentWeaponTrait.objects.filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A weapon trait with this name already exists in the content library."
            )
        # Check uniqueness within the current pack.
        if self._pack is not None:
            from django.contrib.contenttypes.models import ContentType

            from gyrinx.core.models.pack import CustomContentPackItem

            trait_ct = ContentType.objects.get_for_model(ContentWeaponTrait)
            pack_trait_ids = CustomContentPackItem.objects.filter(
                pack=self._pack, content_type=trait_ct, archived=False
            ).values_list("object_id", flat=True)
            qs = ContentWeaponTrait.objects.all_content().filter(
                pk__in=pack_trait_ids, name__iexact=value
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "A weapon trait with this name already exists in this Content Pack."
                )
        return value


class ContentGearPackForm(forms.ModelForm):
    """Form for adding/editing gear (non-weapon equipment) in a content pack."""

    class Meta:
        model = ContentEquipment
        fields = ["name", "category", "cost", "rarity", "rarity_roll"]
        labels = {
            "name": "Name",
            "category": "Category",
            "cost": "Cost",
            "rarity": "Availability",
            "rarity_roll": "Availability level",
        }
        help_texts = {
            "name": "The name of the gear.",
            "category": "The gear category (e.g. Armour, Wargear).",
            "cost": "The credit cost at the Trading Post.",
            "rarity": "The availability of this gear.",
            "rarity_roll": "The roll required to find this gear (e.g. 7, 10).",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "cost": forms.TextInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter to gear categories only (exclude weapons), ordered by group then name.
        self.fields["category"].queryset = (
            ContentEquipmentCategory.objects.exclude(
                group__in=["Weapons & Ammo", "Other"]
            )
        ).order_by(
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

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentEquipment.objects.filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "Gear with this name already exists in the content library."
            )
        return value


class ContentWeaponPackForm(forms.ModelForm):
    """Form for adding/editing weapons in a content pack.

    Filters categories to "Weapons & Ammo" only (inverse of the gear form).
    """

    class Meta:
        model = ContentEquipment
        fields = ["name", "category", "cost", "rarity", "rarity_roll"]
        labels = {
            "name": "Name",
            "category": "Category",
            "cost": "Cost",
            "rarity": "Availability",
            "rarity_roll": "Availability level",
        }
        help_texts = {
            "name": "The name of the weapon.",
            "category": "The weapon category (e.g. Pistols, Basic Weapons).",
            "cost": "The credit cost at the Trading Post.",
            "rarity": "The availability of this weapon.",
            "rarity_roll": "The roll required to find this weapon (e.g. 7, 10).",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "cost": forms.TextInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter to weapon categories only, ordered by group then name.
        self.fields["category"].queryset = (
            ContentEquipmentCategory.objects.filter(group="Weapons & Ammo")
        ).order_by("name")

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentEquipment.objects.filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A weapon with this name already exists in the content library."
            )
        return value


class ContentWeaponProfilePackForm(forms.ModelForm):
    """Form for adding/editing weapon profiles in a content pack."""

    class Meta:
        model = ContentWeaponProfile
        fields = ["name", "cost", "rarity", "rarity_roll"]
        labels = {
            "name": "Profile name",
            "cost": "Cost",
            "rarity": "Availability",
            "rarity_roll": "Availability level",
        }
        help_texts = {
            "name": "Leave blank for the standard profile. Named profiles represent alternate fire modes.",
            "cost": "The credit cost. Standard (unnamed) profiles must have zero cost.",
            "rarity": "The availability of this profile.",
            "rarity_roll": "The roll required to find this profile (e.g. 7, 10).",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "cost": forms.NumberInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
        }
