"""Golden-equivalence test for the advancement select page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_advancement_select_matches_legacy(
    user, make_list, make_list_fighter
):
    from gyrinx.core.forms.advancement import SkillSelectionForm

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    skill_type = "primary"
    form = SkillSelectionForm(
        fighter=fighter, skill_type=skill_type, packs=lst.packs.all()
    )

    request = _request(user)
    context = {
        "form": form,
        "fighter": fighter,
        "list": lst,
        "is_campaign_mode": False,
        "steps": 2,
        "current_step": 2,
        "advancement_type": "skill",
        "skill_type": skill_type,
        "is_random": False,
    }
    assert_equivalent("core/list_fighter_advancement_select.html", context, request)
