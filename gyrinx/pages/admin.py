from django.contrib import admin
from django.contrib.flatpages.admin import FlatPageAdmin as BaseFlatPageAdmin
from django.contrib.flatpages.models import FlatPage
from django.urls import reverse
from tinymce.widgets import TinyMCE

from gyrinx.pages.models import FlatPageVisibility, WaitingListEntry, WaitingListSkill


class FlatPageVisibilityInline(admin.TabularInline):
    model = FlatPageVisibility
    extra = 0


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


# Waiting List


@admin.register(WaitingListSkill)
class WaitingListSkillAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name", "description")
    ordering = ("name",)


def display(field, key):
    return lambda obj: ", ".join(
        [getattr(item, key) for item in getattr(obj, field).all()]
    )


@admin.register(WaitingListEntry)
class WaitingListEntryAdmin(admin.ModelAdmin):
    readonly_fields = ("share_code",)
    list_display = (
        "email",
        "desired_username",
        "yaktribe_username",
        "share_code",
        display("skills", "name"),
    )
    search_fields = (
        "email",
        "desired_username",
        "yaktribe_username",
        "skills__name",
        "notes",
    )
    ordering = ("email",)
