"""Configure and render printable gang sheets using n26.core.printing layouts.

Signed-in readers may print any shareable gang. Only its owner may save a
PrintConfig; other readers submit their selections through the print URL.
Owner POSTs reuse named or unnamed configurations instead of adding a row
for every print.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import redirect, render
from django.template.defaultfilters import pluralize
from django.urls import reverse

from n26.core.fields import to_ulid
from n26.core.views.permissions import _any_gang_or_404, _own_gang_or_404


class _Selection:
    """Adapt weapon identifiers to the AssignmentSet selected_ids interface.

    Filter before effect computation so excluded weapons and their dependent
    grants cannot affect the printed card.
    """

    def __init__(self, ids):
        self._ids = ids

    def selected_ids(self):
        return self._ids


def _roster(gang):
    """Use the gang sheet's roster and ordering for print cards."""
    from n26.core.render import roster

    return roster(gang)


def _print_rows(
    gang,
    gang_card,
    miniatures,
    weapon_ids=None,
    brought_in=None,
    *,
    include_campaign=False,
):
    """Build filtered and computed model cards with print detail columns.

    Reuse gang_card and one modifier index. None weapon_ids includes all weapons;
    a supplied set narrows weapon assignments while retaining wargear.
    Read brought_in from the complete roster so omitted pets remain identified
    on their owner's card.
    """
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute, compute_gang
    from n26.core.models import Assignment, DismissedOffer
    from n26.core.printing import detail_columns
    from n26.core.progression import progression_summaries
    from n26.core.render import (
        build_campaign_block,
        build_model_card,
        hide_dismissed,
        hide_dismissed_choices,
    )

    selection = None
    if weapon_ids is not None:
        wargear = Assignment.objects.filter(
            gang_root=gang, wargear__isnull=False
        ).values_list("pk", flat=True)
        selection = _Selection(set(weapon_ids) | set(wargear))

    # Reuse fetched assignments and one modifier index across all selected cards.
    cards = dict(gang_card.members_under(selection))
    for miniature in miniatures:
        if miniature.pk not in cards:
            # Build the member card omitted by the gang derivation.
            cards[miniature.pk] = build_card(
                miniature, with_statlines=True, assignment_set=selection
            )
    index = build_modifier_index(carriers(gang_card, *cards.values()))
    gang_computed = compute_gang(gang_card, index)
    campaign = (
        build_campaign_block(gang_card, index=index, computed=gang_computed)
        if include_campaign
        else None
    )
    computed = {
        miniature.pk: compute(cards[miniature.pk], index) for miniature in miniatures
    }
    ranks = progression_summaries(cards, miniatures, computed)
    # Hide dismissed choices with one shared lookup for the print.
    dismissed = DismissedOffer.keys_for(gang)
    if campaign is not None:
        hide_dismissed_choices(dismissed, campaign.choices)

    rows = []
    for miniature in miniatures:
        model_card = build_model_card(
            miniature,
            card=cards[miniature.pk],
            computed=computed[miniature.pk],
            brought_in=brought_in,
            rank_summaries=ranks[miniature.pk],
        )
        hide_dismissed(dismissed, model_card)
        rows.append(
            {
                "card": model_card,
                "subtitle": " · ".join(
                    part
                    for part in (
                        model_card.status_label,
                        model_card.profile_name,
                        model_card.owner_line,
                    )
                    if part
                ),
                "columns": detail_columns(model_card),
            }
        )
    return rows, campaign


def _config_for(request, gang):
    """Resolve the URL-selected print config within this gang."""
    return _gang_config(gang, request.GET.get("config"))


def _gang_config(gang, config_id):
    """Find a gang-owned print configuration, returning None for missing or invalid identifiers."""
    if not config_id:
        return None
    try:
        return gang.print_configs.filter(pk=config_id).first()
    except ValidationError:
        return None


def _ids(values):
    """Parse valid identifiers and discard malformed values individually."""
    kept = []
    for value in values:
        try:
            kept.append(to_ulid(value))
        except ValueError, AttributeError, TypeError:
            continue
    return kept


def _weapons_named(gang, values, models):
    """Resolve selected weapons belonging to this gang and the selected models."""
    return set(_picked_weapons(gang, values, models).values_list("pk", flat=True))


def _picked_weapons(gang, values, models):
    """Filter weapon assignments by gang, selected identities and selected models."""
    from n26.core.models import Assignment

    return Assignment.objects.filter(
        gang_root=gang,
        weapon__isnull=False,
        pk__in=_ids(values),
        miniature_root__in=_ids(models),
    )


def _orientation(value):
    """Validate paper orientation, defaulting to portrait."""
    from n26.core.models import PrintConfig

    if value in PrintConfig.Orientation.values:
        return value
    return PrintConfig.Orientation.PORTRAIT


def _what_to_print(request, gang, config):
    """Resolve a saved setup, explicit URL selection or whole-gang defaults, in that order.

    The pick marker distinguishes an explicit empty selection from no filter.
    Canonicalise model and assignment identifiers. None means unrestricted selection.
    """
    if config is not None:
        return (
            {str(pk) for pk in config.miniatures.values_list("pk", flat=True)},
            set(config.assignments.values_list("pk", flat=True)),
            config.include_header,
            config.include_stash,
            config.include_notes,
            config.orientation,
        )
    if request.GET.get("pick"):
        return (
            {str(model_id) for model_id in _ids(request.GET.getlist("fighters"))},
            _weapons_named(
                gang,
                request.GET.getlist("weapons"),
                request.GET.getlist("fighters"),
            ),
            bool(request.GET.get("include_header")),
            bool(request.GET.get("include_stash")),
            bool(request.GET.get("include_notes")),
            _orientation(request.GET.get("orientation")),
        )
    return None, None, True, True, True, _orientation(None)


#: The picker submits this marker in both server and island renderings.
#: Missing selection fields without it indicate a failed picker, not an empty choice.
PICKER_MARKER = "picker"

#: Validation message for submissions missing the picker marker.
PICKER_MISSING = (
    "The model list did not load, so nothing was saved. "
    "Check the models below and print again."
)


def _print_picker(sheet, ticked_models, ticked_weapons, slot_budget, marker):
    """Build picker props with stored weapons and each model's weaponless base rating.

    The client adds selected weapons to the base for a preview total; printing
    recomputes its own cards. Computed weapons have no selectable assignment ID.
    """
    return {
        "marker": marker,
        "slotBudget": slot_budget,
        "models": [
            {
                "id": str(card.id),
                "name": card.name,
                "profileName": card.profile_name,
                "rating": card.rating,
                "baseRating": card.rating
                - sum(weapon.total_rating for weapon in card.weapons),
                "ticked": card.id in ticked_models,
                "hasWeapons": bool(card.weapons),
                "weapons": [
                    {
                        "id": str(weapon.id),
                        "label": (
                            f"{weapon.name}{weapon.slot_mark}"
                            f"{weapon.total_brought_mark}"
                        ),
                        "slots": weapon.slots,
                        "slotsLabel": (
                            ""
                            if weapon.slots == 1
                            else f"{weapon.slots} slot{pluralize(weapon.slots)}"
                        ),
                        "rating": weapon.total_rating,
                        "ticked": str(weapon.id) in ticked_weapons,
                    }
                    for weapon in card.weapons
                    if weapon.id
                ],
            }
            for card in sheet.models
        ],
    }


def _picker_fallback(picker):
    """Build server controls and totals using the island's initial selection data.

    Preserve selections if the form submits before the island mounts.
    """
    budget = picker["slotBudget"]
    rows = []
    total = 0
    for model in picker["models"]:
        ticked = [weapon for weapon in model["weapons"] if weapon["ticked"]]
        slots = sum(weapon["slots"] for weapon in ticked)
        rows.append({"model": model, "slots": slots, "over": slots > budget})
        if model["ticked"]:
            total += model["baseRating"] + sum(weapon["rating"] for weapon in ticked)
    return {"rows": rows, "total": total}


@login_required
def print_setup(request, pk):
    """Display shared print setups and save owner submissions.

    Require the picker marker before saving so a failed island cannot clear
    model and weapon selections. Match names case-insensitively; an empty name
    reuses the scratch setup. Non-owners submit GET directly to print_gang.
    """
    from n26.core.models import Miniature, PrintConfig

    if request.method == "POST":
        from django.db import transaction

        from n26.write_pause import write_guard

        gang = _own_gang_or_404(request, pk)
        name = request.POST.get("name", "").strip()
        if not request.POST.get(PICKER_MARKER):
            # A missing marker must not clear selections; restore the loaded or matching named setup.
            loaded = _gang_config(gang, request.POST.get("config"))
            if loaded is None and name:
                loaded = gang.print_configs.filter(name__iexact=name).first()
            return _setup_page(
                request, gang, loaded, error=PICKER_MISSING, posted=request.POST
            )
        miniatures = Miniature.objects.filter(
            membership__gang=gang,
            membership__archived=False,
            pk__in=_ids(request.POST.getlist("fighters")),
        )
        weapons = _picked_weapons(
            gang, request.POST.getlist("weapons"), request.POST.getlist("fighters")
        )
        # Match names case-insensitively to agree with the gang-scoped unique constraint.
        with transaction.atomic(), write_guard():
            config = PrintConfig.objects.filter(gang=gang, name__iexact=name).first()
            if config is None:
                config = PrintConfig(gang=gang, name=name)
            config.include_header = bool(request.POST.get("include_header"))
            config.include_stash = bool(request.POST.get("include_stash"))
            config.include_notes = bool(request.POST.get("include_notes"))
            config.orientation = _orientation(request.POST.get("orientation"))
            config.save()
            config.miniatures.set(miniatures)
            config.assignments.set(weapons)
        return redirect(f"{reverse('n26-print', args=[gang.pk])}?config={config.pk}")

    gang = _any_gang_or_404(request, pk)
    return _setup_page(request, gang, _config_for(request, gang))


def _setup_page(request, gang, loaded, error="", posted=None):
    """Build setup props from a saved configuration or whole-gang defaults.

    After an invalid submission, preserve posted name, toggles and orientation;
    use the loaded configuration to restore model and weapon selections.
    """
    from django import forms

    from n26.core.render import WEAPON_SLOTS_PER_CARD, render_gang

    yours = gang.owner_id == request.user.id
    sheet = render_gang(gang)
    errors = None
    if error:
        # Use a bound form to render the non-field setup error.
        errors = forms.Form(data={})
        errors.is_valid()
        errors.add_error(None, error)
    # Expose named setups to all signed-in readers and annotate counts in the same query.
    saved = list(
        gang.print_configs.exclude(name="").annotate(model_count=Count("miniatures"))
    )
    if loaded is not None:
        ticked_models = {
            str(pk) for pk in loaded.miniatures.values_list("pk", flat=True)
        }
        ticked_weapons = {
            str(pk) for pk in loaded.assignments.values_list("pk", flat=True)
        }
    else:
        # Default new selections to every model and stored weapon.
        ticked_models = {card.id for card in sheet.models}
        ticked_weapons = {weapon.id for card in sheet.models for weapon in card.weapons}
    # Require the marker only for owner writes; read-only selections use the URL.
    picker = _print_picker(
        sheet,
        ticked_models,
        ticked_weapons,
        WEAPON_SLOTS_PER_CARD,
        PICKER_MARKER if yours else "",
    )

    return render(
        request,
        "n26/print_setup.html",
        {
            "gang": gang,
            "sheet": sheet,
            "print_picker": picker,
            "print_fallback": _picker_fallback(picker),
            "setup_errors": errors,
            "saved": saved,
            # Resolve optional setup defaults in Python; Django missing attributes become empty
            # strings, which default_if_none cannot replace.
            **(
                {
                    "setup_name": posted.get("name", "").strip(),
                    "include_header": bool(posted.get("include_header")),
                    "include_stash": bool(posted.get("include_stash")),
                    "include_notes": bool(posted.get("include_notes")),
                    "orientation": _orientation(posted.get("orientation")),
                }
                if posted is not None
                else {
                    "setup_name": loaded.name if loaded else "",
                    "include_header": loaded.include_header if loaded else True,
                    "include_stash": loaded.include_stash if loaded else True,
                    "include_notes": loaded.include_notes if loaded else True,
                    "orientation": _orientation(loaded.orientation if loaded else None),
                }
            ),
            "yours": yours,
            # Carry the loaded setup identifier so a failed save can restore its selection.
            "loaded_config": str(loaded.pk) if yours and loaded else "",
            # Owners POST to save; other readers GET the same selection directly as a printable URL.
            "form_action": reverse(
                "n26-print-setup" if yours else "n26-print", args=[gang.pk]
            ),
            "form_method": "post" if yours else "get",
            "lead": (
                "Pick what goes on paper. Name the setup to keep it for next time."
                if yours
                else "Pick what goes on paper. Saved setups belong to whoever owns "
                "the gang, so yours prints without being kept."
            ),
            "setup_title": (
                ("New setup" if saved else "Setup") if yours else "This print"
            ),
        },
    )


@login_required
def print_gang(request, pk):
    """Render a signed-in reader's selected gang cards as a standalone print document.

    Resolve the setup or URL selection, derive the gang once and record one
    export event for the whole print.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.card import build_gang_card
    from n26.core.models import PrintConfig
    from n26.core.render import brought_in_by, stash_lines

    gang = _any_gang_or_404(request, pk)
    config = _config_for(request, gang)
    (
        wanted,
        weapon_ids,
        include_header,
        include_stash,
        include_notes,
        orientation,
    ) = _what_to_print(request, gang, config)
    # Reuse one gang derivation for header figures, stash and model cards.
    gang_card = build_gang_card(gang)
    miniatures = _roster(gang)
    # Read pet-owner labels before filtering the roster for this print.
    brought = brought_in_by(miniatures)
    if wanted is not None:
        miniatures = [m for m in miniatures if str(m.pk) in wanted]
    rows, campaign = _print_rows(
        gang,
        gang_card,
        miniatures,
        weapon_ids=weapon_ids,
        brought_in=brought,
        include_campaign=include_header,
    )

    # Record one export per sheet, including its card count, rather than one per model.
    record(
        request,
        N26Noun.PRINT_RUN,
        EventVerb.EXPORT,
        gang,
        cards=len(rows),
        saved_config=config is not None,
        include_stash=include_stash,
        own_gang=gang.owner_id == request.user.id,
    )

    return render(
        request,
        "n26/print_gang.html",
        {
            "gang": gang,
            "rows": rows,
            "campaign": campaign,
            "stash": stash_lines(gang_card, brought_in=brought),
            "stash_rating": gang_card.stash_rating,
            "include_header": include_header,
            "include_notes": include_notes,
            "include_stash": include_stash,
            "orientation": orientation,
            # Use three columns for landscape and two for portrait.
            "grid_columns": 3
            if orientation == PrintConfig.Orientation.LANDSCAPE
            else 2,
        },
    )
