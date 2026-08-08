from django.contrib import admin

from n26.library.models import (
    ContentPack,
    GangType,
    Profile,
    ProfileType,
    Stat,
    Statline,
    StatlineStat,
    StatlineType,
    StatlineTypeStat,
)


@admin.register(ContentPack)
class ContentPackAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "archived"]
    list_filter = ["archived"]
    prepopulated_fields = {"slug": ["name"]}
    search_fields = ["name", "slug"]


@admin.register(GangType)
class GangTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "pack", "archived"]
    list_filter = ["pack", "archived"]
    search_fields = ["name"]
    list_select_related = ["pack"]


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    list_display = ["short_name", "full_name", "field_name", "pack"]
    list_filter = ["pack", "is_inches", "is_target", "is_modifier", "is_inverted"]
    search_fields = ["short_name", "full_name", "field_name"]
    list_select_related = ["pack"]


class StatlineTypeStatInline(admin.TabularInline):
    model = StatlineTypeStat
    extra = 1
    fields = ["stat", "position"]
    ordering = ["position"]


@admin.register(StatlineType)
class StatlineTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "pack"]
    list_filter = ["pack"]
    search_fields = ["name"]
    inlines = [StatlineTypeStatInline]
    list_select_related = ["pack"]


@admin.register(ProfileType)
class ProfileTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "statline_type", "pack"]
    list_filter = ["pack", "statline_type"]
    search_fields = ["name"]
    list_select_related = ["pack", "statline_type"]


class StatlineStatInline(admin.TabularInline):
    model = StatlineStat
    extra = 0
    fields = ["statline_type_stat", "value"]


@admin.register(Statline)
class StatlineAdmin(admin.ModelAdmin):
    list_display = ["profile", "pack"]
    inlines = [StatlineStatInline]
    list_select_related = ["profile", "pack"]


class StatlineInline(admin.StackedInline):
    model = Statline
    extra = 0
    can_delete = True
    show_change_link = True
    fields = []


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "profile_type",
        "gang_type",
        "price",
        "pack",
        "archived",
    ]
    list_filter = ["pack", "profile_type", "gang_type", "archived"]
    search_fields = ["name"]
    inlines = [StatlineInline]
    list_select_related = ["pack", "profile_type", "gang_type"]
