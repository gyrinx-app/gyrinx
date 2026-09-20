"""Named model cards: equipment-display preferences, not purchases."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Lower

from n26.core.models import Assignment, AssignmentSet, Gang, Miniature
from n26.write_pause import guarded_write


def equipment_for(miniature):
    """Selectable equipment roots; ammunition follows its weapon."""
    return (
        Assignment.objects.filter(
            miniature=miniature,
            parent__isnull=True,
            archived=False,
            removes=False,
        )
        .filter(Q(weapon__isnull=False) | Q(wargear__isnull=False))
        .select_related("weapon", "wargear")
        .order_by("weapon__name", "wargear__name", "created", "pk")
    )


def _lock_model(miniature):
    # Equipment operations lock the gang first. The same order keeps a sale
    # from racing the validation below without recording a ledger event.
    gang = miniature.gang
    if not (
        Gang.objects.select_for_update()
        .filter(pk=gang.pk, owner_id=gang.owner_id, archived=False)
        .first()
    ):
        raise ValidationError("This gang changed. Reload the page and try again.")
    locked = (
        Miniature.objects.select_for_update(of=("self",))
        .filter(
            pk=miniature.pk,
            membership__gang=gang,
            membership__archived=False,
        )
        .first()
    )
    if locked is None:
        raise ValidationError("This model is no longer in the gang.")
    return locked


def _lock_card(miniature, assignment_set, revision):
    found = (
        AssignmentSet.objects.select_for_update()
        .filter(pk=assignment_set.pk, miniature=miniature)
        .first()
    )
    if found is None:
        raise ValidationError("This model card has been removed.")
    if not revision or revision != found.modified.isoformat():
        raise ValidationError(
            "This model card changed. Reload the page before saving or removing it."
        )
    return found


@guarded_write
@transaction.atomic
def save_model_card(
    miniature, *, name, assignments, assignment_set=None, revision=None
):
    """Save only this model's live equipment, serialised with its purchases."""
    locked = _lock_model(miniature)
    card = (
        _lock_card(locked, assignment_set, revision)
        if assignment_set is not None
        else AssignmentSet(miniature=locked)
    )
    name = name.strip()
    AssignmentSet._meta.get_field("name").clean(name, card)
    duplicate = AssignmentSet.objects.filter(miniature=locked).annotate(
        folded_name=Lower("name")
    )
    if card.pk:
        duplicate = duplicate.exclude(pk=card.pk)
    if duplicate.filter(folded_name=Lower(Value(name))).exists():
        raise ValidationError({"name": "This model already has a card with that name."})
    selected = {row.pk for row in assignments}
    available = set(equipment_for(locked).values_list("pk", flat=True))
    if not selected <= available:
        raise ValidationError(
            {
                "assignments": "Some equipment is no longer on this model. Reload the page and choose again."
            }
        )
    card.name = name
    # Saving even an equipment-only edit advances the stale-form token.
    card.save()
    card.assignments.set(selected)
    return card


@guarded_write
@transaction.atomic
def remove_model_card(miniature, assignment_set, *, revision):
    """Remove a display preference, leaving equipment and battle copies alone."""
    locked = _lock_model(miniature)
    card = _lock_card(locked, assignment_set, revision)
    card.delete()
