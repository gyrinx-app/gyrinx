from django.contrib import admin
from django.contrib.flatpages.admin import FlatPageAdmin as BaseFlatPageAdmin
from django.contrib.flatpages.models import FlatPage
from django.urls import reverse
from tinymce.widgets import TinyMCE

from gyrinx.pages.models import FlatPageVisibility


class FlatPageAdmin(BaseFlatPageAdmin):
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "content":
            return db_field.formfield(
                widget=TinyMCE(
                    attrs={"cols": 80, "rows": 30},
                    mce_attrs={"external_link_list_url": reverse("tinymce-linklist")},
                )
            )
        return super().formfield_for_dbfield(db_field, **kwargs)


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
