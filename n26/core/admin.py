"""Inspect player data without bypassing operation-managed writes.

Assignments, ledger entries, events and stash records are read-only.
Gang and model totals are also read-only because operations recompute them.
Superusers may delete individual objects through Django's cascade preview;
changelists offer no batch deletion.

Display preferences remain editable. Assignment selections use the application's
card and print screens, which provide the context for selecting equipment.
"""

from django.contrib import admin

from n26.core.models import (
    Assignment,
    AssignmentSet,
    Battle,
    Campaign,
    CampaignEvent,
    CampaignMembership,
    DismissedOffer,
    Gang,
    LedgerEntry,
    LedgerEvent,
    Miniature,
    PrintConfig,
    Stash,
    StatOverride,
)
from n26.core.models.assignment import ASSIGNABLE_FIELDS


class OneAtATime:
    """Disable changelist batch deletion in favour of each object's cascade preview."""

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class ReadOnlyAdmin(OneAtATime, admin.ModelAdmin):
    """Permit inspection and superuser deletion while refusing creation and edits.

    Operation-managed creation requires assignments, ledger entries, events and
    recomputed totals together. Deleting part of a gang may invalidate totals.
    Reconciliation checks entries and cached totals; deleting journal-only events
    can lose history without check_gang reporting a discrepancy.

    Deleting a gang cascades through memberships to roster models.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Gang)
class GangAdmin(OneAtATime, admin.ModelAdmin):
    list_display = [
        "name",
        "gang_type",
        "owner",
        "rating",
        "credits",
        "archived",
        "sheet",
    ]
    list_filter = ["gang_type", "archived", "created"]
    search_fields = ["name", "owner__username"]
    list_select_related = ["gang_type", "owner"]
    autocomplete_fields = ["owner"]
    date_hierarchy = "created"
    ordering = ["-created"]
    # Keep cached totals read-only. Show founding as read-only rather than
    # rendering every assignment as a dropdown option.
    readonly_fields = [
        "rating",
        "credits",
        "founding",
        "archived_at",
        "created",
        "modified",
    ]
    actions = ["archive_gangs", "unarchive_gangs"]

    @admin.display(description="Sheet")
    def sheet(self, gang):
        """Link to the gang's public roster."""
        from django.utils.html import format_html

        return format_html(
            '<a href="/n26/gangs/{}/" target="_blank" rel="noopener">Open</a>', gang.pk
        )

    @admin.action(description="Archive selected gangs")
    def archive_gangs(self, request, queryset):
        """Archive each selected gang through its lifecycle method.

        Individual calls preserve archive timestamps and related lifecycle handling.
        """
        done = 0
        for gang in queryset.exclude(archived=True):
            gang.archive()
            done += 1
        self.message_user(request, f"Archived {done} gang{'' if done == 1 else 's'}.")

    @admin.action(description="Unarchive selected gangs")
    def unarchive_gangs(self, request, queryset):
        """Restore visibility for archived gangs."""
        done = 0
        for gang in queryset.filter(archived=True):
            gang.unarchive()
            done += 1
        self.message_user(request, f"Restored {done} gang{'' if done == 1 else 's'}.")


@admin.register(Miniature)
class MiniatureAdmin(admin.ModelAdmin):
    list_display = ["name", "gang", "owner", "rating", "xp", "xp_target"]
    search_fields = ["name", "owner__username"]
    autocomplete_fields = ["owner"]
    readonly_fields = ["rating", "membership", "created", "modified"]

    def get_queryset(self, request):
        # `gang` is derived through the membership assignment; without the
        # join the changelist pays a query per row to print it.
        return super().get_queryset(request).select_related("membership__gang", "owner")


@admin.register(Stash)
class StashAdmin(ReadOnlyAdmin):
    list_display = ["gang", "rating"]
    list_select_related = ["gang"]
    search_fields = ["gang__name"]


@admin.register(Assignment)
class AssignmentAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "gang_root", "reason", "archived", "created"]
    list_filter = ["archived"]
    search_fields = ["gang_root__name", "miniature_root__name"]

    @admin.display(description="Reason")
    def reason(self, assignment):
        # Display acquisition reason from the joined ledger entry.
        entry = getattr(assignment, "ledger_entry", None)
        return entry.reason if entry else ""

    def get_queryset(self, request):
        # Preload assignable and host relations used by __str__ to avoid queries
        # per changelist entry.
        return (
            super()
            .get_queryset(request)
            .select_related(
                *ASSIGNABLE_FIELDS,
                "gang",
                "miniature",
                "stash",
                "gang_root",
                "miniature_root",
                "ledger_entry",
            )
        )


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = [
        "assignment",
        "reason",
        "list_price",
        "paid",
        "rating_contribution",
        "created",
    ]
    list_filter = ["reason"]
    search_fields = ["assignment__gang_root__name", "note"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                *(f"assignment__{field}" for field in ASSIGNABLE_FIELDS),
                "assignment__gang",
                "assignment__miniature",
                "assignment__stash",
            )
        )


@admin.register(LedgerEvent)
class LedgerEventAdmin(ReadOnlyAdmin):
    list_display = [
        "kind",
        "about",
        "gang",
        "actor",
        "credits_delta",
        "rating_delta",
        "created",
    ]
    list_filter = ["kind"]
    search_fields = ["gang__name", "note"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                *(f"assignment__{field}" for field in ASSIGNABLE_FIELDS),
                "assignment__gang",
                "assignment__miniature",
                "assignment__stash",
                "miniature",
                "gang",
                "actor",
            )
        )


@admin.register(AssignmentSet)
class AssignmentSetAdmin(admin.ModelAdmin):
    list_display = ["name", "miniature"]
    search_fields = ["name", "miniature__name"]
    autocomplete_fields = ["miniature"]
    list_select_related = ["miniature"]
    # Edit equipment selection through the card, which provides item context.
    exclude = ["assignments"]


@admin.register(StatOverride)
class StatOverrideAdmin(admin.ModelAdmin):
    list_display = ["miniature", "statline_type_stat", "value"]
    search_fields = ["miniature__name", "statline_type_stat__stat__full_name"]
    autocomplete_fields = ["miniature"]
    # Preload stat and statline type for each cell's display label.
    list_select_related = [
        "miniature",
        "statline_type_stat__stat",
        "statline_type_stat__statline_type",
    ]


@admin.register(DismissedOffer)
class DismissedOfferAdmin(admin.ModelAdmin):
    list_display = ["slot_key", "gang", "created"]
    search_fields = ["slot_key", "gang__name"]
    autocomplete_fields = ["gang"]
    list_select_related = ["gang"]


@admin.register(PrintConfig)
class PrintConfigAdmin(admin.ModelAdmin):
    list_display = ["__str__", "gang", "include_header", "include_stash"]
    search_fields = ["name", "gang__name"]
    autocomplete_fields = ["gang"]
    list_select_related = ["gang"]
    # As on AssignmentSet: the ticking happens on the print setup screen.
    exclude = ["miniatures", "assignments"]


@admin.register(Campaign)
class CampaignAdmin(OneAtATime, admin.ModelAdmin):
    """Edit campaign metadata while its founding type, pack and additions remain read-only."""

    list_display = ["name", "owner", "campaign_type", "budget", "archived"]
    list_filter = ["archived", "campaign_type"]
    search_fields = ["name", "owner__username"]
    autocomplete_fields = ["owner"]
    list_select_related = ["owner", "campaign_type"]
    # Founding creates the type, pack and additions together; admin cannot
    # create an incomplete campaign.
    readonly_fields = ["campaign_type", "pack", "additions"]

    def has_add_permission(self, request):
        return False


@admin.register(CampaignEvent)
class CampaignEventAdmin(ReadOnlyAdmin):
    """Keep append-only campaign events read-only."""

    list_display = ["kind", "campaign", "actor", "note", "created"]
    list_filter = ["kind"]
    search_fields = ["campaign__name", "note"]
    list_select_related = ["campaign", "actor"]


@admin.register(CampaignMembership)
class CampaignMembershipAdmin(ReadOnlyAdmin):
    """Keep memberships read-only so joins and departures retain matching events."""

    list_display = ["gang", "campaign", "created", "left"]
    list_filter = ["campaign"]
    search_fields = ["campaign__name", "gang__name"]
    list_select_related = ["campaign", "gang"]
    raw_id_fields = ["type_carrier", "additions_carrier"]


@admin.register(Battle)
class BattleAdmin(ReadOnlyAdmin):
    """Keep battles read-only so their campaign events remain consistent."""

    list_display = ["scenario", "date", "result", "campaign", "created"]
    list_filter = ["campaign"]
    search_fields = ["campaign__name", "scenario"]
    list_select_related = ["campaign"]


# Register maintenance operations during admin autodiscovery through the
# edition seam. Importing the platform admin here would initialise its
# console before the platform's own admin registration.
import n26.maintenance  # noqa: E402,F401  (imported for its registrations)
