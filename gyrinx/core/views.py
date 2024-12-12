from itertools import zip_longest
from random import randint

from django.shortcuts import get_list_or_404, get_object_or_404, render
from django.views import generic

from gyrinx.content.models import ContentEquipment, ContentHouse, ContentPageRef
from gyrinx.core.models import List


def index(request):
    return render(request, "core/index.html", {})


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


class ListView(generic.ListView):
    template_name = "core/lists.html"
    context_object_name = "lists"

    def get_queryset(self):
        return List.objects.all()


class ListPrintView(generic.DetailView):
    template_name = "core/list_print.html"
    context_object_name = "list"

    def get_object(self):
        return get_object_or_404(List, id=self.kwargs["id"])
