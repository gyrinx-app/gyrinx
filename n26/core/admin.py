"""The admin's window onto player data — and mostly a window.

Player data is written by ``n26.operations`` and nowhere else: a row
created or edited here would skip the ledger entry, the event and the
repin, and nothing would notice until reconcile ran. So the
ledger-adjacent models — Assignment, LedgerEntry, LedgerEvent, Stash —
are registered read-only: the admin is for finding and inspecting, not
for writing what only an operation may write. The pinned caches on Gang
and Miniature are read-only fields for the same reason.

Display-only state (AssignmentSet, PrintConfig) is editable — it costs
nothing, changes no rating and touches no ledger — though their
selection M2Ms are managed in the app, where the choices are drawn with
the context a bare multi-select cannot give.
"""

from django.contrib import admin

from n26.core.models import (
    Assignment,
    AssignmentSet,
    Gang,
    LedgerEntry,
    LedgerEvent,
    Miniature,
    PrintConfig,
    Stash,
)
from n26.core.models.assignment import ASSIGNABLE_FIELDS


class ReadOnlyAdmin(admin.ModelAdmin):
    """Look, don't touch — see the module docstring."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Gang)
class GangAdmin(admin.ModelAdmin):
    list_display = ["name", "gang_type", "owner", "rating", "credits", "archived"]
    list_filter = ["gang_type", "archived"]
    search_fields = ["name", "owner__username"]
    list_select_related = ["gang_type", "owner"]
    autocomplete_fields = ["owner"]
    # The caches are reconcile's to repair, and the founding is an
    # assignment — a dropdown over that table would render every row in
    # the database into one select.
    readonly_fields = ["rating", "credits", "founding", "created", "modified"]


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
        # The reason is the ledger's fact about the assignment, not the
        # assignment's own — named here as a column because "why does
        # this row exist" is the first question an inspection asks.
        entry = getattr(assignment, "ledger_entry", None)
        return entry.reason if entry else ""

    def get_queryset(self, request):
        # __str__ is "<assignable> on <host>", which reads one of nineteen
        # union FKs plus a host — joined here so a changelist page is one
        # query rather than three per row.
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
        "assignment",
        "actor",
        "credits_delta",
        "rating_delta",
        "created",
    ]
    list_filter = ["kind"]
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
                "actor",
            )
        )


@admin.register(AssignmentSet)
class AssignmentSetAdmin(admin.ModelAdmin):
    list_display = ["name", "miniature"]
    search_fields = ["name", "miniature__name"]
    autocomplete_fields = ["miniature"]
    list_select_related = ["miniature"]
    # The selection is edited in the app, against the model's own card;
    # a multi-select over the whole assignment table says nothing.
    exclude = ["assignments"]


@admin.register(PrintConfig)
class PrintConfigAdmin(admin.ModelAdmin):
    list_display = ["__str__", "gang", "include_header", "include_stash"]
    search_fields = ["name", "gang__name"]
    autocomplete_fields = ["gang"]
    list_select_related = ["gang"]
    # As on AssignmentSet: the ticking happens on the print setup screen.
    exclude = ["miniatures", "assignments"]
