"""Golden-equivalence test for the pack fighter default psyker powers page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import models as dj_models
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.psyker import (
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerDiscipline,
    ContentPsykerPower,
)
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_fighter_default_psyker_powers_matches_legacy(user, content_fighter):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)

    fighter_ct = ContentType.objects.get_for_model(content_fighter.__class__)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=fighter_ct,
        object_id=content_fighter.id,
        owner=user,
    )

    # Two disciplines: one assigned to the fighter, one generic.
    disc_a = ContentPsykerDiscipline.objects.create(name="Biomancy")
    disc_b = ContentPsykerDiscipline.objects.create(name="Pyromancy", generic=True)
    power_a1 = ContentPsykerPower.objects.create(name="Iron Arm", discipline=disc_a)
    ContentPsykerPower.objects.create(name="Warp Speed", discipline=disc_a)
    ContentPsykerPower.objects.create(name="Fireball", discipline=disc_b)

    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=content_fighter, discipline=disc_a
    )
    # One existing default power (so the "current defaults" branch renders).
    ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=content_fighter, psyker_power=power_a1
    )

    # Replicate the view's GET-branch query construction exactly.
    current = (
        ContentFighterPsykerPowerDefaultAssignment.objects.with_packs([pack])
        .filter(fighter=content_fighter)
        .select_related("psyker_power", "psyker_power__discipline")
    )
    assigned_disc_ids = list(
        ContentFighterPsykerDisciplineAssignment.objects.with_packs([pack])
        .filter(fighter=content_fighter)
        .values_list("discipline_id", flat=True)
    )
    available = (
        ContentPsykerPower.objects.with_packs([pack])
        .filter(
            dj_models.Q(discipline_id__in=assigned_disc_ids)
            | dj_models.Q(discipline__generic=True)
        )
        .select_related("discipline")
        .order_by("discipline__name", "name")
        .exclude(id__in=[c.psyker_power_id for c in current])
    )

    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "current": current,
        "available": available,
    }
    assert_equivalent(
        "core/pack/pack_fighter_default_psyker_powers.html", context, request
    )
