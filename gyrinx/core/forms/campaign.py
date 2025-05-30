from django import forms
from tinymce.widgets import TinyMCE

from gyrinx.core.models.campaign import Campaign, CampaignAction


# TinyMCE configuration shared between forms
TINYMCE_CONFIG = {
    "relative_urls": False,
    "promotion": False,
    "resize": "both",
    "width": "100%",
    "height": "400px",
    "plugins": "autoresize autosave code emoticons fullscreen help link lists quickbars textpattern visualblocks",
    "toolbar": "undo redo | blocks | bold italic underline link | numlist bullist align | code",
    "menubar": "edit view insert format table tools help",
    "menu": {
        "edit": {
            "title": "Edit",
            "items": "undo redo | cut copy paste pastetext | selectall | searchreplace",
        },
        "view": {
            "title": "View",
            "items": "code revisionhistory | visualaid visualchars visualblocks | spellchecker | preview fullscreen | showcomments",
        },
        "insert": {
            "title": "Insert",
            "items": "image link media addcomment pageembed codesample inserttable | math | charmap emoticons hr | pagebreak nonbreaking anchor tableofcontents | insertdatetime",
        },
        "format": {
            "title": "Format",
            "items": "bold italic underline strikethrough superscript subscript codeformat | styles blocks fontfamily fontsize align lineheight | forecolor backcolor | language | removeformat",
        },
        "tools": {
            "title": "Tools",
            "items": "spellchecker spellcheckerlanguage | a11ycheck code wordcount",
        },
        "table": {
            "title": "Table",
            "items": "inserttable | cell row column | advtablesort | tableprops deletetable",
        },
    },
    "textpattern_patterns": [
        {"start": "# ", "replacement": "<h1>%</h1>"},
        {"start": "## ", "replacement": "<h2>%</h2>"},
        {"start": "### ", "replacement": "<h3>%</h3>"},
        {"start": "#### ", "replacement": "<h4>%</h4>"},
        {"start": "##### ", "replacement": "<h5>%</h5>"},
        {"start": "###### ", "replacement": "<h6>%</h6>"},
        {
            "start": r"\*\*([^\*]+)\*\*",
            "replacement": "<strong>%</strong>",
        },
        {"start": r"\*([^\*]+)\*", "replacement": "<em>%</em>"},
    ],
}


class NewCampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "summary", "narrative", "public"]
        labels = {
            "name": "Name",
            "summary": "Summary",
            "narrative": "Narrative",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this Campaign. This may be public.",
            "summary": "A short summary of the campaign (300 characters max). This will be displayed on the campaign list page.",
            "narrative": "A longer narrative description of the campaign. This will be displayed on the campaign detail page.",
            "public": "If checked, this campaign will be visible to all users of Gyrinx. You can edit this later.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "summary": TinyMCE(
                attrs={"cols": 80, "rows": 5},
                mce_attrs={**TINYMCE_CONFIG, "height": "150px"},
            ),
            "narrative": TinyMCE(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_CONFIG
            ),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CampaignActionForm(forms.ModelForm):
    """Form for creating campaign actions with optional dice rolls"""

    class Meta:
        model = CampaignAction
        fields = ["description", "dice_count"]
        labels = {
            "description": "Action Description",
            "dice_count": "Number of D6 Dice (optional)",
        }
        help_texts = {
            "description": "Describe the action being taken",
            "dice_count": "How many D6 dice to roll (leave at 0 for no roll)",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "e.g., Attacking enemy fighter with bolt pistol",
                }
            ),
            "dice_count": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 20, "value": 0}
            ),
        }


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
                    "placeholder": "e.g., Hit! Enemy takes 1 wound",
                }
            ),
        }


class EditCampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "summary", "narrative", "public"]
        labels = {
            "name": "Name",
            "summary": "Summary",
            "narrative": "Narrative",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this campaign. This may be public.",
            "summary": "A short summary of the campaign (300 characters max). This will be displayed on the campaign list page.",
            "narrative": "A longer narrative description of the campaign. This will be displayed on the campaign detail page.",
            "public": "If checked, this campaign will be visible to all users.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "summary": TinyMCE(
                attrs={"cols": 80, "rows": 5},
                mce_attrs={**TINYMCE_CONFIG, "height": "150px"},
            ),
            "narrative": TinyMCE(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_CONFIG
            ),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
