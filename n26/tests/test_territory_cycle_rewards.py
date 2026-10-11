"""The separate content pass is previewable, conservative and idempotent."""

import pytest
from django.apps import apps

from n26.library.authoring import create_wargear
from n26.library.core_campaign import seed_core_campaign
from n26.library.gang_supertypes import seed_gang_supertypes
from n26.library.models import Modifier, Pickable
from n26.library.territory_boon_choices import seed_all as seed_choices
from n26.library.territory_boons import seed_all as seed_baselines
from n26.library.territory_cycle_rewards import NOTHING_TO_DO, preview, seed_all

pytestmark = pytest.mark.django_db


def test_preview_rerun_and_authored_conflicts(default_pack):
    seed_core_campaign(apps)
    seed_gang_supertypes()
    seed_baselines()
    seed_choices()
    create_wargear("Hazard suit", price=15)
    create_wargear("Respirator", price=10)
    edited = Pickable.objects.get(name="Respirators", qualifier="Mine Workings")
    edited.summary = "A custom reward."
    edited.save()
    before = Modifier.objects.count()
    planned = preview()
    assert Modifier.objects.count() == before
    assert any("added Promethium Cache" in row for row in planned)
    assert any("skipped Mine Workings: boon choice differs" in row for row in planned)
    assert seed_all() == planned
    reward = Modifier.objects.get(name="Promethium Cache: cycle reward")
    assert reward.offers_cycle_equipment.quantity == 3
    assert Pickable.objects.get(modifiers=reward).name == "Hazard suits"
    assert seed_all()[0] == NOTHING_TO_DO
    assert Modifier.objects.filter(name="Promethium Cache: cycle reward").count() == 1
    edited.refresh_from_db()
    assert edited.summary == "A custom reward."
