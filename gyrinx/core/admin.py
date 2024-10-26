from django.contrib import admin

from .models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipment,
    ContentHouse,
    ContentImportVersion,
    ContentPolicy,
    ContentSkill,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ContentCategoryAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentEquipmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentEquipmentCategoryAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentFighterAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentFighterEquipmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentHouseAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentImportVersionAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentPolicyAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


class ContentSkillAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    pass


admin.site.register(ContentCategory, ContentCategoryAdmin)
admin.site.register(ContentEquipment, ContentEquipmentAdmin)
admin.site.register(ContentEquipmentCategory, ContentEquipmentCategoryAdmin)
admin.site.register(ContentFighter, ContentFighterAdmin)
admin.site.register(ContentFighterEquipment, ContentFighterEquipmentAdmin)
admin.site.register(ContentHouse, ContentHouseAdmin)
admin.site.register(ContentImportVersion, ContentImportVersionAdmin)
admin.site.register(ContentPolicy, ContentPolicyAdmin)
admin.site.register(ContentSkill, ContentSkillAdmin)
