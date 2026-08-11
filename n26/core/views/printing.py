"""Choosing what goes on paper, and the paper itself.

The layout decisions these draw on live in :mod:`n26.core.printing`;
this is the pair of views around them.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_gang_or_404


class _Selection:
    """An ad-hoc stand-in for an ``AssignmentSet`` at card-build time.

    ``assemble`` asks a set one question — ``selected_ids()`` — so a print
    config's ticked weapons can filter a card through the same seam that
    drops an unselected weapon's children and keeps its modifiers off the
    computed card. Filtering the rendered lines instead would leave a
    hidden weapon's granted subtype printed on the sheet.
    """

    def __init__(self, ids):
        self._ids = ids

    def selected_ids(self):
        return self._ids


def _roster(gang):
    """The models a print covers — the same set the gang sheet draws,
    in the same order: a print is the sheet on paper, and the two
    disagreeing about who comes first would read as a bug on either.
    """
    from n26.core.render import roster

    return roster(gang)


def _print_rows(gang, gang_card, miniatures, weapon_ids=None):
    """A print card per model: filtered, computed, columned.

    ``gang_card`` is the gang already built — the same build the header
    and stash blocks read, so a print derives the gang once however much
    of it is ticked. ``weapon_ids`` of None means everything; a set means
    only those weapon assignments show. Wargear always rides — the
    selection is about which guns clutter the card, so every wargear row
    of the gang's joins the selected set before it filters anything.
    """
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.models import Assignment
    from n26.core.printing import detail_columns
    from n26.core.render import build_model_card

    selection = None
    if weapon_ids is not None:
        wargear = Assignment.objects.filter(
            gang_root=gang, wargear__isnull=False
        ).values_list("pk", flat=True)
        selection = _Selection(set(weapon_ids) | set(wargear))

    # The selection re-deals the cards from rows already fetched, and one
    # modifier index is shared by every card: a card build pays for its
    # queries mostly in planning, so a print that built each model's card
    # alone would cost seconds on a full roster.
    cards = gang_card.members_under(selection)
    index = build_modifier_index(
        [node.assignable for card in cards.values() for node in card.all_nodes()]
        + [node.assignable for node in gang_card.all_nodes()]
    )

    rows = []
    for miniature in miniatures:
        card = cards.get(miniature.pk)
        if card is None:
            # A roster model with no rows of its own still gets a card —
            # built alone, which is the rare path, not the norm.
            card = build_card(miniature, with_statlines=True, assignment_set=selection)
        model_card = build_model_card(
            miniature, card=card, computed=compute(card, index)
        )
        rows.append({"card": model_card, "columns": detail_columns(model_card)})
    return rows


def _config_for(request, gang):
    """The print config the URL names, if it is this gang's own."""
    config_id = request.GET.get("config")
    if not config_id:
        return None
    try:
        return gang.print_configs.filter(pk=config_id).first()
    except ValidationError:
        return None


@login_required
def print_setup(request, pk):
    """Choose what a print includes, before the paper is committed.

    GET lists the gang's saved configs — each a one-press print — above
    the form for a new run: an optional name, the two toggles, and every
    model with its weapons as checkboxes, all ticked to start. Loading a
    saved config (?config=) pre-fills the form instead, which is how one
    is edited.

    POST writes a config and redirects to the print page carrying its
    id. A named POST saves under that name; an unnamed one rewrites the
    gang's single scratch config, so ad-hoc prints never pile up rows.
    """
    from n26.core.models import Assignment, Miniature, PrintConfig
    from n26.core.render import render_gang

    gang = _own_gang_or_404(request, pk)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        miniatures = Miniature.objects.filter(
            membership__gang=gang,
            membership__archived=False,
            pk__in=request.POST.getlist("fighters"),
        )
        weapons = Assignment.objects.filter(
            gang_root=gang,
            weapon__isnull=False,
            pk__in=request.POST.getlist("weapons"),
        )
        # Matched on the lowercased name, which is what the gang is
        # unique over: saving "Roster" where the gang already holds
        # "roster" would otherwise miss, insert, and trip the constraint
        # rather than overwriting the setup the player meant.
        config = PrintConfig.objects.filter(gang=gang, name__iexact=name).first()
        if config is None:
            config = PrintConfig(gang=gang, name=name)
        config.include_header = bool(request.POST.get("include_header"))
        config.include_stash = bool(request.POST.get("include_stash"))
        config.save()
        config.miniatures.set(miniatures)
        config.assignments.set(weapons)
        return redirect(f"{reverse('n26-print', args=[gang.pk])}?config={config.pk}")

    from n26.core.render import WEAPON_SLOTS_PER_CARD

    loaded = _config_for(request, gang)
    sheet = render_gang(gang)
    if loaded is not None:
        ticked_models = {
            str(pk) for pk in loaded.miniatures.values_list("pk", flat=True)
        }
        ticked_weapons = {
            str(pk) for pk in loaded.assignments.values_list("pk", flat=True)
        }
    else:
        # A fresh run prints everything: every box starts ticked.
        ticked_models = {card.id for card in sheet.models}
        ticked_weapons = {weapon.id for card in sheet.models for weapon in card.weapons}

    return render(
        request,
        "n26/print_setup.html",
        {
            "gang": gang,
            "sheet": sheet,
            # What each model is worth with no weapons ticked — the live
            # crew total starts here and adds ticked weapons back on the
            # client. Derived server-side so the template only reads it;
            # `ticked` too, because a cotton :prop evaluates a variable,
            # not an `in` expression — passed as one, every card rendered
            # unticked and nothing errored.
            "model_rows": [
                {
                    "card": card,
                    "ticked": card.id in ticked_models,
                    "base_rating": card.rating
                    - sum(weapon.total_rating for weapon in card.weapons),
                }
                for card in sheet.models
            ],
            "saved": gang.print_configs.exclude(name=""),
            # Resolved here, not in the template: `loaded.include_header`
            # on a None resolves to the empty string, which default_if_none
            # does not catch — a template-side default silently unticks.
            "setup_name": loaded.name if loaded else "",
            "include_header": loaded.include_header if loaded else True,
            "include_stash": loaded.include_stash if loaded else True,
            "ticked_models": ticked_models,
            "ticked_weapons": ticked_weapons,
            "slot_budget": WEAPON_SLOTS_PER_CARD,
        },
    )


@login_required
def print_gang(request, pk):
    """The gang on paper — the print target itself.

    A bare document, like the lab's sheet: this URL is what a phone opens
    and what turns into the PDF, so it carries no chrome to hide again
    with print rules. With ?config= it prints that config's selection;
    without one, everything.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.card import build_gang_card
    from n26.core.render import stash_lines

    gang = _own_gang_or_404(request, pk)
    config = _config_for(request, gang)
    # One derivation serves the whole page — the header's figures, the
    # stash block and every model's card all read this build.
    gang_card = build_gang_card(gang)
    miniatures = _roster(gang)

    if config is not None:
        wanted = {str(pk) for pk in config.miniatures.values_list("pk", flat=True)}
        rows = _print_rows(
            gang,
            gang_card,
            [m for m in miniatures if str(m.pk) in wanted],
            weapon_ids=set(config.assignments.values_list("pk", flat=True)),
        )
        include_header = config.include_header
        include_stash = config.include_stash
    else:
        rows = _print_rows(gang, gang_card, miniatures)
        include_header = True
        include_stash = True

    # One event for the sheet, carrying how much of the gang it covers —
    # a card per model would make a big roster look like heavy use.
    record(
        request,
        N26Noun.PRINT_RUN,
        EventVerb.EXPORT,
        gang,
        cards=len(rows),
        saved_config=config is not None,
        include_stash=include_stash,
    )

    return render(
        request,
        "n26/print_gang.html",
        {
            "gang": gang,
            "rows": rows,
            "stash": stash_lines(gang_card),
            "stash_rating": gang_card.stash_rating,
            "include_header": include_header,
            "include_stash": include_stash,
        },
    )
