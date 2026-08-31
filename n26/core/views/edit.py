"""One model's own page — the card, editable, and the owner's notes."""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_miniature_or_404, trade_points_href

#: The kinds an owner edits by hand on this page: the assignable column
#: each section writes, the input name its form posts, and the heading
#: over its boxes.
EDITABLE_KINDS = {"subtypes": "subtype", "rules": "rule"}


@dataclass(frozen=True)
class _EditState:
    """How each thing of one kind stands on a card, keyed the way a pick
    list keys its options.

    Not "is it held" but *how* it is held, because each answer settles a
    different write: an owner's own addition is archived, anything else
    gains a removal, a standing removal is archived to bring the thing
    back, and something fixed is not offered at all.
    """

    #: Every thing of the kind the live library offers.
    offered: list
    #: The written assignment showing each thing, by key.
    stored: dict
    #: The subset the owner added themselves.
    own_adds: dict
    #: Keys the gang holds, riding this card.
    gang_held: set
    #: Key -> what grants it, for things no assignment stands behind.
    granted: dict
    #: Key -> the owner's standing removal of it.
    removed: dict
    #: Keys a removal could not shift, because money stands behind them.
    fixed: set


def _edit_state(own, computed, field):
    """What the card currently says for one editable kind, keyed the way
    a tick list keys its options.

    The diff needs to know not just whether a thing is held but *how*:
    any stored assignment showing it, which of those are the gang's
    riding this card, the subset that are the owner's own additions,
    what a modifier grants, the owner's standing removals — and which
    could not be taken away at all, because money stands behind every
    line of them. A suppressed line is held by nobody: it has been taken
    away, and the box for it opens clear.
    """
    from n26.core.effects import stands_whatever_happens
    from n26.core.models import Assignment, Reason
    from n26.core.views.learn import _key

    kind_class = Assignment._meta.get_field(field).related_model
    # The live library, as every player-facing offer reads it — an
    # archived subtype is not a box to tick.
    offered = list(kind_class.objects.selectable())
    stored, own_adds, gang_held = {}, {}, set()
    for node in own.all_nodes():
        if node.suppressed or node.assignment is None:
            continue
        if not isinstance(node.assignable, kind_class):
            continue
        key = _key(node.assignable)
        stored.setdefault(key, node.assignment)
        if node.broadcast:
            # The gang's, riding this card: it applies to this model —
            # which is what a tick says — and clearing it takes it away
            # from this model alone.
            gang_held.add(key)
            continue
        entry = getattr(node.assignment, "ledger_entry", None)
        if entry is not None and entry.reason == Reason.EDITED:
            own_adds.setdefault(key, node.assignment)
    granted = {
        _key(contribution.thing): contribution.source
        for contribution in getattr(computed, f"{field}s")
    }
    removed = {
        _key(row.assignable): row
        for row in own.removals
        if isinstance(row.assignable, kind_class)
    }
    # Bought, so a removal would leave it exactly where it is. Asked of
    # the engine's own rule rather than restated here, because a surface
    # that disagreed would offer a clearing that quietly does nothing.
    fixed = {
        key
        for key, assignment in stored.items()
        if stands_whatever_happens(own, assignment.assignable)
    }
    return _EditState(
        offered=offered,
        stored=stored,
        own_adds=own_adds,
        gang_held=gang_held,
        granted=granted,
        removed=removed,
        fixed=fixed,
    )


def _edits_offer(own, computed, field, heading):
    """One section of the edits box: every thing of the kind, as options.

    A granted thing's box still clears — the owner's clearing becomes a
    stored removal, and ticking it again archives that removal, so the
    content's own answer is always one click away. What does *not* clear
    is a thing money stands behind: a removal would leave it exactly
    where it is, so it is drawn fixed and says so rather than being
    offered and refused.

    Two answers, because the page draws them differently. What the card
    shows — and anything the owner has touched, so a thing they took
    away stays where it can be put back — is the list of boxes. The rest
    of the library is what the search panel offers: a box each, which
    appears in the list above once it is ticked.
    """
    from n26.core.render import ChoiceOffer, Choosable, ChoosableGroup
    from n26.core.views.learn import _key

    state = _edit_state(own, computed, field)
    current, rest = [], []
    for thing in state.offered:
        key = _key(thing)
        fixed_because = ""
        if key in state.fixed:
            # Named as a price rather than a rule: the owner can sell it
            # from the equip screen, which is the way back.
            fixed_because = "bought — sell it to take it away"
        if key in state.own_adds:
            detail = "added by you"
        elif key in state.removed:
            detail = "taken away by you"
        elif key in state.granted and key not in state.stored:
            detail = f"from {state.granted[key]}"
        elif key in state.gang_held:
            detail = "from the gang"
        else:
            detail = ""
        option = Choosable(
            key=key,
            name=str(thing),
            thing=thing,
            is_current=key in state.stored or key in state.granted,
            detail=detail,
            fixed_because=fixed_because,
        )
        if option.is_current or detail:
            current.append(option)
        else:
            rest.append(option)

    held = (
        ChoiceOffer(label="", groups=[ChoosableGroup(name=heading, options=current)])
        if current
        else None
    )
    return held, rest, bool(state.own_adds or state.removed)


#: How the skills box's two listings are named in the address.
OWN_SETS, ALL_SETS = "their-sets", "all-sets"


def _skills_tabs(miniature, current):
    """The two ways the skills box lists a model's sets.

    Their own first, because it is the everyday answer: the handful of
    sets somebody wrote a placement for, which is what a reader came to
    settle. The whole library is a tab away rather than the default,
    since it holds every set the content has and the two that are theirs
    would be lost among them.

    Both addresses render the whole page on a plain visit, so a tab is
    somewhere a link can point and a reload comes back to.
    """
    here = reverse("n26-edit-fighter", args=[miniature.pk])
    return [
        {
            "label": "Their sets",
            "href": f"{here}?skills={OWN_SETS}",
            "current": current == OWN_SETS,
        },
        {
            "label": "All sets",
            "href": f"{here}?skills={ALL_SETS}",
            "current": current == ALL_SETS,
        },
    ]


def _skills_here(request, miniature):
    """Where a skills save goes back to: the tab it was made from.

    The form carries which listing drew it, so settling the boxes leaves
    the reader looking at the same ones. A form naming no tab, or one
    this page does not draw, lands on the page's own default.

    What was posted chooses between addresses; it never becomes part of
    one. Every address here is built from this page's own route and one
    of its two constants, so no value a form carries can reach the
    reader's browser as somewhere to go.
    """
    here = reverse("n26-edit-fighter", args=[miniature.pk])
    asked = request.POST.get("tab")
    for tab in (OWN_SETS, ALL_SETS):
        if asked == tab:
            return f"{here}?skills={tab}"
    return here


def _apply_edits(op, miniature, own, computed, field, ticked):
    """Make what the card shows match what was ticked, and say what moved.

    The state is derived again here rather than trusted from the page,
    so a stale form can only name things the library offers now. Each
    box's difference picks its own write: a cleared owner-addition is
    archived, any other cleared held thing gains a stored removal, a
    ticked standing removal is archived so the thing comes back, and a
    ticked absence is added in the owner's name.
    """
    from n26.core.models import Reason
    from n26.core.views.learn import _key

    state = _edit_state(own, computed, field)
    added, taken, restored = [], [], []
    for thing in state.offered:
        key = _key(thing)
        if key in state.fixed:
            # Drawn fixed, and a fixed box submits nothing — so its
            # silence is not a clearing. Nothing here may act on it: a
            # removal would leave the thing on the card and the page
            # would report a loss the card denies.
            continue
        shown = key in state.stored or key in state.granted
        if key in ticked:
            if key in state.removed and not shown:
                op.remove(state.removed[key], note="restored")
                restored.append(str(thing))
            elif not shown and key not in state.removed:
                op.assign(thing, miniature=miniature, paid=0, reason=Reason.EDITED)
                added.append(str(thing))
        elif key in state.own_adds:
            op.remove(state.own_adds[key])
            if key in state.granted and key not in state.removed:
                # A grant also supplies it, and archiving the owner's
                # addition leaves that standing — clearing means gone by
                # every route, so the grant is cancelled too.
                op.take_away(miniature, thing)
            taken.append(str(thing))
        elif shown and key not in state.removed:
            op.take_away(miniature, thing)
            taken.append(str(thing))
    return added, taken, restored


@login_required
def edit_fighter(request, pk):
    """One model, whole: their card with its edit affordances, the
    characteristics they can set by hand, and the notes box.

    The card is rendered off the same gang derivation the sheet uses —
    one call, fixed queries — and the member picked out of it, so this
    page and the sheet cannot disagree about what the model is. The
    card draws in ``edit`` mode: the choice controls the sheet hides
    are offered here, outlined, and the Gear and Weapons rows carry the
    way to the Equip tab.

    Several forms post here, and ``act`` says which was clicked. Every
    one goes through an operation: notes and characteristics price
    nothing and move no rating, but they are part of the gang's story,
    so each writes a journal event and the history can say what the
    owner did. Notes and lore each save on their own, and htmx leaves
    the page as drawn so typing in one box survives saving the other.
    What the notes editor produced is stored as written and sanitised
    on the way out, so a tightened allowlist reaches old notes too.

    The subtypes and rules box edits what the model *is*: ticking adds
    in the owner's name, clearing stores a removal whatever route the
    thing arrived by, and each section's Reset archives the owner's
    edits so the content's own answer returns. The skills a model
    holds post the same way, and selecting writes an assignment while
    clearing archives one, so the whole difference lands or none of it
    does.

    A refused characteristic redraws the page with the boxes as typed
    and the complaint under them; anything saved lands back here.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.forms import (
        FighterLoreForm,
        FighterNotesForm,
        PictureForm,
        statline_override_form_for,
    )
    from n26.core.images import MAX_PX, PORTRAIT
    from n26.core.operations import Refusal, operation
    from n26.core.render import render_gang, roster, summarise_roster
    from n26.core.views.choose import link_slots
    from n26.core.views.gangs import _fighter_named
    from n26.core.views.htmx import is_htmx, stay_or_redirect
    from n26.core.views.learn import apply_ticks, link_skills, skills_offer
    from n26.core.views.owned import link_counters

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.membership.gang
    profile = miniature.membership.profile
    # A model with no entry behind it has no shape to set characteristics
    # to, so the section is simply not drawn for one.
    statline_class = statline_override_form_for(profile) if profile else None
    statline_edit = None

    if request.method == "POST" and request.POST.get("act") == "statline":
        if statline_class is not None:
            statline_edit = statline_class.opened_on(miniature, request.POST)
            if statline_edit.is_valid():
                with operation(gang, actor=request.user) as op:
                    op.set_stats(miniature, statline_edit.changes())
                record(
                    request, N26Noun.MODEL, EventVerb.UPDATE, miniature, statline=True
                )
                messages.success(request, "Characteristics saved.")
                return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST" and request.POST.get("act") == "skills":
        own = build_card(miniature)
        index = build_modifier_index([node.assignable for node in own.all_nodes()])
        try:
            with operation(gang, actor=request.user) as op:
                learned, cleared = apply_ticks(
                    op,
                    miniature,
                    own,
                    compute(own, index),
                    set(request.POST.getlist("skills")),
                )
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(_skills_here(request, miniature))
        record(
            request,
            N26Noun.MODEL,
            EventVerb.UPDATE,
            miniature,
            learned=len(learned),
            cleared=len(cleared),
        )
        # What moved, by name: a box ticked by mistake is easiest to spot
        # in the sentence saying what it did.
        moved = [
            phrase
            for phrase in (
                f"selected {', '.join(learned)}" if learned else "",
                f"lost {', '.join(cleared)}" if cleared else "",
            )
            if phrase
        ]
        messages.success(
            request,
            f"{miniature.name} {' and '.join(moved)}." if moved else "Skills saved.",
        )
        return redirect(_skills_here(request, miniature))
    elif request.method == "POST" and request.POST.get("act") in EDITABLE_KINDS:
        field = EDITABLE_KINDS[request.POST["act"]]
        own = build_card(miniature)
        index = build_modifier_index([node.assignable for node in own.all_nodes()])
        try:
            with operation(gang, actor=request.user) as op:
                added, taken, restored = _apply_edits(
                    op,
                    miniature,
                    own,
                    compute(own, index),
                    field,
                    set(request.POST.getlist(request.POST["act"])),
                )
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect("n26-edit-fighter", pk=miniature.pk)
        record(
            request,
            N26Noun.MODEL,
            EventVerb.UPDATE,
            miniature,
            edits=field,
            added=len(added),
            taken=len(taken),
            restored=len(restored),
        )
        # Everything named here really moved: a thing a removal could not
        # shift is drawn fixed and never acted on, so the sentence cannot
        # claim a loss the card denies.
        moved = [
            phrase
            for phrase in (
                f"gained {', '.join(added)}" if added else "",
                f"lost {', '.join(taken)}" if taken else "",
                f"got {', '.join(restored)} back" if restored else "",
            )
            if phrase
        ]
        messages.success(
            request,
            f"{miniature.name} {' and '.join(moved)}." if moved else "Saved.",
        )
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST" and request.POST.get("act") == "reset-edits":
        field = request.POST.get("kind")
        if field in EDITABLE_KINDS.values():
            try:
                with operation(gang, actor=request.user) as op:
                    undone = op.reset_edits(miniature, field)
            except Refusal as refusal:
                messages.error(request, str(refusal))
                return redirect("n26-edit-fighter", pk=miniature.pk)
            record(
                request,
                N26Noun.MODEL,
                EventVerb.UPDATE,
                miniature,
                reset=field,
                undone=len(undone),
            )
            messages.success(
                request,
                f"{miniature.name}'s {field} edits are undone."
                if undone
                else "Nothing to reset.",
            )
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST" and request.POST.get("act") == "lore":
        form = FighterLoreForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_lore(miniature, form.cleaned_data["lore"])
            record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, lore=True)
            messages.success(request, "Lore saved.")
        return stay_or_redirect(
            request, reverse("n26-edit-fighter", args=[miniature.pk])
        )
    elif request.method == "POST" and request.POST.get("act") == "notes":
        form = FighterNotesForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_notes(miniature, form.cleaned_data["notes"])
            record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, notes=True)
            messages.success(request, "Notes saved.")
        return stay_or_redirect(
            request, reverse("n26-edit-fighter", args=[miniature.pk])
        )
    elif request.method == "POST" and request.POST.get("act") == "picture":
        form = PictureForm(request.POST, request.FILES, ratio=PORTRAIT)
        if form.is_valid():
            new_picture = bool(form.cleaned_data["image"])
            dropped_picture = (
                form.cleaned_data["remove_image"]
                and bool(miniature.image)
                and not new_picture
            )
            with operation(gang, actor=request.user) as op:
                op.set_image(
                    miniature,
                    form.cleaned_data["image"],
                    clear=form.cleaned_data["remove_image"],
                )
            record(
                request,
                N26Noun.MODEL,
                EventVerb.UPDATE,
                miniature,
                image=new_picture or dropped_picture,
            )
            if new_picture:
                messages.success(request, "Picture saved.")
            elif dropped_picture:
                messages.success(request, "Picture removed.")
            else:
                messages.success(request, "Nothing changed.")
        else:
            # The one field that can refuse — a file that is not an
            # image. The reason travels as a message to the page this
            # redirects back to.
            for wrong in form.errors.get("image", []):
                messages.error(request, wrong)
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST":
        # An act this page does not know writes nothing — the notes form
        # is not a place for a stray submit to land, because its empty
        # box is a real answer and would clear what is written.
        return redirect("n26-edit-fighter", pk=miniature.pk)

    if statline_edit is None and statline_class is not None:
        statline_edit = statline_class.opened_on(miniature)

    # The model's own card, computed: the boxes need the assignments and
    # the grants behind what the card shows, which the sheet does not
    # carry. A fixed reading, however much this model knows.
    own = build_card(miniature)
    index = build_modifier_index([node.assignable for node in own.all_nodes()])
    computed = compute(own, index)
    skills = skills_offer(own, computed)
    asked = request.GET.get("skills")
    # A model no placement names has nothing under the first heading, so
    # the box opens on the listing holding every set. An address naming a
    # tab is obeyed either way: the first one saying so is a real answer.
    tab = (
        asked
        if asked in (OWN_SETS, ALL_SETS)
        else (ALL_SETS if skills.own.is_empty else OWN_SETS)
    )
    skills_box = {
        "miniature": miniature,
        "edit_url": reverse("n26-edit-fighter", args=[miniature.pk]),
        # Nothing rather than an empty box: a library with no set for a
        # model to take anything from is not worth asking about. Which of
        # the two listings is empty is the box's own business, and it says
        # so under its own heading.
        "skills": None
        if skills.everything.is_empty
        else (skills.own if tab == OWN_SETS else skills.everything),
        # The panel searches what the drawn listing leaves out, which on
        # the listing holding every set is nothing.
        "skills_more": skills.rest if tab == OWN_SETS else [],
        "skills_tab": tab,
        "skills_tabs": _skills_tabs(miniature, tab),
    }

    # A tab clicked with script running is answered with the box alone,
    # before the gang sheet is built: changing which sets are listed
    # changes nothing else on the page, and the address still says which
    # tab is open so a reload draws the same screen.
    if request.method == "GET" and asked and is_htmx(request):
        answer = render(
            request, "n26/includes/skills_box.html", {**skills_box, "oob": True}
        )
        answer["HX-Replace-Url"] = request.get_full_path()
        return answer

    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    link_skills(*sheet.models)
    card = next(
        (member for member in sheet.models if member.id == str(miniature.pk)), None
    )
    if card is None:
        raise Http404("No such model")
    # Only here. A counter is drawn wherever a card is, and moved on the
    # model's own page: doing it quickly, for a whole roster after a
    # battle, is a screen built for that and not a control the gang
    # sheet grows.
    link_counters(card)

    subtype_edits, subtype_more, subtype_edits_dirty = _edits_offer(
        own, computed, "subtype", "Subtypes"
    )
    rule_edits, rule_more, rule_edits_dirty = _edits_offer(
        own, computed, "rule", "Special rules"
    )

    # The header's far corner: the gang's figures and the roster tally,
    # the same numbers the equip face keeps there. One query.
    members = roster(gang)
    return render(
        request,
        "n26/fighter_edit.html",
        {
            "miniature": miniature,
            "gang": gang,
            "card": card,
            "summary": summarise_roster(members),
            "trade_points_href": trade_points_href(gang, request.user),
            # The role beside the name: the rank the profile is filed
            # under, which is what a reader checking "which of my models
            # is this" wants said once at the top. The bare name — the
            # category's own str carries its section, which is taxonomy
            # rather than anything about this model.
            "role": profile.category.name if profile and profile.category else "",
            "form": FighterNotesForm(initial={"notes": miniature.notes}),
            "lore_form": FighterLoreForm(initial={"lore": miniature.lore}),
            # The boxes, not the form: pairing a statline type with a
            # bound form is display logic, and the component that draws
            # them has no business knowing what a form looks like.
            "statline_cells": statline_edit.cells() if statline_edit else None,
            # Which sets are listed, which tab is open, and what the
            # panel searches — the same box the tab click is answered
            # with, so the two cannot draw different things.
            **skills_box,
            # A library offering no subtypes and no rules draws no edits
            # box at all. Each section carries its own Reset, drawn only
            # while the owner has edits of that kind to undo.
            "subtype_edits": subtype_edits,
            "subtype_more": subtype_more,
            "subtype_edits_dirty": subtype_edits_dirty,
            "rule_edits": rule_edits,
            "rule_more": rule_more,
            "rule_edits_dirty": rule_edits_dirty,
            "renaming": _fighter_named(request, gang, "rename"),
            # The crop spec the picture box stamps onto the browser's
            # dialog — handed from the same constants the server crops
            # with, so the two cannot disagree.
            "picture_shape": PORTRAIT,
            "picture_max": MAX_PX,
            "picture_url": miniature.image.url if miniature.image else "",
        },
    )
