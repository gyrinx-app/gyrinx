"""Find choices introduced by an operation and build their follow-up navigation.

Slots are computed, so identify arrivals through the stored anchor IDs in
``Operation.written``. ``arrived`` examines the gang's cards for matching
choices. A newly satisfied condition on an older anchor is not an arrival.

Founding, hiring and choosing views opt into authored follow-up screens;
purchases and clones do not. ``onward`` encodes arriving choices and the
continuation URL in the n26-next address. The screen is rederived from
that address without storing navigation state.

A library with no applicable screens requires only the initial existence
query and no card derivation.
"""

from urllib.parse import parse_qs, urlencode, urlsplit

from django.urls import reverse

from n26.library.staged import sees_staged

#: Maximum choices per follow-up screen. Remaining choices continue on
#: a chained screen.
MAX_ASKS = 20


def any_interstitials(*, include_staged=True):
    """Check for any attached follow-up screen before deriving cards.

    Archived screens count. Staged screens count only for viewers permitted
    to see them, avoiding unnecessary derivation for other viewers.
    """
    from n26.library.models import InterstitialSlot

    rows = InterstitialSlot.objects.all()
    if not include_staged:
        rows = rows.filter(staged=False, interstitial__staged=False)
    return rows.exists()


def arrived(gang, written):
    """The choice slots these assignments just put on this gang's cards.

    ``[(host, slot)]`` — ``host`` is the model's pk, or ``GANG_SLOT_HOST``
    for the gang's own card, so a caller can build the address the pick
    screen reads. One derivation of the whole gang, the same one the
    sheet makes, however many slots arrived.
    """
    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute, compute_gang
    from n26.core.render import GANG_SLOT_HOST

    if not written:
        return []
    gang_card = build_gang_card(gang)
    cards = gang_card.members
    index = build_modifier_index(carriers(gang_card, *cards.values()))
    computed = [(GANG_SLOT_HOST, compute_gang(gang_card, index))]
    computed.extend((str(pk), compute(card, index)) for pk, card in cards.items())
    found = []
    for host, done in computed:
        for slot in done.choices:
            anchor = getattr(slot.anchor, "assignment", None)
            if anchor is None or slot.identity is None:
                continue
            if str(anchor.pk) in written:
                found.append((host, slot))
    return found


def interstitials_on(slot_pks, *, include_staged=False):
    """Map slot IDs to ordered screen attachments and their interstitials.

    Include archived screens, attachments and packs for slots already held.
    Exclude staged content unless permitted. Do not narrow packs: the held
    slot can use a screen attached from another pack.
    """
    from n26.library.models import InterstitialSlot

    if not slot_pks:
        return {}
    rows = (
        InterstitialSlot.objects.filter(slot_id__in=slot_pks)
        .select_related("interstitial")
        .order_by("interstitial__position", "interstitial__name", "position")
    )
    if not include_staged:
        rows = rows.filter(staged=False, interstitial__staged=False)
    found = {}
    for row in rows:
        found.setdefault(row.slot_id, []).append(row)
    return found


def asking(gang, written, *, include_staged=False, hosts=None):
    """The addresses of the arriving slots the screen should ask about:
    unresolved, taking at least one pick, and carrying a live
    interstitial. In card order.

    ``hosts`` narrows to the cards named — ``{GANG_SLOT_HOST}`` for the
    gang's own questions and none of its models'. Founding passes it, so
    the screen after founding asks about the gang and nothing else
    however the library is authored. A question left out this way is not
    lost: the slot stands unresolved on the sheet, which is where a
    reader makes it.
    """
    from n26.core.render import is_tier_ladder, slot_key

    open_slots = [
        (host, slot)
        for host, slot in arrived(gang, written)
        if slot.slot is not None and slot.max_picks > 0 and not slot.is_resolved
        if not is_tier_ladder(slot)
        if hosts is None or host in hosts
    ]
    if not open_slots:
        return []
    carrying = interstitials_on(
        {slot.slot.pk for _, slot in open_slots}, include_staged=include_staged
    )
    return [
        slot_key(slot, host) for host, slot in open_slots if slot.slot.pk in carrying
    ]


def next_url(gang, keys, back):
    """Encode unique choice addresses and their continuation URL.

    Split more than MAX_ASKS choices across chained screens without dropping
    any. Encode nested continuation URLs once.
    """
    asked = []
    for key in keys:
        if key and key not in asked:
            asked.append(key)
    if len(asked) > MAX_ASKS:
        back = next_url(gang, asked[MAX_ASKS:], back)
        asked = asked[:MAX_ASKS]
    return (
        reverse("n26-next", args=[gang.pk])
        + "?"
        + urlencode([*(("ask", key) for key in asked), ("next", back)])
    )


def _already_asking(gang, back):
    """``(keys, next)`` when ``back`` is itself this gang's screen for
    what arrived, else None.

    A pick made on the pick screen, reached from that screen for its
    roll, comes back to it: what the pick brought joins the questions
    already there rather than opening a second screen in front of the
    first.
    """
    parts = urlsplit(back)
    if parts.path != reverse("n26-next", args=[gang.pk]):
        return None
    query = parse_qs(parts.query)
    return query.get("ask", []), query.get("next", [""])[0]


def arriving(request, gang, op, *, hosts=None):
    """Return arriving unresolved choices with visible follow-up screens.

    ``hosts`` narrows the cards as described by ``asking``. Check screen
    existence before deriving cards, including staged visibility.
    """
    if not op.written or not any_interstitials():
        return []
    shown = sees_staged(request.user)
    if not shown and not any_interstitials(include_staged=False):
        # Skip card derivation when every attached screen is hidden by staging.
        return []
    return asking(gang, op.written, include_staged=shown, hosts=hosts)


def toward(gang, keys, back):
    """The screen asking these questions, in front of ``back`` — or,
    where ``back`` is itself this gang's screen, that screen with these
    questions joined to its own rather than a second one in front of it.

    A pick made on the pick screen, reached from the screen for its
    roll, comes back to it this way.
    """
    standing = _already_asking(gang, back)
    if standing is not None:
        asked, back = standing
        keys = [*asked, *(key for key in keys if key not in asked)]
    return next_url(gang, keys, back)


def onward(request, gang, op, back, *, hosts=None):
    """Return the arriving choices' follow-up URL, or ``back`` when none apply.

    ``hosts`` narrows the cards as described by ``asking``.
    """
    keys = arriving(request, gang, op, hosts=hosts)
    if not keys:
        return back
    return toward(gang, keys, back)
