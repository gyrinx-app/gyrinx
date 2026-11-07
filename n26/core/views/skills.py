"""Select skills and powers through a model's placed grids or checkbox editor.

The dedicated skills page limits offers to placed tiers. The edit-page offer
includes every skill and power set, grouped into placed or already-held sets
and the remaining options. These partitions affect presentation only.

Normally selections are free assignments with no cause. When a selected skill
matches an unresolved starting-skill offer, settle that offer instead so it
stops requesting a duplicate starting skill. Removing its answer reopens it.
Computed grants remain fixed because no stored assignment can be removed.
"""

import dataclasses

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_miniature_or_404
from n26.library.staged import sees_staged


def link_skills(*cards, among=None):
    """Link placed card skill grids to the model's checkbox editor.

    Read selectable collections once for all cards, or reuse ``among``.
    Preview cards without model identifiers remain unlinked.
    """
    from n26.core.access import model_collections

    selectable = {
        str(collection.pk)
        for collection in (model_collections() if among is None else among)
    }
    for card in cards:
        if card.id and set(card.placed_in) & selectable:
            card.skills_href = (
                reverse("n26-edit-fighter", args=[card.id]) + "#n26-skills-box"
            )


def _key(thing):
    """Identify content by model label and primary key across assignable tables."""
    return f"{thing._meta.label_lower}:{thing.pk}"


def _rows_on(card):
    """Index unsuppressed, non-broadcast root assignments by content identity."""
    rows = {}
    for node in card.roots:
        if node.broadcast or node.suppressed or node.assignment is None:
            continue
        rows.setdefault(_key(node.assignable), node.assignment)
    return rows


def _grants_on(computed):
    """Index computed skill and power grants with their granting sources."""
    return {
        _key(contribution.thing): contribution.source
        for contribution in (*computed.skills, *computed.powers)
    }


@dataclasses.dataclass(frozen=True)
class SkillsOffer:
    """One complete offer and its presentation partitions.

    Apply saves against ``everything``; ``own`` and ``rest`` only organise display.
    """

    #: Complete grouped offer used for saving and the All sets tab.
    everything: object
    #: Placed or already-held sets, including skills from outside the model's grid.
    own: object
    #: Flattened remaining options for search.
    rest: list


def _sets_on_offer(card, computed, among=None, *, include_staged=False):
    """Browse all skill and power collections, retaining fallback tiers.

    Mark tiers reached by placements and preserve section captions when the
    collection has several tiers. Query each collection independently so the
    editor can also offer unplaced sets.
    """
    from n26.core.access import model_collections
    from n26.core.browse import (
        EQUIPMENT_LIST,
        browse,
        narrow,
        placements_for,
        regrouped_by_placement,
        usability_for,
        with_use_notes,
    )
    from n26.core.render import offer_from_view
    from n26.library.models import Power, Skill

    held = _rows_on(card)
    granted = _grants_on(computed)
    found = []
    for collection in model_collections() if among is None else among:
        placements = placements_for(computed, collection)
        placed = {placement.section.name for placement in placements.values()}
        listed = with_use_notes(
            regrouped_by_placement(
                # Exclude subtypes because their checkbox editor uses a different write path.
                # Including them here could remove subtypes absent from this form's submitted skills.
                narrow(
                    browse(collection, EQUIPMENT_LIST, include_staged=include_staged),
                    kinds=(Skill, Power),
                ),
                placements,
                fallback=collection.default_section(),
                name=str(collection),
            ),
            usability_for(computed),
        )
        tiered = len(listed.sections) > 1
        for section in listed.sections:
            offer = offer_from_view(
                dataclasses.replace(listed, sections=[section]),
                label=str(collection),
                held=held,
                granted=granted,
            )
            for group in offer.groups:
                if tiered:
                    group.caption = section.name
                found.append((section.name in placed, group))
    return found


def skills_offer(card, computed, among=None, *, include_staged=False):
    """Build the complete checkbox offer and its placed, held and remaining partitions.

    Existing picks are checked; computed grants are fixed. Keep sets containing
    held skills in the main partition so their assignments can be cleared.
    Reuse ``among`` when the caller already loaded selectable collections.
    """
    from n26.core.render import ChoiceOffer

    own, rest, every = [], [], []
    for placed, group in _sets_on_offer(
        card, computed, among, include_staged=include_staged
    ):
        every.append(group)
        if placed or any(option.is_current for option in group.options):
            own.append(group)
        else:
            rest.extend(group.options)
    return SkillsOffer(
        everything=ChoiceOffer(label="", groups=every),
        own=ChoiceOffer(label="", groups=own),
        rest=rest,
    )


def _offered_keys(slot, computed, *, include_staged=False):
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
    return frozenset(_key(thing) for thing in things if thing is not None)


def _open_questions(computed):
    """Find unresolved modifier offers, excluding slot-pickable choices."""
    return [
        slot
        for slot in computed.choices
        if not slot.is_resolved and slot.offer is not None
    ]


def _answered_by(computed):
    """Map assigned content to the starting-skill offers it currently answers."""
    found = {}
    for slot in computed.choices:
        if slot.offer is None:
            continue
        for pick in slot.picks:
            if pick.assignment is None:
                continue
            found[_key(pick.assignable)] = slot
    return found


def _question_for(thing, questions, lists):
    """Find the first unresolved offer whose current Choose list includes the content."""
    key = _key(thing)
    for slot in questions:
        if key in lists[id(slot)]:
            return slot
    return None


def _answer_with(op, miniature, thing, questions, lists):
    """Settle a matching starting-skill offer, otherwise make a standing selection.

    Require an assignment anchor; broadcast anchors also identify the target model.
    """
    slot = _question_for(thing, questions, lists)
    if slot is None:
        return op.select(miniature, thing)
    anchor = getattr(slot.anchor, "assignment", None)
    if anchor is None:
        return op.select(miniature, thing)
    questions.remove(slot)
    host = {}
    if getattr(slot.anchor, "broadcast", False):
        host["miniature"] = miniature
    return op.choose(anchor, thing, offer=slot.offer, **host)


def apply_ticks(op, miniature, card, computed, ticked, *, include_staged=False):
    """Make stored skill selections match the complete current checkbox offer.

    Rebuild the offer server-side. A stale submission can clear newer selections
    across the whole offer, independently of its displayed tab. Ignore fixed grants
    on both sides of the comparison.

    Remove old selections first so a reopened starting-skill offer can receive a
    replacement in the same operation. Use standing selection when no offer matches.
    """
    offer = skills_offer(card, computed, include_staged=include_staged).everything
    rows = _rows_on(card)
    granted = _grants_on(computed)
    questions = _open_questions(computed)
    lists = {
        id(slot): _offered_keys(slot, computed, include_staged=include_staged)
        for slot in questions
    }
    answered = _answered_by(computed)

    # Deduplicate skill identities shared by multiple collections before selecting.
    options = {}
    for group in offer.groups:
        for option in group.options:
            options.setdefault(option.key, option)

    # Clear old answers before selecting replacements so a reopened offer can be settled.
    selected, cleared = [], []
    for key, option in options.items():
        if key in granted or key in ticked or key not in rows:
            continue
        op.remove(rows[key])
        cleared.append(option.name)
        slot = answered.get(key)
        if slot is not None and slot not in questions:
            questions.append(slot)
            lists.setdefault(
                id(slot), _offered_keys(slot, computed, include_staged=include_staged)
            )

    for key, option in options.items():
        if key in granted:
            continue
        if key in ticked and key not in rows:
            _answer_with(op, miniature, option.thing, questions, lists)
            selected.append(option.name)
    return selected, cleared


def _known_on(card):
    """Index stored non-broadcast card roots for duplicate marking."""
    return {
        f"{node.assignable._meta.label_lower}:{node.assignable.pk}"
        for node in card.roots
        if not node.broadcast
    }


def _marked(offer, known):
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


@login_required
def skills(request, pk):
    """List placed skill tiers and select one submitted content identity at no charge.

    Rebuild offers server-side and reject stale identities or known root assignments.
    Keep usability notes visible. A model with no placed collections receives an
    empty page rather than an unavailable route.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.access import selectable_for
    from n26.core.browse import (
        EQUIPMENT_LIST,
        browse,
        narrow,
        placements_for,
        regrouped_by_placement,
        usability_for,
        with_use_notes,
    )
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute
    from n26.core.operations import Refusal, operation
    from n26.core.render import offer_from_view
    from n26.core.views.equip import collection_tabs

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang
    # Use the same staged-content access for display and submitted selection.
    shown = sees_staged(request.user)

    # Reuse one computed card for placement and usability reads.
    card = build_card(miniature)
    index = build_modifier_index(carriers(card))
    computed = compute(card, index)

    back = reverse("n26-gang", args=[gang.pk])
    # Cancel and successful selection return to the model edit page that opened this screen.
    their_page = reverse("n26-edit-fighter", args=[miniature.pk])

    collections = selectable_for(computed)
    if not collections:
        # Keep an empty state for models without a grid so sibling navigation remains valid.
        return render(
            request,
            "n26/skills.html",
            {
                "gang": gang,
                "miniature": miniature,
                "nothing_to_select": True,
                "action": request.path,
                "back": back,
                "their_page": their_page,
                # Omit form actions when there is no selectable content; breadcrumbs provide navigation.
                "submit_label": "",
                "cancel_url": "",
                "pick_lead": "",
            },
        )

    chosen = next(
        (c for c in collections if str(c.pk) == request.GET.get("list")),
        collections[0],
    )
    placements = placements_for(computed, chosen)
    listed = narrow(
        with_use_notes(
            regrouped_by_placement(
                browse(chosen, EQUIPMENT_LIST, include_staged=shown),
                placements,
                fallback=chosen.default_section(),
                name=str(chosen),
            ),
            usability_for(computed),
        ),
        # Limit this screen to placed tiers; the checkbox editor separately offers unplaced sets.
        sections=[placement.section.name for placement in placements.values()],
    )
    offer = _marked(offer_from_view(listed, label=str(chosen)), _known_on(card))
    here = f"{request.path}?list={chosen.pk}"

    if request.method == "POST":
        wanted = request.POST.get("thing", "")
        picked = next(
            (
                option
                for group in offer.groups
                for option in group.options
                if option.key == wanted
            ),
            None,
        )
        if picked is None:
            # Reject stale or empty selections and redisplay the current offer.
            messages.error(request, "That is not one of the things available to pick.")
            return redirect(here)
        # Reject content already represented by a known non-broadcast root.
        if picked.key in _known_on(card):
            messages.error(request, f"{miniature.name} already has {picked.name}.")
            return redirect(here)
        try:
            with operation(gang, actor=request.user) as op:
                questions = _open_questions(computed)
                lists = {
                    id(slot): _offered_keys(slot, computed, include_staged=shown)
                    for slot in questions
                }
                selected = _answer_with(op, miniature, picked.thing, questions, lists)
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(here)
        record(
            request,
            N26Noun.ASSIGNMENT,
            EventVerb.CREATE,
            selected,
            gang_id=str(gang.pk),
            miniature_id=str(miniature.pk),
            thing=picked.name,
            collection=chosen.name,
        )
        messages.success(request, f"{miniature.name} selected {picked.name}.")
        return redirect(their_page)

    return render(
        request,
        "n26/skills.html",
        {
            "gang": gang,
            "miniature": miniature,
            "nothing_to_select": False,
            "chosen": chosen,
            "offer": offer,
            "action": here,
            "back": back,
            "their_page": their_page,
            "submit_label": "Select",
            "cancel_url": their_page,
            # Show collection tabs only when the grid reaches more than one collection.
            "collection_tabs": collection_tabs(collections, chosen),
            # Use a distinct slot name: Cotton slots share context names with unrelated page components.
            "pick_lead": (f"Select skills for {miniature.name}."),
        },
    )
