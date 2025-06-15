from django import forms

from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
    CampaignResourceType,
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
            "public": "If checked, this campaign will be visible to all users of Gyrinx. You can edit this later.",
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
        fields = ["list", "description", "dice_count"]
        labels = {
            "list": "Related Gang (Optional)",
            "description": "Action Description",
            "dice_count": "Number of D6 Dice",
        }
        help_texts = {
            "list": "Select the gang this action is related to (if applicable)",
            "description": "Describe the action being taken",
            "dice_count": "How many D6 dice to roll. Leave at 0 for no roll.",
        }
        widgets = {
            "list": forms.Select(attrs={"class": "form-select"}),
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

            # Make the field not required
            self.fields["list"].required = False


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
        fields = ["name", "summary", "narrative", "public", "budget"]
        labels = {
            "name": "Name",
            "summary": "Summary",
            "narrative": "Narrative",
            "public": "Public",
            "budget": "Starting Budget",
        }
        help_texts = {
            "name": "The name you use to identify this campaign. This may be public.",
            "summary": "A short summary of the campaign (300 characters max). This will be displayed on the campaign list page.",
            "narrative": "A longer narrative description of the campaign. This will be displayed on the campaign detail page.",
            "public": "If checked, this campaign will be visible to all users.",
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


class CampaignAssetTypeForm(forms.ModelForm):
    """Form for creating and editing campaign asset types"""

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


class CampaignAssetForm(forms.ModelForm):
    """Form for creating and editing campaign assets"""

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
        asset_type = kwargs.pop("asset_type", None)
        super().__init__(*args, **kwargs)

        # Limit holder choices to lists in the campaign
        if asset_type:
            self.fields["holder"].queryset = asset_type.campaign.lists.all()
        elif self.instance and self.instance.pk:
            self.fields[
                "holder"
            ].queryset = self.instance.asset_type.campaign.lists.all()


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
