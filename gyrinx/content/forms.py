from django import forms

from gyrinx.content.models import ContentFighter, ContentHouse


class CopySelectedToFighterForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    to_fighters = forms.ModelMultipleChoiceField(
        ContentFighter.objects, label="To ContentFighters:"
    )


class CopySelectedToHouseForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    to_houses = forms.ModelMultipleChoiceField(
        ContentHouse.objects, label="To ContentHouses:"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Group houses by legacy status
        from gyrinx.forms import group_select

        group_select(
            self,
            "to_houses",
            key=lambda x: "Legacy House" if x.legacy else "House",
            sort_groups_by=lambda group: 0 if group == "House" else 1,
        )
