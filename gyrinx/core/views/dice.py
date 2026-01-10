"""Dice rolling views."""

from itertools import zip_longest
from random import randint  # nosec B311 - game dice, not crypto

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from gyrinx.core.models.events import EventNoun, EventVerb, log_event


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
            dice=[randint(0, 5) % mod + 1 for _ in range(group[0])],  # nosec B311
            firepower=[randint(1, 6) for _ in range(group[1])],  # nosec B311
            injury=[randint(1, 6) for _ in range(group[2])],  # nosec B311
            dice_n=group[0],
            firepower_n=group[1],
            injury_n=group[2],
        )
        for group in zip_longest(d, fp, i, fillvalue=0)
    ]

    # Log the dice roll
    log_event(
        user=request.user,
        noun=EventNoun.USER,
        verb=EventVerb.VIEW,
        request=request,
        page="dice",
        dice_mode=mode,
        standard_dice_count=sum(d) if d else 0,
        firepower_dice_count=sum(fp) if fp else 0,
        injury_dice_count=sum(i) if i else 0,
    )

    return render(
        request,
        "core/dice.html",
        {
            "mode": mode,
            "groups": groups,
        },
    )
