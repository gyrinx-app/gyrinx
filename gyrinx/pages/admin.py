from django.contrib import admin
from django.contrib.flatpages.admin import FlatPageAdmin as BaseFlatPageAdmin
from django.contrib.flatpages.models import FlatPage
from django.urls import reverse

from gyrinx.core.widgets import TinyMCEWithUpload
from gyrinx.pages.models import FlatPageVisibility


class FlatPageVisibilityInline(admin.TabularInline):
    model = FlatPageVisibility
    extra = 0


class FlatPageAdmin(BaseFlatPageAdmin):
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "content":
            return db_field.formfield(
                widget=TinyMCEWithUpload(
                    attrs={"cols": 120, "rows": 30},
                    mce_attrs={
                        "height": "66vh",
                        "external_link_list_url": reverse("tinymce-linklist"),
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
                    },
                )
            )
        return super().formfield_for_dbfield(db_field, **kwargs)

    inlines = [FlatPageVisibilityInline]


admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin)


@admin.display(description="Only Visible to Groups")
def groups_name(obj):
    return ", ".join([group.name for group in obj.groups.all()])


@admin.register(FlatPageVisibility)
class FlatPageVisibilityAdmin(admin.ModelAdmin):
    list_display = ("page", groups_name)
    search_fields = ("page__title", "groups__name")
    ordering = ("page__title",)
    actions = None
