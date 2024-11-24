from django.contrib import admin

from .models import (
    ContentEquipment,
    ContentFighter,
    ContentFighterEquipment,
    ContentFighterEquipmentAssignment,
    ContentHouse,
    ContentPolicy,
    ContentSkill,
)


class ContentAdmin(admin.ModelAdmin):
    def __init__(self, model, admin_site):
        self.list_display = [
            f.name
            for f in model._meta.fields
            if f.name not in ["created", "modified", "id"]
        ]
        self.list_display += ["id", "created", "modified"]
        self.initial_list_display = self.list_display.copy()
        super().__init__(model, admin_site)


class ContentTabularInline(admin.TabularInline):
    def __init__(self, parent_model, admin_site):
        super().__init__(parent_model, admin_site)


class ContentStackedInline(admin.StackedInline):
    def __init__(self, parent_model, admin_site):
        super().__init__(parent_model, admin_site)


@admin.register(ContentEquipment)
class ContentEquipmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name", "category__name"]


@admin.register(ContentFighterEquipment)
class ContentFighterEquipmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name"]


class ContentFighterEquipmentInline(ContentTabularInline):
    model = ContentFighterEquipment


@admin.register(ContentFighterEquipmentAssignment)
class ContentFighterEquipmentAssignmentAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["fighter__type", "equipment__name"]


class ContentFighterEquipmentAssignmentInline(ContentTabularInline):
    model = ContentFighterEquipmentAssignment


@admin.register(ContentFighter)
class ContentFighterAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["type", "category__name", "house__name"]
    inlines = [ContentFighterEquipmentInline, ContentFighterEquipmentAssignmentInline]


class ContentFighterInline(ContentTabularInline):
    model = ContentFighter


@admin.register(ContentHouse)
class ContentHouseAdmin(ContentAdmin, admin.ModelAdmin):
    list_display_links = ["name"]
    search_fields = ["name"]
    inlines = [ContentFighterInline]


@admin.register(ContentPolicy)
class ContentPolicyAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(ContentSkill)
class ContentSkillAdmin(ContentAdmin, admin.ModelAdmin):
    search_fields = ["name"]
