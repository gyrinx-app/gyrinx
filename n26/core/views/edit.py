"""One model's own page — the card, editable, and the owner's notes."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_miniature_or_404


@login_required
def edit_fighter(request, pk):
    """One model, whole: their card with its edit affordances, and the
    notes box.

    The card is rendered off the same gang derivation the sheet uses —
    one call, fixed queries — and the member picked out of it, so this
    page and the sheet cannot disagree about what the model is. The
    card draws in ``edit`` mode: the choice controls the sheet hides
    are offered here, outlined, and the Gear and Weapons rows carry the
    way to the Equip tab.

    POST saves the notes and nothing else. Notes are the owner's prose,
    not a fact the books watch — no rating moves, no ledger row is
    written — so this is a plain save rather than an operation. What
    the editor produced is stored as written and sanitised on the way
    out, so a tightened allowlist reaches old notes too.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import FighterNotesForm
    from n26.core.render import render_gang, roster, summarise_roster
    from n26.core.views.choose import link_slots
    from n26.core.views.gangs import _fighter_named
    from n26.core.views.learn import link_skills

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.membership.gang

    if request.method == "POST":
        form = FighterNotesForm(request.POST)
        # The one field is optional, so the form cannot fail — kept as a
        # form anyway, because that is where a second field will land.
        if form.is_valid():
            miniature.notes = form.cleaned_data["notes"]
            miniature.save(update_fields=["notes"])
            record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, notes=True)
            messages.success(request, "Notes saved.")
        return redirect("n26-edit-fighter", pk=miniature.pk)

    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    link_skills(*sheet.models)
    card = next(
        (member for member in sheet.models if member.id == str(miniature.pk)), None
    )
    if card is None:
        raise Http404("No such model")

    profile = miniature.membership.profile
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
            "renaming": _fighter_named(request, gang, "rename"),
            "edit_url": reverse("n26-edit-fighter", args=[miniature.pk]),
        },
    )
