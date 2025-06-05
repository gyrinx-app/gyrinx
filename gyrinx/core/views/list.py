from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchVector
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
    CloneListFighterForm,
    CloneListForm,
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
    ListFighterPsykerPowerAssignment,
    VirtualListFighterEquipmentAssignment,
    VirtualListFighterPsykerPowerAssignment,
)
from gyrinx.core.views import make_query_params_str
from gyrinx.models import QuerySetOf, is_int, is_valid_uuid


class ListsListView(generic.ListView):
    """
    Display a list of public :model:`core.List` objects.

    **Context**

    ``lists``
        A list of :model:`core.List` objects where `public=True`.

    **Template**

    :template:`core/lists.html`
    """

    template_name = "core/lists.html"
    context_object_name = "lists"

    def get_queryset(self):
        """
        Return :model:`core.List` objects that are public and in list building mode.
        Campaign mode lists are only visible within their campaigns.
        """
        return List.objects.filter(public=True, status=List.LIST_BUILDING)


class ListDetailView(generic.DetailView):
    """
    Display a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.

    **Template**

    :template:`core/list.html`
    """

    template_name = "core/list.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])


class ListAboutDetailView(generic.DetailView):
    """
    Display a narrative view of a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.

    **Template**

    :template:`core/list_about.html`
    """

    template_name = "core/list_about.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])


class ListPrintView(generic.DetailView):
    """
    Display a printable view of a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.

    **Template**

    :template:`core/list_print.html`
    """

    template_name = "core/list_print.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])


@login_required
def new_list(request):
    """
    Create a new :model:`core.List` owned by the current user.

    **Context**

    ``form``
        A NewListForm for entering the name and details of the new list.
    ``houses``
        A queryset of :model:`content.ContentHouse` objects, possibly used in the form display.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_new.html`
    """
    houses = ContentHouse.objects.all()

    error_message = None
    if request.method == "POST":
        form = NewListForm(request.POST)
        if form.is_valid():
            list_ = form.save(commit=False)
            list_.owner = request.user
            list_.save()
            return HttpResponseRedirect(reverse("core:list", args=(list_.id,)))
    else:
        form = NewListForm(
            initial={
                "name": request.GET.get("name", ""),
            }
        )

    return render(
        request,
        "core/list_new.html",
        {"form": form, "houses": houses, "error_message": error_message},
    )


@login_required
def edit_list(request, id):
    """
    Edit an existing :model:`core.List` owned by the current user.

    **Context**

    ``form``
        A EditListForm for editing the list's details.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_edit.html`
    """
    list_ = get_object_or_404(List, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = EditListForm(request.POST, instance=list_)
        if form.is_valid():
            updated_list = form.save(commit=False)
            updated_list.save()
            return HttpResponseRedirect(reverse("core:list", args=(list_.id,)))
    else:
        form = EditListForm(instance=list_)

    return render(
        request,
        "core/list_edit.html",
        {"form": form, "error_message": error_message},
    )


@login_required
def clone_list(request, id):
    """
    Clone an existing :model:`core.List` owned by any user.

    **Context**

    ``form``
        A CloneListForm for entering the name and details of the new list.
    ``list``
        The :model:`core.List` to be cloned.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_clone.html`
    """
    # You can clone a list owned by another user
    list_ = get_object_or_404(List, id=id)

    error_message = None
    if request.method == "POST":
        form = CloneListForm(request.POST, instance=list_)
        if form.is_valid():
            new_list = list_.clone(
                name=form.cleaned_data["name"],
                owner=request.user,
                public=form.cleaned_data["public"],
            )
            new_list.save()
            return HttpResponseRedirect(reverse("core:list", args=(new_list.id,)))
    else:
        form = CloneListForm(
            instance=list_,
            initial={
                "name": f"{list_.name} (Clone)",
            },
        )

    return render(
        request,
        "core/list_clone.html",
        {"form": form, "list": list_, "error_message": error_message},
    )


@login_required
def new_list_fighter(request, id):
    """
    Add a new :model:`core.ListFighter` to an existing :model:`core.List`.

    **Context**

    ``form``
        A NewListFighterForm for adding a new fighter.
    ``list``
        The :model:`core.List` to which this fighter will be added.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_new.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = ListFighter(list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = NewListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            fighter = form.save(commit=False)
            fighter.list = lst
            fighter.owner = lst.owner
            fighter.save()
            query_params = urlencode(dict(flash=fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )
    else:
        form = NewListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_new.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter(request, id, fighter_id):
    """
    Edit an existing :model:`core.ListFighter` within a :model:`core.List`.

    **Context**

    ``form``
        A NewListFighterForm for editing fighter details.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_edit.html`
    """
    print(f"Editing fighter {fighter_id} in list {id}")
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = NewListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            fighter = form.save(commit=False)
            fighter.list = lst
            fighter.owner = lst.owner
            fighter.save()
            query_params = urlencode(dict(flash=fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )
    else:
        form = NewListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def clone_list_fighter(request: HttpRequest, id, fighter_id):
    """
    Clone an existing :model:`core.ListFighter` to the same or another :model:`core.List`.

    **Context**

    ``form``
        A CloneListFighterForm for entering the name and details of the new fighter.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to be cloned.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_clone.html`
    """
    lst = get_object_or_404(List, id=id)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    error_message = None
    if request.method == "POST":
        form = CloneListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            new_fighter = fighter.clone(
                name=form.cleaned_data["name"],
                content_fighter=form.cleaned_data["content_fighter"],
                list=form.cleaned_data["list"],
            )
            new_fighter.save()
            query_params = urlencode(dict(flash=new_fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(new_fighter.list.id,))
                + f"?{query_params}"
                + f"#{str(new_fighter.id)}"
            )
    else:
        form = CloneListFighterForm(
            instance=fighter,
            initial={"name": f"{fighter.name} (Clone)"},
            user=request.user,
        )

    return render(
        request,
        "core/list_fighter_clone.html",
        {"form": form, "list": lst, "fighter": fighter, "error_message": error_message},
    )


@login_required
def edit_list_fighter_skills(request, id, fighter_id):
    """
    Edit the skills of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterSkillsForm for selecting fighter skills.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_skills_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterSkillsForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )
    else:
        form = ListFighterSkillsForm(instance=fighter)

    skill_cats = ContentSkillCategory.objects.filter(restricted=False).annotate(
        primary=Exists(
            ContentSkillCategory.primary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
        secondary=Exists(
            ContentSkillCategory.secondary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
    )
    special_cats = fighter.content_fighter.house.skill_categories.all().annotate(
        primary=Exists(
            ContentSkillCategory.primary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
        secondary=Exists(
            ContentSkillCategory.secondary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
    )
    n_cats = skill_cats.count() + special_cats.count()

    return render(
        request,
        "core/list_fighter_skills_edit.html",
        {
            "form": form,
            "list": lst,
            "error_message": error_message,
            "n_cats": n_cats,
            "skill_cats": list(skill_cats),
            "special_cats": list(special_cats),
        },
    )


@login_required
def edit_list_fighter_powers(request, id, fighter_id):
    """
    Edit the psyker powers of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterPowersForm for selecting fighter powers.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_psyker_powers_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        power_id = request.POST.get("psyker_power_id", None)
        if not power_id:
            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

        if request.POST.get("action") == "remove":
            kind = request.POST.get("assign_kind")
            if kind == "default":
                default_assign = get_object_or_404(
                    ContentFighterPsykerPowerDefaultAssignment,
                    psyker_power=power_id,
                    fighter=fighter.content_fighter_cached,
                )
                fighter.disabled_pskyer_default_powers.add(default_assign)
                fighter.save()
                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            elif kind == "assigned":
                assign = get_object_or_404(
                    ListFighterPsykerPowerAssignment,
                    psyker_power=power_id,
                    list_fighter=fighter,
                )
                assign.delete()
                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            else:
                error_message = "Invalid action."
        elif request.POST.get("action") == "add":
            power = get_object_or_404(
                ContentPsykerPower,
                id=power_id,
            )
            assign = ListFighterPsykerPowerAssignment(
                list_fighter=fighter,
                psyker_power=power,
            )
            assign.save()
            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

    # TODO: A fair bit of this logic should live in the model, or a manager method of some kind
    disabled_defaults = fighter.disabled_pskyer_default_powers.values("id")
    powers: QuerySetOf[ContentPsykerPower] = (
        ContentPsykerPower.objects.filter(
            # Get powers via disciplines that are are assigned, or are generic...
            Q(
                discipline__in=ContentPsykerDiscipline.objects.filter(
                    Q(fighter_assignments__fighter=fighter.content_fighter_cached)
                    | Q(generic=True)
                ).distinct()
            )
            # ...and get powers that are assigned to this fighter by default
            | Q(
                fighter_assignments__fighter=fighter.content_fighter_cached,
            )
        )
        .distinct()
        .prefetch_related("discipline")
        .annotate(
            assigned_direct=Exists(
                ListFighterPsykerPowerAssignment.objects.filter(
                    list_fighter=fighter,
                    psyker_power=OuterRef("pk"),
                ).values("psyker_power_id")
            ),
            assigned_default=Exists(
                ContentFighterPsykerPowerDefaultAssignment.objects.filter(
                    fighter=fighter.content_fighter_cached,
                    psyker_power=OuterRef("pk"),
                )
                .exclude(id__in=disabled_defaults)
                .values("psyker_power_id")
            ),
        )
    )

    # TODO: Re-querying this is inefficient, but it's ok for now.
    assigns = []
    for power in powers:
        if power.assigned_direct:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment.from_assignment(
                    ListFighterPsykerPowerAssignment(
                        list_fighter=fighter,
                        psyker_power=power,
                    ),
                )
            )
        elif power.assigned_default:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment.from_default_assignment(
                    ContentFighterPsykerPowerDefaultAssignment(
                        fighter=fighter.content_fighter_cached,
                        psyker_power=power,
                    ),
                    fighter=fighter,
                )
            )
        else:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment(
                    fighter=fighter, psyker_power=power
                )
            )

    return render(
        request,
        "core/list_fighter_psyker_powers_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "powers": powers,
            "assigns": assigns,
            "error_message": error_message,
        },
    )


@login_required
def edit_list_fighter_narrative(request, id, fighter_id):
    """
    Edit the narrative of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterNarrativeForm for editing fighter narrative.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_narrative_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = EditListFighterNarrativeForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list-about", args=(lst.id,)) + f"#about-{str(fighter.id)}"
            )
    else:
        form = EditListFighterNarrativeForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_narrative_edit.html",
        {
            "form": form,
            "list": lst,
            "error_message": error_message,
        },
    )


@login_required
def edit_list_fighter_equipment(request, id, fighter_id, is_weapon=False):
    """
    Edit the equipment (weapons or gear) of an existing :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``equipment``
        A filtered list of :model:`content.ContentEquipment` items.
    ``categories``
        Available equipment categories.
    ``assigns``
        A list of :class:`.VirtualListFighterEquipmentAssignment` objects.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.
    ``is_weapon``
        Boolean indicating if we're editing weapons or gear.

    **Template**

    :template:`core/list_fighter_weapons_edit.html` or :template:`core/list_fighter_gear_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    view_name = (
        "core:list-fighter-weapons-edit" if is_weapon else "core:list-fighter-gear-edit"
    )
    template_name = (
        "core/list_fighter_weapons_edit.html"
        if is_weapon
        else "core/list_fighter_gear_edit.html"
    )

    error_message = None
    if request.method == "POST":
        instance = ListFighterEquipmentAssignment(list_fighter=fighter)
        form = ListFighterEquipmentAssignmentForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            query_params = make_query_params_str(
                flash=instance.id,
                filter=request.POST.get("filter"),
                q=request.POST.get("q"),
            )
            return HttpResponseRedirect(
                reverse(view_name, args=(lst.id, fighter.id))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )

    # Get the appropriate equipment
    if is_weapon:
        equipment = (
            ContentEquipment.objects.weapons()
            .with_cost_for_fighter(fighter.equipment_list_fighter)
            .with_profiles_for_fighter(fighter.equipment_list_fighter)
        )
        search_vector = SearchVector(
            "name", "category__name", "contentweaponprofile__name"
        )
    else:
        equipment = ContentEquipment.objects.non_weapons().with_cost_for_fighter(
            fighter.equipment_list_fighter
        )
        search_vector = SearchVector("name", "category__name")

    # Get categories for this equipment type
    categories = (
        ContentEquipmentCategory.objects.filter(id__in=equipment.values("category_id"))
        .distinct()
        .order_by("name")
    )

    # Filter by category if specified
    cats = (
        [
            cat
            for cat in request.GET.getlist("cat", list())
            if cat and is_valid_uuid(cat)
        ]
        if not is_weapon
        else request.GET.getlist("cat", list())
    )

    if cats and "all" not in cats:
        equipment = equipment.filter(category_id__in=cats)

    # Apply search filter if provided
    if request.GET.get("q"):
        equipment = (
            equipment.annotate(search=search_vector)
            .filter(search=request.GET.get("q", ""))
            .distinct("category__name", "name", "id")
        )

    # Filter by availability level
    als = request.GET.getlist("al", ["C", "R"])
    if request.GET.get("filter", None) in [None, "", "equipment-list"]:
        # Always show Exclusive in equipment lists
        als += ["E"]
        equipment = equipment.exclude(
            ~Q(
                id__in=ContentFighterEquipmentListItem.objects.filter(
                    fighter=fighter.equipment_list_fighter
                ).values("equipment_id")
            )
        )

    equipment = equipment.filter(rarity__in=set(als))

    # Apply maximum availability level filter if provided
    mal = (
        int(request.GET.get("mal"))
        if request.GET.get("mal") and is_int(request.GET.get("mal"))
        else None
    )
    if mal:
        # Only filter by rarity_roll for items that aren't Common
        # Common items should always be visible
        equipment = equipment.filter(Q(rarity="C") | Q(rarity_roll__lte=mal))

    # Create assignment objects
    assigns = []
    for item in equipment:
        if is_weapon:
            profiles = item.profiles_for_fighter(fighter.equipment_list_fighter)
            profiles = [
                profile
                for profile in profiles
                # Keep standard profiles
                if profile.cost == 0
                # They have an Al that matches the filter, and no roll value
                or (not profile.rarity_roll and profile.rarity in als)
                # They have an Al that matches the filter, and a roll
                or (
                    profile.rarity_roll
                    and profile.rarity in als
                    and (
                        # If mal is set, check if profile passes the threshold
                        (mal and profile.rarity_roll <= mal)
                        # If mal is not set, show all profiles with matching rarity
                        or not mal
                    )
                )
            ]
            assigns.append(
                VirtualListFighterEquipmentAssignment(
                    fighter=fighter,
                    equipment=item,
                    profiles=profiles,
                )
            )
        else:
            assigns.append(
                VirtualListFighterEquipmentAssignment(
                    fighter=fighter,
                    equipment=item,
                )
            )

    context = {
        "fighter": fighter,
        "equipment": equipment,
        "categories": categories,
        "assigns": assigns,
        "list": lst,
        "error_message": error_message,
        "is_weapon": is_weapon,
    }

    # Add weapons-specific context if needed
    if is_weapon:
        context["weapons"] = equipment

    return render(request, template_name, context)


@login_required
def edit_list_fighter_assign_cost(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit the cost of an existing :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_assign_cost_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        form = ListFighterEquipmentAssignmentCostForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    form = ListFighterEquipmentAssignmentCostForm(
        instance=assignment,
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
        assignment.upgrade = None
        assignment.upgrades_field.remove(upgrade)
        assignment.save()
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
def edit_list_fighter_weapon_accessories(request, id, fighter_id, assign_id):
    """
    Managed weapon accessories for a :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``accessories``
        A list of :model:`content.ContentWeaponAccessory` objects.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_weapons_accessories_edit.html`

    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        form = ListFighterEquipmentAssignmentAccessoriesForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    # TODO: Exclude accessories that cannot be added to this weapon
    form = ListFighterEquipmentAssignmentAccessoriesForm(
        instance=assignment,
    )

    return render(
        request,
        "core/list_fighter_weapons_accessories_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "form": form,
            "error_message": error_message,
        },
    )


@login_required
def delete_list_fighter_weapon_accessory(
    request, id, fighter_id, assign_id, accessory_id
):
    """
    Remove a :model:`content.ContentWeaponAccessory` from a fighter :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.
    ``accessory``
        The :model:`content.ContentWeaponAccessory` to be removed.

    **Template**

    :template:`core/list_fighter_weapons_accessory_delete.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )
    accessory = get_object_or_404(
        ContentWeaponAccessory,
        pk=accessory_id,
    )

    if request.method == "POST":
        assignment.weapon_accessories_field.remove(accessory)
        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_weapons_accessory_delete.html",
        {"list": lst, "fighter": fighter, "assign": assignment, "accessory": accessory},
    )


@login_required
def edit_list_fighter_weapon_upgrade(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit the weapon upgrade of an existing :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``upgrade``
        The :model:`content.ContentEquipmentUpgrade` upgrade to be added.

    **Template**

    :template:`core/list_fighter_assign_upgrade_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    if request.method == "POST":
        form = ListFighterEquipmentAssignmentUpgradeForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
            )
    else:
        form = ListFighterEquipmentAssignmentUpgradeForm(instance=assignment)

    return render(
        request,
        "core/list_fighter_assign_upgrade_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
            "form": form,
        },
    )


@login_required
def disable_list_fighter_default_assign(
    request, id, fighter_id, assign_id, action_name, back_name
):
    """
    Disable a default assignment from :model:`content.ContentFighterDefaultAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`content.ContentFighterDefaultAssignment` to be disabled.

    **Template**

    :template:`core/list_fighter_assign_disable.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
    )

    if request.method == "POST":
        fighter.disabled_default_assignments.add(assignment)
        fighter.save()
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_disable.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def convert_list_fighter_default_assign(
    request, id, fighter_id, assign_id, action_name, back_name
):
    """
    Convert a default assignment from :model:`content.ContentFighterDefaultAssignment` to a
    :model:`core.ListFighterEquipmentAssignment`.
    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`content.ContentFighterDefaultAssignment` to be converted.
    ``action_url``
        The URL to redirect to after the conversion.
    ``back_url``
        The URL to redirect back to the list fighter.

    **Template**
    :template:`core/list_fighter_assign_convert.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
    )

    if request.method == "POST":
        fighter.convert_default_assignment(assignment)
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_convert.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
def archive_list_fighter(request, id, fighter_id):
    """
    Archive or unarchive a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be archived or unarchived.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_archive.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    if request.method == "POST":
        if request.POST.get("archive") == "1":
            fighter.archive()
        elif fighter.archived:
            fighter.unarchive()
        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    return render(
        request,
        "core/list_fighter_archive.html",
        {"fighter": fighter, "list": lst},
    )


@login_required
def delete_list_fighter(request, id, fighter_id):
    """
    Delete a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be deleted.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_delete.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    if request.method == "POST":
        fighter.delete()
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_delete.html",
        {"fighter": fighter, "list": lst},
    )


def embed_list_fighter(request, id, fighter_id):
    """
    Display a single :model:`core.ListFighter` object in an embedded view.

    **Context**

    ``fighter``
        The requested :model:`core.ListFighter` object.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_embed.html`
    """
    lst = get_object_or_404(List, id=id)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    return render(
        request,
        "core/list_fighter_embed.html",
        {"fighter": fighter, "list": lst},
    )


class ListArchivedFightersView(generic.ListView):
    """
    Display a page with archived :model:`core.ListFighter` objects within a given :model:`core.List`.

    **Context**

    ``list``
        The requested :model:`core.List` object (retrieved by ID).

    **Template**

    :template:`core/list_archived_fighters.html`
    """

    template_name = "core/list_archived_fighters.html"
    context_object_name = "list"

    def get_queryset(self):
        """
        Retrieve the :model:`core.List` by its `id`, ensuring it's owned by the current user.
        """
        return get_object_or_404(List, id=self.kwargs["id"], owner=self.request.user)
