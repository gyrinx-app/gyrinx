from django import forms

from gyrinx.core.models import List


class NewListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "content_house"]
        labels = {
            "name": "Name",
            "content_house": "House",
        }
        help_texts = {
            "name": "The name you use to identify this list. This may be public.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_house": forms.Select(attrs={"class": "form-select"}),
        }
