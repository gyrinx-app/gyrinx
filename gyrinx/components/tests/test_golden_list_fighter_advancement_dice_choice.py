"""Golden-equivalence test: the advancement dice-choice page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent

TEMPLATE = "core/list_fighter_advancement_dice_choice.html"


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _context(fighter, lst):
    from gyrinx.core.forms.advancement import AdvancementDiceChoiceForm
    from gyrinx.core.views.fighter.advancements import (
        can_fighter_roll_dice_for_advancement,
    )

    return {
        "form": AdvancementDiceChoiceForm(),
        "fighter": fighter,
        "list": lst,
        "can_roll_dice": can_fighter_roll_dice_for_advancement(fighter),
        "fighter_category": fighter.get_category_label(),
    }


@pytest.mark.django_db
def test_advancement_dice_choice_can_roll_matches_legacy(
    user, make_list, make_list_fighter, make_content_fighter, content_house
):
    """Ganger fighter -> can_roll_dice True (info alert, controls enabled)."""
    from gyrinx.models import FighterCategoryChoices

    ganger_cf = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", content_fighter=ganger_cf)
    request = _request(user)

    assert_equivalent(TEMPLATE, _context(fighter, lst), request)


@pytest.mark.django_db
def test_advancement_dice_choice_cannot_roll_matches_legacy(
    user, make_list, make_list_fighter
):
    """Default (non-ganger) fighter -> can_roll_dice False (warning, controls disabled)."""
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Runt")
    request = _request(user)

    assert_equivalent(TEMPLATE, _context(fighter, lst), request)
