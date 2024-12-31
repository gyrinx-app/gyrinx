from django import forms

from gyrinx.content.models import ContentFighter
from gyrinx.core.models import List, ListFighter


class NewListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "content_house", "public"]
        labels = {
            "name": "Name",
            "content_house": "House",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this list. This may be public.",
            "public": "If checked, this list will be visible to all users.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_house": forms.Select(attrs={"class": "form-select"}),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EditListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "public"]
        labels = {
            "name": "Name",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this list. This may be public.",
            "public": "If checked, this list will be visible to all users.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ContentFighterChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", forms.Select(attrs={"class": "form-select"}))
        kwargs.setdefault("label", "Fighter")
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        return f"{obj.name()}"


class NewListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = kwargs.get("instance", {})
        if inst:
            self.fields["content_fighter"].queryset = ContentFighter.objects.filter(
                house=inst.list.content_house
            )

        self.fields["content_fighter"] = ContentFighterChoiceField(
            queryset=self.fields["content_fighter"].queryset
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
