from django import forms
from django.contrib import admin

from .models import (
    Build,
    BuildFighter,
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


class BuildForm(forms.ModelForm):
    class Meta:
        model = Build
        fields = "__all__"
        exclude = ["content_house_uuid"]

    content_house = forms.ModelChoiceField(
        queryset=ContentHouse.objects.all().order_by("name"),
        widget=forms.Select,
        required=True,
        label="House",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            if self.instance:
                self.initial["content_house"] = self.instance.get_content_house().pk
        except ContentHouse.DoesNotExist:
            pass

    def save(self, commit=True):
        self.instance.content_house_uuid = self.cleaned_data["content_house"].uuid
        return super().save(commit)


@admin.register(Build)
class BuildAdmin(admin.ModelAdmin):
    form = BuildForm


class BuildFighterForm(forms.ModelForm):
    class Meta:
        model = BuildFighter
        fields = "__all__"
        exclude = ["content_fighter_uuid"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and hasattr(self.instance, "build") and self.instance.build:
            house = self.instance.build.get_content_house()
            self.fields["content_fighter"].queryset = ContentFighter.objects.filter(
                house=house
            )
        else:
            self.fields["content_fighter"].queryset = ContentFighter.objects.all()

        try:
            if self.instance:
                self.initial["content_fighter"] = self.instance.get_content_fighter().pk
        except ContentFighter.DoesNotExist:
            pass

    content_fighter = forms.ModelChoiceField(
        queryset=ContentFighter.objects.all(),
        widget=forms.Select,
        required=True,
        label="Fighter",
    )

    def save(self, commit=True):
        self.instance.content_fighter_uuid = self.cleaned_data["content_fighter"].uuid
        return super().save(commit)


@admin.register(BuildFighter)
class BuildFighterAdmin(admin.ModelAdmin):
    form = BuildFighterForm
