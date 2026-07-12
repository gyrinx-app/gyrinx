"""Dice rolling views."""

from itertools import zip_longest
from random import Random, randint  # nosec B311 - game dice, not crypto

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from gyrinx.core.models.events import EventNoun, EventVerb, log_event

# The dice configuration comes straight from the (shareable, hand-editable) URL,
# so it is untrusted: a non-numeric value would otherwise raise (HTTP 500) and a
# huge count or a flood of groups would allocate and render an unbounded page.
# Counts are clamped per group and the number of groups is capped.
MAX_GROUPS = 20
MAX_DICE_PER_GROUP = 100


def _dice_counts(request, key):
    """Parse a repeated integer query param (``d`` / ``fp`` / ``i``) into a
    bounded list of dice counts.

    Non-numeric entries are skipped, each count is clamped to
    ``0..MAX_DICE_PER_GROUP``, and at most ``MAX_GROUPS`` entries are returned —
    so a hand-edited or hostile URL can neither crash the view nor make it render
    an unbounded page.
    """
    counts = []
    for raw in request.GET.getlist(key):
        if len(counts) >= MAX_GROUPS:
            break
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        counts.append(max(0, min(n, MAX_DICE_PER_GROUP)))
    return counts


@login_required
def dice(request):
    """
    Display dice roll results (regular, firepower, or injury rolls).

    The dice configuration (how many dice, in how many groups) lives in the
    query string, so the page is fully described by its URL. A roll is only
    produced when a ``seed`` is present: results are derived deterministically
    from that seed, so the same URL always reproduces the same roll and can be
    shared. Without a seed the page renders empty ("?") placeholder dice and
    rolls nothing — so a fresh visit, or changing the dice/groups, shows no
    values until a Roll button (which supplies a fresh seed) is pressed.

    **Query Parameters**

    ``m`` (str)
        Mode for the dice roll, e.g. 'd6' or 'd3'.
    ``d`` (list of int)
        Number of standard dice to roll, one entry per group.
    ``fp`` (list of int)
        Number of firepower dice to roll.
    ``i`` (list of int)
        Number of injury dice to roll.
    ``seed`` (str)
        When present, seeds the roll. Absent means "not rolled yet".

    **Context**

    ``mode``
        The dice mode (e.g. 'd6', 'd3').
    ``rolled``
        Whether a roll was produced (a seed was supplied).
    ``next_seed``
        A fresh candidate seed for the Roll buttons, so each press rolls anew.
    ``groups``
        A list of dictionaries, each containing:
          - ``dice``: one entry per standard die — the rolled value, or ``None``
            when not rolled (rendered as a placeholder).
          - ``firepower``, ``injury``: same, for firepower/injury dice.
          - ``dice_n``, ``firepower_n``, ``injury_n``: the counts used.

    **Template**

    :template:`core/dice.html`
    """
    mode = request.GET.get("m", "d6")
    d = _dice_counts(request, "d")
    fp = _dice_counts(request, "fp")
    i = _dice_counts(request, "i")
    # A bare visit (no dice configured in the URL) still renders one group of a
    # single die, so the page is always a usable roller and the client script
    # always has a group to clone / reset.
    if not (d or fp or i):
        d = [1]
    sides = {
        "d3": 3,
    }.get(mode, 6)

    seed = request.GET.get("seed", "")
    rolled = bool(seed)
    # Random(str) is deterministic across processes (it hashes the seed with
    # SHA-512, not the salted builtin hash()), so a given URL reproduces its roll.
    rng = Random(seed) if rolled else None  # nosec B311 - game dice, not crypto

    def roll(n, die_sides):
        # One entry per die: the rolled value when we have a seed, else None so
        # the template renders an empty placeholder.
        if rng is None:
            return [None] * n
        return [rng.randint(1, die_sides) for _ in range(n)]

    groups = [
        dict(
            dice=roll(group[0], sides),
            firepower=roll(group[1], 6),
            injury=roll(group[2], 6),
            dice_n=group[0],
            firepower_n=group[1],
            injury_n=group[2],
        )
        for group in zip_longest(d, fp, i, fillvalue=0)
    ]

    # A fresh candidate seed embedded in the Roll buttons so each press produces
    # a new (and thereafter reproducible) roll.
    next_seed = f"{randint(0, 0xFFFFFFFF):08x}"  # nosec B311 - game dice, not crypto

    # Log the dice roll
    log_event(
        user=request.user,
        noun=EventNoun.USER,
        verb=EventVerb.VIEW,
        request=request,
        page="dice",
        dice_mode=mode,
        dice_rolled=rolled,
        standard_dice_count=sum(d) if d else 0,
        firepower_dice_count=sum(fp) if fp else 0,
        injury_dice_count=sum(i) if i else 0,
    )

    return render(
        request,
        "core/dice.html",
        {
            "mode": mode,
            "rolled": rolled,
            "next_seed": next_seed,
            "groups": groups,
        },
    )
