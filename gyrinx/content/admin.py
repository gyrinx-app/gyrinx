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
    pass


@admin.register(ContentEquipment)
class ContentEquipmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentEquipmentCategory)
class ContentEquipmentCategoryAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentFighter)
class ContentFighterAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentFighterEquipment)
class ContentFighterEquipmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentFighterEquipmentAssignment)
class ContentFighterEquipmentAssignmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentHouse)
class ContentHouseAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentImportVersion)
class ContentImportVersionAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentPolicy)
class ContentPolicyAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


@admin.register(ContentSkill)
class ContentSkillAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass
