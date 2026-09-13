"""What an act just brought, and where the reader goes next.

A slot is computed, never stored, so "this slot just arrived" is a fact
about an act rather than a row: a slot arrives when the assignment it
hangs from — its anchor — was written by the operation that just ran.
``Operation.written`` holds those ids, and ``arrived`` walks the gang's
cards once and keeps the choice slots anchored on one of them.

An author may attach a screen — an interstitial — to a slot. When any
arriving slot carries one, ``onward`` sends the reader to the
``n26-next`` screen with every such slot named in the address, and to
wherever the act was going otherwise. Three acts ask: founding a gang,
hiring a model, and making a pick. A purchase and a clone never do,
however many slots they bring — each view opts in, so nothing here
decides. Nothing is stored: the screen derives itself from the address
each time it is opened.

A library with nothing attached pays one query per act for this and
nothing more.

A slot whose anchor predates the act — one made live because a
condition turned true — is not an arrival. Nothing in the library does
that today, and the gang sheet's own note about an unresolved slot still
says so.
"""

from urllib.parse import parse_qs, urlencode, urlsplit

from django.urls import reverse

from n26.library.staged import sees_staged

#: The most questions one screen asks. A founding can bring more than a
#: reader can take in at once; the rest wait on a screen of their own,
#: reached by Continue, so nothing that arrived is dropped.
MAX_ASKS = 20


def any_interstitials(*, include_staged=True):
    """Whether any interstitial is attached to any slot: the one query an
    act pays when the library holds none. Archived ones count, on the
    same terms ``interstitials_on`` reads them; staged ones count only
    for a reader who may see staged content, so a library holding
    nothing but staged screens is as cheap for everyone else as an
    empty one."""
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
    """``{slot pk: [attachment, …]}`` for the slots that carry one, each
    attachment with its ``interstitial`` and its ``position`` — the
    order the author gave the slots under that screen — the lists in
    the interstitials' own order.

    The player-side read, on the terms ``Slot.interstitials(
    include_archived=True)`` states: archiving is a pack owner's soft
    delete and never retracts content from a gang already holding the
    slot, so archived interstitials, attachments and packs all count.
    Staged ones are left out unless the reader may see staged content —
    staged is not yet live, which is a different thing from withdrawn.
    No pack narrowing: a slot the gang holds is already in play,
    whichever pack the screen attached to it belongs to.
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


def asking(gang, written, *, include_staged=False):
    """The addresses of the arriving slots the screen should ask about:
    unresolved, taking at least one pick, and carrying a live
    interstitial. In card order."""
    from n26.core.render import slot_key

    open_slots = [
        (host, slot)
        for host, slot in arrived(gang, written)
        if slot.slot is not None and slot.max_picks > 0 and not slot.is_resolved
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
    """The screen's address: every question it asks, each once, and where
    Continue leads. Encoded once here, so an address nested inside
    another is carried whole.

    More than ``MAX_ASKS`` questions are split: the first screenful is
    asked here, and the rest become a further screen that ``next``
    leads to — so Continue walks the reader through everything that
    arrived, and no question is quietly dropped.
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


def onward(request, gang, op, back, *, via=""):
    """Where the reader goes after an act: the screen for what just
    arrived when any of it carries an interstitial, else ``back``.

    ``via`` is a second address that may be that screen already — the
    pick screen's own return, where a choice worked at a pick at a time
    comes back to itself rather than to it. Where either is the screen,
    what arrived joins its questions instead of opening a second one.
    """
    if not op.written or not any_interstitials():
        return back
    shown = sees_staged(request.user)
    if not shown and not any_interstitials(include_staged=False):
        # Only staged screens, and a reader who may not see them: no
        # need to derive the gang to find out nothing will draw.
        return back
    keys = asking(gang, op.written, include_staged=shown)
    if not keys:
        return back
    standing = _already_asking(gang, back)
    if standing is None and via:
        standing = _already_asking(gang, via)
    if standing is not None:
        asked, back = standing
        keys = [*asked, *(key for key in keys if key not in asked)]
    return next_url(gang, keys, back)
