"""Owner-only management of a model's named equipment cards."""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from n26.core.assignment_set_forms import ModelCardForm, RemoveModelCardForm
from n26.core.assignment_sets import remove_model_card as remove_card
from n26.core.assignment_sets import save_model_card
from n26.core.card import assemble, build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.fields import to_ulid
from n26.core.models import Assignment, AssignmentSet, DismissedOffer, Miniature
from n26.core.progression import progression_summaries_for_cards
from n26.core.render import ModelCard, brought_in_by, build_model_card, hide_dismissed
from n26.core.views.permissions import _own_miniature_or_404
from n26.flags import CAMPAIGNS, requires_flag


def _model(request, pk, miniature_pk):
    miniature = _own_miniature_or_404(request, miniature_pk)
    try:
        if miniature.gang.pk != to_ulid(pk):
            raise Http404("No such model")
    except ValueError, TypeError, ValidationError:
        raise Http404("No such model") from None
    return miniature


def _card(miniature, pk):
    try:
        return get_object_or_404(AssignmentSet, miniature=miniature, pk=pk)
    except ValidationError:
        raise Http404("No such model card") from None


def _back(miniature):
    return reverse(
        "n26-model-cards",
        kwargs={"pk": miniature.gang.pk, "miniature_pk": miniature.pk},
    )


@dataclass(frozen=True)
class _Selection:
    ids: set

    def selected_ids(self):
        return self.ids


@dataclass(frozen=True)
class NamedCard:
    name: str
    card: ModelCard
    id: str = ""


def _previews(miniature, assignment_sets):
    """Build once, then deal every selection from the same hydrated rows."""
    base = build_card(miniature, with_statlines=True)
    own_rows = [
        node.assignment for node in base.all_nodes() if not node.broadcast
    ] + base.removals
    cards = [
        assemble(
            miniature,
            own_rows,
            assignment_set=_Selection({row.pk for row in named.selected_equipment}),
            broadcast=base.gang_card.shared_rows,
            gang_card=base.gang_card,
            stat_overrides=base.stat_overrides,
        )
        for named in assignment_sets
    ]
    if not cards:
        cards = [base]
    index = build_modifier_index(carriers(base.gang_card, *cards))
    computed = [compute(card, index) for card in cards]
    ranks = progression_summaries_for_cards(
        (position, miniature, card, effects)
        for position, (card, effects) in enumerate(zip(cards, computed, strict=True))
    )
    brought = brought_in_by(
        Miniature.objects.filter(
            membership__caused_by__miniature_root=miniature,
            membership__archived=False,
        ).select_related("membership__profile")
    )
    dismissed = DismissedOffer.keys_for(miniature.gang)
    previews = []
    for position, (named, card, effects) in enumerate(
        zip(assignment_sets or [None], cards, computed, strict=True)
    ):
        drawn = build_model_card(
            miniature,
            card=card,
            computed=effects,
            brought_in=brought,
            rank_summaries=ranks[position],
        )
        hide_dismissed(dismissed, drawn)
        # Previews have no edit controls or duplicate model/tab anchors.
        drawn.id = ""
        previews.append(
            NamedCard(
                name=named.name if named else "Standard",
                card=drawn,
                id=str(named.pk) if named else "",
            )
        )
    return previews


@requires_flag(CAMPAIGNS)
@login_required
def model_cards(request, pk, miniature_pk):
    miniature = _model(request, pk, miniature_pk)
    named = list(
        miniature.assignment_sets.prefetch_related(
            Prefetch(
                "assignments",
                queryset=Assignment.objects.only("pk"),
                to_attr="selected_equipment",
            )
        )
    )
    return render(
        request,
        "n26/model_cards.html",
        {
            "miniature": miniature,
            "gang": miniature.gang,
            "cards": _previews(miniature, named),
            "has_named_cards": bool(named),
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def edit_model_card(request, pk, miniature_pk, set_pk=None):
    miniature = _model(request, pk, miniature_pk)
    named = _card(miniature, set_pk) if set_pk is not None else None
    form = ModelCardForm(
        request.POST if request.method == "POST" else None,
        miniature=miniature,
        assignment_set=named,
    )
    if request.method == "POST" and form.is_valid():
        try:
            save_model_card(miniature, assignment_set=named, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Model card saved.")
            return redirect(_back(miniature))
    return render(
        request,
        "n26/edit_model_card.html",
        {
            "miniature": miniature,
            "gang": miniature.gang,
            "assignment_set": named,
            "form": form,
            "back": _back(miniature),
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def remove_model_card(request, pk, miniature_pk, set_pk):
    miniature = _model(request, pk, miniature_pk)
    named = _card(miniature, set_pk)
    form = RemoveModelCardForm(
        request.POST if request.method == "POST" else None, assignment_set=named
    )
    if request.method == "POST" and form.is_valid():
        try:
            remove_card(miniature, named, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Model card removed.")
            return redirect(_back(miniature))
    return render(
        request,
        "n26/remove_model_card.html",
        {
            "miniature": miniature,
            "gang": miniature.gang,
            "assignment_set": named,
            "form": form,
            "back": _back(miniature),
            "last_card": miniature.assignment_sets.count() == 1,
        },
    )
