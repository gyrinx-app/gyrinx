from django.contrib import admin

from .models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipment,
    ContentFighterEquipmentAssignment,
    ContentHouse,
    ContentImportVersion,
    ContentPolicy,
    ContentSkill,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def __init__(self, model, admin_site):
        self.list_display = [f.name for f in model._meta.fields]
        super().__init__(model, admin_site)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContentCategory)
class ContentCategoryAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentEquipment)
class ContentEquipmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["name", "category__name"]


@admin.register(ContentEquipmentCategory)
class ContentEquipmentCategoryAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentFighter)
class ContentFighterAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["type", "category__name", "house__name"]


@admin.register(ContentFighterEquipment)
class ContentFighterEquipmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name"]


@admin.register(ContentFighterEquipmentAssignment)
class ContentFighterEquipmentAssignmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name"]


@admin.register(ContentHouse)
class ContentHouseAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentImportVersion)
class ContentImportVersionAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["ruleset", "directory"]


@admin.register(ContentPolicy)
class ContentPolicyAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentSkill)
class ContentSkillAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    search_fields = ["name"]
