from django import forms

from gyrinx.content.models import ContentFighter


class CopySelectedToFighterForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    to_fighters = forms.ModelMultipleChoiceField(
        ContentFighter.objects, label="To ContentFighters:"
    )
