"""The admin's window onto player data — and mostly a window.

Player data is written by ``n26.operations`` and nowhere else: an
assignment created or edited here would skip the ledger entry, the event
and the repin, and nothing would notice until reconcile ran. So the
ledger-adjacent models — Assignment, LedgerEntry, LedgerEvent, Stash —
are registered read-only: the admin is for finding and inspecting, not
for writing what only an operation may write. The pinned caches on Gang
and Miniature are read-only fields for the same reason.

Removing is the exception, and a superuser's alone. Django asks for
the delete permission on every model a cascade reaches, so a gang is
deletable only where the models its deletion touches allow it. It is
taken one at a time, on the page that says what goes: the changelists
offer no batch delete.

Display-only state (AssignmentSet, PrintConfig, StatOverride) is
editable — it moves no money, changes no rating and touches no ledger —
though their selection M2Ms are managed in the app, where the choices
are drawn with the context a bare multi-select cannot give.

FeatureFlag is editable too, and is not player data at all: it says who
may reach a feature still being built. That belongs on a page precisely
so opening one to another player does not wait for a deploy.
"""

from django.contrib import admin

from n26.core.models import (
    Assignment,
    AssignmentSet,
    FeatureFlag,
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
    """No batch delete from a list.

    Deleting player data is a deliberate act, taken on the page that
    says what goes with it. The changelist's batch offers the same
    power a checkbox at a time, over things whose consequences differ
    one from the next, and with no such page in between.
    """

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class ReadOnlyAdmin(OneAtATime, admin.ModelAdmin):
    """Look, don't write — but a superuser may still remove.

    Writing is what the guard is for: an assignment created or edited
    here skips the ledger entry, the event and the repin, and nothing
    notices until reconcile runs. Removing is a different act, and a
    superuser's: a gang that has to go takes its assignments, its
    ledger and its stash with it. Its models stay — belonging to a gang
    is an assignment, and a model outlives the one that placed it.

    Deleting *part* of a gang is possible and is the sharp edge: one
    assignment out of a live chain leaves that gang's pinned totals
    standing for what has gone, which reconcile reports as a
    discrepancy, and a lone ledger event is the audit trail losing a
    line. The repair is to recompute, or to delete the gang whole.
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
    # The caches are reconcile's to repair, and the founding is an
    # assignment — a dropdown over that table would render every row in
    # the database into one select.
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
        """The gang as a player reads it — a roster is readable by
        whoever holds its address, so this is a plain link."""
        from django.utils.html import format_html

        return format_html(
            '<a href="/n26/gangs/{}/" target="_blank" rel="noopener">Open</a>', gang.pk
        )

    @admin.action(description="Archive selected gangs")
    def archive_gangs(self, request, queryset):
        """Put gangs away, one ``archive()`` each.

        A soft delete: nothing is dropped, and the gang stops being
        listed, founded from, or reachable by its address. One gang at a
        time rather than one UPDATE, because archiving stamps the time it
        happened and carries to anything a gang says goes with it — a bulk
        write would set the flag and neither.
        """
        done = 0
        for gang in queryset.exclude(archived=True):
            gang.archive()
            done += 1
        self.message_user(request, f"Archived {done} gang{'' if done == 1 else 's'}.")

    @admin.action(description="Unarchive selected gangs")
    def unarchive_gangs(self, request, queryset):
        """The way back, for a gang put away by mistake."""
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
    # The selection is edited in the app, against the model's own card;
    # a multi-select over the whole assignment table says nothing.
    exclude = ["assignments"]


@admin.register(StatOverride)
class StatOverrideAdmin(admin.ModelAdmin):
    list_display = ["miniature", "statline_type_stat", "value"]
    search_fields = ["miniature__name", "statline_type_stat__stat__full_name"]
    autocomplete_fields = ["miniature"]
    # The cell names itself as "<shape> — <stat>", so both sides of that
    # ride the changelist rather than costing a query per row.
    list_select_related = [
        "miniature",
        "statline_type_stat__stat",
        "statline_type_stat__statline_type",
    ]


@admin.register(PrintConfig)
class PrintConfigAdmin(admin.ModelAdmin):
    list_display = ["__str__", "gang", "include_header", "include_stash"]
    search_fields = ["name", "gang__name"]
    autocomplete_fields = ["gang"]
    list_select_related = ["gang"]
    # As on AssignmentSet: the ticking happens on the print setup screen.
    exclude = ["miniatures", "assignments"]


@admin.register(FeatureFlag)
class FeatureFlagAdmin(OneAtATime, admin.ModelAdmin):
    """Where a half-built feature is opened and shut.

    Editable, and for a reason none of the others here share: this is not
    player data at all. Which accounts may see an unfinished screen is a
    decision somebody makes while the work is going on, not one to hold
    until a deploy.

    The slug is what code asks for, so it is settable when the row is
    created and fixed afterwards: editing it later would not rename a
    feature, it would turn one off and leave a second nobody reads.
    """

    list_display = ["name", "slug", "availability", "group"]
    list_filter = ["availability"]
    search_fields = ["name", "slug"]
    list_select_related = ["group"]

    def get_readonly_fields(self, request, obj=None):
        # Added to whatever is already fixed rather than replacing it, so a
        # field pinned on this class or a mixin later is not silently freed.
        fixed = list(super().get_readonly_fields(request, obj))
        return [*fixed, "slug"] if obj else fixed


# Registering this edition's maintenance operations happens on import, and
# admin autodiscovery is when it must happen. Importing the seam here — and
# never gyrinx.maintenance.admin, which installs the console's admin site and
# must run after the platform's own admin — is what puts them on the console.
import n26.maintenance  # noqa: E402,F401  (imported for its registrations)
