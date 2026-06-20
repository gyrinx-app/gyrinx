import copy

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Case, When

from gyrinx.content.models.attribute import ContentAttribute, ContentAttributeValue
from gyrinx.content.models.equipment import ContentEquipment, ContentEquipmentCategory
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.house import ContentHouse
from gyrinx.content.models.psyker import (
    ContentPsykerDiscipline,
    ContentPsykerPower,
)
from gyrinx.content.models.statline import ContentStatlineType
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.skill import ContentSkill, ContentSkillCategory
from gyrinx.content.models.weapon import (
    ContentWeaponAccessory,
    ContentWeaponProfile,
    ContentWeaponTrait,
)
from gyrinx.core.forms import BsCheckboxSelectMultipleCompact
from gyrinx.core.models.pack import (
    CustomContentPack,
    CustomContentPackAttachment,
)
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, TinyMCEWithUpload
from gyrinx.forms import group_select
from gyrinx.models import FighterCategoryChoices, equipment_category_groups


def rich_text_description_widget(height="200px"):
    """TinyMCE widget for short rich-text description fields on pack content.

    Mirrors the editor used for ``PackForm.summary`` so that custom rules,
    skills, gear, traits, etc. support rich text formatting — but with image
    insertion removed (these are short descriptions in a dense listing where
    embedded images render awkwardly). The rest of the standard toolbar
    (headings, lists, links, formatting, etc.) is retained. Rendered output is
    sanitised on display via the ``safe_rich_text`` template filter.

    Returns a fresh instance per call so each form owns its own widget.
    """
    # Drop the image item from the insert menu (deep-copied so the shared
    # TINYMCE_EXTRA_ATTRS dict used by PackForm is left untouched).
    menu = copy.deepcopy(TINYMCE_EXTRA_ATTRS["menu"])
    menu["insert"]["items"] = (
        "link media addcomment pageembed codesample inserttable | math "
        "| charmap emoticons hr | pagebreak nonbreaking anchor "
        "tableofcontents | insertdatetime"
    )
    return TinyMCEWithUpload(
        attrs={"cols": 80, "rows": 5},
        mce_attrs={
            **TINYMCE_EXTRA_ATTRS,
            "menu": menu,
            "height": height,
            # No image support: drop the image plugin, its toolbar button,
            # and the empty-line quick-insert bar (which offers quickimage).
            "plugins": "autoresize autosave code emoticons fullscreen help link lists quickbars textpattern visualblocks",
            "toolbar": "undo redo | blocks | bold italic underline link | numlist bullist align | code",
            "quickbars_insert_toolbar": False,
        },
    )


# Fighter categories excluded from pack creation.
# STASH is auto-managed (one per gang); GANG_TERRAIN has its own territory
# mechanics out of scope for pack support. VEHICLE and EXOTIC_BEAST ARE
# permitted — the pack create flow auto-spawns a companion ContentEquipment
# for them; see ``_ensure_auto_equipment_for_fighter`` in views/pack.py.
_EXCLUDED_FIGHTER_CATEGORIES = {
    FighterCategoryChoices.STASH,
    FighterCategoryChoices.GANG_TERRAIN,
}


# Appended to the ``cost`` / ``base_cost`` help text on pack forms when editing
# an existing item. Cost propagation to subscribed gangs runs as a background
# task (see ``propagate_content_cost_change``), so the change may take a moment
# to appear on every list using this item.
COST_PROPAGATION_HELP_SUFFIX = (
    " Changing the cost of an existing item updates lists already using it in "
    "the background — it may take a moment to appear on every gang."
)


def _append_cost_propagation_help(form, field_name="cost"):
    """If editing an existing instance, append the propagation-delay note to
    the named field's help text. No-op on create (nothing to propagate to)."""
    if form.instance.pk and field_name in form.fields:
        existing = form.fields[field_name].help_text or ""
        form.fields[field_name].help_text = existing + COST_PROPAGATION_HELP_SUFFIX


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


class PackAttachmentForm(forms.ModelForm):
    class Meta:
        model = CustomContentPackAttachment
        fields = ["file", "title", "description"]
        labels = {
            "file": "File",
            "title": "Title",
            "description": "Description",
        }
        help_texts = {
            "file": "PDF or image, up to 20MB.",
            "title": "An optional display title. Defaults to the file name.",
            "description": "An optional description shown alongside the file.",
        }
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class ContentFighterPackForm(forms.ModelForm):
    """Form for adding/editing fighters in a content pack.

    On create (no instance): shows type, category, house, base_cost.
    On edit (has instance): adds skills, skill categories, and rules.

    Accepts an optional ``pack`` kwarg to filter house/rules querysets
    to include both base library content and pack-specific content.

    Whether the statline-override section is shown is a URL-driven variant:
    the view reads ``?override_statline=1`` and passes ``override_statline``
    to this form. When off, the ``statline_type`` field is removed entirely
    so it can never submit a value (no client-side disabling needed).
    """

    statline_type = forms.ModelChoiceField(
        queryset=ContentStatlineType.objects.none(),
        required=False,
        label="Statline type",
        widget=forms.Select(attrs={"class": "form-select"}),
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
            "rules": "Special rules",
        }
        help_texts = {
            "type": "The name of this fighter or vehicle (e.g. 'Gang Leader', 'Goliath Mauler').",
            "category": "The category for this fighter or vehicle.",
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

    def __init__(self, *args, pack=None, override_statline=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack
        self._override_statline = override_statline
        _append_cost_propagation_help(self, "base_cost")

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

        # URL-driven variant: only include statline_type when overriding.
        # When the override is off the field is removed so it can never
        # submit a value, and clean() forces statline_type to None.
        if self._override_statline:
            # Place the statline-type field right after category.
            field_order = list(self.fields.keys())
            cat_idx = field_order.index("category") + 1
            field_order.remove("statline_type")
            field_order.insert(cat_idx, "statline_type")
            self.order_fields(field_order)
        else:
            del self.fields["statline_type"]

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
            self.fields.pop("statline_type", None)

            # Psyker discipline picker. Only non-generic disciplines are
            # shown — generic disciplines are pooled and cannot be assigned
            # to a fighter (see ContentFighterPsykerDisciplineAssignment.clean).
            from gyrinx.content.models.psyker import (
                ContentFighterPsykerDisciplineAssignment,
                ContentPsykerDiscipline,
            )

            if pack is not None:
                disc_qs = ContentPsykerDiscipline.objects.with_packs([pack]).filter(
                    generic=False
                )
            else:
                disc_qs = ContentPsykerDiscipline.objects.filter(generic=False)
            self.fields["psyker_disciplines"] = forms.ModelMultipleChoiceField(
                queryset=disc_qs.order_by("name"),
                required=False,
                widget=BsCheckboxSelectMultipleCompact(
                    attrs={"class": "form-check-input"}
                ),
                label="Psyker disciplines",
                help_text=(
                    "Disciplines this fighter has access to. Generic "
                    "disciplines are not shown — they are available to any "
                    "psyker by default."
                ),
            )
            # Pre-select disciplines this fighter is currently assigned to —
            # but only those visible through the field's pack-scoped queryset,
            # so disciplines/assignments authored in OTHER packs don't leak
            # into this pack's editing UI.
            current = (
                ContentFighterPsykerDisciplineAssignment.objects.all_content()
                .filter(
                    fighter=self.instance,
                    discipline__in=self.fields["psyker_disciplines"].queryset,
                )
                .values_list("discipline_id", flat=True)
            )
            self.initial["psyker_disciplines"] = list(current)

    def clean(self):
        cleaned = super().clean()
        # Server-side enforcement: ignore statline_type unless the
        # URL-driven override variant is active.
        if not self._override_statline:
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

    def _save_m2m(self):
        super()._save_m2m()
        self._sync_psyker_disciplines()

    def _sync_psyker_disciplines(self):
        """Reconcile ContentFighterPsykerDisciplineAssignment rows + their
        CustomContentPackItem entries with the form's selected disciplines.

        Pack-scoped throughout: only the current pack's links are mutated.
        The same ``ContentFighterPsykerDisciplineAssignment`` row CAN be
        registered to multiple packs (see
        ``test_pack_item_in_multiple_packs``); this pack's editor must not
        delete or claim other packs' links.
        """
        if "psyker_disciplines" not in self.fields:
            return
        from django.contrib.contenttypes.models import ContentType

        from gyrinx.content.models.psyker import (
            ContentFighterPsykerDisciplineAssignment,
        )
        from gyrinx.core.models.pack import CustomContentPackItem

        if self._pack is None:
            return

        ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)

        # Assignments registered TO THIS PACK (via CustomContentPackItem with
        # pack=self._pack), keyed by discipline_id.
        pack_links = {
            link.object_id: link
            for link in CustomContentPackItem.objects.filter(
                pack=self._pack, content_type=ct, archived=False
            )
        }
        existing_assignments = {
            a.discipline_id: a
            for a in ContentFighterPsykerDisciplineAssignment.objects.all_content().filter(
                fighter=self.instance, pk__in=pack_links.keys()
            )
        }
        selected = set(self.cleaned_data.get("psyker_disciplines", []))
        selected_ids = {d.id for d in selected}

        # Uncheck → drop only THIS pack's link. Delete the assignment row
        # only if no other pack still references it.
        for disc_id, assignment in existing_assignments.items():
            if disc_id in selected_ids:
                continue
            link = pack_links.get(assignment.pk)
            if link is not None:
                link.delete()
            other_links_exist = CustomContentPackItem.objects.filter(
                content_type=ct, object_id=assignment.pk
            ).exists()
            if not other_links_exist:
                assignment.delete()

        # Add → reuse an existing assignment row (could already be registered
        # to a different pack) or create one; then ensure THIS pack has a link.
        for discipline in selected:
            if discipline.id in existing_assignments:
                continue
            assignment = (
                ContentFighterPsykerDisciplineAssignment.objects.all_content()
                .filter(fighter=self.instance, discipline=discipline)
                .first()
            )
            if assignment is None:
                assignment = ContentFighterPsykerDisciplineAssignment.objects.create(
                    fighter=self.instance, discipline=discipline
                )
            CustomContentPackItem.objects.get_or_create(
                pack=self._pack,
                content_type=ct,
                object_id=assignment.pk,
                defaults={"owner": self._pack.owner},
            )


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
            "description": rich_text_description_widget(),
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
            "description": rich_text_description_widget(),
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
            "description": rich_text_description_widget(),
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


class StandardFieldsMixin:
    """Exposes ``standard_fields`` for templates that render synthetic-field
    pickers alongside the regular ``Meta.fields`` (used by both the accessory
    mod picker and the equipment fighter-mod picker).
    """

    @property
    def standard_fields(self):
        """Iterate the bound fields for the regular ModelForm fields only."""
        for name in self.Meta.fields:
            yield self[name]


class ContentWeaponAccessoryPackForm(StandardFieldsMixin, forms.ModelForm):
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
            "description": rich_text_description_widget(),
            "cost": forms.NumberInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
        }

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
        _append_cost_propagation_help(self, "cost")

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
            "description": rich_text_description_widget(),
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


class ContentAttributePackForm(forms.ModelForm):
    """Form for adding/editing gang attributes in a content pack."""

    class Meta:
        model = ContentAttribute
        fields = ["name", "is_single_select", "restricted_to"]
        labels = {
            "name": "Name",
            "is_single_select": "Single-select",
            "restricted_to": "Restricted to houses",
        }
        help_texts = {
            "name": "The name of the attribute (e.g. 'Alignment', 'Alliance').",
            "is_single_select": "If checked, only one value can be selected. Otherwise multiple values are allowed.",
            "restricted_to": "If any houses are selected, the attribute is only available to lists in those houses. Leave empty to make it available to all houses.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "is_single_select": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "restricted_to": BsCheckboxSelectMultipleCompact(),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack
        if pack is not None:
            # Pack-aware so houses authored in this pack are selectable.
            self.fields["restricted_to"].queryset = ContentHouse.objects.with_packs(
                [pack]
            ).order_by("name")

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentAttribute.objects.all_content().filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "An attribute with this name already exists. "
                "Attribute names are unique across the library and all packs."
            )
        return value


class ContentAttributeValuePackForm(forms.ModelForm):
    """Form for adding/editing gang-attribute values in a content pack."""

    class Meta:
        model = ContentAttributeValue
        fields = ["name", "attribute", "description"]
        labels = {
            "name": "Name",
            "attribute": "Attribute",
            "description": "Description",
        }
        help_texts = {
            "name": "The value name (e.g. 'Law Abiding', 'Outlaw').",
            "attribute": "The attribute this value belongs to.",
            "description": "Optional description of what this value represents.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "attribute": forms.Select(attrs={"class": "form-select"}),
            "description": rich_text_description_widget(),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack
        if pack is not None:
            qs = ContentAttribute.objects.with_packs([pack])
        else:
            qs = ContentAttribute.objects.all()
        self.fields["attribute"].queryset = qs

        # Group choices into "Default" (base game) and "Custom" (pack content)
        if pack is not None:
            from gyrinx.core.models.pack import CustomContentPackItem

            pack_attr_ids = set(
                CustomContentPackItem.objects.filter(
                    pack=pack,
                    content_type__model="contentattribute",
                    archived=False,
                ).values_list("object_id", flat=True)
            )
            default_choices = []
            custom_choices = []
            for attr in qs.order_by("name"):
                choice = (attr.pk, str(attr))
                if attr.pk in pack_attr_ids:
                    custom_choices.append(choice)
                else:
                    default_choices.append(choice)
            grouped = [("", "---------")]
            if custom_choices:
                grouped.append(("Custom", custom_choices))
            if default_choices:
                grouped.append(("Default", default_choices))
            self.fields["attribute"].choices = grouped

    def clean_name(self):
        value = self.cleaned_data["name"]
        attribute = self.cleaned_data.get("attribute")
        if attribute:
            qs = ContentAttributeValue.objects.all_content().filter(
                name__iexact=value, attribute=attribute
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "A value with this name already exists for this attribute."
                )
        return value


class FighterModPickerMixin(StandardFieldsMixin):
    """Form mixin that exposes a fighter mod picker for ``ContentEquipment``.

    Adds synthetic fields that find-or-create ``ContentModFighterStat``,
    ``ContentModFighterRule`` and ``ContentModFighterSkill`` rows and attach
    them to ``instance.modifiers`` (matching the pattern used by
    ``ContentWeaponAccessoryPackForm`` for weapon stat/trait mods).

    Host form contract:
    - ``Meta.model`` must have a ``modifiers`` M2M to ``ContentMod``.
    - ``__init__`` accepts ``pack`` (forwarded by ``super().__init__``).

    The mixin overrides ``_save_m2m`` to call ``_save_fighter_mods`` itself,
    so consumers don't have to remember the wiring.
    """

    FIGHTER_STAT_MODE_CHOICES = [
        ("", "None"),
        ("improve", "Improve"),
        ("worsen", "Worsen"),
        ("set", "Set"),
    ]
    FIGHTER_MOD_MODE_CHOICES = [
        ("", "None"),
        ("add", "Add"),
        ("remove", "Remove"),
    ]

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack

        from gyrinx.content.models.statline import ContentStat

        # Only surface stats that belong to a fighter-side statline type
        # (Fighter / Vehicle / Crew). ``ContentStat`` is shared with weapon
        # profiles (ammo, AP, range, accuracy) — those have no meaning when
        # applied to a fighter and would just confuse the picker.
        self._fmod_stats = list(
            ContentStat.objects.filter(statline_type_stats__isnull=False)
            .distinct()
            .order_by("full_name")
        )
        for stat in self._fmod_stats:
            self.fields[f"fmod_stat_{stat.field_name}_mode"] = forms.ChoiceField(
                choices=self.FIGHTER_STAT_MODE_CHOICES,
                required=False,
                label=stat.full_name,
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
            )
            self.fields[f"fmod_stat_{stat.field_name}_value"] = forms.CharField(
                required=False,
                max_length=5,
                label=f"{stat.full_name} value",
                widget=forms.TextInput(
                    attrs={"class": "form-control form-control-sm", "size": "5"}
                ),
            )

        if pack is not None:
            rule_qs = ContentRule.objects.with_packs([pack])
            skill_qs = ContentSkill.objects.with_packs([pack])
        else:
            rule_qs = ContentRule.objects.all_content()
            skill_qs = ContentSkill.objects.all_content()
        self._fmod_rules = list(rule_qs.order_by("name"))
        self._fmod_skills = list(
            skill_qs.select_related("category").order_by("category__name", "name")
        )

        for rule in self._fmod_rules:
            self.fields[f"fmod_rule_{rule.pk}"] = forms.ChoiceField(
                choices=self.FIGHTER_MOD_MODE_CHOICES,
                required=False,
                label=str(rule),
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
            )
        for skill in self._fmod_skills:
            self.fields[f"fmod_skill_{skill.pk}"] = forms.ChoiceField(
                choices=self.FIGHTER_MOD_MODE_CHOICES,
                required=False,
                label=str(skill),
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
            )

        if self.instance.pk and not self.is_bound:
            self._populate_initial_fighter_mods()

    @property
    def fighter_stat_mod_rows(self):
        return [
            {
                "stat": stat,
                "label": stat.full_name,
                "mode_field": self[f"fmod_stat_{stat.field_name}_mode"],
                "value_field": self[f"fmod_stat_{stat.field_name}_value"],
            }
            for stat in self._fmod_stats
        ]

    @property
    def fighter_rule_mod_rows(self):
        return [
            {"rule": rule, "field": self[f"fmod_rule_{rule.pk}"]}
            for rule in self._fmod_rules
        ]

    @property
    def fighter_skill_mod_rows(self):
        return [
            {"skill": skill, "field": self[f"fmod_skill_{skill.pk}"]}
            for skill in self._fmod_skills
        ]

    @property
    def any_fighter_rule_mod_set(self):
        return any(self[f"fmod_rule_{rule.pk}"].value() for rule in self._fmod_rules)

    @property
    def any_fighter_skill_mod_set(self):
        return any(
            self[f"fmod_skill_{skill.pk}"].value() for skill in self._fmod_skills
        )

    @property
    def any_fighter_stat_mod_set(self):
        return any(
            self[f"fmod_stat_{stat.field_name}_mode"].value()
            for stat in self._fmod_stats
        )

    def _populate_initial_fighter_mods(self):
        from gyrinx.content.models.modifier import (
            ContentModFighterRule,
            ContentModFighterSkill,
            ContentModFighterStat,
        )

        for mod in self.instance.modifiers.all():
            if isinstance(mod, ContentModFighterStat):
                mode_key = f"fmod_stat_{mod.stat}_mode"
                value_key = f"fmod_stat_{mod.stat}_value"
                if mode_key in self.fields:
                    self.initial[mode_key] = mod.mode
                    self.initial[value_key] = mod.value
            elif isinstance(mod, ContentModFighterRule):
                key = f"fmod_rule_{mod.rule_id}"
                if key in self.fields:
                    self.initial[key] = mod.mode
            elif isinstance(mod, ContentModFighterSkill):
                key = f"fmod_skill_{mod.skill_id}"
                if key in self.fields:
                    self.initial[key] = mod.mode

    def clean(self):
        cleaned = super().clean()
        for stat in self._fmod_stats:
            mode_key = f"fmod_stat_{stat.field_name}_mode"
            value_key = f"fmod_stat_{stat.field_name}_value"
            mode = cleaned.get(mode_key)
            value = (cleaned.get(value_key) or "").strip()
            # Normalise so " 1 " and "1" dedupe in get_or_create.
            cleaned[value_key] = value
            if mode and not value:
                self.add_error(
                    value_key,
                    f"A value is required when a mode is selected for {stat.full_name}.",
                )
            elif value and not mode:
                self.add_error(
                    mode_key,
                    f"Choose a mode for the {stat.full_name} value, or clear the value.",
                )
            elif mode in {"improve", "worsen"} and value:
                # ContentModFighterStat.apply() does int(self.value) for
                # improve/worsen — reject non-integers up front.
                try:
                    int(value)
                except (TypeError, ValueError):
                    self.add_error(
                        value_key,
                        f"Enter an integer for {stat.full_name} when using {mode}.",
                    )
        return cleaned

    def _save_fighter_mods(self, instance):
        from gyrinx.content.models.modifier import (
            ContentModFighterRule,
            ContentModFighterSkill,
            ContentModFighterStat,
        )

        new_mods = []
        for stat in self._fmod_stats:
            mode = self.cleaned_data.get(f"fmod_stat_{stat.field_name}_mode")
            value = self.cleaned_data.get(f"fmod_stat_{stat.field_name}_value")
            if mode and value:
                mod, _ = ContentModFighterStat.objects.get_or_create(
                    stat=stat.field_name, mode=mode, value=value
                )
                new_mods.append(mod)
        for rule in self._fmod_rules:
            mode = self.cleaned_data.get(f"fmod_rule_{rule.pk}")
            if mode:
                mod, _ = ContentModFighterRule.objects.get_or_create(
                    rule=rule, mode=mode
                )
                new_mods.append(mod)
        for skill in self._fmod_skills:
            mode = self.cleaned_data.get(f"fmod_skill_{skill.pk}")
            if mode:
                mod, _ = ContentModFighterSkill.objects.get_or_create(
                    skill=skill, mode=mode
                )
                new_mods.append(mod)

        # Preserve any existing mods this picker doesn't manage (e.g. skill-tree
        # or psyker-discipline access mods set via admin on library equipment).
        managed = (
            ContentModFighterStat,
            ContentModFighterRule,
            ContentModFighterSkill,
        )
        preserved = [m for m in instance.modifiers.all() if not isinstance(m, managed)]
        instance.modifiers.set([*preserved, *new_mods])

    def _save_m2m(self):
        super()._save_m2m()
        self._save_fighter_mods(self.instance)


class EquipmentModifiersForm(FighterModPickerMixin, forms.ModelForm):
    """Form for the Modifiers tab on a pack-defined gear/weapon edit page.

    Carries no detail fields itself — those live on the Details tab via
    ``ContentGearPackForm`` / ``ContentWeaponPackForm``. This form only
    exposes the synthetic fighter-mod picker fields (stat / rule / skill)
    and writes them to ``instance.modifiers``.
    """

    class Meta:
        model = ContentEquipment
        fields = []


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
            "description": rich_text_description_widget(),
            "category": forms.Select(attrs={"class": "form-select"}),
            "cost": forms.TextInput(attrs={"class": "form-control"}),
            "rarity": forms.Select(attrs={"class": "form-select"}),
            "rarity_roll": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _append_cost_propagation_help(self, "cost")

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
        _append_cost_propagation_help(self, "cost")

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
        _append_cost_propagation_help(self, "cost")
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


class ContentPsykerDisciplinePackForm(forms.ModelForm):
    """Form for adding/editing psyker disciplines in a content pack."""

    class Meta:
        model = ContentPsykerDiscipline
        fields = ["name", "generic", "description"]
        labels = {
            "name": "Name",
            "generic": "Available to all psykers?",
            "description": "Description",
        }
        help_texts = {
            "name": "The name of the discipline (e.g. 'Biomancy').",
            "generic": (
                "If checked, any psyker fighter can use powers from this "
                "discipline. Unchecked disciplines must be explicitly assigned "
                "to fighters."
            ),
            "description": "Optional flavour text or rules summary.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "generic": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "description": rich_text_description_widget(),
        }

    def clean_name(self):
        value = self.cleaned_data["name"]
        qs = ContentPsykerDiscipline.objects.all_content().filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A psyker discipline with this name already exists in the content "
                "library."
            )
        return value


class ContentPsykerPowerPackForm(forms.ModelForm):
    """Form for adding/editing psyker powers in a content pack."""

    class Meta:
        model = ContentPsykerPower
        fields = ["name", "discipline", "description"]
        labels = {
            "name": "Name",
            "discipline": "Discipline",
            "description": "Description",
        }
        help_texts = {
            "name": "The name of the power (e.g. 'Mind Bolt').",
            "discipline": "The discipline this power belongs to.",
            "description": "Optional flavour text or rules for this power.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "discipline": forms.Select(attrs={"class": "form-select"}),
            "description": rich_text_description_widget(),
        }

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pack = pack
        if pack is not None:
            qs = ContentPsykerDiscipline.objects.with_packs([pack])
        else:
            qs = ContentPsykerDiscipline.objects.all()
        self.fields["discipline"].queryset = qs

        # Group choices into "Custom" (pack content) and "Default" (base game).
        if pack is not None:
            from gyrinx.core.models.pack import CustomContentPackItem

            pack_disc_ids = set(
                CustomContentPackItem.objects.filter(
                    pack=pack,
                    content_type__model="contentpsykerdiscipline",
                    archived=False,
                ).values_list("object_id", flat=True)
            )
            default_choices = []
            custom_choices = []
            for disc in qs.order_by("name"):
                choice = (disc.pk, str(disc))
                if disc.pk in pack_disc_ids:
                    custom_choices.append(choice)
                else:
                    default_choices.append(choice)
            grouped = [("", "---------")]
            if custom_choices:
                grouped.append(("Custom", custom_choices))
            if default_choices:
                grouped.append(("Default", default_choices))
            self.fields["discipline"].choices = grouped

    def clean_name(self):
        value = self.cleaned_data["name"]
        discipline = self.cleaned_data.get("discipline")
        if discipline:
            qs = ContentPsykerPower.objects.all_content().filter(
                name__iexact=value, discipline=discipline
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "A psyker power with this name already exists in this discipline."
                )
        return value


# House-rule mod target choices. These map to the slug used in URLs and to
# the ContentType being targeted.
HOUSE_RULE_TARGET_CHOICES = [
    ("weapon-profile", "Weapons"),
    ("fighter", "Fighters & Vehicles"),
]


VALID_MOD_KINDS = ("stat", "trait", "rule")

# Kind choices scoped per target type, in display order. These also determine
# the order the kind picker is rendered in the template.
WEAPON_MOD_KIND_CHOICES = [
    ("stat", "Stat"),
    ("trait", "Trait"),
]
FIGHTER_MOD_KIND_CHOICES = [
    ("stat", "Stat"),
    ("rule", "Special rule"),
]


def mod_kind_choices_for(target_type):
    if target_type == "fighter":
        return FIGHTER_MOD_KIND_CHOICES
    return WEAPON_MOD_KIND_CHOICES


def kind_valid_for_target(mod_kind, target_type):
    """Return True if ``mod_kind`` is a legal pairing with ``target_type``."""
    return mod_kind in {k for k, _ in mod_kind_choices_for(target_type)}


class ContentHouseRuleForm(forms.Form):
    """House-rule definition for ONE specific ``mod_kind``.

    The kind (stat / trait / rule) is **not** a form field — it's a URL
    parameter passed in via the ``mod_kind`` constructor kwarg. The form
    only renders fields relevant to that kind:

    - ``stat`` → ``stat`` + ``mode`` + ``value``
    - ``trait`` → ``trait`` + ``mode``
    - ``rule`` → ``rule`` + ``mode``

    Switching kind is a URL navigation handled by the view, not an in-form
    state change — see ``add_house_rule`` / ``edit_house_rule`` and the
    server-rendered kind picker in ``house_rule_form.html``.

    On valid POST the view creates the matching ``ContentMod`` subclass:
    ``ContentModStat`` / ``ContentModFighterStat`` for ``stat``,
    ``ContentModTrait`` for ``trait``, ``ContentModFighterRule`` for
    ``rule`` — then wraps it in a ``ContentModApplication`` and links to
    the pack via ``CustomContentPackItem``, all in one transaction.
    """

    STAT_MODE_CHOICES = [
        ("improve", "Improve"),
        ("worsen", "Worsen"),
        ("set", "Set"),
    ]
    ADD_REMOVE_MODE_CHOICES = [
        ("add", "Add"),
        ("remove", "Remove"),
    ]

    # Weapon stat choices match ContentModStat.stat
    WEAPON_STAT_CHOICES = [
        ("strength", "Strength"),
        ("range_short", "Range (Short)"),
        ("range_long", "Range (Long)"),
        ("accuracy_short", "Accuracy (Short)"),
        ("accuracy_long", "Accuracy (Long)"),
        ("armour_piercing", "Armour Piercing"),
        ("damage", "Damage"),
        ("ammo", "Ammo"),
    ]

    target_type = forms.ChoiceField(
        choices=HOUSE_RULE_TARGET_CHOICES,
        widget=forms.HiddenInput(),
    )
    target_id = forms.UUIDField(
        widget=forms.HiddenInput(),
        required=True,
    )

    stat = forms.ChoiceField(
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="The statistic to modify.",
    )
    mode = forms.ChoiceField(
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="How to apply the change.",
    )
    value = forms.CharField(
        max_length=5,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="A number, e.g. 1.",
    )

    trait = forms.ModelChoiceField(
        queryset=ContentWeaponTrait.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="The trait to add or remove on the weapon profile.",
    )
    rule = forms.ModelChoiceField(
        queryset=ContentRule.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="The special rule to add or remove on the fighter.",
    )

    def __init__(
        self,
        *args,
        mod_kind,
        target_type,
        available_stat_field_names=None,
        pack=None,
        **kwargs,
    ):
        if mod_kind not in VALID_MOD_KINDS:
            raise ValueError(f"Unknown mod_kind: {mod_kind!r}")
        if not kind_valid_for_target(mod_kind, target_type):
            raise ValueError(
                f"mod_kind={mod_kind!r} is not valid for target_type={target_type!r}"
            )
        if pack is None:
            raise TypeError("ContentHouseRuleForm requires a pack= keyword argument.")

        super().__init__(*args, **kwargs)
        self.mod_kind = mod_kind
        self._target_type = target_type
        self._available_stat_field_names = (
            set(available_stat_field_names)
            if available_stat_field_names is not None
            else None
        )

        # Remove the fields that don't belong to this kind. Hidden target
        # fields are always kept; per-kind groups are pruned.
        keep = {"target_type", "target_id", "mode"}
        if mod_kind == "stat":
            keep |= {"stat", "value"}
        elif mod_kind == "trait":
            keep |= {"trait"}
        elif mod_kind == "rule":
            keep |= {"rule"}
        for name in list(self.fields):
            if name not in keep:
                del self.fields[name]

        # Per-kind configuration.
        if mod_kind == "stat":
            self.fields["mode"].choices = self.STAT_MODE_CHOICES
            self.fields["stat"].choices = self._stat_choices_for_target()
        else:
            self.fields["mode"].choices = self.ADD_REMOVE_MODE_CHOICES
            if mod_kind == "trait":
                self.fields["trait"].queryset = ContentWeaponTrait.objects.with_packs(
                    [pack]
                ).order_by("name")
            elif mod_kind == "rule":
                self.fields["rule"].queryset = ContentRule.objects.with_packs(
                    [pack]
                ).order_by("name")

    def _stat_choices_for_target(self):
        """Compute the stat dropdown choices for the form's target type."""
        from gyrinx.content.models.statline import ContentStat

        if self._target_type == "weapon-profile":
            choices = list(self.WEAPON_STAT_CHOICES)
        else:
            weapon_only = {fc for fc, _ in self.WEAPON_STAT_CHOICES} - {"strength"}
            choices = [
                (s.field_name, s.full_name)
                for s in ContentStat.objects.exclude(
                    field_name__in=weapon_only
                ).order_by("full_name")
            ]
        if self._available_stat_field_names is not None:
            choices = [c for c in choices if c[0] in self._available_stat_field_names]
        return choices

    def clean(self):
        cleaned = super().clean()
        # The view already validated target_type / mod_kind against the URL,
        # but defend against tampered hidden inputs here too.
        if cleaned.get("target_type") != self._target_type:
            self.add_error(
                "target_type", "Target type doesn't match the URL — start again."
            )

        if self.mod_kind == "stat":
            value = cleaned.get("value")
            mode = cleaned.get("mode")
            stat = cleaned.get("stat")
            if (
                stat
                and self._available_stat_field_names is not None
                and stat not in self._available_stat_field_names
            ):
                self.add_error("stat", "That stat isn't on this target's statline.")

            # For improve/worsen modes, value must be an integer (the modifier
            # operates numerically). 'set' allows non-numeric values (e.g. "S").
            if mode in ("improve", "worsen") and value:
                try:
                    int(value)
                except (TypeError, ValueError):
                    self.add_error(
                        "value",
                        "Value must be a whole number when improving or worsening a stat.",
                    )
        return cleaned
