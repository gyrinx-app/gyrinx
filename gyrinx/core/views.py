from django.db.models import Case, When
from django.shortcuts import get_list_or_404, render

from gyrinx.content.models import ContentEquipment, ContentHouse


def index(request):
    return render(request, "core/index.html", {})


def content(request):
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
