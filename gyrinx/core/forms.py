from django import forms

from gyrinx.content.models import ContentFighter
from gyrinx.core.models import List, ListFighter


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


class EditListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name"]
        labels = {
            "name": "Name",
        }
        help_texts = {
            "name": "The name you use to identify this list. This may be public.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }


class NewListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lst = kwargs.get("initial", {}).get("list")
        if lst:
            self.fields["content_fighter"].queryset = ContentFighter.objects.filter(
                house=lst.content_house
            )

    class Meta:
        model = ListFighter
        fields = ["name", "content_fighter"]
        labels = {
            "name": "Name",
            "content_fighter": "Fighter",
        }
        help_texts = {
            "name": "The name you use to identify this Fighter. This may be public.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_fighter": forms.Select(attrs={"class": "form-select"}),
        }
