from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Case, When

from gyrinx.content.models.equipment import ContentEquipment, ContentEquipmentCategory
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.house import ContentHouse
from gyrinx.content.models.statline import ContentStatlineType
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.skill import ContentSkill, ContentSkillCategory
from gyrinx.content.models.weapon import (
    ContentWeaponAccessory,
    ContentWeaponProfile,
    ContentWeaponTrait,
)
from gyrinx.core.forms import BsCheckboxSelectMultipleCompact
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, TinyMCEWithUpload
from gyrinx.forms import group_select
from gyrinx.models import FighterCategoryChoices, equipment_category_groups

# Fighter categories excluded from pack creation.
# STASH is auto-managed (one per gang); GANG_TERRAIN has its own territory
# mechanics out of scope for pack support. VEHICLE and EXOTIC_BEAST ARE
# permitted — the pack create flow auto-spawns a companion ContentEquipment
# for them; see ``_ensure_auto_equipment_for_fighter`` in views/pack.py.
_EXCLUDED_FIGHTER_CATEGORIES = {
    FighterCategoryChoices.STASH,
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

    override_statline = forms.BooleanField(
        required=False,
        label="Override default statline for this Category?",
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input", "id": "id_override_statline"}
        ),
    )
    statline_type = forms.ModelChoiceField(
        queryset=ContentStatlineType.objects.none(),
        required=False,
        label="Statline type",
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "disabled": "disabled",
                "id": "id_statline_type",
            }
        ),
    )

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
            "house": "The house or faction this fighter or vehicle belongs to.",
            "base_cost": "The credit cost to hire this fighter or vehicle.",
        }
        widgets = {
            "type": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "house": forms.Select(attrs={"class": "form-select"}),
            "base_cost": forms.NumberInput(attrs={"class": "form-control"}),
            "skills": BsCheckboxSelectMultipleCompact(
                attrs={"class": "form-check-input"}
            ),
            "primary_skill_categories": BsCheckboxSelectMultipleCompact(
                attrs={"class": "form-check-input"}
            ),
            "secondary_skill_categories": BsCheckboxSelectMultipleCompact(
                attrs={"class": "form-check-input"}
            ),
            "rules": BsCheckboxSelectMultipleCompact(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter category choices.
        self.fields["category"].choices = [("", "---------")] + [
            (value, label)
            for value, label in FighterCategoryChoices.choices
            if value not in _EXCLUDED_FIGHTER_CATEGORIES
        ]

        # Populate statline type choices filtered to types relevant to
        # the categories available in this form.
        allowed_categories = {
            value
            for value, _ in FighterCategoryChoices.choices
            if value not in _EXCLUDED_FIGHTER_CATEGORIES
        }
        relevant_ids = [
            st.pk
            for st in ContentStatlineType.objects.all()
            if set(st.default_for_categories) & allowed_categories
        ]
        self.fields["statline_type"].queryset = ContentStatlineType.objects.filter(
            pk__in=relevant_ids
        )
        self.fields["statline_type"].empty_label = "Default"
        # Remove disabled attr when override is checked so the value submits.
        if self.data.get("override_statline"):
            del self.fields["statline_type"].widget.attrs["disabled"]

        # Place the override/statline fields right after category.
        field_order = list(self.fields.keys())
        cat_idx = field_order.index("category") + 1
        for name in ("override_statline", "statline_type"):
            field_order.remove(name)
        field_order.insert(cat_idx, "override_statline")
        field_order.insert(cat_idx + 1, "statline_type")
        self.order_fields(field_order)

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

        # Filter skills and skill categories: base library + pack content.
        if pack is not None:
            if "skills" in self.fields:
                self.fields["skills"].queryset = ContentSkill.objects.with_packs([pack])
            if "primary_skill_categories" in self.fields:
                self.fields[
                    "primary_skill_categories"
                ].queryset = ContentSkillCategory.objects.with_packs([pack])
            if "secondary_skill_categories" in self.fields:
                self.fields[
                    "secondary_skill_categories"
                ].queryset = ContentSkillCategory.objects.with_packs([pack])
        else:
            if "skills" in self.fields:
                self.fields["skills"].queryset = ContentSkill.objects.all()
            if "primary_skill_categories" in self.fields:
                self.fields[
                    "primary_skill_categories"
                ].queryset = ContentSkillCategory.objects.all()
            if "secondary_skill_categories" in self.fields:
                self.fields[
                    "secondary_skill_categories"
                ].queryset = ContentSkillCategory.objects.all()

        # Fix initial values for skills M2M fields when editing (same issue as rules).
        if not self.instance._state.adding:
            if "skills" in self.fields:
                self.initial["skills"] = list(
                    self.fields["skills"]
                    .queryset.filter(contentfighter=self.instance)
                    .values_list("pk", flat=True)
                )
            if "primary_skill_categories" in self.fields:
                self.initial["primary_skill_categories"] = list(
                    self.fields["primary_skill_categories"]
                    .queryset.filter(primary_fighters=self.instance)
                    .values_list("pk", flat=True)
                )
            if "secondary_skill_categories" in self.fields:
                self.initial["secondary_skill_categories"] = list(
                    self.fields["secondary_skill_categories"]
                    .queryset.filter(secondary_fighters=self.instance)
                    .values_list("pk", flat=True)
                )

        # Group skills by category for better readability.
        if "skills" in self.fields:
            group_select(self, "skills", key=lambda x: x.category)

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
        else:
            # Override statline is only relevant during creation.
            for field_name in ["override_statline", "statline_type"]:
                self.fields.pop(field_name, None)

    def clean(self):
        cleaned = super().clean()
        # Server-side enforcement: ignore statline_type unless override is checked.
        if not cleaned.get("override_statline"):
            cleaned["statline_type"] = None
        return cleaned

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
        fields = ["name", "description"]
        labels = {
            "name": "Name",
            "description": "Description",
        }
        help_texts = {
            "name": "The name of the house or faction.",
            "description": "Lore or background for this house.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
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


class ContentWeaponAccessoryPackForm(forms.ModelForm):
    """Form for adding/editing weapon accessories in a content pack.

    Includes a synthetic mod picker (weapon stat mods + weapon trait mods)
    that find-or-creates ``ContentModStat`` and ``ContentModTrait`` rows in
    the base library and attaches them to the accessory's ``modifiers`` M2M.
    """

    STAT_FIELD_KEYS = [
        ("strength", "Strength"),
        ("range_short", "Range (short)"),
        ("range_long", "Range (long)"),
        ("accuracy_short", "Accuracy (short)"),
        ("accuracy_long", "Accuracy (long)"),
        ("armour_piercing", "Armour piercing"),
        ("damage", "Damage"),
        ("ammo", "Ammo"),
    ]
    STAT_MODE_CHOICES = [
        ("", "None"),
        ("improve", "Improve"),
        ("worsen", "Worsen"),
        ("set", "Set"),
    ]
    TRAIT_MODE_CHOICES = [
        ("", "None"),
        ("add", "Add"),
        ("remove", "Remove"),
    ]

    class Meta:
        model = ContentWeaponAccessory
        fields = ["name", "description", "cost", "rarity", "rarity_roll"]
        labels = {
            "name": "Name",
            "description": "Description",
            "cost": "Cost",
            "rarity": "Availability",
            "rarity_roll": "Availability level",
        }
        help_texts = {
            "name": "The name of the accessory (e.g. 'Telescopic sight').",
            "description": "Flavour text or rules for this accessory.",
            "cost": "The credit cost at the Trading Post.",
            "rarity": "The availability of this accessory.",
            "rarity_roll": "The roll required to find this accessory (e.g. 7, 10).",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "cost": forms.NumberInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
        }

    @property
    def standard_fields(self):
        """Iterate the bound fields for the regular ModelForm fields only."""
        for name in self.Meta.fields:
            yield self[name]

    @property
    def stat_mod_rows(self):
        """Per-stat groupings of (mode, value) bound fields for the picker."""
        return [
            {
                "stat": stat_key,
                "label": stat_label,
                "mode_field": self[f"stat_mod_{stat_key}_mode"],
                "value_field": self[f"stat_mod_{stat_key}_value"],
            }
            for stat_key, stat_label in self.STAT_FIELD_KEYS
        ]

    @property
    def trait_mod_rows(self):
        """Per-trait bound fields for the trait picker."""
        return [
            {
                "trait": trait,
                "field": self[f"trait_mod_{trait.pk}"],
            }
            for trait in self._traits
        ]

    @property
    def any_trait_mod_set(self):
        """True if any trait mod has a current value (initial or submitted)."""
        return any(self[f"trait_mod_{trait.pk}"].value() for trait in self._traits)

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack

        for stat_key, stat_label in self.STAT_FIELD_KEYS:
            self.fields[f"stat_mod_{stat_key}_mode"] = forms.ChoiceField(
                choices=self.STAT_MODE_CHOICES,
                required=False,
                label=stat_label,
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
            )
            self.fields[f"stat_mod_{stat_key}_value"] = forms.CharField(
                required=False,
                max_length=5,
                label=f"{stat_label} value",
                widget=forms.TextInput(
                    attrs={"class": "form-control form-control-sm", "size": "5"}
                ),
            )

        if pack is not None:
            traits = ContentWeaponTrait.objects.with_packs([pack])
        else:
            traits = ContentWeaponTrait.objects.all_content()
        self._traits = list(traits.order_by("name"))
        for trait in self._traits:
            self.fields[f"trait_mod_{trait.pk}"] = forms.ChoiceField(
                choices=self.TRAIT_MODE_CHOICES,
                required=False,
                label=str(trait),
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
            )

        if self.instance.pk and not self.is_bound:
            self._populate_initial_mods()

    def _populate_initial_mods(self):
        from gyrinx.content.models.modifier import ContentModStat, ContentModTrait

        for mod in self.instance.modifiers.all():
            if isinstance(mod, ContentModStat):
                self.initial[f"stat_mod_{mod.stat}_mode"] = mod.mode
                self.initial[f"stat_mod_{mod.stat}_value"] = mod.value
            elif isinstance(mod, ContentModTrait):
                key = f"trait_mod_{mod.trait_id}"
                if key in self.fields:
                    self.initial[key] = mod.mode

    def clean(self):
        cleaned = super().clean()
        for stat_key, stat_label in self.STAT_FIELD_KEYS:
            mode = cleaned.get(f"stat_mod_{stat_key}_mode")
            value = (cleaned.get(f"stat_mod_{stat_key}_value") or "").strip()
            # Normalise the cleaned value so " 1 " and "1" dedupe in get_or_create.
            cleaned[f"stat_mod_{stat_key}_value"] = value
            if mode and not value:
                self.add_error(
                    f"stat_mod_{stat_key}_value",
                    f"A value is required when a mode is selected for {stat_label}.",
                )
            elif value and not mode:
                self.add_error(
                    f"stat_mod_{stat_key}_mode",
                    f"Choose a mode for the {stat_label} value, or clear the value.",
                )
            elif mode in {"improve", "worsen"} and value:
                # ContentModStat.apply() does int(self.value) for improve/worsen,
                # so reject non-integer values here rather than letting them blow
                # up at runtime when the mod is applied to a weapon profile.
                try:
                    int(value)
                except (TypeError, ValueError):
                    self.add_error(
                        f"stat_mod_{stat_key}_value",
                        f"Enter an integer for {stat_label} when using {mode}.",
                    )
        return cleaned

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentWeaponAccessory.objects.filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A weapon accessory with this name already exists in the content library."
            )
        if self._pack is not None:
            from django.contrib.contenttypes.models import ContentType

            from gyrinx.core.models.pack import CustomContentPackItem

            accessory_ct = ContentType.objects.get_for_model(ContentWeaponAccessory)
            pack_accessory_ids = CustomContentPackItem.objects.filter(
                pack=self._pack, content_type=accessory_ct, archived=False
            ).values_list("object_id", flat=True)
            qs = ContentWeaponAccessory.objects.all_content().filter(
                pk__in=pack_accessory_ids, name__iexact=value
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "A weapon accessory with this name already exists in this Content Pack."
                )
        return value

    def _save_m2m(self):
        super()._save_m2m()
        self._save_mods(self.instance)

    def _save_mods(self, instance):
        from gyrinx.content.models.modifier import ContentModStat, ContentModTrait

        mods = []
        for stat_key, _ in self.STAT_FIELD_KEYS:
            mode = self.cleaned_data.get(f"stat_mod_{stat_key}_mode")
            value = self.cleaned_data.get(f"stat_mod_{stat_key}_value")
            if mode and value:
                mod, _created = ContentModStat.objects.get_or_create(
                    stat=stat_key, mode=mode, value=value
                )
                mods.append(mod)
        for trait in self._traits:
            mode = self.cleaned_data.get(f"trait_mod_{trait.pk}")
            if mode:
                mod, _created = ContentModTrait.objects.get_or_create(
                    trait=trait, mode=mode
                )
                mods.append(mod)
        instance.modifiers.set(mods)


class ContentSkillCategoryPackForm(forms.ModelForm):
    """Form for adding/editing skill categories (skill trees) in a content pack."""

    class Meta:
        model = ContentSkillCategory
        fields = ["name"]
        labels = {
            "name": "Name",
        }
        help_texts = {
            "name": "The name of the skill tree (e.g. 'Bravado').",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentSkillCategory.objects.all_content().filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A skill tree with this name already exists in the content library."
            )
        return value


class ContentSkillPackForm(forms.ModelForm):
    """Form for adding/editing skills in a content pack."""

    class Meta:
        model = ContentSkill
        fields = ["name", "category", "description"]
        labels = {
            "name": "Name",
            "category": "Skill tree",
            "description": "Description",
        }
        help_texts = {
            "name": "The name of the skill.",
            "category": "The skill tree this skill belongs to.",
            "description": "Optional description of what this skill does.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack
        if pack is not None:
            qs = ContentSkillCategory.objects.with_packs([pack])
        else:
            qs = ContentSkillCategory.objects.all()
        self.fields["category"].queryset = qs

        # Group choices into "Default" (base game) and "Custom" (pack content)
        if pack is not None:
            from gyrinx.core.models.pack import CustomContentPackItem

            pack_cat_ids = set(
                CustomContentPackItem.objects.filter(
                    pack=pack,
                    content_type__model="contentskillcategory",
                    archived=False,
                ).values_list("object_id", flat=True)
            )
            default_choices = []
            custom_choices = []
            for cat in qs.order_by("name"):
                choice = (cat.pk, str(cat))
                if cat.pk in pack_cat_ids:
                    custom_choices.append(choice)
                else:
                    default_choices.append(choice)
            grouped = [("", "---------")]
            if custom_choices:
                grouped.append(("Custom", custom_choices))
            if default_choices:
                grouped.append(("Default", default_choices))
            self.fields["category"].choices = grouped

    def clean_name(self):
        value = self.cleaned_data["name"]
        category = self.cleaned_data.get("category")
        if category:
            qs = ContentSkill.objects.all_content().filter(
                name__iexact=value, category=category
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "A skill with this name already exists in this skill tree."
                )
        return value


class ContentGearPackForm(forms.ModelForm):
    """Form for adding/editing gear (non-weapon equipment) in a content pack."""

    class Meta:
        model = ContentEquipment
        fields = ["name", "description", "category", "cost", "rarity", "rarity_roll"]
        labels = {
            "name": "Name",
            "description": "Description",
            "category": "Category",
            "cost": "Cost",
            "rarity": "Availability",
            "rarity_roll": "Availability level",
        }
        help_texts = {
            "name": "The name of the gear.",
            "description": "Flavour text or rules for this gear.",
            "category": "The gear category (e.g. Armour, Personal Equipment).",
            "cost": "The credit cost at the Trading Post.",
            "rarity": "The availability of this gear.",
            "rarity_roll": "The roll required to find this gear (e.g. 7, 10).",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "cost": forms.TextInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter to gear categories only (exclude weapons), ordered by group then name.
        # "Vehicles" is also excluded — pack vehicles are auto-created from
        # VEHICLE fighters, so users should never pick it manually.
        self.fields["category"].queryset = (
            ContentEquipmentCategory.objects.exclude(
                group__in=["Weapons & Ammo", "Other"]
            ).exclude(name="Vehicles")
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

        # Filter to weapon categories only (exclude Ammo), ordered by name.
        self.fields["category"].queryset = (
            ContentEquipmentCategory.objects.filter(group="Weapons & Ammo").exclude(
                name="Ammo"
            )
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
    """Form for adding/editing weapon profiles in a content pack.

    Accepts an optional ``pack`` kwarg to filter the traits queryset
    to include both base library traits and pack-specific traits.
    """

    class Meta:
        model = ContentWeaponProfile
        fields = ["name", "cost", "rarity", "rarity_roll", "traits"]
        labels = {
            "name": "Profile name",
            "cost": "Cost",
            "rarity": "Availability",
            "rarity_roll": "Availability level",
            "traits": "Traits",
        }
        help_texts = {
            "name": "e.g. ranged, melee, gas shells...",
            "cost": "The credit cost. If free, the other free profiles must be named.",
            "rarity": "The availability of this profile.",
            "rarity_roll": "The roll required to find this profile (e.g. 7, 10).",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "cost": forms.NumberInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
            "traits": BsCheckboxSelectMultipleCompact(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        if pack is not None:
            self.fields["traits"].queryset = ContentWeaponTrait.objects.with_packs(
                [pack]
            )

        # Fix initial values for traits M2M when editing.
        # model_to_dict() uses instance.traits.all() which goes through
        # ContentManager and excludes pack content.
        if not self.instance._state.adding and pack is not None:
            instance_trait_ids = self.instance.traits.values_list("pk", flat=True)
            self.initial["traits"] = list(
                self.fields["traits"]
                .queryset.filter(pk__in=instance_trait_ids)
                .values_list("pk", flat=True)
            )
