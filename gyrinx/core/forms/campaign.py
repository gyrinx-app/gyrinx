import json

from django import forms

from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
    CampaignResourceType,
    CampaignSubAsset,
)
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, TinyMCEWithUpload


class NewCampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "summary", "narrative", "public", "budget"]
        labels = {
            "name": "Name",
            "summary": "Summary",
            "narrative": "Narrative",
            "public": "Public",
            "budget": "Starting Budget",
        }
        help_texts = {
            "name": "The name you use to identify this Campaign. This may be public.",
            "summary": "A short summary of the campaign (300 characters max). This will be displayed on the campaign list page.",
            "narrative": "A longer narrative description of the campaign. This will be displayed on the campaign detail page.",
            "public": "If checked, this campaign will be visible to all users of Gyrinx. If unchecked, it will be unlisted. You can edit this later.",
            "budget": "Starting budget for each gang in credits.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "summary": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 5},
                mce_attrs={"height": "150px", **TINYMCE_EXTRA_ATTRS},
            ),
            "narrative": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "budget": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }


class CampaignActionForm(forms.ModelForm):
    """Form for creating campaign actions with optional dice rolls"""

    class Meta:
        model = CampaignAction
        fields = ["list", "battle", "description", "dice_count"]
        labels = {
            "list": "Related Gang (Optional)",
            "battle": "Related Battle (Optional)",
            "description": "Action Description",
            "dice_count": "Number of D6 Dice",
        }
        help_texts = {
            "list": "Select the gang this action is related to (if applicable)",
            "battle": "Select the battle this action is related to (if applicable)",
            "description": "Describe the action being taken",
            "dice_count": "How many D6 dice to roll. Leave at 0 for no roll.",
        }
        widgets = {
            "list": forms.Select(attrs={"class": "form-select"}),
            "battle": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Rolling for lasting injuries",
                }
            ),
            "dice_count": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 20, "value": 0}
            ),
        }

    def __init__(self, *args, **kwargs):
        campaign = kwargs.pop("campaign", None)
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if campaign:
            # Filter lists to only show those in the campaign that the user owns
            if user:
                self.fields["list"].queryset = campaign.lists.filter(owner=user)
            else:
                self.fields["list"].queryset = campaign.lists.all()

            # Filter battles to only show those in the campaign
            self.fields["battle"].queryset = campaign.battles.order_by(
                "-date", "-created"
            )

            # Make the fields not required
            self.fields["list"].required = False
            self.fields["battle"].required = False


class CampaignActionOutcomeForm(forms.ModelForm):
    """Form for editing the outcome of a campaign action"""

    class Meta:
        model = CampaignAction
        fields = ["outcome"]
        labels = {
            "outcome": "Action Outcome",
        }
        help_texts = {
            "outcome": "Describe the result of the action",
        }
        widgets = {
            "outcome": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Memorable Death",
                }
            ),
        }


class EditCampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = [
            "name",
            "summary",
            "narrative",
            "public",
            "budget",
            "phase",
            "phase_notes",
        ]
        labels = {
            "name": "Name",
            "summary": "Summary",
            "narrative": "Narrative",
            "public": "Public",
            "budget": "Starting Budget",
            "phase": "Phase",
            "phase_notes": "Phase Notes",
        }
        help_texts = {
            "name": "The name you use to identify this campaign. This may be public.",
            "summary": "A short summary of the campaign (300 characters max). This will be displayed on the campaign list page.",
            "narrative": "A longer narrative description of the campaign. This will be displayed on the campaign detail page.",
            "public": "If checked, this campaign will be visible to all users.",
            "budget": "Starting budget for each gang in credits.",
            "phase": "Current campaign phase (e.g., 'Occupation', 'Takeover', 'Dominion')",
            "phase_notes": "Notes about the current phase - special rules, conditions, etc.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "summary": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 5},
                mce_attrs={"height": "150px", **TINYMCE_EXTRA_ATTRS},
            ),
            "narrative": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "budget": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "phase": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., Occupation"}
            ),
            "phase_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self._old_phase = None
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self._old_phase = self.instance.phase

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)

        # Track phase change for logging
        new_phase = self.cleaned_data.get("phase", "")
        phase_changed = self._old_phase != new_phase

        if commit:
            instance.save()

            # Log phase change if it changed and user is provided
            if phase_changed and user:
                from gyrinx.core.models.campaign import CampaignAction

                if self._old_phase and new_phase:
                    description = f"Phase Change: {self._old_phase} → {new_phase}"
                elif new_phase:
                    description = f"Phase Set: {new_phase}"
                else:
                    description = f"Phase Cleared (was: {self._old_phase})"

                CampaignAction.objects.create(
                    campaign=instance,
                    user=user,
                    description=description,
                    owner=user,
                )

        return instance


class CampaignAssetTypeForm(forms.ModelForm):
    """Form for creating and editing campaign asset types"""

    # Hidden field to store the property schema JSON
    property_schema_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "property-schema-json"}),
    )

    # Hidden field to store the sub-asset schema JSON
    sub_asset_schema_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "sub-asset-schema-json"}),
    )

    class Meta:
        model = CampaignAssetType
        fields = ["name_singular", "name_plural", "description"]
        labels = {
            "name_singular": "Name (Singular)",
            "name_plural": "Name (Plural)",
            "description": "Description",
        }
        help_texts = {
            "name_singular": "Singular form of the asset type (e.g., 'Territory')",
            "name_plural": "Plural form of the asset type (e.g., 'Territories')",
            "description": "Describe what this type of asset represents in your campaign",
        }
        widgets = {
            "name_singular": forms.TextInput(attrs={"class": "form-control"}),
            "name_plural": forms.TextInput(attrs={"class": "form-control"}),
            "description": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 10}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
        }

    def __init__(self, *args, **kwargs):
        self.campaign = kwargs.pop("campaign", None)
        super().__init__(*args, **kwargs)
        # Set initial value for the hidden JSON fields
        if self.instance and self.instance.pk:
            self.fields["property_schema_json"].initial = json.dumps(
                self.instance.property_schema or []
            )
            self.fields["sub_asset_schema_json"].initial = json.dumps(
                self.instance.sub_asset_schema or {}
            )
        else:
            self.fields["property_schema_json"].initial = "[]"
            self.fields["sub_asset_schema_json"].initial = "{}"

    def clean_property_schema_json(self):
        """Validate and parse the property schema JSON"""
        data = self.cleaned_data.get("property_schema_json", "[]")
        if not data:
            return []
        try:
            schema = json.loads(data)
            if not isinstance(schema, list):
                raise forms.ValidationError("Property schema must be a list")
            # Validate each item has required fields
            keys = []
            for item in schema:
                if not isinstance(item, dict):
                    raise forms.ValidationError("Each property must be an object")
                if "key" not in item or "label" not in item:
                    raise forms.ValidationError(
                        "Each property must have 'key' and 'label' fields"
                    )
                keys.append(item["key"])
            # Check for duplicate keys
            if len(keys) != len(set(keys)):
                raise forms.ValidationError("Property keys must be unique")
            return schema
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f"Invalid JSON: {e}")

    def clean_sub_asset_schema_json(self):
        """Validate and parse the sub-asset schema JSON"""
        data = self.cleaned_data.get("sub_asset_schema_json", "{}")
        if not data:
            return {}
        try:
            schema = json.loads(data)
            if not isinstance(schema, dict):
                raise forms.ValidationError("Sub-asset schema must be an object")

            # Validate each sub-asset type definition
            for key, definition in schema.items():
                if not isinstance(definition, dict):
                    raise forms.ValidationError(
                        f"Definition for '{key}' must be an object"
                    )
                if "label" not in definition:
                    raise forms.ValidationError(
                        f"Definition for '{key}' must have a 'label'"
                    )

                # Validate property schema if present
                if "property_schema" in definition:
                    prop_schema = definition["property_schema"]
                    if not isinstance(prop_schema, list):
                        raise forms.ValidationError(
                            f"property_schema for '{key}' must be a list"
                        )
                    for item in prop_schema:
                        if not isinstance(item, dict):
                            raise forms.ValidationError(
                                f"Each property in '{key}' must be an object"
                            )
                        if "key" not in item or "label" not in item:
                            raise forms.ValidationError(
                                f"Each property in '{key}' must have 'key' and 'label' fields"
                            )

            return schema
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f"Invalid JSON: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.property_schema = self.cleaned_data.get("property_schema_json", [])
        instance.sub_asset_schema = self.cleaned_data.get("sub_asset_schema_json", {})
        if commit:
            instance.save()
        return instance

    def clean_name_singular(self):
        """Validate that name_singular is unique for this campaign, excluding the current instance"""
        name_singular = self.cleaned_data.get("name_singular")

        # Determine which campaign to check against
        campaign = None
        if self.campaign:
            # Campaign passed in during form creation (for new asset types)
            campaign = self.campaign
        elif self.instance and self.instance.campaign_id:
            # Campaign from existing instance (for editing)
            campaign = self.instance.campaign

        if name_singular and campaign:
            # Check for duplicate name_singular in the same campaign
            existing = CampaignAssetType.objects.filter(
                campaign=campaign, name_singular=name_singular
            )
            # Exclude the current instance if it's being updated
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)

            if existing.exists():
                raise forms.ValidationError(
                    f"An asset type with the name '{name_singular}' already exists in this campaign."
                )
        return name_singular


class CampaignAssetForm(forms.ModelForm):
    """Form for creating and editing campaign assets"""

    # Hidden field for ad-hoc properties JSON (properties not in schema)
    extra_properties_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "extra-properties-json"}),
    )

    class Meta:
        model = CampaignAsset
        fields = ["name", "description", "holder"]
        labels = {
            "name": "Asset Name",
            "description": "Description",
            "holder": "Current Holder",
        }
        help_texts = {
            "name": "Name of this specific asset (e.g., 'The Sump')",
            "description": "Describe this asset - its benefits, location, or any special rules",
            "holder": "The list currently holding this asset (leave blank if unowned)",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 10}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "holder": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        self.asset_type = kwargs.pop("asset_type", None)
        campaign = kwargs.pop("campaign", None)
        super().__init__(*args, **kwargs)

        # Get asset_type from instance if not provided
        if not self.asset_type and self.instance and self.instance.pk:
            self.asset_type = self.instance.asset_type

        # Get campaign from asset_type if not provided
        if not campaign and self.asset_type:
            campaign = self.asset_type.campaign
        elif not campaign and self.instance and self.instance.pk:
            campaign = self.instance.asset_type.campaign

        # Hide holder field if campaign is not in progress
        if campaign and not campaign.is_in_progress:
            if "holder" in self.fields:
                del self.fields["holder"]
        else:
            # Limit holder choices to lists in the campaign
            if self.asset_type:
                self.fields["holder"].queryset = self.asset_type.campaign.lists.all()
            elif self.instance and self.instance.pk:
                self.fields[
                    "holder"
                ].queryset = self.instance.asset_type.campaign.lists.all()

        # Get existing properties from instance
        existing_properties = {}
        if self.instance and self.instance.pk:
            existing_properties = self.instance.properties or {}

        # Add dynamic fields based on property schema
        self.schema_keys = []
        if self.asset_type and self.asset_type.property_schema:
            for prop in self.asset_type.property_schema:
                key = prop.get("key", "")
                label = prop.get("label", key)
                description = prop.get("description", "")
                if key:
                    self.schema_keys.append(key)
                    field_name = f"prop_{key}"
                    self.fields[field_name] = forms.CharField(
                        required=False,
                        label=label,
                        help_text=description,
                        widget=forms.TextInput(attrs={"class": "form-control"}),
                        initial=existing_properties.get(key, ""),
                    )

        # Collect extra properties (those not in schema) for the hidden field
        extra_props = {
            k: v for k, v in existing_properties.items() if k not in self.schema_keys
        }
        self.fields["extra_properties_json"].initial = json.dumps(extra_props)

    def clean_extra_properties_json(self):
        """Parse extra properties JSON"""
        data = self.cleaned_data.get("extra_properties_json", "{}")
        if not data:
            return {}
        try:
            props = json.loads(data)
            if not isinstance(props, dict):
                raise forms.ValidationError("Extra properties must be an object")
            return props
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f"Invalid JSON: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Collect all properties
        properties = {}

        # Add schema-based properties
        for key in self.schema_keys:
            field_name = f"prop_{key}"
            value = self.cleaned_data.get(field_name, "")
            if value:  # Only store non-empty values
                properties[key] = value

        # Add extra properties
        extra_props = self.cleaned_data.get("extra_properties_json", {})
        properties.update(extra_props)

        instance.properties = properties

        if commit:
            instance.save()
        return instance


class AssetTransferForm(forms.Form):
    """Form for transferring an asset to a new holder"""

    new_holder = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="New Holder",
        help_text="Select the gang to transfer this asset to (or leave blank to make it unowned)",
        widget=forms.Select(attrs={"class": "form-select"}),
        empty_label="No one (unowned)",
    )

    def __init__(self, *args, **kwargs):
        asset = kwargs.pop("asset")
        super().__init__(*args, **kwargs)

        # Set queryset to lists in the campaign, excluding current holder
        campaign_lists = asset.asset_type.campaign.lists.all()
        if asset.holder:
            campaign_lists = campaign_lists.exclude(pk=asset.holder.pk)
        self.fields["new_holder"].queryset = campaign_lists


class CampaignSubAssetForm(forms.ModelForm):
    """Form for creating and editing campaign sub-assets"""

    class Meta:
        model = CampaignSubAsset
        fields = ["name"]
        labels = {
            "name": "Name",
        }
        help_texts = {
            "name": "Name of this sub-asset",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.parent_asset = kwargs.pop("parent_asset", None)
        self.sub_asset_type_key = kwargs.pop("sub_asset_type", None)
        super().__init__(*args, **kwargs)

        # Get parent asset from instance if not provided
        if not self.parent_asset and self.instance and self.instance.pk:
            self.parent_asset = self.instance.parent_asset

        # Get sub_asset_type from instance if not provided
        if not self.sub_asset_type_key and self.instance and self.instance.pk:
            self.sub_asset_type_key = self.instance.sub_asset_type

        # Get existing properties from instance
        existing_properties = {}
        if self.instance and self.instance.pk:
            existing_properties = self.instance.properties or {}

        # Add dynamic fields based on property schema
        self.schema_keys = []
        if self.parent_asset and self.sub_asset_type_key:
            asset_type = self.parent_asset.asset_type
            sub_asset_schemas = asset_type.sub_asset_schema or {}
            schema_def = sub_asset_schemas.get(self.sub_asset_type_key, {})
            property_schema = schema_def.get("property_schema", [])

            for prop in property_schema:
                key = prop.get("key", "")
                label = prop.get("label", key)
                description = prop.get("description", "")
                if key:
                    self.schema_keys.append(key)
                    field_name = f"prop_{key}"
                    self.fields[field_name] = forms.CharField(
                        required=False,
                        label=label,
                        help_text=description,
                        widget=forms.TextInput(attrs={"class": "form-control"}),
                        initial=existing_properties.get(key, ""),
                    )

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Set sub_asset_type if provided
        if self.sub_asset_type_key and not instance.sub_asset_type:
            instance.sub_asset_type = self.sub_asset_type_key

        # Build properties dict from schema fields
        properties = {}
        for key in self.schema_keys:
            field_name = f"prop_{key}"
            value = self.cleaned_data.get(field_name, "")
            if value:
                properties[key] = value

        instance.properties = properties

        if commit:
            instance.save()
        return instance


class CampaignResourceTypeForm(forms.ModelForm):
    """Form for creating and editing campaign resource types"""

    class Meta:
        model = CampaignResourceType
        fields = ["name", "description", "default_amount"]
        labels = {
            "name": "Resource Name",
            "description": "Description",
            "default_amount": "Default Amount",
        }
        help_texts = {
            "name": "Name of the resource (e.g., 'Meat', 'Credits', 'Ammo')",
            "description": "Describe what this resource represents and how it's used",
            "default_amount": "Amount given to each gang when the campaign starts",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 10}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "default_amount": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
        }


class ResourceModifyForm(forms.Form):
    """Form for modifying a list's resource amount"""

    modification = forms.IntegerField(
        label="Amount to Modify",
        help_text="Enter a positive number to add or negative to subtract",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        self.resource = kwargs.pop("resource")
        super().__init__(*args, **kwargs)

    def clean_modification(self):
        modification = self.cleaned_data["modification"]
        new_amount = self.resource.amount + modification

        if new_amount < 0:
            raise forms.ValidationError(
                f"Cannot reduce {self.resource.resource_type.name} below zero. "
                f"Current amount: {self.resource.amount}, "
                f"Attempted change: {modification}"
            )

        return modification


class CampaignCopyFromForm(forms.Form):
    """Form for copying content from another campaign"""

    source_campaign = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label="Source Campaign",
        help_text="Select the campaign to copy assets and resources from",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    asset_types = forms.MultipleChoiceField(
        required=False,
        label="Asset Types",
        help_text="Select which asset types to copy. Sub-assets will also be copied.",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    resource_types = forms.MultipleChoiceField(
        required=False,
        label="Resource Types",
        help_text="Select which resource types to copy",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        self.target_campaign = kwargs.pop("target_campaign")
        self.user = kwargs.pop("user")
        self.source_campaign_obj = kwargs.pop("source_campaign_obj", None)
        super().__init__(*args, **kwargs)

        # Build grouped choices for source campaign
        self._build_source_campaign_choices()

        # If source campaign is provided, populate asset/resource type choices
        if self.source_campaign_obj:
            self._populate_type_choices(self.source_campaign_obj)
        else:
            # Hide type selection until source is selected
            self.fields["asset_types"].choices = []
            self.fields["resource_types"].choices = []

    def _build_source_campaign_choices(self):
        """Build grouped choices for source campaign dropdown."""
        choices = [("", "---------")]

        # Get template campaigns (excluding target)
        templates = (
            Campaign.objects.filter(template=True)
            .exclude(pk=self.target_campaign.pk)
            .order_by("name")
        )
        if templates.exists():
            template_choices = [(str(c.pk), c.name) for c in templates]
            choices.append(("Templates", template_choices))

        # Get user's campaigns grouped by status (excluding target)
        user_campaigns = (
            Campaign.objects.filter(owner=self.user)
            .exclude(pk=self.target_campaign.pk)
            .exclude(template=True)  # Don't duplicate templates
            .order_by("name")
        )

        # Group by status
        status_groups = {}
        for campaign in user_campaigns:
            status_label = campaign.get_status_display()
            if status_label not in status_groups:
                status_groups[status_label] = []
            status_groups[status_label].append((str(campaign.pk), campaign.name))

        # Add status groups in a sensible order
        status_order = ["In Progress", "Pre-Campaign", "Post-Campaign"]
        for status_label in status_order:
            if status_label in status_groups:
                choices.append((status_label, status_groups[status_label]))

        # Set as choices (not queryset) for grouped display
        self.fields["source_campaign"].choices = choices
        self.fields["source_campaign"].queryset = Campaign.objects.all()

    def _populate_type_choices(self, source_campaign):
        """Populate asset and resource type choices from source campaign."""
        self.fields["asset_types"].choices = [
            (str(at.id), f"{at.name_plural} ({at.assets.count()} assets)")
            for at in source_campaign.asset_types.all()
        ]
        self.fields["resource_types"].choices = [
            (str(rt.id), rt.name) for rt in source_campaign.resource_types.all()
        ]

    def clean(self):
        cleaned_data = super().clean()
        asset_types = cleaned_data.get("asset_types", [])
        resource_types = cleaned_data.get("resource_types", [])

        if not asset_types and not resource_types:
            raise forms.ValidationError(
                "Please select at least one asset type or resource type to copy."
            )

        return cleaned_data


class CampaignCopyToForm(forms.Form):
    """Form for copying content to another campaign"""

    target_campaign = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label="Target Campaign",
        help_text="Select the campaign to copy assets and resources to",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    asset_types = forms.MultipleChoiceField(
        required=False,
        label="Asset Types",
        help_text="Select which asset types to copy. Sub-assets will also be copied.",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    resource_types = forms.MultipleChoiceField(
        required=False,
        label="Resource Types",
        help_text="Select which resource types to copy",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        self.source_campaign = kwargs.pop("source_campaign")
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        # Build grouped choices for target campaign
        self._build_target_campaign_choices()

        # Populate asset and resource type choices from source campaign
        self.fields["asset_types"].choices = [
            (str(at.id), f"{at.name_plural} ({at.assets.count()} assets)")
            for at in self.source_campaign.asset_types.all()
        ]
        self.fields["resource_types"].choices = [
            (str(rt.id), rt.name) for rt in self.source_campaign.resource_types.all()
        ]

    def _build_target_campaign_choices(self):
        """Build grouped choices for target campaign dropdown."""
        choices = [("", "---------")]

        # Get user's campaigns grouped by status (excluding source)
        user_campaigns = (
            Campaign.objects.filter(owner=self.user)
            .exclude(pk=self.source_campaign.pk)
            .order_by("name")
        )

        # Group by status
        status_groups = {}
        for campaign in user_campaigns:
            status_label = campaign.get_status_display()
            if status_label not in status_groups:
                status_groups[status_label] = []
            status_groups[status_label].append((str(campaign.pk), campaign.name))

        # Add status groups in a sensible order
        status_order = ["In Progress", "Pre-Campaign", "Post-Campaign"]
        for status_label in status_order:
            if status_label in status_groups:
                choices.append((status_label, status_groups[status_label]))

        # Set as choices (not queryset) for grouped display
        self.fields["target_campaign"].choices = choices
        self.fields["target_campaign"].queryset = Campaign.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        asset_types = cleaned_data.get("asset_types", [])
        resource_types = cleaned_data.get("resource_types", [])

        if not asset_types and not resource_types:
            raise forms.ValidationError(
                "Please select at least one asset type or resource type to copy."
            )

        return cleaned_data
