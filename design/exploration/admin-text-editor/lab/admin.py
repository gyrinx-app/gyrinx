from pathlib import Path

from django import forms
from django.contrib import admin
from django.contrib.flatpages.admin import FlatPageAdmin as BaseFlatPageAdmin
from django.contrib.flatpages.forms import FlatpageForm
from django.contrib.flatpages.models import FlatPage
from django.templatetags.static import static

from .models import FlatPageOptions, FlatPageVisibility


def editor_asset_version():
    public = Path(__file__).resolve().parents[1] / "public"
    return str(
        max(
            (
                path.stat().st_mtime_ns
                for path in (
                    public / "editor.js",
                    public / "theme.css",
                    public / "tiny-editor.js",
                    public / "tiny-content.css",
                )
                if path.exists()
            ),
            default=0,
        )
    )


class EditorWidget(forms.Textarea):
    @property
    def media(self):
        return forms.Media(js=(f"{static('editor.js')}?v={editor_asset_version()}",))

    def __init__(self, attrs=None):
        super().__init__(
            {
                "data-gyrinx-editor": "",
                "data-editor-version": editor_asset_version(),
                "rows": 14,
                **(attrs or {}),
            }
        )


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

    def response_change(self, request, obj):
        response = super().response_change(request, obj)
        if (
            request.GET.get("editor") == "tinymce"
            and "_continue" in request.POST
            and response.status_code == 302
        ):
            separator = "&" if "?" in response.url else "?"
            response["Location"] = response.url + separator + "editor=tinymce"
        return response

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
