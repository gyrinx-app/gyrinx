from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouse,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentSkillCategory,
    ContentWeaponAccessory,
)
from gyrinx.core.forms.list import (
    AddInjuryForm,
    CloneListFighterForm,
    CloneListForm,
    EditFighterStateForm,
    EditListFighterNarrativeForm,
    EditListForm,
    ListFighterEquipmentAssignmentAccessoriesForm,
    ListFighterEquipmentAssignmentCostForm,
    ListFighterEquipmentAssignmentForm,
    ListFighterEquipmentAssignmentUpgradeForm,
    ListFighterSkillsForm,
    NewListFighterForm,
    NewListForm,
)
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    ListFighterInjury,
    ListFighterPsykerPowerAssignment,
    VirtualListFighterEquipmentAssignment,
    VirtualListFighterPsykerPowerAssignment,
)
from gyrinx.core.views import make_query_params_str
from gyrinx.models import QuerySetOf, is_int, is_valid_uuid


def make_list_queryset(request: HttpRequest, *, exclude_archived: bool = True):
    """
    Create a queryset for Lists based on the current request.

    This applies various filters including search queries and visibility rules.
    """
    qs: QuerySetOf[List] = List.objects.all()

    if exclude_archived:
        qs = qs.exclude(archived_at__isnull=False)

    # Annotate with custom house's existence
    user = request.user
    if user.is_authenticated:
        qs = qs.annotate(
            has_custom_house=Exists(
                ContentHouse.objects.filter(name=OuterRef("pk"), owner=user)
            )
        )

    # Apply search filters
    if query := request.GET.get("query"):
        sv = SearchVector("name", "owner__username", "content_house__name")
        sq = SearchQuery(query, search_type="plain")
        qs = qs.annotate(search=sv).filter(search=sq)

    # Apply house filter
    house_id = request.GET.get("house")
    if house_id and is_valid_uuid(house_id):
        qs = qs.filter(content_house=house_id)
    elif house_id == "custom" and user.is_authenticated:
        qs = qs.filter(has_custom_house=True)

    # Apply visibility filter
    visibility = request.GET.get("visibility", "all")
    user = request.user
    if visibility == "mine" and user.is_authenticated:
        qs = qs.filter(owner=user)
    elif visibility == "others" and user.is_authenticated:
        qs = qs.exclude(owner=user).filter(public=True)
    elif visibility == "public":
        qs = qs.filter(public=True)
    else:  # all
        if user.is_authenticated:
            qs = qs.filter(Q(public=True) | Q(owner=user))
        else:
            qs = qs.filter(public=True)

    return qs


class ListsListView(generic.ListView):
    """
    Display a list of :model:`core.List`.

    **Context**

    ``object_list``
        Filtered queryset of :model:`core.List` instances.

    **Template**

    :template:`core/lists.html`
    """

    template_name = "core/lists.html"
    paginate_by = 20
    context_object_name = "lists"

    def get_queryset(self):
        return make_list_queryset(self.request)

    def get_ordering(self):
        ordering = self.request.GET.get("ordering", "-created")
        # Basic validation to prevent SQL injection
        allowed_fields = ["name", "-name", "created", "-created", "owner", "-owner"]
        if ordering in allowed_fields:
            return ordering
        return "-created"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass visibility to maintain state
        context["current_visibility"] = self.request.GET.get("visibility", "all")
        context["current_house"] = self.request.GET.get("house", "")
        context["current_query"] = self.request.GET.get("query", "")
        context["current_ordering"] = self.request.GET.get("ordering", "-created")
        context["query_params"] = make_query_params_str(self.request)

        # Get list of houses for filter
        context["houses"] = ContentHouse.objects.all().order_by("name")

        return context


class ListDetailView(generic.DetailView):
    """
    Display a single :model:`core.List`.

    **Context**

    ``list``
        An instance of :model:`core.List`.

    **Template**

    :template:`core/list.html`
    """

    model = List
    template_name = "core/list.html"
    context_object_name = "list"
    pk_url_kwarg = "id"

    def get_queryset(self):
        # Allow viewing of public lists or lists owned by the current user
        if self.request.user.is_authenticated:
            return List.objects.filter(
                Q(public=True) | Q(owner=self.request.user)
            ).prefetch_related("fighters")
        else:
            return List.objects.filter(public=True).prefetch_related("fighters")


class ListAboutDetailView(generic.DetailView):
    """
    Display the narrative/about page for a :model:`core.List`.

    **Context**

    ``list``
        An instance of :model:`core.List`.

    **Template**

    :template:`core/list_about.html`
    """

    model = List
    template_name = "core/list_about.html"
    context_object_name = "list"
    pk_url_kwarg = "id"

    def get_queryset(self):
        # Allow viewing of public lists or lists owned by the current user
        if self.request.user.is_authenticated:
            return List.objects.filter(Q(public=True) | Q(owner=self.request.user))
        else:
            return List.objects.filter(public=True)


class ListPrintView(generic.DetailView):
    """
    Display a print-friendly version of :model:`core.List`.

    **Context**

    ``list``
        An instance of :model:`core.List`.

    **Template**

    :template:`core/list_print.html`
    """

    model = List
    template_name = "core/list_print.html"
    context_object_name = "list"
    pk_url_kwarg = "id"

    def get_queryset(self):
        # Allow viewing of public lists or lists owned by the current user
        if self.request.user.is_authenticated:
            return List.objects.filter(
                Q(public=True) | Q(owner=self.request.user)
            ).prefetch_related("fighters")
        else:
            return List.objects.filter(public=True).prefetch_related("fighters")


class ListArchivedFightersView(generic.DetailView):
    """
    Display archived fighters for a :model:`core.List`.

    **Context**

    ``list``
        An instance of :model:`core.List`.
    ``fighters``
        Archived fighters in the list.

    **Template**

    :template:`core/list_archived_fighters.html`
    """

    model = List
    template_name = "core/list_archived_fighters.html"
    context_object_name = "list"
    pk_url_kwarg = "id"

    def get_queryset(self):
        # Only owners can view archived fighters
        return List.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fighters"] = self.object.fighters.filter(
            archived_at__isnull=False
        ).order_by("-archived_at")
        return context


@login_required
def new_list(request):
    """
    Create a new :model:`core.List`.

    **Context**

    ``form``
        An instance of :form:`core.NewListForm`.

    **Template**

    :template:`core/list_new.html`
    """
    if request.method == "POST":
        form = NewListForm(request.POST)
        if form.is_valid():
            lst = form.save(commit=False)
            lst.owner = request.user
            lst.save()
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = NewListForm()

    return render(request, "core/list_new.html", {"form": form})


@login_required
def edit_list(request, id):
    """
    Edit an existing :model:`core.List`.

    **Context**

    ``list``
        The :model:`core.List` being edited.
    ``form``
        An instance of :form:`core.EditListForm`.

    **Template**

    :template:`core/list_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)

    if request.method == "POST":
        form = EditListForm(request.POST, instance=lst)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditListForm(instance=lst)

    return render(request, "core/list_edit.html", {"list": lst, "form": form})


@login_required
def clone_list(request, id):
    """
    Clone an existing :model:`core.List`.

    **Context**

    ``original_list``
        The :model:`core.List` being cloned.
    ``form``
        An instance of :form:`core.CloneListForm`.

    **Template**

    :template:`core/list_clone.html`
    """
    original_list = get_object_or_404(List, id=id)

    # Check if user can view this list
    if not original_list.public and original_list.owner != request.user:
        return HttpResponseRedirect(reverse("core:lists"))

    if request.method == "POST":
        form = CloneListForm(request.POST)
        if form.is_valid():
            new_list = original_list.clone()
            new_list.name = form.cleaned_data["name"]
            new_list.owner = request.user
            new_list.public = form.cleaned_data["public"]
            new_list.save()
            return HttpResponseRedirect(reverse("core:list", args=(new_list.id,)))
    else:
        form = CloneListForm(initial={"name": f"{original_list.name} (Clone)"})

    return render(
        request, "core/list_clone.html", {"original_list": original_list, "form": form}
    )


@login_required
def new_list_fighter(request, id):
    """
    Create a new :model:`core.ListFighter` for a list.

    **Context**

    ``list``
        The :model:`core.List` that will own this fighter.
    ``form``
        An instance of :form:`core.NewListFighterForm`.

    **Template**

    :template:`core/list_fighter_new.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)

    if request.method == "POST":
        form = NewListFighterForm(lst.content_house, request.POST)
        if form.is_valid():
            fighter = form.save(commit=False)
            fighter.list = lst
            fighter.owner = request.user
            fighter.save()

            # Apply default assignments if it's a content fighter
            if fighter.content_fighter:
                fighter.apply_defaults()

            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = NewListFighterForm(lst.content_house)

    return render(request, "core/list_fighter_new.html", {"list": lst, "form": form})


@login_required
def edit_list_fighter(request, id, fighter_id):
    """
    Edit a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``form``
        An instance of Django's ModelForm for ListFighter.
    ``xp_form``
        An instance of :form:`core.EditFighterXPForm`.

    **Template**

    :template:`core/list_fighter_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        form = ListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            updated_fighter = form.save(commit=False)
            # Handle cost override
            cost_override = form.cleaned_data.get("cost_override")
            if cost_override is not None and cost_override >= 0:
                updated_fighter.cost_override = cost_override
            else:
                updated_fighter.cost_override = None
            
            # Handle stat overrides
            for stat in ["movement", "weapon_skill", "ballistic_skill", "strength", 
                        "toughness", "wounds", "initiative", "attacks", "leadership", 
                        "cool", "willpower", "intelligence"]:
                override_field = f"{stat}_override"
                value = form.cleaned_data.get(override_field)
                if value is not None and value >= 0:
                    setattr(updated_fighter, override_field, value)
                else:
                    setattr(updated_fighter, override_field, None)
            
            updated_fighter.save()
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        # Create form with initial data including overrides
        initial_data = {}
        if fighter.cost_override is not None:
            initial_data["cost_override"] = fighter.cost_override
        
        for stat in ["movement", "weapon_skill", "ballistic_skill", "strength", 
                    "toughness", "wounds", "initiative", "attacks", "leadership", 
                    "cool", "willpower", "intelligence"]:
            override_field = f"{stat}_override"
            value = getattr(fighter, override_field, None)
            if value is not None:
                initial_data[override_field] = value
                
        form = ListFighterForm(instance=fighter, initial=initial_data)

    xp_form = EditFighterXPForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "form": form,
            "xp_form": xp_form,
        },
    )


@login_required
def clone_list_fighter(request, id, fighter_id):
    """
    Clone a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns the fighter.
    ``original_fighter``
        The :model:`core.ListFighter` being cloned.
    ``form``
        An instance of :form:`core.CloneListFighterForm`.

    **Template**

    :template:`core/list_fighter_clone.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    original_fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        form = CloneListFighterForm(request.POST)
        if form.is_valid():
            new_fighter = original_fighter.clone()
            new_fighter.name = form.cleaned_data["name"]
            new_fighter.save()
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = CloneListFighterForm(
            initial={"name": f"{original_fighter.name} (Clone)"}
        )

    return render(
        request,
        "core/list_fighter_clone.html",
        {"list": lst, "original_fighter": original_fighter, "form": form},
    )


@login_required
def archive_list_fighter(request, id, fighter_id):
    """
    Archive a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to be archived.

    **Template**

    :template:`core/list_fighter_archive.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    if request.method == "POST":
        fighter.archive()
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_archive.html",
        {"list": lst, "fighter": fighter},
    )


@login_required
def delete_list_fighter(request, id, fighter_id):
    """
    Delete a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to be deleted.

    **Template**

    :template:`core/list_fighter_delete.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        fighter.delete()
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request, "core/list_fighter_delete.html", {"list": lst, "fighter": fighter}
    )


@login_required
def edit_list_fighter_skills(request, id, fighter_id):
    """
    Edit skills for a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` whose skills are being edited.
    ``form``
        An instance of :form:`core.ListFighterSkillsForm`.

    **Template**

    :template:`core/list_fighter_skills_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        form = ListFighterSkillsForm(request.POST, instance=fighter, house=lst.content_house)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = ListFighterSkillsForm(instance=fighter, house=lst.content_house)

    return render(
        request,
        "core/list_fighter_skills_edit.html",
        {"list": lst, "fighter": fighter, "form": form},
    )


from gyrinx.core.forms.list import ListFighterPsykerPowersForm


@login_required
def edit_list_fighter_powers(request, id, fighter_id):
    """
    Edit pskyer powers for a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` whose psyker powers are being edited.
    ``form``
        An instance of :form:`core.ListFighterPsykerPowersForm`.

    **Template**

    :template:`core/list_fighter_psyker_powers_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    # Check if the fighter is actually a psyker
    if not fighter.is_psyker_cached:
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = ListFighterPsykerPowersForm(request.POST, instance=fighter)
        if form.is_valid():
            # Remove existing powers
            fighter.psyker_powers.all().delete()

            # Add selected powers
            for power in form.cleaned_data["powers"]:
                ListFighterPsykerPowerAssignment.objects.create(
                    list_fighter=fighter,
                    psyker_power=power,
                    owner=request.user,
                )

            # Save the disabled default powers
            fighter.disabled_pskyer_default_powers = form.cleaned_data.get(
                "disabled_default_powers", []
            )
            fighter.save()

            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = ListFighterPsykerPowersForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_psyker_powers_edit.html",
        {"list": lst, "fighter": fighter, "form": form},
    )


@login_required
def edit_list_fighter_narrative(request, id, fighter_id):
    """
    Edit narrative for a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` whose narrative is being edited.
    ``form``
        An instance of :form:`core.EditListFighterNarrativeForm`.

    **Template**

    :template:`core/list_fighter_narrative_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        form = EditListFighterNarrativeForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditListFighterNarrativeForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_narrative_edit.html",
        {"list": lst, "fighter": fighter, "form": form},
    )


def embed_list_fighter(request, id, fighter_id):
    """
    Display an embeddable version of a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to embed.

    **Template**

    :template:`core/list_fighter_embed.html`
    """
    lst = get_object_or_404(List, id=id, public=True)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    return render(
        request,
        "core/list_fighter_embed.html",
        {"list": lst, "fighter": fighter, "print": True},
    )


from django import forms
from django.contrib import messages

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighterState


class ListFighterForm(forms.ModelForm):
    """Form for editing ListFighter model"""

    cost_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the calculated cost for this fighter",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    
    # Stat override fields
    movement_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the movement value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    weapon_skill_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the weapon skill value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    ballistic_skill_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the ballistic skill value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    strength_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the strength value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    toughness_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the toughness value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    wounds_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the wounds value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    initiative_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the initiative value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    attacks_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the attacks value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    leadership_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the leadership value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    cool_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the cool value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    willpower_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the willpower value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    intelligence_override = forms.IntegerField(
        required=False,
        min_value=0,
        help_text="Override the intelligence value",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = ListFighter
        fields = ["name", "narrative"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "narrative": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


@login_required
def edit_list_fighter_equipment(request, id, fighter_id, is_weapon):
    """
    Edit equipment for a :model:`core.ListFighter`.

    Handles both weapons and gear based on the is_weapon parameter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` whose equipment is being edited.
    ``assignments``
        Current equipment assignments for the fighter.
    ``form``
        An instance of :form:`core.ListFighterEquipmentAssignmentForm`.
    ``is_weapon``
        Boolean indicating if editing weapons (True) or gear (False).

    **Template**

    :template:`core/list_fighter_weapons_edit.html` or
    :template:`core/list_fighter_gear_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    # Get categories based on type
    if is_weapon:
        categories = ContentEquipmentCategory.WEAPON_CATEGORIES
        template = "core/list_fighter_weapons_edit.html"
    else:
        categories = ContentEquipmentCategory.GEAR_CATEGORIES
        template = "core/list_fighter_gear_edit.html"

    # Get virtual equipment assignments for this fighter
    assignments = fighter.virtual_equipment_assignments(
        categories=categories, include_linked_equipment=False
    )

    if request.method == "POST":
        form = ListFighterEquipmentAssignmentForm(
            request.POST,
            categories=categories,
            content_house=lst.content_house,
            list_fighter=fighter,
        )
        if form.is_valid():
            equipment = form.cleaned_data["equipment"]

            # Check if this equipment is already assigned (not from defaults)
            existing = ListFighterEquipmentAssignment.objects.filter(
                list_fighter=fighter,
                content_equipment=equipment,
                from_default_assignment=False,
            ).first()

            if not existing:
                assignment = ListFighterEquipmentAssignment.objects.create(
                    list_fighter=fighter,
                    content_equipment=equipment,
                    owner=request.user,
                )
                # Handle weapon profiles for weapons
                if equipment.weapon_profiles.exists():
                    # Add all weapon profiles
                    assignment.weapon_profiles.set(equipment.weapon_profiles.all())

            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#fighter-{fighter.id}"
            )
    else:
        form = ListFighterEquipmentAssignmentForm(
            categories=categories,
            content_house=lst.content_house,
            list_fighter=fighter,
        )

    return render(
        request,
        template,
        {
            "list": lst,
            "fighter": fighter,
            "assignments": assignments,
            "form": form,
            "is_weapon": is_weapon,
        },
    )


@login_required
def edit_list_fighter_weapon_accessories(request, id, fighter_id, assign_id):
    """
    Edit weapon accessories for a :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assignment``
        The :model:`core.ListFighterEquipmentAssignment` being edited.
    ``form``
        An instance of :form:`core.ListFighterEquipmentAssignmentAccessoriesForm`.

    **Template**

    :template:`core/list_fighter_weapons_accessories_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Get the assignment - could be real or virtual
    virtual_assignments = fighter.virtual_equipment_assignments(include_linked_equipment=False)
    assignment = None

    for va in virtual_assignments:
        if str(va.pk) == str(assign_id):
            assignment = va
            break

    if not assignment:
        # TODO: Handle error
        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    if request.method == "POST":
        form = ListFighterEquipmentAssignmentAccessoriesForm(
            request.POST, equipment=assignment.content_equipment
        )
        if form.is_valid():
            # If this is a virtual assignment from defaults, we need to create a real one
            if isinstance(assignment, VirtualListFighterEquipmentAssignment):
                real_assignment = ListFighterEquipmentAssignment.objects.create(
                    list_fighter=fighter,
                    content_equipment=assignment.content_equipment,
                    from_default_assignment=True,
                    owner=request.user,
                )
                # Copy over weapon profiles
                real_assignment.weapon_profiles.set(assignment.weapon_profiles.all())
                assignment = real_assignment

            # Update accessories
            assignment.weapon_accessories.set(form.cleaned_data["accessories"])

            return HttpResponseRedirect(
                reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
            )
    else:
        # Get current accessories
        current_accessories = []
        if hasattr(assignment, "weapon_accessories"):
            current_accessories = assignment.weapon_accessories.all()

        form = ListFighterEquipmentAssignmentAccessoriesForm(
            equipment=assignment.content_equipment,
            initial={"accessories": current_accessories},
        )

    return render(
        request,
        "core/list_fighter_weapons_accessories_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assignment": assignment,
            "form": form,
        },
    )


@login_required
def delete_list_fighter_weapon_accessory(
    request, id, fighter_id, assign_id, accessory_id
):
    """
    Remove a weapon accessory from a :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assignment``
        The :model:`core.ListFighterEquipmentAssignment` being modified.
    ``accessory``
        The :model:`content.ContentWeaponAccessory` to be removed.

    **Template**

    :template:`core/list_fighter_weapon_accessory_delete.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Get the real assignment
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment, pk=assign_id, list_fighter=fighter
    )
    accessory = get_object_or_404(ContentWeaponAccessory, pk=accessory_id)

    if request.method == "POST":
        assignment.weapon_accessories.remove(accessory)
        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_weapon_accessory_delete.html",
        {
            "list": lst,
            "fighter": fighter,
            "assignment": assignment,
            "accessory": accessory,
        },
    )


@login_required
def disable_list_fighter_default_assign(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Disable a default equipment assignment for a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``default_assignment``
        The :model:`content.ContentFighterDefaultAssignment` to be disabled.

    **Template**

    :template:`core/list_fighter_assign_disable.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Find the default assignment
    default_assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
        content_fighter=fighter.content_fighter,
    )

    if request.method == "POST":
        # Add to disabled defaults
        fighter.disabled_default_assignments.add(default_assignment)
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_disable.html",
        {
            "list": lst,
            "fighter": fighter,
            "default_assignment": default_assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def convert_list_fighter_default_assign(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Convert a default equipment assignment to a regular assignment.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``default_assignment``
        The :model:`content.ContentFighterDefaultAssignment` to be converted.

    **Template**

    :template:`core/list_fighter_assign_convert.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Find the default assignment
    default_assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
        content_fighter=fighter.content_fighter,
    )

    if request.method == "POST":
        # Create a real assignment from the default
        assignment = ListFighterEquipmentAssignment.objects.create(
            list_fighter=fighter,
            content_equipment=default_assignment.content_equipment,
            from_default_assignment=True,
            owner=request.user,
        )
        # Copy weapon profiles
        assignment.weapon_profiles.set(default_assignment.weapon_profiles.all())
        # Copy weapon accessories
        assignment.weapon_accessories.set(default_assignment.weapon_accessories.all())

        # Disable the default
        fighter.disabled_default_assignments.add(default_assignment)

        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_convert.html",
        {
            "list": lst,
            "fighter": fighter,
            "default_assignment": default_assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def edit_list_fighter_assign_cost(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit the cost override for a :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The equipment assignment (real or virtual).
    ``form``
        An instance of :form:`core.ListFighterEquipmentAssignmentCostForm`.

    **Template**

    :template:`core/list_fighter_assign_cost_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Get the assignment - could be real or virtual
    virtual_assignments = fighter.virtual_equipment_assignments(include_linked_equipment=False)
    assignment = None

    for va in virtual_assignments:
        if str(va.pk) == str(assign_id):
            assignment = va
            break

    if not assignment:
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    error_message = None

    if request.method == "POST":
        form = ListFighterEquipmentAssignmentCostForm(request.POST)
        if form.is_valid():
            cost_override = form.cleaned_data["cost_override"]

            # If this is a virtual assignment, we need to create a real one
            if isinstance(assignment, VirtualListFighterEquipmentAssignment):
                real_assignment = ListFighterEquipmentAssignment.objects.create(
                    list_fighter=fighter,
                    content_equipment=assignment.content_equipment,
                    from_default_assignment=True,
                    cost_override=cost_override if cost_override >= 0 else None,
                    owner=request.user,
                )
                # Copy over weapon profiles and accessories
                real_assignment.weapon_profiles.set(assignment.weapon_profiles.all())
                if hasattr(assignment, "weapon_accessories"):
                    real_assignment.weapon_accessories.set(
                        assignment.weapon_accessories.all()
                    )
            else:
                # Update existing assignment
                if cost_override >= 0:
                    assignment.cost_override = cost_override
                else:
                    assignment.cost_override = None
                assignment.save()

            return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))
    else:
        # Initialize form with current cost override
        initial_cost = None
        if hasattr(assignment, "cost_override") and assignment.cost_override is not None:
            initial_cost = assignment.cost_override

        form = ListFighterEquipmentAssignmentCostForm(
            initial={"cost_override": initial_cost}
        )

    return render(
        request,
        "core/list_fighter_assign_cost_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "form": form,
            "error_message": error_message,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def delete_list_fighter_assign(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Remove a :model:`core.ListFighterEquipmentAssignment` from a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.

    **Template**

    :template:`core/list_fighter_assign_delete_confirm.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    if request.method == "POST":
        assignment.delete()
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def delete_list_fighter_gear_upgrade(
    request, id, fighter_id, assign_id, upgrade_id, back_name, action_name
):
    """
    Remove am upgrade from a :model:`core.ListFighterEquipmentAssignment` for a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.
    ``upgrade``
        The :model:`content.ContentEquipmentUpgrade` upgrade to be removed.

    **Template**

    :template:`core/list_fighter_assign_upgrade_delete_confirm.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )
    upgrade = get_object_or_404(
        ContentEquipmentUpgrade,
        pk=upgrade_id,
    )

    if request.method == "POST":
        assignment.upgrades.remove(upgrade)
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_upgrade_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "upgrade": upgrade,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def edit_list_fighter_weapon_upgrade(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit equipment upgrades for a :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assignment``
        The equipment assignment (real or virtual).
    ``form``
        An instance of :form:`core.ListFighterEquipmentAssignmentUpgradeForm`.
    ``error_message``
        Optional error message to display.

    **Template**

    :template:`core/list_fighter_assign_upgrade_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Get the assignment - could be real or virtual
    virtual_assignments = fighter.virtual_equipment_assignments(include_linked_equipment=False)
    assignment = None

    for va in virtual_assignments:
        if str(va.pk) == str(assign_id):
            assignment = va
            break

    if not assignment:
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    error_message = None

    if request.method == "POST":
        form = ListFighterEquipmentAssignmentUpgradeForm(
            request.POST, equipment=assignment.content_equipment
        )
        if form.is_valid():
            selected_upgrades = form.cleaned_data["upgrades"]

            # If this is a virtual assignment, we need to create a real one
            if isinstance(assignment, VirtualListFighterEquipmentAssignment):
                real_assignment = ListFighterEquipmentAssignment.objects.create(
                    list_fighter=fighter,
                    content_equipment=assignment.content_equipment,
                    from_default_assignment=True,
                    owner=request.user,
                )
                # Copy over weapon profiles and accessories
                real_assignment.weapon_profiles.set(assignment.weapon_profiles.all())
                if hasattr(assignment, "weapon_accessories"):
                    real_assignment.weapon_accessories.set(
                        assignment.weapon_accessories.all()
                    )
                assignment = real_assignment

            # Check for conflicting upgrades
            upgrade_names = set()
            for upgrade in selected_upgrades:
                if upgrade.name in upgrade_names:
                    error_message = f"Cannot select multiple upgrades with the same name: {upgrade.name}"
                    break
                upgrade_names.add(upgrade.name)

            if not error_message:
                # Update upgrades
                assignment.upgrades.set(selected_upgrades)
                return HttpResponseRedirect(
                    reverse(back_name, args=(lst.id, fighter.id))
                )
    else:
        # Get current upgrades
        current_upgrades = []
        if hasattr(assignment, "upgrades"):
            current_upgrades = assignment.upgrades.all()

        form = ListFighterEquipmentAssignmentUpgradeForm(
            equipment=assignment.content_equipment, initial={"upgrades": current_upgrades}
        )

    return render(
        request,
        "core/list_fighter_assign_upgrade_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assignment": assignment,
            "form": form,
            "error_message": error_message,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


from gyrinx.content.models import ContentInjury


@login_required
def list_fighter_injuries_edit(request, id, fighter_id):
    """
    View and manage injuries for a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` whose injuries are being managed.
    ``injuries``
        The fighter's current injuries.
    ``available_injuries``
        All available injuries that can be applied.

    **Template**

    :template:`core/list_fighter_injuries_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    injuries = fighter.injuries.filter(archived=False).select_related("injury")
    available_injuries = ContentInjury.objects.all().order_by("name")

    return render(
        request,
        "core/list_fighter_injuries_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "injuries": injuries,
            "available_injuries": available_injuries,
        },
    )


@login_required
def list_fighter_add_injury(request, id, fighter_id):
    """
    Add an injury to a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to add the injury to.
    ``form``
        An instance of :form:`core.AddInjuryForm`.

    **Template**

    :template:`core/list_fighter_add_injury.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        form = AddInjuryForm(request.POST)
        if form.is_valid():
            injury = form.cleaned_data["injury"]

            # Create the injury assignment
            ListFighterInjury.objects.create(
                list_fighter=fighter,
                injury=injury,
                owner=request.user,
            )

            # If this is a campaign list, log the action
            if lst.campaign:
                action_desc = f"{fighter.name} suffered {injury.name}"
                outcome = injury.description if injury.description else ""

                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=lst.campaign,
                    list=lst,
                    description=action_desc,
                    outcome=outcome,
                )

            messages.success(request, f"Added {injury.name} to {fighter.name}")
            return HttpResponseRedirect(
                reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
            )
    else:
        form = AddInjuryForm()

    return render(
        request,
        "core/list_fighter_add_injury.html",
        {
            "list": lst,
            "fighter": fighter,
            "form": form,
        },
    )


@login_required
def list_fighter_remove_injury(request, id, fighter_id, injury_id):
    """
    Remove an injury from a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to remove the injury from.
    ``injury_assignment``
        The :model:`core.ListFighterInjury` to remove.

    **Template**

    :template:`core/list_fighter_remove_injury.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)
    injury_assignment = get_object_or_404(
        ListFighterInjury, id=injury_id, list_fighter=fighter
    )

    if request.method == "POST":
        injury_name = injury_assignment.injury.name

        # Archive the injury instead of deleting
        injury_assignment.archived = True
        injury_assignment.save()

        # If this is a campaign list, log the action
        if lst.campaign:
            action_desc = f"{fighter.name} recovered from {injury_name}"

            CampaignAction.objects.create(
                user=request.user,
                owner=request.user,
                campaign=lst.campaign,
                list=lst,
                description=action_desc,
                outcome="",
            )

        messages.success(request, f"Removed {injury_name} from {fighter.name}")
        return HttpResponseRedirect(
            reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_remove_injury.html",
        {
            "list": lst,
            "fighter": fighter,
            "injury_assignment": injury_assignment,
        },
    )


@login_required
def list_fighter_state_edit(request, id, fighter_id):
    """
    Edit the state of a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` whose state is being edited.
    ``form``
        An instance of :form:`core.EditFighterStateForm`.

    **Template**

    :template:`core/list_fighter_state_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        form = EditFighterStateForm(request.POST)
        if form.is_valid():
            new_state = form.cleaned_data["state"]
            old_state = fighter.state

            # Update the fighter's state
            fighter.state = new_state
            fighter.save_with_user(user=request.user)

            # If this is a campaign list, log the action
            if lst.campaign and old_state != new_state:
                # Get human-readable state names
                old_state_display = dict(ListFighterState.choices).get(
                    old_state, old_state
                )
                new_state_display = dict(ListFighterState.choices).get(
                    new_state, new_state
                )

                action_desc = (
                    f"{fighter.name} state changed from {old_state_display} "
                    f"to {new_state_display}"
                )

                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=lst.campaign,
                    list=lst,
                    description=action_desc,
                    outcome="",
                )

            messages.success(request, f"Updated state for {fighter.name}")
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditFighterStateForm(initial={"state": fighter.state})

    return render(
        request,
        "core/list_fighter_state_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "form": form,
        },
    )


from gyrinx.core.forms.list import EditFighterXPForm


@login_required
def edit_list_fighter_xp(request, id, fighter_id):
    """
    Edit XP for a :model:`core.ListFighter`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` whose XP is being edited.
    ``form``
        An instance of :form:`core.EditFighterXPForm`.

    **Template**

    :template:`core/list_fighter_xp_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    if request.method == "POST":
        form = EditFighterXPForm(request.POST, fighter=fighter)
        if form.is_valid():
            operation = form.cleaned_data["operation"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data.get("description", "")

            # Validate the operation
            if operation == "spend" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot spend more XP than available ({fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot reduce XP below zero (current: {fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_total:
                form.add_error(
                    "amount",
                    f"Cannot reduce total XP below zero (total: {fighter.xp_total})",
                )
            else:
                # Apply the XP change
                if operation == "add":
                    fighter.xp_current += amount
                    fighter.xp_total += amount
                    action_desc = f"Added {amount} XP for {fighter.name}"
                elif operation == "spend":
                    fighter.xp_current -= amount
                    action_desc = f"Spent {amount} XP for {fighter.name}"
                elif operation == "reduce":
                    fighter.xp_current -= amount
                    fighter.xp_total -= amount
                    action_desc = f"Reduced {amount} XP for {fighter.name}"

                fighter.save_with_user(user=request.user)

                # Add description if provided
                if description:
                    action_desc += f" - {description}"

                # Log to campaign action
                if lst.campaign:
                    outcome = f"Current: {fighter.xp_current} XP, Total: {fighter.xp_total} XP"
                    CampaignAction.objects.create(
                        user=request.user,
                        owner=request.user,
                        campaign=lst.campaign,
                        list=lst,
                        description=action_desc,
                        outcome=outcome,
                    )

                messages.success(request, f"XP updated for {fighter.name}")
                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditFighterXPForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_xp_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


class ListCampaignClonesView(generic.DetailView):
    """
    Display all campaign clones of a list.
    
    Shows a table of all campaign versions of this list with their campaign status.
    """
    model = List
    template_name = "core/list_campaign_clones.html"
    context_object_name = "list"
    pk_url_kwarg = "id"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all campaign clones of this list
        context["clones"] = self.object.active_campaign_clones.select_related(
            "campaign", "campaign__owner"
        ).order_by("-created")
        return context