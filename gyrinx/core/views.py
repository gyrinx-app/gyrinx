from dataclasses import dataclass
from itertools import zip_longest
from random import randint
from typing import List as TList
from typing import TypeVar, Union
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchVector
from django.db.models import QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import get_list_or_404, get_object_or_404, render
from django.urls import reverse
from django.views import generic

from gyrinx.content.models import (
    ContentEquipment,
    ContentHouse,
    ContentPageRef,
    ContentWeaponProfile,
)
from gyrinx.core.forms import (
    EditListForm,
    ListFighterEquipmentAssignmentForm,
    ListFighterGearForm,
    ListFighterSkillsForm,
    NewListFighterForm,
    NewListForm,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment

T = TypeVar("T")
QuerySetOf = Union[QuerySet, TList[T]]


def index(request):
    # User's Lists
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
    return render(
        request,
        "core/cookies.html",
    )


def content(request):
    # Unused view
    return render(
        request,
        "core/content.html",
    )


class GangIndexView(generic.ListView):
    template_name = "core/content_gangs.html"
    context_object_name = "houses"

    def get_queryset(self):
        return ContentHouse.objects.all()


class EquipmentIndexView(generic.ListView):
    template_name = "core/content_equipment.html"
    context_object_name = "equipment"

    def get_queryset(self):
        return ContentEquipment.objects.all()


def content_index(request):
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
        return ContentPageRef.all_ordered()


def dice(request):
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
    template_name = "core/lists.html"
    context_object_name = "lists"

    def get_queryset(self):
        return List.objects.filter(public=True)


class ListDetailView(generic.DetailView):
    template_name = "core/list.html"
    context_object_name = "list"

    def get_object(self):
        return get_object_or_404(List, id=self.kwargs["id"])


class ListPrintView(generic.DetailView):
    template_name = "core/list_print.html"
    context_object_name = "list"

    def get_object(self):
        return get_object_or_404(List, id=self.kwargs["id"])


@login_required
def new_list(request):
    houses = ContentHouse.objects.all()

    error_message = None
    if request.method == "POST":
        form = NewListForm(request.POST)
        if form.is_valid():
            list = form.save(commit=False)
            list.owner = request.user
            list.save()
            return HttpResponseRedirect(reverse("core:list", args=(list.id,)))

    else:
        form = NewListForm()

    return render(
        request,
        "core/list_new.html",
        {"form": form, "houses": houses, "error_message": error_message},
    )


@login_required
def edit_list(request, id):
    list = get_object_or_404(List, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = EditListForm(request.POST, instance=list)
        if form.is_valid():
            updated_list = form.save(commit=False)
            updated_list.save()
            return HttpResponseRedirect(reverse("core:list", args=(list.id,)))

    else:
        form = EditListForm(instance=list)

    return render(
        request,
        "core/list_edit.html",
        {"form": form, "error_message": error_message},
    )


@login_required
def new_list_fighter(request, id):
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = ListFighter(list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = NewListFighterForm(
            request.POST,
            instance=fighter,
        )
        if form.is_valid():
            fighter = form.save(commit=False)
            # You would think this would be handled by the form, but it's not. So we do it here.
            fighter.list = lst
            fighter.owner = lst.owner
            fighter.save()
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )

    else:
        form = NewListFighterForm(
            instance=fighter,
        )

    return render(
        request,
        "core/list_fighter_new.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter(request, id, fighter_id):
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = NewListFighterForm(
            request.POST,
            instance=fighter,
        )
        if form.is_valid():
            fighter = form.save(commit=False)
            # You would think this would be handled by the form, but it's not. So we do it here.
            fighter.list = lst
            fighter.owner = lst.owner
            fighter.save()
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )

    else:
        form = NewListFighterForm(
            instance=fighter,
        )

    return render(
        request,
        "core/list_fighter_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter_skills(request, id, fighter_id):
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterSkillsForm(
            request.POST,
            instance=fighter,
        )
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )

    else:
        form = ListFighterSkillsForm(
            instance=fighter,
        )

    return render(
        request,
        "core/list_fighter_skills_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter_gear(request, id, fighter_id):
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterGearForm(
            request.POST,
            instance=fighter,
        )
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )

    else:
        form = ListFighterGearForm(
            instance=fighter,
        )

    return render(
        request,
        "core/list_fighter_gear_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@dataclass
class VirtualListFighterEquipmentAssignment:
    fighter: ListFighter
    equipment: ContentEquipment
    profiles: QuerySetOf[ContentWeaponProfile]

    @property
    def category(self):
        return self.equipment.category

    def base_cost_int(self):
        return self.equipment.cost_for_fighter

    def base_cost_display(self):
        return f"{self.base_cost_int()}¢"

    def base_name(self):
        return f"{self.equipment}"

    def all_profiles(self):
        return self.profiles

    def standard_profiles(self):
        # TODO: This could very well be shifted to the database query.
        return [profile for profile in self.profiles if profile.cost == 0]

    def weapon_profiles_display(self):
        """Return a list of dictionaries with the weapon profiles and their costs."""
        # TODO: This could very well be shifted to the database query.
        return [
            {
                "profile": profile,
                "cost_int": profile.cost_for_fighter,
                "cost_display": f"+{profile.cost_for_fighter}¢",
            }
            for profile in self.profiles
            if profile.cost_int() > 0
        ]

    def cat(self):
        return self.equipment.cat()


@login_required
def edit_list_fighter_weapons(request, id, fighter_id):
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
                reverse(
                    "core:list-fighter-weapons-edit",
                    args=(
                        lst.id,
                        fighter.id,
                    ),
                )
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
                fighter,
                weapon,
                profiles=profiles,
            )
        )

    return render(
        request,
        "core/list_fighter_weapons_edit.html",
        {
            # "formset": formset,
            "fighter": fighter,
            "weapons": weapons,
            "assigns": assigns,
            "list": lst,
            "error_message": error_message,
        },
    )


@login_required
def delete_list_fighter_weapon(request, id, fighter_id, assign_id):
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


class ListArchivedFightersView(generic.ListView):
    template_name = "core/list_archived_fighters.html"
    context_object_name = "list"

    def get_queryset(self):
        return get_object_or_404(List, id=self.kwargs["id"], owner=self.request.user)
