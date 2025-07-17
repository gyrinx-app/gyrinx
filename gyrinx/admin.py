from django.contrib import admin
from polymorphic.admin import (
    StackedPolymorphicInline,
)


class GyAdmin(admin.ModelAdmin):
    def __init__(self, model, admin_site):
        self.list_display = [
            f.name
            for f in model._meta.fields
            if f.name not in ["created", "modified", "id"]
        ]
        self.initial_list_display = self.list_display.copy()
        super().__init__(model, admin_site)


class GyTabularInline(admin.TabularInline):
    show_change_link = True

    def __init__(self, parent_model, admin_site):
        super().__init__(parent_model, admin_site)


class GyStackedInline(admin.StackedInline):
    show_change_link = True

    def __init__(self, parent_model, admin_site):
        super().__init__(parent_model, admin_site)


class GyStackedPolymorphicInline(StackedPolymorphicInline, GyStackedInline): ...
