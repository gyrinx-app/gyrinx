"""Pack list, detail, and CRUD views."""

import itertools
from collections import defaultdict
from typing import NamedTuple

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.paginator import Paginator
from django.db import models, transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx import messages
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.house import ContentHouse
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.statline import (
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
)
from gyrinx.core.forms.pack import ContentFighterPackForm, ContentRuleForm, PackForm
from gyrinx.core.models.list import List
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.core.views.auth import (
    GroupMembershipRequiredMixin,
    group_membership_required,
)
from gyrinx.models import is_valid_uuid


class ContentTypeEntry(NamedTuple):
    model_class: type
    label: str
    description: str
    icon: str
    form_class: type | None
    slug: str


# Content types that can be added to packs, in display order.
SUPPORTED_CONTENT_TYPES = [
    ContentTypeEntry(
        ContentHouse,
        "Houses",
        "Custom factions and houses for your fighters.",
        "bi-house-door",
        None,
        "house",
    ),
    ContentTypeEntry(
        ContentFighter,
        "Fighters",
        "Custom fighters for your Content Pack.",
        "bi-person",
        ContentFighterPackForm,
        "fighter",
    ),
    ContentTypeEntry(
        ContentRule,
        "Rules",
        "Custom rules for your Content Pack.",
        "bi-journal-text",
        ContentRuleForm,
        "rule",
    ),
]

# Lookup from URL slug to content type entry.
_CONTENT_TYPE_BY_SLUG = {entry.slug: entry for entry in SUPPORTED_CONTENT_TYPES}


# Fields to exclude from change diffs (internal/inherited fields).
_SKIP_FIELDS = {
    "id",
    "created",
    "modified",
    "owner",
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
    "archived": "Archived",
}


class _ActivityRecord:
    """Wraps a SimpleHistory record with display helpers for templates."""

    __slots__ = (
        "_record",
        "is_pack_record",
        "is_content_edit",
        "is_archive_action",
        "archive_action",
        "item_description",
        "changes",
    )

    def __init__(
        self,
        record,
        is_pack_record,
        item_description="",
        changes=None,
        is_content_edit=False,
        is_archive_action=False,
        archive_action="",
    ):
        self._record = record
        self.is_pack_record = is_pack_record
        self.is_content_edit = is_content_edit
        self.is_archive_action = is_archive_action
        self.archive_action = archive_action
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
    changes are excluded. Also includes edits to content objects
    (e.g. renaming a rule) linked through pack items.
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
        # Detect archive/restore: the only change is the "archived" field.
        is_archive_change = (
            r.history_type == "~"
            and len(changes) == 1
            and changes[0].startswith("Archived ")
        )
        if is_archive_change:
            desc = _resolve_item_description(r)
            action = "Archived" if r.archived else "Restored"
            item_records.append(
                _ActivityRecord(
                    r,
                    is_pack_record=False,
                    item_description=desc,
                    is_archive_action=True,
                    archive_action=action,
                )
            )
            continue
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

    # Content object edit records (e.g. renaming a rule).
    # Group pack item object_ids by content type, then query each model's
    # history for update records only (create/delete are covered by item history).
    content_edit_records = []
    ids_by_ct = defaultdict(set)
    for pi in pack.items.all():
        if pi.content_type_id and pi.object_id:
            ids_by_ct[pi.content_type_id].add(pi.object_id)

    for ct_id, obj_ids in ids_by_ct.items():
        ct = ContentType.objects.get_for_id(ct_id)
        model_class = ct.model_class()
        if model_class is None or not hasattr(model_class, "history"):
            continue
        for r in (
            model_class.history.filter(id__in=obj_ids, history_type="~")
            .select_related("history_user")
            .all()
        ):
            changes = _compute_changes(r)
            if not changes:
                continue
            # Use the name from the historical record (captures name at time of edit)
            desc = (
                f"{r.name} ({ct.name.title()})"
                if hasattr(r, "name")
                else ct.name.title()
            )
            content_edit_records.append(
                _ActivityRecord(
                    r,
                    is_pack_record=False,
                    is_content_edit=True,
                    item_description=desc,
                    changes=changes,
                )
            )

    combined = sorted(
        itertools.chain(pack_records, item_records, content_edit_records),
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

        # Group prefetched items by content type, splitting active/archived.
        active_by_ct = defaultdict(list)
        archived_by_ct = defaultdict(list)
        for item in pack.items.all():
            if item.content_object is not None:
                entry = {"pack_item": item, "content_object": item.content_object}
                if item.archived:
                    archived_by_ct[item.content_type_id].append(entry)
                else:
                    active_by_ct[item.content_type_id].append(entry)

        content_sections = []
        for entry in SUPPORTED_CONTENT_TYPES:
            ct = ContentType.objects.get_for_model(entry.model_class)
            items = active_by_ct.get(ct.id, [])
            archived_items = archived_by_ct.get(ct.id, [])
            content_sections.append(
                {
                    "label": entry.label,
                    "description": entry.description,
                    "icon": entry.icon,
                    "items": items,
                    "count": len(items),
                    "archived_items": archived_items,
                    "archived_count": len(archived_items),
                    "slug": entry.slug,
                    "can_add": entry.form_class is not None,
                }
            )

        context["content_sections"] = content_sections
        all_activities = _get_pack_activity(pack)
        context["recent_activities"] = all_activities[:5]
        context["total_activity_count"] = len(all_activities)

        # Subscription info: user's lists and which are subscribed
        if user.is_authenticated:
            user_lists = (
                List.objects.filter(owner=user, archived=False)
                .select_related("content_house")
                .order_by("name")
            )
            subscribed_list_ids = set(
                pack.subscribed_lists.filter(owner=user).values_list("id", flat=True)
            )
            context["user_lists"] = user_lists
            context["subscribed_list_ids"] = subscribed_list_ids
            context["unsubscribed_lists"] = [
                lst for lst in user_lists if lst.id not in subscribed_list_ids
            ]

        return context


@login_required
@group_membership_required(["Custom Content"])
def new_pack(request):
    """Create a new content pack owned by the current user."""
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
        {"form": form},
    )


@login_required
@group_membership_required(["Custom Content"])
def edit_pack(request, id):
    """Edit an existing content pack owned by the current user."""
    pack = get_object_or_404(CustomContentPack, id=id, owner=request.user)

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
        {"form": form, "pack": pack},
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


class PackArchivedItemsView(GroupMembershipRequiredMixin, generic.DetailView):
    """Display archived items for a pack section."""

    template_name = "core/pack/pack_archived.html"
    context_object_name = "pack"
    required_groups = ["Custom Content"]

    def get_object(self):
        pack = get_object_or_404(
            CustomContentPack.objects.select_related("owner").prefetch_related(
                "items__content_type"
            ),
            id=self.kwargs["id"],
        )
        if pack.owner != self.request.user:
            raise Http404
        return pack

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pack = self.object
        slug = self.kwargs["content_type_slug"]
        entry = _CONTENT_TYPE_BY_SLUG.get(slug)
        if entry is None:
            raise Http404

        ct = ContentType.objects.get_for_model(entry.model_class)
        archived_items = []
        for item in pack.items.filter(archived=True, content_type=ct):
            if item.content_object is not None:
                archived_items.append(
                    {"pack_item": item, "content_object": item.content_object}
                )

        context["archived_items"] = archived_items
        context["section_label"] = entry.label
        context["slug"] = slug
        return context


def _get_fighter_stat_definitions():
    """Load the stat definitions for the Fighter statline type."""
    statline_type = ContentStatlineType.objects.get(name="Fighter")
    return statline_type.stats.select_related("stat").order_by("position")


def _normalize_stat_value(raw_value, content_stat):
    """Normalize a stat value based on ContentStat formatting config.

    Auto-adds the correct suffix/prefix:
    - is_inches: ``4`` → ``4"``
    - is_target: ``3`` → ``3+``
    - is_modifier: ``2`` → ``+2``
    """
    value = raw_value.strip() if raw_value else ""
    # Replace smart quotes with straight quotes.
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = value.replace("\u2018", "'").replace("\u2019", "'")

    if value in ("", "-"):
        return "-"

    if content_stat.is_inches:
        # Strip trailing " to get the number, then re-add.
        number_str = value.rstrip('"').strip()
        try:
            n = int(number_str)
            return f'{n}"'
        except ValueError:
            return value

    if content_stat.is_target:
        # Strip trailing + to get the number, then re-add.
        number_str = value.rstrip("+").strip()
        try:
            n = int(number_str)
            return f"{n}+"
        except ValueError:
            return value

    if content_stat.is_modifier:
        # Strip leading +/- to get the number, then re-add sign.
        number_str = value.lstrip("+-").strip()
        try:
            n = int(number_str)
            # Preserve sign from original input; default positive.
            if value.startswith("-"):
                n = -abs(n)
            else:
                n = abs(n)
            return f"+{n}" if n >= 0 else str(n)
        except ValueError:
            return value

    # Plain number stat — store as-is.
    return value


def _stat_placeholder(content_stat):
    """Return a placeholder example for a stat input field."""
    if content_stat.is_inches:
        return '4"'
    if content_stat.is_target:
        return "3+"
    if content_stat.is_modifier:
        return "+1"
    return "3"


def _create_fighter_statline(fighter, stat_definitions, post_data):
    """Create a ContentStatline and populate stat values from POST data."""
    statline_type = ContentStatlineType.objects.get(name="Fighter")
    statline = ContentStatline.objects.create(
        content_fighter=fighter,
        statline_type=statline_type,
    )
    for type_stat in stat_definitions:
        raw = post_data.get(f"stat_{type_stat.stat.field_name}", "-") or "-"
        value = _normalize_stat_value(raw, type_stat.stat)
        ContentStatlineStat.objects.create(
            statline=statline,
            statline_type_stat=type_stat,
            value=value,
        )
    return statline


def _update_fighter_stats(fighter, post_data):
    """Update existing statline stat values from POST data."""
    for stat_obj in fighter.custom_statline.stats.select_related(
        "statline_type_stat__stat"
    ):
        field_name = stat_obj.statline_type_stat.stat.field_name
        raw = post_data.get(f"stat_{field_name}", "-") or "-"
        new_value = _normalize_stat_value(raw, stat_obj.statline_type_stat.stat)
        if stat_obj.value != new_value:
            stat_obj.value = new_value
            stat_obj.save()


def _get_content_type_entry(slug):
    """Look up a SUPPORTED_CONTENT_TYPES entry by URL slug, or raise 404."""
    entry = _CONTENT_TYPE_BY_SLUG.get(slug)
    if entry is None or entry.form_class is None:
        raise Http404
    return entry


def _get_entry_for_pack_item(pack_item):
    """Look up the SUPPORTED_CONTENT_TYPES entry matching a pack item, or raise 404."""
    for e in SUPPORTED_CONTENT_TYPES:
        ct = ContentType.objects.get_for_model(e.model_class)
        if ct == pack_item.content_type:
            return e
    raise Http404


def _form_kwargs(entry, pack):
    """Return extra kwargs for forms that accept a ``pack`` parameter."""
    if entry.form_class is ContentFighterPackForm:
        return {"pack": pack}
    return {}


@login_required
@group_membership_required(["Custom Content"])
def add_pack_item(request, id, content_type_slug):
    """Add a new content item to a pack."""
    pack = get_object_or_404(CustomContentPack, id=id, owner=request.user)
    entry = _get_content_type_entry(content_type_slug)
    singular_label = entry.label.rstrip("s")
    is_fighter = entry.model_class is ContentFighter

    # Load fighter stat definitions for the form.
    stat_definitions = _get_fighter_stat_definitions() if is_fighter else None

    if request.method == "POST":
        form = entry.form_class(request.POST, **_form_kwargs(entry, pack))
        if form.is_valid():
            with transaction.atomic():
                content_obj = form.save(commit=False)
                content_obj._history_user = request.user
                content_obj.save()
                ct = ContentType.objects.get_for_model(entry.model_class)
                item = CustomContentPackItem(
                    pack=pack,
                    content_type=ct,
                    object_id=content_obj.pk,
                    owner=request.user,
                )
                item.save_with_user(user=request.user)
                if is_fighter:
                    _create_fighter_statline(
                        content_obj, stat_definitions, request.POST
                    )
            return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))
    else:
        form = entry.form_class(**_form_kwargs(entry, pack))

    context = {
        "form": form,
        "pack": pack,
        "label": singular_label,
        "icon": entry.icon,
        "slug": entry.slug,
    }
    if stat_definitions is not None:
        stat_context = []
        for ts in stat_definitions:
            field_name = ts.stat.field_name
            entry_dict = {
                "field_name": field_name,
                "short_name": ts.stat.short_name,
                "placeholder": _stat_placeholder(ts.stat),
            }
            if request.method == "POST":
                entry_dict["value"] = request.POST.get(f"stat_{field_name}", "")
            stat_context.append(entry_dict)
        context["stat_definitions"] = stat_context

    return render(request, "core/pack/pack_item_add.html", context)


@login_required
@group_membership_required(["Custom Content"])
def edit_pack_item(request, id, item_id):
    """Edit a content item in a pack."""
    pack = get_object_or_404(CustomContentPack, id=id, owner=request.user)
    pack_item = get_object_or_404(
        CustomContentPackItem.objects.select_related("content_type"),
        id=item_id,
        pack=pack,
        archived=False,
    )

    content_obj = pack_item.content_object
    if content_obj is None:
        raise Http404

    entry = _get_entry_for_pack_item(pack_item)
    if entry.form_class is None:
        raise Http404

    singular_label = entry.label.rstrip("s")
    is_fighter = entry.model_class is ContentFighter

    # Load fighter stat data for the form.
    stat_values = None
    if is_fighter and hasattr(content_obj, "custom_statline"):
        stat_values = [
            {
                "field_name": s.statline_type_stat.stat.field_name,
                "short_name": s.statline_type_stat.stat.short_name,
                "value": s.value,
                "placeholder": _stat_placeholder(s.statline_type_stat.stat),
            }
            for s in content_obj.custom_statline.stats.select_related(
                "statline_type_stat__stat"
            ).order_by("statline_type_stat__position")
        ]

    if request.method == "POST":
        form = entry.form_class(
            request.POST, instance=content_obj, **_form_kwargs(entry, pack)
        )
        if form.is_valid():
            form.instance._history_user = request.user
            form.save()
            if is_fighter and hasattr(content_obj, "custom_statline"):
                _update_fighter_stats(content_obj, request.POST)
            return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))
    else:
        form = entry.form_class(instance=content_obj, **_form_kwargs(entry, pack))

    context = {
        "form": form,
        "pack": pack,
        "pack_item": pack_item,
        "content_obj": content_obj,
        "label": singular_label,
        "icon": entry.icon,
    }
    # On POST re-render (validation error), use submitted values instead of DB values.
    if stat_values is not None and request.method == "POST":
        for sv in stat_values:
            sv["value"] = request.POST.get(f"stat_{sv['field_name']}", sv["value"])
    if stat_values is not None:
        context["stat_values"] = stat_values

    return render(request, "core/pack/pack_item_edit.html", context)


@login_required
@group_membership_required(["Custom Content"])
def delete_pack_item(request, id, item_id):
    """Archive a content item from a pack (soft-delete)."""
    pack = get_object_or_404(CustomContentPack, id=id, owner=request.user)
    pack_item = get_object_or_404(
        CustomContentPackItem.objects.select_related("content_type"),
        id=item_id,
        pack=pack,
        archived=False,
    )

    content_obj = pack_item.content_object
    if content_obj is None:
        raise Http404

    entry = _get_entry_for_pack_item(pack_item)
    label = entry.label.rstrip("s")
    icon = entry.icon

    if request.method == "POST":
        pack_item._history_user = request.user
        pack_item.archive()
        return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))

    return render(
        request,
        "core/pack/pack_item_delete.html",
        {
            "pack": pack,
            "pack_item": pack_item,
            "content_obj": content_obj,
            "label": label,
            "icon": icon,
        },
    )


@login_required
@group_membership_required(["Custom Content"])
def restore_pack_item(request, id, item_id):
    """Restore an archived content item in a pack."""
    if request.method != "POST":
        raise Http404

    pack = get_object_or_404(CustomContentPack, id=id, owner=request.user)
    pack_item = get_object_or_404(
        CustomContentPackItem.objects.select_related("content_type"),
        id=item_id,
        pack=pack,
        archived=True,
    )

    pack_item._history_user = request.user
    pack_item.unarchive()
    return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))


@login_required
@group_membership_required(["Custom Content"])
def pack_lists(request, id):
    """Manage which of the user's lists are subscribed to a content pack."""
    pack = get_object_or_404(
        CustomContentPack.objects.select_related("owner"),
        id=id,
    )
    user = request.user
    if not pack.listed and pack.owner != user:
        raise Http404

    user_lists = (
        List.objects.filter(owner=user, archived=False)
        .select_related("content_house")
        .order_by("name")
    )
    subscribed_list_ids = set(
        pack.subscribed_lists.filter(owner=user).values_list("id", flat=True)
    )
    unsubscribed_lists = [
        lst for lst in user_lists if lst.id not in subscribed_list_ids
    ]
    subscribed_lists = [lst for lst in user_lists if lst.id in subscribed_list_ids]

    return render(
        request,
        "core/pack/pack_lists.html",
        {
            "pack": pack,
            "is_owner": user == pack.owner,
            "subscribed_lists": subscribed_lists,
            "unsubscribed_lists": unsubscribed_lists,
        },
    )


@login_required
@group_membership_required(["Custom Content"])
def subscribe_pack(request, id):
    """Subscribe one of the user's lists to a content pack."""
    if request.method != "POST":
        raise Http404

    pack = get_object_or_404(CustomContentPack, id=id, archived=False)
    # Pack must be listed or owned by user
    if not pack.listed and pack.owner != request.user:
        raise Http404

    list_id = request.POST.get("list_id")
    if not list_id or not is_valid_uuid(list_id):
        messages.error(request, "Please select a list.")
        return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))

    lst = get_object_or_404(List, id=list_id, owner=request.user)
    lst.packs.add(pack)

    messages.success(request, f"Subscribed {lst.name} to {pack.name}")

    return_url = request.POST.get("return_url", "")
    if return_url == "pack-lists":
        return HttpResponseRedirect(reverse("core:pack-lists", args=(pack.id,)))
    return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))


@login_required
@group_membership_required(["Custom Content"])
def unsubscribe_pack(request, id):
    """Unsubscribe a list from a content pack."""
    if request.method != "POST":
        raise Http404

    pack = get_object_or_404(CustomContentPack, id=id)

    list_id = request.POST.get("list_id")
    if not list_id or not is_valid_uuid(list_id):
        raise Http404

    lst = get_object_or_404(List, id=list_id, owner=request.user)
    lst.packs.remove(pack)

    # Redirect back to where the user came from
    return_url = request.POST.get("return_url", "")
    if return_url == "list":
        messages.success(request, f"Unsubscribed from {pack.name}")
        return HttpResponseRedirect(reverse("core:list-packs", args=(lst.id,)))
    if return_url == "pack-lists":
        messages.success(request, f"Unsubscribed {lst.name} from {pack.name}")
        return HttpResponseRedirect(reverse("core:pack-lists", args=(pack.id,)))

    messages.success(request, f"Unsubscribed {lst.name} from {pack.name}")
    return HttpResponseRedirect(reverse("core:pack", args=(pack.id,)))


@login_required
@group_membership_required(["Custom Content"])
def list_packs_manage(request, id):
    """Manage content pack subscriptions for a list."""
    lst = get_object_or_404(List, id=id, owner=request.user)

    subscribed_packs = lst.packs.all().select_related("owner")

    # Available packs: listed packs or packs owned by user, excluding already subscribed
    available_packs = (
        CustomContentPack.objects.filter(archived=False)
        .exclude(id__in=subscribed_packs.values_list("id", flat=True))
        .filter(models.Q(listed=True) | models.Q(owner=request.user))
        .select_related("owner")
        .order_by("name")
    )

    # "Your Packs Only" filter — defaults to off (show all available packs)
    show_my_packs = request.GET.get("my", "0") == "1"
    if show_my_packs:
        available_packs = available_packs.filter(owner=request.user)

    search_query = request.GET.get("q", "").strip()
    if search_query:
        available_packs = available_packs.filter(name__icontains=search_query)

    if request.method == "POST":
        pack_id = request.POST.get("pack_id")
        action = request.POST.get("action")
        if pack_id and is_valid_uuid(pack_id) and action == "add":
            pack = get_object_or_404(CustomContentPack, id=pack_id, archived=False)
            if pack.listed or pack.owner == request.user:
                lst.packs.add(pack)
                messages.success(request, f"Subscribed to {pack.name}")
        return HttpResponseRedirect(reverse("core:list-packs", args=(lst.id,)))

    return render(
        request,
        "core/list_packs.html",
        {
            "list": lst,
            "subscribed_packs": subscribed_packs,
            "available_packs": available_packs,
            "search_query": search_query,
            "show_my_packs": show_my_packs,
        },
    )
