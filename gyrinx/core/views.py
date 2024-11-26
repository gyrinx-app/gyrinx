from django.shortcuts import get_list_or_404, render

from gyrinx.content.models import ContentEquipment, ContentHouse


def index(request):
    return render(request, "core/index.html", {})


def content(request):
    houses = get_list_or_404(ContentHouse)
    for house in houses:
        house.fighters = list(house.contentfighter_set.all())

    equipment = get_list_or_404(ContentEquipment)
    categories = {}
    for item in equipment:
        category = item.cat()
        item.profiles = list(item.contentweaponprofile_set.all())
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
