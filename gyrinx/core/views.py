from itertools import zip_longest
from random import randint

from django.db.models import Case, When
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


def content_gangs(request):
    houses = get_list_or_404(ContentHouse)
    for house in houses:
        house.fighters = list(
            house.contentfighter_set.all().order_by(
                Case(
                    When(category="LEADER", then=0),
                    When(category="CHAMPION", then=1),
                    When(category="PROSPECT", then=2),
                    When(category="JUVE", then=3),
                    default=99,
                ),
                "type",
            )
        )
    return render(request, "core/content_gangs.html", {"houses": houses})


class EquipmentIndexView(generic.ListView):
    template_name = "core/content_equipment.html"
    context_object_name = "equipment"

    def get_queryset(self):
        return ContentEquipment.objects.all()


def content_index(request):
    page_refs = get_list_or_404(ContentPageRef.all_ordered())
    categories = {}
    for page_ref in page_refs:
        category = page_ref.category
        if category not in categories:
            categories[category] = []
        categories[category].append(page_ref)

    return render(
        request,
        "core/content_index.html",
        {
            "page_refs": page_refs,
            "categories": categories,
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


def lists(request):
    # TODO: Turn some amount of this into reusable stuff (e.g. "hydrate" calls)

    lists = get_list_or_404(List)
    for lst in lists:
        lst.fighters = list(
            lst.listfighter_set.all().order_by(
                Case(
                    When(content_fighter__category="LEADER", then=0),
                    When(content_fighter__category="CHAMPION", then=1),
                    When(content_fighter__category="PROSPECT", then=2),
                    When(content_fighter__category="JUVE", then=3),
                    default=99,
                ),
                "name",
            )
        )

        for fighter in lst.fighters:
            fighter.assigned_equipment = list(
                fighter.equipment.through.objects.filter(list_fighter=fighter).order_by(
                    "list_fighter__name"
                )
            )

    return render(
        request,
        "core/lists.html",
        {
            "lists": lists,
        },
    )


def list_print(request, id):
    lst = get_object_or_404(List, id=id)
    lst.fighters = list(
        lst.listfighter_set.all().order_by(
            Case(
                When(content_fighter__category="LEADER", then=0),
                When(content_fighter__category="CHAMPION", then=1),
                When(content_fighter__category="PROSPECT", then=2),
                When(content_fighter__category="JUVE", then=3),
                default=99,
            ),
            "name",
        )
    )

    for fighter in lst.fighters:
        fighter.assigned_equipment = list(
            fighter.equipment.through.objects.filter(list_fighter=fighter).order_by(
                "list_fighter__name"
            )
        )

    return render(
        request,
        "core/list_print.html",
        {
            "list": lst,
        },
    )
