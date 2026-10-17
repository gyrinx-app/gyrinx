from django import forms


class ChangelogTagColourSelect(forms.Select):
    """A native admin field enhanced with an isolated Cotton colour menu."""

    template_name = "admin/gyrinxsite/widgets/tag_colour.html"

    class Media:
        js = ["gyrinxsite/tag-colour.js"]
