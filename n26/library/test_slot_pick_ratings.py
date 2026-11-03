"""A slot can set a shared option's rating without spending credits."""

from types import SimpleNamespace

import pytest

from n26.library import authoring as a
from n26.library.forms import generate_form
from n26.library.models import Slot
from n26.library.specs import specs


@pytest.mark.parametrize("override,expected", [(None, 10), (0, 0), (5, 5), (-5, -5)])
def test_a_slot_resolves_an_explicit_zero_separately_from_no_override(
    override, expected
):
    slot = Slot(pick_rating_override=override, pack_id=None)
    assert slot.rating_for_pick(SimpleNamespace(rating_contribution=10)) == expected


@pytest.mark.django_db
@pytest.mark.parametrize("value,expected", [("", None), ("0", 0), ("5", 5)])
def test_authoring_retains_blank_zero_and_positive_rating_per_pick(
    default_pack, value, expected
):
    kind = a.create_slot_type("Names")
    table = a.create_picklist("Names", kind)
    form_type = generate_form(specs()["create_slot"])
    form = form_type(
        data={
            "name": "Name choice",
            "slot_type": str(kind.pk),
            "picklist": str(table.pk),
            "min_picks": 1,
            "max_picks": 1,
            "assigned_to": "bearer",
            "mode": "standard",
            "position": 0,
            "pick_rating_override": value,
        }
    )
    assert form.is_valid(), form.errors
    slot = form.compile()
    assert slot.pick_rating_override == expected
    edit = form_type.opened_on(
        slot,
        data={
            "edit-name": slot.name,
            "edit-picklist": str(table.pk),
            "edit-min_picks": 1,
            "edit-max_picks": 1,
            "edit-assigned_to": "bearer",
            "edit-mode": "standard",
            "edit-position": 0,
            "edit-pick_rating_override": "",
        },
    )
    assert edit.is_valid(), edit.errors
    edit.apply_to(slot)
    slot.refresh_from_db()
    assert slot.pick_rating_override is None
