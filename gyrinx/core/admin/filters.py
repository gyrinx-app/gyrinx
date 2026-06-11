import uuid

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelectMultiple


class AutocompleteRelatedFilter(admin.SimpleListFilter):
    """
    Changelist filter on a FK, rendered as a select2 multi-select autocomplete
    instead of the default list of links — usable when the related table has
    thousands of rows.

    Subclasses set ``title``, ``parameter_name``, and ``field_name`` (a FK on
    the changelist model). The related model's admin must define
    ``search_fields`` (it backs the autocomplete endpoint), and the ModelAdmin
    using the filter must include the widget's assets in its media — see
    ``autocomplete_filter_media``.

    Selected values are carried in the query string as comma-separated UUIDs.
    """

    template = "admin/gyrinx_autocomplete_filter.html"
    field_name = None

    def __init__(self, request, params, model, model_admin):
        self.field = model._meta.get_field(self.field_name)
        self.admin_site = model_admin.admin_site
        super().__init__(request, params, model, model_admin)

    def has_output(self):
        return True

    def lookups(self, request, model_admin):
        return ()

    def selected_ids(self):
        ids = []
        for part in (self.value() or "").split(","):
            try:
                ids.append(uuid.UUID(part.strip()))
            except ValueError:
                continue
        return ids

    def queryset(self, request, queryset):
        ids = self.selected_ids()
        if ids:
            return queryset.filter(**{f"{self.field_name}__id__in": ids})
        return queryset

    def widget_id(self):
        return f"id_{self.parameter_name}_autocomplete_filter"

    def rendered_widget(self):
        remote_model = self.field.remote_field.model
        form_field = forms.ModelMultipleChoiceField(
            queryset=remote_model._default_manager.all(),
            widget=AutocompleteSelectMultiple(self.field, self.admin_site),
            required=False,
        )
        return form_field.widget.render(
            name=f"{self.parameter_name}_select",
            value=self.selected_ids(),
            attrs={"id": self.widget_id(), "style": "width: 100%"},
        )


def autocomplete_filter_media(model, field_name, admin_site):
    """
    The select2/autocomplete assets an AutocompleteRelatedFilter needs on the
    changelist page. Changelists don't collect filter media, so the ModelAdmin
    must add this to its own ``media`` property.
    """
    return AutocompleteSelectMultiple(
        model._meta.get_field(field_name), admin_site
    ).media
