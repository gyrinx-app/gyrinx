"""Golden-equivalence test: battle note add page matches legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_battle_note_add_matches_legacy(user, campaign):
    from gyrinx.core.forms.battle import BattleNoteForm
    from gyrinx.core.models import Battle

    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    form = BattleNoteForm()
    request = _request(user)
    return_url = reverse("core:battle", args=[battle.id])
    context = {
        "form": form,
        "battle": battle,
        "existing_note": None,
        "return_url": return_url,
    }
    assert_equivalent("core/battle/battle_note_add.html", context, request)
