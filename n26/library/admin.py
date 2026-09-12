from django import forms
from django.contrib import admin

from n26.library import artwork
from n26.library.models import (
    Asset,
    AssetTable,
    AssetTableEntry,
    AssetType,
    CampaignType,
    ContentPack,
    GangType,
    Interstitial,
    InterstitialSlot,
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


class AssetTypeInline(admin.TabularInline):
    model = AssetType
    extra = 1
    fields = ["label_singular", "label_plural", "ownership", "position"]
    ordering = ["position"]


@admin.register(CampaignType)
class CampaignTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "pack", "archived"]
    list_filter = ["pack", "archived"]
    search_fields = ["name"]
    inlines = [AssetTypeInline]
    list_select_related = ["pack"]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["name", "asset_type", "pack", "archived"]
    list_filter = [
        "pack",
        "asset_type__campaign_type",
        "asset_type__ownership",
        "archived",
    ]
    search_fields = ["name", "qualifier"]
    list_select_related = ["pack", "asset_type", "asset_type__campaign_type"]

    def save_model(self, request, obj, form, change):
        """Ticking Archived here is the one way a person archives an asset,
        and unticking it the one way they bring one back. The change form
        saves the row rather than calling ``archive`` or ``unarchive``, so
        the memberships that give a possession are taken out and put back
        here, as those two methods do it."""
        from n26.library.authoring import take_out_of_built_ins
        from n26.library.possessions import give_back

        if obj.archived:
            take_out_of_built_ins(obj)
        super().save_model(request, obj, form, change)
        if not obj.archived and "archived" in form.changed_data:
            give_back(obj)


class AssetTableEntryInline(admin.TabularInline):
    model = AssetTableEntry
    extra = 1
    fields = ["asset", "position", "roll_low", "roll_high"]
    ordering = ["position"]
    autocomplete_fields = ["asset"]


@admin.register(AssetTable)
class AssetTableAdmin(admin.ModelAdmin):
    list_display = ["name", "asset_type", "dice", "pack", "archived"]
    list_filter = ["pack", "asset_type__campaign_type", "dice", "archived"]
    search_fields = ["name", "qualifier"]
    list_select_related = ["pack", "asset_type", "asset_type__campaign_type"]
    inlines = [AssetTableEntryInline]

    def save_model(self, request, obj, form, change):
        """Ticking Archived here is the one way a person archives a table,
        and unticking it the one way they bring one back. The change form
        saves the row rather than calling ``archive`` or ``unarchive``, so
        the memberships that give a table are taken out and put back
        here, as those two methods do it."""
        from n26.library.authoring import take_out_of_built_ins
        from n26.library.tables import give_back

        if obj.archived:
            take_out_of_built_ins(obj)
        super().save_model(request, obj, form, change)
        if not obj.archived and "archived" in form.changed_data:
            give_back(obj)


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


class InterstitialSlotInline(admin.TabularInline):
    model = InterstitialSlot
    extra = 1
    fields = ["slot", "position", "pack"]
    ordering = ["position"]
    autocomplete_fields = ["slot"]

    def get_formset(self, request, obj=None, **kwargs):
        """A new attachment starts in its interstitial's pack, as the
        authoring verb puts it, rather than in the default pack."""
        formset = super().get_formset(request, obj, **kwargs)
        if obj is not None:
            formset.form.base_fields["pack"].initial = obj.pack_id
        return formset


@admin.register(Interstitial)
class InterstitialAdmin(admin.ModelAdmin):
    list_display = ["name", "title", "skippable", "position", "pack", "archived"]
    list_filter = ["pack", "skippable", "archived"]
    search_fields = ["name", "title"]
    inlines = [InterstitialSlotInline]
    list_select_related = ["pack"]


@admin.register(InterstitialSlot)
class InterstitialSlotAdmin(admin.ModelAdmin):
    list_display = ["interstitial", "slot", "position", "archived"]
    list_filter = ["interstitial", "archived"]
    search_fields = ["interstitial__name", "slot__name"]
    list_select_related = ["interstitial", "slot"]


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
