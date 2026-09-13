from django.contrib import admin
from django.contrib.flatpages.admin import FlatPageAdmin as BaseFlatPageAdmin
from django.contrib.flatpages.models import FlatPage
from django.urls import reverse

from gyrinx.pages.models import FlatPageOptions, FlatPageVisibility
from gyrinx.widgets import TinyMCEWithUpload


class FlatPageVisibilityInline(admin.TabularInline):
    model = FlatPageVisibility
    extra = 0


def rich_text_widget(*, rows, height):
    """
    The editor used for both the page content and the page introduction.

    One definition for both so the menus, the link list and the Markdown-style
    shortcuts stay identical; only the box's size differs.
    """
    return TinyMCEWithUpload(
        attrs={"cols": 120, "rows": rows},
        mce_attrs={
            "height": height,
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


class FlatPageOptionsInline(admin.StackedInline):
    model = FlatPageOptions
    # One-to-one: show the single form straight away rather than behind an
    # "Add another" link. An untouched form is not saved, so a page without
    # options set gets no row.
    extra = 1
    max_num = 1
    can_delete = False

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "introduction":
            # Same editor as the page content, in a shorter box: an
            # introduction is a paragraph or two, not a page.
            return db_field.formfield(
                widget=rich_text_widget(rows=8, height="20vh"), required=False
            )
        return super().formfield_for_dbfield(db_field, **kwargs)


class FlatPageAdmin(BaseFlatPageAdmin):
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "content":
            return db_field.formfield(widget=rich_text_widget(rows=30, height="66vh"))
        return super().formfield_for_dbfield(db_field, **kwargs)

    inlines = [FlatPageOptionsInline, FlatPageVisibilityInline]


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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Prefetch groups to avoid N+1 queries
        return qs.prefetch_related("groups").select_related("page")
