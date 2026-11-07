"""Edit the acquisition options recorded on a model's profile assignment."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify

from n26.core.views.permissions import (
    _own_miniature_or_404,
    credits_href,
    may_mark_status,
    status_href,
    trade_points_href,
)


def _option_rows(entry, chosen_pks):
    """Build hire-option groups checked from recorded selections.

    Use the same group indices as hiring. Choose a pick-one group's default only
    when no recorded selection belongs to it; omit synthesised standard choices.
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
                # Skip the synthetic default option because it represents no stored default set.
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
    """Reopen hire options and settle replacements through ``Operation.rechoose``.

    The original hire's ledger entry records any price difference. Parse options
    with the hiring parser. Card controls return to the model's edit page because
    this page has no partial-update hosts.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute
    from n26.core.hire import build_hire_entry
    from n26.core.operations import Refusal, operation
    from n26.core.owned import EquipHost
    from n26.core.render import roster, summarise_roster
    from n26.core.views.edit import link_model_card
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
            # Reject option-set identities outside this profile's current offer as invalid input.
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
    # Load option provenance so card actions identify the exact owned copy.
    # Return every card action to the model edit page, which has its update hosts.
    own = build_card(miniature, with_statlines=True, with_options=True)
    computed = compute(own, build_modifier_index(carriers(own)))
    edit = reverse("n26-edit-fighter", args=[miniature.pk])
    host = EquipHost.fighter(gang, own, miniature, edit)
    card = link_model_card(
        gang,
        miniature,
        own,
        computed,
        host,
        back=edit,
        dismissal_at=request.get_full_path(),
    )
    return render(
        request,
        "n26/fighter_options.html",
        {
            "miniature": miniature,
            "gang": gang,
            "role": (profile.category.name if profile and profile.category else ""),
            "summary": summarise_roster(members),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
            "card": card,
            # After status changes, return to the model edit page.
            "status_href": (
                status_href(gang, miniature, back="edit")
                if may_mark_status(gang, request.user)
                else ""
            ),
            "groups": _option_rows(entry, chosen_pks),
            # Match the hiring form's slugified profile identifier for the shared POST parser.
            "field_scope": slugify(str(profile.pk)),
            "options_url": here,
        },
    )
