"""One model's own page — the card, editable, and the owner's notes."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_miniature_or_404


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

    Three forms post here, and ``act`` says which was clicked. Notes are
    the owner's prose and characteristics they set are the owner's
    numbers; neither is a fact the books watch — no rating moves, no
    ledger entry is written — so both are plain saves rather than
    operations. What the notes editor produced is stored as written and
    sanitised on the way out, so a tightened allowlist reaches old notes
    too.

    The skills a model holds are the third, and the one thing here the
    books do watch: learning writes an assignment and clearing archives one, so
    that form goes through an operation and the whole difference lands
    or none of it does.

    A refused characteristic redraws the page with the boxes as typed
    and the complaint under them; anything saved lands back here.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.forms import FighterNotesForm, statline_override_form_for
    from n26.core.operations import Refusal, operation
    from n26.core.render import render_gang, roster, summarise_roster
    from n26.core.views.choose import link_slots
    from n26.core.views.gangs import _fighter_named
    from n26.core.views.learn import apply_ticks, link_skills, ticked_offer

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
                statline_edit.save(miniature)
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
            return redirect("n26-edit-fighter", pk=miniature.pk)
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
                f"learned {', '.join(learned)}" if learned else "",
                f"lost {', '.join(cleared)}" if cleared else "",
            )
            if phrase
        ]
        messages.success(
            request,
            f"{miniature.name} {' and '.join(moved)}." if moved else "Skills saved.",
        )
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST":
        form = FighterNotesForm(request.POST)
        # The one field is optional, so the form cannot fail — kept as a
        # form anyway, because that is where a second field will land.
        if form.is_valid():
            miniature.notes = form.cleaned_data["notes"]
            miniature.save(update_fields=["notes"])
            record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, notes=True)
            messages.success(request, "Notes saved.")
        return redirect("n26-edit-fighter", pk=miniature.pk)

    if statline_edit is None and statline_class is not None:
        statline_edit = statline_class.opened_on(miniature)

    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    link_skills(*sheet.models)
    card = next(
        (member for member in sheet.models if member.id == str(miniature.pk)), None
    )
    if card is None:
        raise Http404("No such model")

    # The model's own card again, computed: the sheet hands back what to
    # draw, and the tick list needs the assignments and the grants behind it.
    # A fixed reading, however much this model knows.
    own = build_card(miniature)
    index = build_modifier_index([node.assignable for node in own.all_nodes()])
    skills = ticked_offer(own, compute(own, index))

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
            "roster_count": len(members),
            "summary": summarise_roster(members),
            # The role beside the name: the rank the profile is filed
            # under, which is what a reader checking "which of my models
            # is this" wants said once at the top. The bare name — the
            # category's own str carries its section, which is taxonomy
            # rather than anything about this model.
            "role": profile.category.name if profile and profile.category else "",
            "form": FighterNotesForm(initial={"notes": miniature.notes}),
            # The boxes, not the form: pairing a statline type with a
            # bound form is display logic, and the component that draws
            # them has no business knowing what a form looks like.
            "statline_cells": statline_edit.cells() if statline_edit else None,
            # Nothing rather than an empty box: a model whose grid reaches
            # no set has nothing to tick, and a heading over a blank
            # square would read as a list that failed to load. The card's
            # own Skills row still leads to the screen that says why.
            "skills": None if skills.is_empty else skills,
            "renaming": _fighter_named(request, gang, "rename"),
            "edit_url": reverse("n26-edit-fighter", args=[miniature.pk]),
        },
    )
