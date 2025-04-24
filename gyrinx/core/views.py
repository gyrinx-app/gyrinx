from itertools import zip_longest
from random import randint
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchVector
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_list_or_404, get_object_or_404, render
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
    ContentPageRef,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentSkillCategory,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.forms import (
    CloneListFighterForm,
    CloneListForm,
    EditListForm,
    ListFighterEquipmentAssignmentAccessoriesForm,
    ListFighterEquipmentAssignmentCostForm,
    ListFighterEquipmentAssignmentForm,
    ListFighterEquipmentAssignmentUpgradeForm,
    ListFighterSkillsForm,
    NewListFighterForm,
    NewListForm,
)
from gyrinx.core.models import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    ListFighterPsykerPowerAssignment,
    VirtualListFighterEquipmentAssignment,
    VirtualListFighterPsykerPowerAssignment,
)
from gyrinx.models import QuerySetOf, is_int, is_valid_uuid


def make_query_params_str(**kwargs) -> str:
    return urlencode(dict([(k, v) for k, v in kwargs.items() if v is not None]))


def index(request):
    """
    Display a list of the user's :model:`core.List` objects, or an empty list if the user is anonymous.

    **Context**

    ``lists``
        A list of :model:`core.List` objects owned by the current user.

    **Template**

    :template:`core/index.html`
    """
    if request.user.is_anonymous:
        lists = []
    else:
        lists = List.objects.filter(owner=request.user)
    return render(
        request,
        "core/index.html",
        {
            "lists": lists,
        },
    )


@login_required
def account_home(request):
    """
    Management page for the user's account.

    """
    return render(
        request,
        "core/account_home.html",
    )


def content(request):
    """
    Display a placeholder content page (currently unused).

    **Context**

    None

    **Template**

    :template:`core/content.html`
    """
    return render(
        request,
        "core/content.html",
    )


class GangIndexView(generic.ListView):
    """
    Display a list of all :model:`content.ContentHouse` objects.

    **Context**

    ``houses``
        A list of :model:`content.ContentHouse` objects.

    **Template**

    :template:`core/content_gangs.html`
    """

    template_name = "core/content_gangs.html"
    context_object_name = "houses"

    def get_queryset(self):
        """
        Return all :model:`content.ContentHouse` objects.
        """
        return ContentHouse.objects.all()


class EquipmentIndexView(generic.ListView):
    """
    Display a list of all :model:`content.ContentEquipment` objects.

    **Context**

    ``equipment``
        A list of :model:`content.ContentEquipment` objects.

    **Template**

    :template:`core/content_equipment.html`
    """

    template_name = "core/content_equipment.html"
    context_object_name = "equipment"

    def get_queryset(self):
        """
        Return all :model:`content.ContentEquipment` objects.
        """
        return ContentEquipment.objects.all()


def content_index(request):
    """
    Display an index of :model:`content.ContentPageRef` objects (page references),
    ordered by book shortname and page number.

    **Context**

    ``page_refs``
        A list of :model:`content.ContentPageRef` objects returned by the `all_ordered` class method.
    ``category_order``
        A list of string categories used to guide the display order.

    **Template**

    :template:`core/content_index.html`
    """
    page_refs = get_list_or_404(ContentPageRef.all_ordered())
    return render(
        request,
        "core/content_index.html",
        {
            "page_refs": page_refs,
            "category_order": [
                "Rules",
                "Background",
                "Gangs",
                "Dramatis Personae",
                "Hangers-On",
                "Brutes",
                "Exotic Beasts",
                "Trading Post",
                "Vehicles",
                "Skills",
                "Gang Tactics",
                "Campaigns",
                "Scenarios",
            ],
        },
    )


class ContentIndexIndexView(generic.ListView):
    """
    Display an index of :model:`content.ContentPageRef` objects (page references),
    ordered by book shortname and page number. This class-based view version
    returns the same result as `content_index`.

    **Context**

    ``page_refs``
        A list of :model:`content.ContentPageRef` objects returned by the `all_ordered` method.
    ``category_order``
        A list of string categories used to guide the display order.

    **Template**

    :template:`core/content_index.html`
    """

    template_name = "core/content_index.html"
    context_object_name = "page_refs"
    extra_context = {
        "category_order": [
            "Rules",
            "Background",
            "Gangs",
            "Dramatis Personae",
            "Hangers-On",
            "Brutes",
            "Exotic Beasts",
            "Trading Post",
            "Vehicles",
            "Skills",
            "Gang Tactics",
            "Campaigns",
            "Scenarios",
        ],
    }

    def get_queryset(self):
        """
        Return :model:`content.ContentPageRef` objects via `all_ordered`.
        """
        return ContentPageRef.all_ordered()


@login_required
def dice(request):
    """
    Display dice roll results (regular, firepower, or injury rolls).
    Users can specify query parameters to control the number of each die type.

    **Query Parameters**

    ``m`` (str)
        Mode for the dice roll, e.g. 'd6' or 'd3'.
    ``d`` (list of int)
        Number of standard dice to roll.
    ``fp`` (list of int)
        Number of firepower dice to roll.
    ``i`` (list of int)
        Number of injury dice to roll.

    **Context**

    ``mode``
        The dice mode (e.g. 'd6', 'd3').
    ``groups``
        A list of dictionaries, each containing:
          - ``dice``: rolled results for standard dice.
          - ``firepower``: rolled results for firepower dice.
          - ``injury``: rolled results for injury dice.
          - ``dice_n``, ``firepower_n``, ``injury_n``: the counts used.

    **Template**

    :template:`core/dice.html`
    """
    mode = request.GET.get("m", "d6")
    d = [int(x) for x in request.GET.getlist("d")]
    fp = [int(x) for x in request.GET.getlist("fp")]
    i = [int(x) for x in request.GET.getlist("i")]
    mod = {
        "d3": 3,
    }.get(mode, 6)
    groups = [
        dict(
            dice=[randint(0, 5) % mod + 1 for _ in range(group[0])],
            firepower=[randint(1, 6) for _ in range(group[1])],
            injury=[randint(1, 6) for _ in range(group[2])],
            dice_n=group[0],
            firepower_n=group[1],
            injury_n=group[2],
        )
        for group in zip_longest(d, fp, i, fillvalue=0)
    ]
    return render(
        request,
        "core/dice.html",
        {
            "mode": mode,
            "groups": groups,
        },
    )


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
        Return :model:`core.List` objects that are public.
        """
        return List.objects.filter(public=True)


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
def edit_list_fighter_gear(request, id, fighter_id):
    """
    Edit the gear of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterEquipmentAssignmentForm for assigning non-weapon equipment.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_gear_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

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
                reverse("core:list-fighter-gear-edit", args=(lst.id, fighter.id))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )

    equipment: QuerySetOf[ContentEquipment] = (
        ContentEquipment.objects.non_weapons().with_cost_for_fighter(
            fighter.content_fighter_cached
        )
    )

    categories = (
        ContentEquipmentCategory.objects.filter(id__in=equipment.values("category_id"))
        .distinct()
        .order_by("name")
    )

    cats = [
        cat for cat in request.GET.getlist("cat", list()) if cat and is_valid_uuid(cat)
    ]
    if cats and "all" not in cats:
        equipment = equipment.filter(category_id__in=cats)

    if request.GET.get("q"):
        equipment = (
            equipment.annotate(
                search=SearchVector("name", "category__name"),
            )
            .filter(search=request.GET.get("q", ""))
            .distinct("category__name", "name", "id")
        )

    als = request.GET.getlist("al", ["C", "R"])
    if request.GET.get("filter", None) in [None, "", "equipment-list"]:
        # Always show Exclusive in equipment lists
        als += ["E"]
        equipment = equipment.exclude(
            ~Q(
                id__in=ContentFighterEquipmentListItem.objects.filter(
                    fighter=fighter.content_fighter_cached
                ).values("equipment_id")
            )
        )

    equipment = equipment.filter(rarity__in=als)
    if request.GET.get("mal") and is_int(request.GET.get("mal")):
        equipment = equipment.filter(rarity_roll__lte=int(request.GET.get("mal", 0)))

    assigns = []
    for item in equipment:
        assigns.append(
            VirtualListFighterEquipmentAssignment(
                fighter=fighter,
                equipment=item,
            )
        )

    return render(
        request,
        "core/list_fighter_gear_edit.html",
        {
            "fighter": fighter,
            "equipment": equipment,
            "categories": categories,
            "assigns": assigns,
            "list": lst,
            "error_message": error_message,
        },
    )


@login_required
def edit_list_fighter_weapons(request, id, fighter_id):
    """
    Display and handle weapon assignments for a :model:`core.ListFighter`.

    **Query Parameters**

    ``q`` (str)
        Optional search string to filter weapons by name, category, or weapon profile name.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``weapons``
        A filtered or unfiltered list of :model:`content.ContentEquipment` items (weapon category).
    ``assigns``
        A list of :class:`.VirtualListFighterEquipmentAssignment` objects, containing
        each weapon, its associated profiles, and cost data.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_weapons_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

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
                reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )

    weapons: QuerySetOf[ContentEquipment] = (
        ContentEquipment.objects.weapons()
        .with_cost_for_fighter(fighter.content_fighter_cached)
        .with_profiles_for_fighter(fighter.content_fighter_cached)
    )

    # All categories with weapons in them
    categories = (
        ContentEquipmentCategory.objects.filter(id__in=weapons.values("category_id"))
        .distinct()
        .order_by("name")
    )

    cats = request.GET.getlist("cat", list())
    if cats and "all" not in cats:
        weapons: QuerySetOf[ContentEquipment] = weapons.filter(category_id__in=cats)

    if request.GET.get("q"):
        weapons: QuerySetOf[ContentEquipment] = (
            weapons.annotate(
                search=SearchVector(
                    "name", "category__name", "contentweaponprofile__name"
                ),
            )
            .filter(search=request.GET.get("q", ""))
            .distinct("category__name", "name", "id")
        )

    als = request.GET.getlist("al", ["C", "R"])
    if request.GET.get("filter", None) in [None, "", "equipment-list"]:
        # Always show Exclusive in equipment lists
        als += ["E"]
        weapons: QuerySetOf[ContentEquipment] = weapons.exclude(
            ~Q(
                id__in=ContentFighterEquipmentListItem.objects.filter(
                    fighter=fighter.content_fighter_cached
                ).values("equipment_id")
            )
        )

    weapons: QuerySetOf[ContentEquipment] = weapons.filter(rarity__in=set(als))
    mal = (
        int(request.GET.get("mal"))
        if request.GET.get("mal") and is_int(request.GET.get("mal"))
        else None
    )
    if mal:
        weapons: QuerySetOf[ContentEquipment] = weapons.filter(rarity_roll__lte=mal)

    assigns = []
    for weapon in weapons:
        profiles: list[ContentWeaponProfile] = weapon.profiles_for_fighter(
            fighter.content_fighter_cached
        )
        profiles = [
            profile
            for profile in profiles
            # Keep standard profiles
            if profile.cost == 0
            # They have an Al that matches the filter, and no roll value
            or (not profile.rarity_roll and profile.rarity in als)
            # They have an Al that matches the filter, and a roll
            or (
                mal
                and profile.rarity_roll
                and profile.rarity_roll <= mal
                and profile.rarity in als
            )
        ]
        assigns.append(
            VirtualListFighterEquipmentAssignment(
                fighter=fighter,
                equipment=weapon,
                profiles=profiles,
            )
        )

    return render(
        request,
        "core/list_fighter_weapons_edit.html",
        {
            "fighter": fighter,
            "weapons": weapons,
            "categories": categories,
            "assigns": assigns,
            "list": lst,
            "error_message": error_message,
        },
    )


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


# Users


def user(request, slug_or_id):
    """
    Display a user profile page with public lists.

    **Context**

    ``user``
        The requested user object.

    **Template**

    :template:`core/user.html`
    """
    User = get_user_model()
    slug_or_id = str(slug_or_id).lower()
    if slug_or_id.isnumeric():
        query = Q(id=slug_or_id)
    else:
        query = Q(username__iexact=slug_or_id)
    user = get_object_or_404(User, query)
    public_lists = List.objects.filter(owner=user, public=True)
    return render(
        request,
        "core/user.html",
        {"user": user, "public_lists": public_lists},
    )
