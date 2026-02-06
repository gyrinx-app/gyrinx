"""Pack list, detail, and CRUD views."""

import itertools
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.content.models.house import ContentHouse
from gyrinx.core.forms.pack import PackForm
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.core.views.auth import (
    GroupMembershipRequiredMixin,
    group_membership_required,
)

# Content types that can be added to packs, in display order.
# Each entry: (model_class, label, description, icon)
SUPPORTED_CONTENT_TYPES = [
    (
        ContentHouse,
        "Houses",
        "Custom factions and houses for your fighters.",
        "bi-house-door",
    ),
]


# Fields to exclude from change diffs (internal/inherited fields).
_SKIP_FIELDS = {
    "id",
    "created",
    "modified",
    "owner",
    "archived",
    "archived_at",
    "object_id",
    "content_type",
    "pack",
}

# Human-readable labels for model fields.
_FIELD_LABELS = {
    "name": "Name",
    "summary": "Summary",
    "description": "Description",
    "listed": "Listed",
}


class _ActivityRecord:
    """Wraps a SimpleHistory record with display helpers for templates."""

    __slots__ = ("_record", "is_pack_record", "item_description", "changes")

    def __init__(self, record, is_pack_record, item_description="", changes=None):
        self._record = record
        self.is_pack_record = is_pack_record
        self.item_description = item_description
        self.changes = changes or []

    def __getattr__(self, name):
        return getattr(self._record, name)


def _format_change(field_name, new_value, field_obj):
    """Format a single field change for display.

    For TextFields (summary, description), just say "updated".
    For BooleanFields, show the new value as a readable string.
    For CharFields, show the new value.
    """
    from django.db import models

    label = _FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())

    if isinstance(field_obj, models.TextField):
        return f"{label} updated"
    elif isinstance(field_obj, models.BooleanField):
        return f"{label} set to {'yes' if new_value else 'no'}"
    else:
        return f"{label} set to {new_value}"


def _compute_changes(record):
    """Compute a list of human-readable change descriptions for a history record."""
    if record.history_type != "~":
        return []

    prev = record.prev_record
    if prev is None:
        return []

    delta = record.diff_against(prev)
    changes = []

    # Build a field lookup from the original model
    model_class = record.instance_type
    field_map = {f.name: f for f in model_class._meta.fields}

    for change in delta.changes:
        if change.field in _SKIP_FIELDS:
            continue
        field_obj = field_map.get(change.field)
        if field_obj is None:
            continue
        changes.append(_format_change(change.field, change.new, field_obj))

    return changes


def _resolve_item_description(record):
    """Resolve a pack item history record to a human-readable description.

    Attempts to load the content object to get its name. Falls back to
    the content type name if the object no longer exists.
    """
    ct_name = record.content_type.name.title() if record.content_type else "item"
    if record.object_id and record.content_type:
        model_class = record.content_type.model_class()
        if model_class:
            manager = model_class._default_manager
            qs = (
                manager.all_content()
                if hasattr(manager, "all_content")
                else manager.all()
            )
            try:
                obj = qs.get(pk=record.object_id)
                return f"{obj} ({ct_name})"
            except model_class.DoesNotExist:
                pass
    return ct_name


def _get_pack_activity(pack, limit=None):
    """Get unified activity history for a pack and its items.

    Returns a sorted list of _ActivityRecord wrappers, ordered by
    history_date descending. Update records with no meaningful field
    changes are excluded.
    """
    pack_history = pack.history.select_related("history_user").all()
    item_history = (
        CustomContentPackItem.history.filter(pack_id=pack.id)
        .select_related("history_user", "content_type")
        .all()
    )

    pack_records = []
    for r in pack_history:
        changes = _compute_changes(r)
        if r.history_type == "~" and not changes:
            continue
        pack_records.append(_ActivityRecord(r, is_pack_record=True, changes=changes))

    item_records = []
    for r in item_history:
        changes = _compute_changes(r)
        if r.history_type == "~" and not changes:
            continue
        item_records.append(
            _ActivityRecord(
                r,
                is_pack_record=False,
                item_description=_resolve_item_description(r),
                changes=changes,
            )
        )

    combined = sorted(
        itertools.chain(pack_records, item_records),
        key=lambda h: h.history_date,
        reverse=True,
    )

    if limit:
        return combined[:limit]
    return combined


class PacksView(GroupMembershipRequiredMixin, generic.ListView):
    template_name = "core/pack/packs.html"
    context_object_name = "packs"
    required_groups = ["Custom Content"]
    paginate_by = 20

    def get_queryset(self):
        queryset = CustomContentPack.objects.all().select_related("owner")

        # Default to user's own packs if authenticated
        if self.request.user.is_authenticated:
            show_my_packs = self.request.GET.get("my", "1")
            if show_my_packs == "1":
                queryset = queryset.filter(owner=self.request.user)
            else:
                queryset = queryset.filter(listed=True)
        else:
            queryset = queryset.filter(listed=True)

        # Search
        q = self.request.GET.get("q", "").strip()
        if q:
            search_vector = SearchVector("name", "summary", "owner__username")
            search_query = SearchQuery(q)
            queryset = queryset.annotate(search=search_vector).filter(
                search=search_query
            )

        return queryset.order_by("name")


class PackDetailView(GroupMembershipRequiredMixin, generic.DetailView):
    template_name = "core/pack/pack.html"
    context_object_name = "pack"
    required_groups = ["Custom Content"]

    def get_object(self):
        pack = get_object_or_404(
            CustomContentPack.objects.select_related("owner").prefetch_related(
                "items__content_type"
            ),
            id=self.kwargs["id"],
        )
        # Unlisted packs are only visible to their owner
        user = self.request.user
        if not pack.listed and (not user.is_authenticated or user != pack.owner):
            raise Http404
        return pack

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pack = self.object
        user = self.request.user

        context["is_owner"] = user.is_authenticated and user == pack.owner

        # Group prefetched items by content type to avoid N+1 queries
        items_by_ct = defaultdict(list)
        for item in pack.items.all():
            if item.content_object is not None:
                items_by_ct[item.content_type_id].append(item.content_object)

        content_sections = []
        for model_class, label, description, icon in SUPPORTED_CONTENT_TYPES:
            ct = ContentType.objects.get_for_model(model_class)
            items = items_by_ct.get(ct.id, [])
            content_sections.append(
                {
                    "label": label,
                    "description": description,
                    "icon": icon,
                    "items": items,
                    "count": len(items),
                }
            )

        context["content_sections"] = content_sections
        all_activities = _get_pack_activity(pack)
        context["recent_activities"] = all_activities[:5]
        context["total_activity_count"] = len(all_activities)

        return context


@login_required
@group_membership_required(["Custom Content"])
def new_pack(request):
    """Create a new content pack owned by the current user."""
    error_message = None
    if request.method == "POST":
        form = PackForm(request.POST)
        if form.is_valid():
            pack = form.save(commit=False)
            pack.owner = request.user
            pack.save()
            return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))
    else:
        form = PackForm(
            initial={
                "name": request.GET.get("name", ""),
            }
        )

    return render(
        request,
        "core/pack/pack_new.html",
        {"form": form, "error_message": error_message},
    )


@login_required
@group_membership_required(["Custom Content"])
def edit_pack(request, id):
    """Edit an existing content pack owned by the current user."""
    pack = get_object_or_404(CustomContentPack, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = PackForm(request.POST, instance=pack)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))
    else:
        form = PackForm(instance=pack)

    return render(
        request,
        "core/pack/pack_edit.html",
        {"form": form, "pack": pack, "error_message": error_message},
    )


class PackActivityView(GroupMembershipRequiredMixin, generic.TemplateView):
    """Display full activity history for a pack."""

    template_name = "core/pack/pack_activity.html"
    required_groups = ["Custom Content"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pack = get_object_or_404(
            CustomContentPack.objects.select_related("owner"),
            id=self.kwargs["id"],
        )

        user = self.request.user
        if not pack.listed and (not user.is_authenticated or user != pack.owner):
            raise Http404

        all_activity = _get_pack_activity(pack)
        paginator = Paginator(all_activity, 50)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        context["pack"] = pack
        context["activities"] = page_obj
        context["page_obj"] = page_obj
        context["is_paginated"] = page_obj.has_other_pages()
        context["is_owner"] = user.is_authenticated and user == pack.owner

        return context
