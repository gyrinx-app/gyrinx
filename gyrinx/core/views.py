from itertools import zip_longest
from random import randint
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchVector
from django.http import HttpResponseRedirect
from django.shortcuts import get_list_or_404, get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.content.models import ContentEquipment, ContentHouse, ContentPageRef
from gyrinx.core.forms import (
    EditListForm,
    ListFighterEquipmentAssignmentForm,
    ListFighterGearForm,
    ListFighterSkillsForm,
    NewListFighterForm,
    NewListForm,
)
from gyrinx.core.models import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    VirtualListFighterEquipmentAssignment,
)
from gyrinx.models import QuerySetOf


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


def cookies(request):
    """
    Display the site's cookies policy information.

    **Context**

    None

    **Template**

    :template:`core/cookies.html`
    """
    return render(
        request,
        "core/cookies.html",
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
        form = NewListForm()

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
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
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
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )
    else:
        form = NewListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
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

    return render(
        request,
        "core/list_fighter_skills_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter_gear(request, id, fighter_id):
    """
    Edit the gear of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterGearForm for assigning non-weapon equipment.
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
        form = ListFighterGearForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )
    else:
        form = ListFighterGearForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_gear_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
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
            query_params = urlencode(dict(flash=instance.id))
            return HttpResponseRedirect(
                reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )

    weapons: QuerySetOf[ContentEquipment] = (
        ContentEquipment.objects.with_cost_for_fighter(
            fighter.content_fighter
        ).weapons()
    )

    if request.GET.get("q"):
        weapons = (
            weapons.annotate(
                search=SearchVector("name", "category", "contentweaponprofile__name"),
            )
            .filter(search__contains=request.GET.get("q", ""))
            .distinct("category", "name", "id")
        )

    assigns = []
    for weapon in weapons:
        profiles = weapon.profiles_for_fighter(fighter.content_fighter)
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
            "assigns": assigns,
            "list": lst,
            "error_message": error_message,
        },
    )


@login_required
def delete_list_fighter_weapon(request, id, fighter_id, assign_id):
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

    :template:`core/list_fighter_weapons_delete.html`
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
        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_weapons_delete.html",
        {"list": lst, "fighter": fighter, "assign": assignment},
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
