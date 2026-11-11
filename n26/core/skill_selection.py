"""Shared skill and power offer matching for model selection and editing."""

import dataclasses


def content_key(thing):
    """Identify content by model label and primary key across assignable tables."""
    return f"{thing._meta.label_lower}:{thing.pk}"


def offered_keys(slot, computed, *, include_staged=False):
    """Index exactly the content listed by Choose for a starting-skill offer.

    A skill from another tier cannot settle the offer merely because its kind matches.
    """
    from n26.core.browse import offered_by

    listed = offered_by(slot, computed, include_staged=include_staged)
    if listed is None:
        return frozenset()
    if hasattr(listed, "all_lines"):
        things = (line.thing for line in listed.all_lines())
    else:
        things = (getattr(item, "thing", item) for item in listed)
    return frozenset(content_key(thing) for thing in things if thing is not None)


def open_offers(computed):
    """Find unresolved modifier offers, excluding slot-pickable choices."""
    return [
        slot
        for slot in computed.choices
        if not slot.is_resolved and slot.offer is not None
    ]


def offer_for(thing, offers, lists):
    """Find the first unresolved offer whose current Choose list includes the content."""
    key = content_key(thing)
    for slot in offers:
        if key in lists[id(slot)]:
            return slot
    return None


def select_from_offer(op, miniature, thing, offers, lists):
    """Settle a matching starting-skill offer, otherwise make a standing selection.

    Require an assignment anchor; broadcast anchors also identify the target model.
    """
    slot = offer_for(thing, offers, lists)
    if slot is None:
        return op.select(miniature, thing)
    anchor = getattr(slot.anchor, "assignment", None)
    if anchor is None:
        return op.select(miniature, thing)
    offers.remove(slot)
    host = {}
    if getattr(slot.anchor, "broadcast", False):
        host["miniature"] = miniature
    return op.choose(anchor, thing, offer=slot.offer, **host)


def known_on(card):
    """Index stored non-broadcast card roots for duplicate marking."""
    return {content_key(node.assignable) for node in card.roots if not node.broadcast}


def mark_known(offer, known):
    """Annotate known skills without removing them from the offer."""
    for group in offer.groups:
        group.options = [
            option
            if option.key not in known
            else dataclasses.replace(
                option,
                detail="; ".join(filter(None, [option.detail, "already known"])),
            )
            for option in group.options
        ]
    return offer
