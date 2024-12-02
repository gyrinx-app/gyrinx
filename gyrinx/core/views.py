from django.db.models import Case, When
from django.shortcuts import get_list_or_404, get_object_or_404, render

from gyrinx.content.models import ContentEquipment, ContentHouse
from gyrinx.core.models import List


def index(request):
    return render(request, "core/index.html", {})


def content(request):
    # TODO: Turn some amount of this into reusable stuff (e.g. "hydrate" calls)
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

    equipment = get_list_or_404(ContentEquipment)
    categories = {}
    for item in equipment:
        category = item.cat()
        item.profiles = list(
            item.contentweaponprofile_set.all().order_by(
                Case(
                    When(name="", then=0),
                    default=1,
                ),
                "cost",
            )
        )
        if category not in categories:
            categories[category] = []
        categories[category].append(item)

    return render(
        request,
        "core/content.html",
        {
            "houses": houses,
            "categories": categories,
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
