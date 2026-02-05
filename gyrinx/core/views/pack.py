"""Pack list, detail, and CRUD views."""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.content.models.house import ContentHouse
from gyrinx.core.forms.pack import PackForm
from gyrinx.core.models.pack import CustomContentPack
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
