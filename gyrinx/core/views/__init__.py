from itertools import zip_longest
from random import randint
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from gyrinx.core.models.list import List

from .upload import tinymce_upload as tinymce_upload


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
        lists = List.objects.filter(owner=request.user, status=List.LIST_BUILDING)
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
    public_lists = List.objects.filter(
        owner=user, public=True, status=List.LIST_BUILDING
    )
    return render(
        request,
        "core/user.html",
        {"user": user, "public_lists": public_lists},
    )
