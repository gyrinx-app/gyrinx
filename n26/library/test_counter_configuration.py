"""Counter minima and per-point contributions are available through authoring forms."""

import pytest

from n26.library.authoring import create_counter
from n26.library.forms import generate_form
from n26.library.specs import specs

pytestmark = pytest.mark.django_db


def test_counter_form_creates_and_edits_a_minimum(default_pack):
    form_type = generate_form(specs()["create_counter"])
    form = form_type(data={"name": "Renown", "drawn": "on", "minimum": "3"})
    assert form.is_valid(), form.errors
    counter = form.compile()
    assert counter.minimum == 3
    edit = form_type.opened_on(
        counter, data={"edit-name": "Renown", "edit-drawn": "on", "edit-minimum": "2"}
    )
    assert edit.is_valid(), edit.errors
    edit.apply_to(counter)
    counter.refresh_from_db()
    assert counter.minimum == 2


def test_counter_form_rejects_a_negative_minimum(default_pack):
    form = generate_form(specs()["create_counter"])(
        data={"name": "Renown", "minimum": "-1"}
    )
    assert not form.is_valid()
    assert "minimum" in form.errors


def test_contribution_form_accepts_an_optional_source_counter(default_pack):
    reputation = create_counter("Reputation", minimum=1)
    income = create_counter("Income")
    form = generate_form(specs()["ef_contributes_to_counter"])(
        data={
            "counter": str(income.pk),
            "amount": "10",
            "per_counter": str(reputation.pk),
        }
    )
    assert form.is_valid(), form.errors
    effect = form.compile()
    assert effect.counter == income
    assert effect.per_counter == reputation
    assert effect.amount == 10
    assert "per point of Reputation" in str(effect)
