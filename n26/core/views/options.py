"""Changing a model's options — the web face of ``Operation.rechoose``."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify

from n26.core.views.permissions import _own_miniature_or_404


def _option_rows(entry, chosen_pks):
    """The entry's groups as the page draws them, checked states decided here.

    The same groups the hire listing drew, in the same order and under
    the same field scheme, so the submission parses through the same code
    — but checked from what the model *currently* takes rather than from
    the defaults. A one-of group with nothing recorded is on its head:
    that is what a group with nothing picked means at purchase, and what
    ``resolve_selection`` will read an untouched submission back to.
    """
    groups = []
    for index, group in enumerate(entry.groups):
        if not group.offers_a_choice:
            continue
        taken_here = any(
            option.default_set is not None and option.default_set.pk in chosen_pks
            for option in group.options
        )
        options = []
        for position, option in enumerate(group.options):
            if option.default_set is None:
                # The synthesised standard option: what a profile with no
                # alternatives has. Nothing to save, nothing to draw.
                continue
            options.append(
                {
                    "name": option.name,
                    "price": option.price,
                    "value": position,
                    "checked": option.default_set.pk in chosen_pks
                    or (group.choose == "one" and not taken_here and option.is_default),
                }
            )
        groups.append(
            {
                "index": index,
                "choose": group.choose,
                "options": options,
                "none_checked": group.choose == "one-or-none" and not taken_here,
            }
        )
    return groups


@login_required
def fighter_options(request, pk):
    """The options a model was hired with, reopened.

    The same groups the hire listing offered, checked from what the model
    currently takes, with one Save. POST resolves the picks exactly as
    the hire did and hands them to ``op.rechoose``: rows swap, the price
    difference lands on the hire's own line in either direction, and an
    upgrade the gang cannot afford unwinds whole.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.hire import build_hire_entry
    from n26.core.operations import Refusal, operation
    from n26.core.render import roster, summarise_roster
    from n26.core.views.hire import _chosen, _picks

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.membership.gang
    profile = miniature.membership.profile
    here = reverse("n26-fighter-options", args=[miniature.pk])
    entry = build_hire_entry(profile)

    if request.method == "POST":
        picks = _picks(request.POST, profile, entry)
        entry_row = getattr(miniature.membership, "ledger_entry", None)
        before = entry_row.paid if entry_row is not None else 0
        try:
            with operation(gang, actor=request.user) as op:
                op.rechoose(miniature.membership, option=_chosen(picks))
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(here)
        except ValueError:
            # A set this profile does not offer — what resolve_selection
            # refuses and the indices cannot express. A broken link, not
            # a rule to explain.
            raise Http404("No such option") from None
        if entry_row is not None:
            entry_row.refresh_from_db()
        after = entry_row.paid if entry_row is not None else 0
        record(
            request,
            N26Noun.MODEL,
            EventVerb.UPDATE,
            miniature,
            options=True,
            delta=after - before,
        )
        if after > before:
            messages.success(request, f"Options saved — {after - before}¢ charged.")
        elif after < before:
            messages.success(request, f"Options saved — {before - after}¢ back.")
        else:
            messages.success(request, "Options saved.")
        return redirect(here)

    chosen_pks = {
        row.default_set_id for row in miniature.membership.chosen_options.all()
    }
    members = roster(gang)
    return render(
        request,
        "n26/fighter_options.html",
        {
            "miniature": miniature,
            "gang": gang,
            "role": (profile.category.name if profile and profile.category else ""),
            "roster_count": len(members),
            "summary": summarise_roster(members),
            "groups": _option_rows(entry, chosen_pks),
            # The field scheme is the hire listing's, slugified pk and all,
            # so the parser reads this page's POST unchanged.
            "field_scope": slugify(str(profile.pk)),
            "options_url": here,
        },
    )
