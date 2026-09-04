from django import forms
from django.contrib import admin

from n26.library import artwork
from n26.library.models import (
    Asset,
    AssetKind,
    CampaignType,
    ContentPack,
    GangType,
    Pickable,
    Picklist,
    PicklistMember,
    Profile,
    ProfileType,
    Slot,
    SlotType,
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


class GangTypeForm(forms.ModelForm):
    """The badge's two ways in, in the admin as on the authoring page.

    The extra control stores nothing of its own: it puts the file in the
    site's storage and writes the resulting address into ``icon_url``, which
    is the only thing the row keeps.
    """

    icon_url_upload = forms.FileField(
        required=False,
        label="Upload a drawing",
        help_text=(
            "An SVG file. Uploading one stores it and fills in the address "
            "above, replacing whatever is there."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".svg,image/svg+xml"}),
    )

    class Meta:
        model = GangType
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        artwork.clean_onto(self, cleaned, "icon_url", "icon_url_upload")
        return cleaned


@admin.register(GangType)
class GangTypeAdmin(admin.ModelAdmin):
    form = GangTypeForm
    list_display = ["name", "pack", "archived"]
    list_filter = ["pack", "archived"]
    search_fields = ["name"]
    list_select_related = ["pack"]


class AssetKindInline(admin.TabularInline):
    model = AssetKind
    extra = 1
    fields = ["label_singular", "label_plural", "mode", "position"]
    ordering = ["position"]


@admin.register(CampaignType)
class CampaignTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "pack", "archived"]
    list_filter = ["pack", "archived"]
    search_fields = ["name"]
    inlines = [AssetKindInline]
    list_select_related = ["pack"]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "income", "pack", "archived"]
    list_filter = ["pack", "kind__campaign_type", "kind__mode", "archived"]
    search_fields = ["name", "qualifier"]
    list_select_related = ["pack", "kind", "kind__campaign_type"]


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


# Slots and picks. A slot type is authored on its own page in the
# library; these registrations are the inspectable graph behind it — every
# table filterable by the slot type it belongs to, so "what is in Gang
# Legacy" is one question of any of them.


@admin.register(SlotType)
class SlotTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "plural_name", "allows_repeats", "pack", "archived"]
    list_filter = ["pack", "allows_repeats", "archived"]
    search_fields = ["name"]
    list_select_related = ["pack"]


@admin.register(Pickable)
class PickableAdmin(admin.ModelAdmin):
    list_display = ["name", "slot_type", "qualifier", "pack", "archived"]
    list_filter = ["pack", "slot_type", "archived"]
    search_fields = ["name", "qualifier"]
    list_select_related = ["pack", "slot_type"]


class PicklistMemberInline(admin.TabularInline):
    model = PicklistMember
    extra = 1
    fields = ["pickable", "label_override", "position"]
    ordering = ["position"]
    # A plain dropdown here would draw every option in the library once
    # per row of the list.
    autocomplete_fields = ["pickable"]


@admin.register(Picklist)
class PicklistAdmin(admin.ModelAdmin):
    list_display = ["name", "slot_type", "pack", "archived"]
    list_filter = ["pack", "slot_type", "archived"]
    search_fields = ["name"]
    inlines = [PicklistMemberInline]
    list_select_related = ["pack", "slot_type"]


@admin.register(PicklistMember)
class PicklistMemberAdmin(admin.ModelAdmin):
    list_display = ["picklist", "pickable", "label_override", "position", "archived"]
    list_filter = ["picklist__slot_type", "archived"]
    search_fields = ["picklist__name", "pickable__name"]
    list_select_related = ["picklist", "pickable"]


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slot_type",
        "picklist",
        "label",
        "min_picks",
        "max_picks",
        "assigned_to",
        "hidden",
        "pack",
        "archived",
    ]
    list_filter = ["pack", "slot_type", "assigned_to", "hidden", "archived"]
    search_fields = ["name", "label"]
    list_select_related = ["pack", "slot_type", "picklist"]


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
