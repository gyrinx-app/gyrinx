"""Selecting a skill — the standing half of the skills surface.

A founding pick is a question somebody asked ("a Leader starts with a
Primary skill") and it is chosen for at its own address. This is the other
half: what a fighter may select at any time, which nobody asked and which
is not a question at all — it is their **grid**, the placements their
profile and subtypes carry, read as a list.

So the address names a fighter rather than a slot::

    /fighters/<model>/skills/?list=<collection>

and the screen is the same shape the choose page draws: the fighter's
own view of a collection, resectioned by their placements, with the
unplaced tier dropped — a skill nobody placed for them is not theirs to
select, however visible it is on a browse (``n26.core.browse`` keeps it
there deliberately, and the roll-anything pick wants exactly that).

A fighter whose grid places nothing gets the screen anyway, saying
there is nothing for them to select. The grid is the access and an
unauthored one is a content gap, but the address names a fighter rather
than the gap: it is theirs whether or not anybody has graded them, so
the switcher on the next fighter's screen can offer it without knowing
which of them have a grid.

What clicking writes is usually ``Operation.select``: free, recorded, and
caused by nothing, so what a fighter earned survives the assignment that
opened the set up to them.

If the card is still asking for a starting skill, and the thing selected
is on that question's Choose list, the click is that answer — written the
way Choose writes it. A Secondary skill is not a Primary skill, so it
stays a standing selection and the question stays open. Otherwise the
card would keep asking beside a skill the owner just picked from the
list, and a later Choose would hand out a second starting skill.

A listing is offered a second way, as a box to tick on the fighter's own
edit page (``skills_offer`` and ``apply_ticks``). One screen selects a
thing at a time and the other settles the whole list at once, and the
two draw different lists: this screen keeps to the fighter's own
placements, while the edit page offers every set the library holds.

The difference is in what each offers, not in what either may write:
both make the same assignment, at no price and caused by nothing, and a
skill selected on one is indistinguishable from the same skill selected
on the other. What separates them is who is reading. This screen is the
fighter's own view — theirs, tier by tier, one click at a time — and
offering every set here would bury the two that are actually theirs
under every set that is not. The edit page is where an owner settles
what a model is, beside the boxes for their subtypes and special rules,
and there the answer to "may I take a skill from another house's tree"
is yes: the game allows it, and a skill already held from such a set can
be cleared nowhere else.
"""

import dataclasses

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_miniature_or_404


def link_skills(*cards, among=None):
    """Point every card's Skills control at this fighter's skills screen.

    One query for a whole roster, and none per card: which collections
    hold what a model selects is asked once, and each card already knows
    which collections its own grid reaches. A card depicting nobody — a
    hire preview, a gallery sample — keeps an empty href and draws no
    control, which is what a print sheet wants too.

    ``among`` is that answer, where the caller has already asked for it —
    a page drawing a listing of the same collections has, and asking
    twice on one request would be the same query twice.
    """
    from n26.core.access import model_collections

    selectable = {
        str(collection.pk)
        for collection in (model_collections() if among is None else among)
    }
    for card in cards:
        if card.id and set(card.placed_in) & selectable:
            card.select_href = reverse("n26-select", args=[card.id])


def _key(thing):
    """How a pick list keys its options: the table and the key, because a
    bare primary key is ambiguous across the assignable tables."""
    return f"{thing._meta.label_lower}:{thing.pk}"


def _rows_on(card):
    """The stored assignment behind each thing this model holds, keyed the
    way a pick list keys its options — so a tick list can find what a
    cleared box refers to.

    The model's own assignments only: what the gang holds rides every member's
    card and is not one fighter's to give up, and a line something has
    taken away is not held at all.
    """
    rows = {}
    for node in card.roots:
        if node.broadcast or node.suppressed or node.assignment is None:
            continue
        rows.setdefault(_key(node.assignable), node.assignment)
    return rows


def _grants_on(computed):
    """What a modifier gives this model and what gives it — skills and
    powers alike, keyed the same way.

    Nothing stored is behind these, so a surface offering things to tick
    draws them fixed rather than as boxes an owner could clear.
    """
    return {
        _key(contribution.thing): contribution.source
        for contribution in (*computed.skills, *computed.powers)
    }


@dataclasses.dataclass(frozen=True)
class SkillsOffer:
    """One derivation, in the three shapes the edit page draws it in.

    ``everything`` is the whole of it and the only one a save is applied
    against. ``own`` and ``rest`` are the same options partitioned for
    reading, so which tab a click came from can never decide what it is
    allowed to do.
    """

    #: Every set, grouped, tier by tier — the All sets tab.
    everything: object
    #: The sets this model's placements name, plus any they already hold
    #: something in, so a skill from elsewhere can be cleared without
    #: going looking for it.
    own: object
    #: The other sets' options, flat, for the panel that searches them.
    rest: list


def _sets_on_offer(card, computed, among=None):
    """Every set a model could hold something from, one group each, said
    with whether their placements name the tier it sits in.

    Every collection holding what a model is, resectioned by their
    placements and kept whole: the fallback tier the unplaced gather
    under stays on the listing, because a set nobody placed for them is
    still a set they may take from.

    That is not free. A screen keeping to the placements browses only
    the collections those reach; this one browses all of them, and each
    is a fixed handful of queries — so a model placed into one of two
    collections pays for the second as well. The price buys the panel
    that searches what the first tab does not draw, which has to know
    the whole library to offer it.

    Built a section at a time so each group knows which tier it came
    from. A one-section view is not tiered and ``offer_from_view`` writes
    no caption for it, so the caption is put back here where the whole
    listing spans more than one — the reader is being told Primary from
    Secondary, and that is a fact about the listing rather than about the
    slice it is being built in.
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
                # Skills and powers, and nothing else a model can be.
                # Subtypes are of the same family and a collection may
                # perfectly well hold them, but they are the edits box's
                # to settle: were one on this list, a save that did not
                # tick it would take it away — by the wrong write, and
                # from a box the owner was not looking at.
                narrow(browse(collection, EQUIPMENT_LIST), kinds=(Skill, Power)),
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


def skills_offer(card, computed, among=None):
    """What this model may hold, as a list to tick rather than to click.

    Every set the library holds for a model, skills and powers alike —
    not only the ones their placements reach. A set nobody placed for
    them is still a set the game has, and an owner reaching for one is
    doing something the rules allow; the placements say which are
    *theirs*, which is worth drawing, and not much more.

    So the tiers are drawn as the placements name them, and everything
    unplaced keeps the heading the browse filed it under — the
    collection's own default section, or "Other" last of all.

    Ticked where the model already holds the thing, by any route. What a
    modifier grants says what grants it and is fixed: no assignment is
    behind it, so there is nothing a click here could take away.

    The partition is a reading aid, never a permission: a set the model
    holds something in is drawn among their own so it can be cleared
    where they will look for it, and everything else is on the same
    listing one tab or one search away.

    ``among`` is the collections to read, for a caller that has already
    asked which they are — the same answer :func:`link_skills` wants,
    and one query rather than two where a page needs both.
    """
    from n26.core.render import ChoiceOffer

    own, rest, every = [], [], []
    for placed, group in _sets_on_offer(card, computed, among):
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


def _offered_keys(slot, computed):
    """What the Choose page lists for this question, keyed as the tick
    list keys its options.

    That list is the match: a Secondary skill is not a Primary skill,
    even though both are skills and both appear on the edit page.
    """
    from n26.core.browse import offered_by

    listed = offered_by(slot, computed)
    if listed is None:
        return frozenset()
    if hasattr(listed, "all_lines"):
        things = (line.thing for line in listed.all_lines())
    else:
        things = (getattr(item, "thing", item) for item in listed)
    return frozenset(_key(thing) for thing in things if thing is not None)


def _open_questions(computed):
    """Founding questions this card still asks, with what Choose lists
    for each.

    A slot of pickables is not one of these: this surface never writes
    those. Only a modifier's offer is — the Leader's starting skill, a
    Haunt's first power.
    """
    return [
        slot
        for slot in computed.choices
        if not slot.is_resolved and slot.offer is not None
    ]


def _answered_by(computed):
    """Which held thing currently answers which founding question."""
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
    """The first open question whose Choose list names this thing."""
    key = _key(thing)
    for slot in questions:
        if key in lists[id(slot)]:
            return slot
    return None


def _answer_with(op, miniature, thing, questions, lists):
    """Write ``thing`` as the answer to an open founding question if it
    is on that question's Choose list, otherwise as a standing selection.

    A tick on the edit page and a click on the skills screen are the
    same write. Selecting a second skill, or a skill the Choose page
    would not have listed, stays a standing selection — caused by
    nothing, surviving a profile swap — because it is not the starting
    pick.
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


def apply_ticks(op, miniature, card, computed, ticked):
    """Make what a model holds match what was ticked, and say what moved.

    The listing is derived again here rather than trusted from the page,
    so a stale form or a hand-made click can only name things that are on
    the list now. That listing is the whole of it, never the half a tab
    is showing: both tabs draw the same options and the panel searches
    the rest of them, so which one a save came from settles nothing and
    is not asked. What follows is that a form submitted from a page
    drawn long ago clears whatever has been selected since, across the
    whole library rather than one corner of it.

    A newly ticked thing is selected — free, and caused by nothing, the
    same write the skills screen makes — unless the card is still asking
    for a starting skill and this thing is on that question's Choose
    list. Then the tick is that answer, written the way Choose writes
    it, so the question leaves the card rather than sitting beside the
    skill as if nobody had picked. A Secondary skill cannot answer
    "Primary skill". Clearing the skill that answered a question opens
    it again; a replacement ticked in the same save answers it afresh
    if it is on the list.

    Granted things are on neither side of the difference, because a
    fixed box submits nothing and reading its silence as a clearing
    would take away the assignment of anything a modifier also grants.
    """
    offer = skills_offer(card, computed).everything
    rows = _rows_on(card)
    granted = _grants_on(computed)
    questions = _open_questions(computed)
    lists = {id(slot): _offered_keys(slot, computed) for slot in questions}
    answered = _answered_by(computed)

    # One entry per thing: two collections may both list a skill, and a
    # second sighting of a ticked one must not select it twice.
    options = {}
    for group in offer.groups:
        for option in group.options:
            options.setdefault(option.key, option)

    # Removals first: clearing the skill that answered a question opens
    # it again, so a replacement ticked in the same save can answer it
    # rather than land as a second starting skill beside a fresh Choose.
    selected, cleared = [], []
    for key, option in options.items():
        if key in granted or key in ticked or key not in rows:
            continue
        op.remove(rows[key])
        cleared.append(option.name)
        slot = answered.get(key)
        if slot is not None and slot not in questions:
            questions.append(slot)
            lists.setdefault(id(slot), _offered_keys(slot, computed))

    for key, option in options.items():
        if key in granted:
            continue
        if key in ticked and key not in rows:
            _answer_with(op, miniature, option.thing, questions, lists)
            selected.append(option.name)
    return selected, cleared


def _known_on(card):
    """What this model already has, keyed the way a pick list keys its
    options — so a listing can say "already known" rather than let
    somebody select the same skill twice in silence."""
    return {
        f"{node.assignable._meta.label_lower}:{node.assignable.pk}"
        for node in card.roots
        if not node.broadcast
    }


def _marked(offer, known):
    """The same offer, with the things this model already has said so.

    Said, never dropped: a known skill keeps its place in the listing so
    the reader can see it is covered, and the mark is why the POST's
    refusal of a second copy never surprises anyone.
    """
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
def select(request, pk):
    """What this fighter may select, and the click that selects it.

    GET asks and writes nothing. POST names one thing from the list the
    server has just re-derived — never a price, and never a free-text
    identity — and writes it as the fighter's own, at no charge.

    Nothing is removed from the listing: a skill the fighter's Type may
    not use keeps its place with a note on it, exactly as it does on the
    equip page, and a skill they already have is marked rather than
    hidden.
    The one click refused is a second copy of something they hold — by
    any route, a grant and a settled choice included — because a
    duplicate skill means nothing and a card reading "Marksman,
    Marksman" is a bug however honestly it got there.
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
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.operations import Refusal, operation
    from n26.core.render import offer_from_view
    from n26.core.views.equip import collection_tabs

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    # One card build serves the whole page: the grid that decides which
    # collections are theirs, and how usable each line is, are both read
    # off the same computed card.
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)

    back = reverse("n26-gang", args=[gang.pk])
    # The model's own page is the way out, because it is the only screen
    # the skills control is drawn on: a reader who cancels, or who selects
    # something, is put back where they clicked rather than a level above
    # it. The gang is still the breadcrumb's parent, one step further up.
    their_page = reverse("n26-edit-fighter", args=[miniature.pk])

    collections = selectable_for(computed)
    if not collections:
        # Nobody has graded this fighter in a category, so there is
        # nothing they could select — a gap in the content, and a page
        # that says so. Refusing instead would put a dead row in the
        # switcher every other fighter's skills screen draws.
        return render(
            request,
            "n26/select.html",
            {
                "gang": gang,
                "miniature": miniature,
                "nothing_to_select": True,
                "action": request.path,
                "back": back,
                "their_page": their_page,
                # No act and no way out at the foot of the page: there is
                # nothing to submit, and a lone Cancel under a page that
                # asked nothing cancels nothing. The breadcrumb is the
                # way back, to the model and to the gang beyond them.
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
                browse(chosen, EQUIPMENT_LIST),
                placements,
                fallback=chosen.default_section(),
                name=str(chosen),
            ),
            usability_for(computed),
        ),
        # Only the tiers their grid names. The browse keeps every
        # unplaced category under the fallback so nothing is hidden from
        # a reader buying from a list; here the tiers *are* the offer, and
        # another house's sets are not this fighter's to select.
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
            # Not on this list — a stale page, or a click with nothing
            # selected. The list itself is the reply either way.
            messages.error(request, "That is not one of the things available to pick.")
            return redirect(here)
        # A skill the model already has, by any route — selected, granted,
        # or chosen for a founding choice. A second copy means nothing
        # in the game and reads as a bug on the card, so this is refused
        # like a stale click rather than left to the owner: it is not a
        # judgement about the rules, there is simply nothing it could add.
        if picked.key in _known_on(card):
            messages.error(request, f"{miniature.name} already has {picked.name}.")
            return redirect(here)
        try:
            with operation(gang, actor=request.user) as op:
                questions = _open_questions(computed)
                lists = {id(slot): _offered_keys(slot, computed) for slot in questions}
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
        "n26/select.html",
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
            # Which collection, when a fighter's grid reaches more than
            # one. Drawn as tabs only then: with a single collection
            # there is nothing to choose, and the heading names it.
            "collection_tabs": collection_tabs(collections, chosen),
            # Not "lead". A cotton slot is a context variable, and any
            # component on the page with a slot of that name — the site
            # footer's columns have one — draws whatever the page
            # happens to have under it.
            "pick_lead": (f"Select skills for {miniature.name}."),
        },
    )
