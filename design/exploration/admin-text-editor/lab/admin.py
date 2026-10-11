from django import forms
from django.contrib import admin
from django.contrib.flatpages.admin import FlatPageAdmin as BaseFlatPageAdmin
from django.contrib.flatpages.forms import FlatpageForm
from django.contrib.flatpages.models import FlatPage

from .models import FlatPageOptions, FlatPageVisibility


class EditorWidget(forms.Textarea):
    class Media:
        js = ("editor.js",)

    def __init__(self, attrs=None):
        super().__init__({"data-gyrinx-editor": "", "rows": 14, **(attrs or {})})


class FlatPageOptionsInline(admin.StackedInline):
    model = FlatPageOptions
    exclude = ("show_contents",)
    extra = 1
    max_num = 1
    can_delete = False

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "introduction":
            return db_field.formfield(
                widget=EditorWidget(
                    {
                        "rows": 8,
                        "data-editor-label": "Introduction",
                        "data-editor-height": "20vh",
                    }
                ),
                required=False,
            )
        return super().formfield_for_dbfield(db_field, **kwargs)


class FlatPageVisibilityInline(admin.TabularInline):
    model = FlatPageVisibility
    extra = 0


class FlatPageAdmin(BaseFlatPageAdmin):
    form = FlatpageForm
    fieldsets = (
        (None, {"fields": ("url", "title", "content", "sites")}),
        BaseFlatPageAdmin.fieldsets[1],
    )
    inlines = [FlatPageOptionsInline, FlatPageVisibilityInline]

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "content":
            return db_field.formfield(
                widget=EditorWidget(
                    {
                        "rows": 30,
                        "data-editor-label": "Page content",
                        "data-editor-height": "66vh",
                    }
                )
            )
        return super().formfield_for_dbfield(db_field, **kwargs)


admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin)


admin.site.site_header = "Gyrinx editor playground"
admin.site.site_title = "Gyrinx design"
admin.site.index_title = "Local demo content"
