"""Resolve a new slot rating or retain the setting of an applied action."""


def rating_for_pick(slot, pickable, *, record=None):
    if record is None:
        return slot.rating_for_pick(pickable)
    context = record.recorded_ratings.get(str(slot.pk))
    if context is not None:
        if context["override"] is not None:
            return context["override"]
        return context["picks"].get(str(pickable.pk), pickable.rating_contribution)
    # An older completed action predates slot overrides.
    if record.completed_event_id:
        return pickable.rating_contribution
    return slot.rating_for_pick(pickable)
