"""Authors explicitly permit powers as substitutes for a skill."""

from importlib import import_module

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError

from n26.core import select
from n26.library import authoring as a
from n26.library.models import (
    Collection,
    CollectionSection,
    OffersChoice,
    Pickable,
    Power,
    Skill,
)
from n26.library.specs import specs
from n26.library.standard_content import STANDARD_CONTENT

pytestmark = pytest.mark.django_db


def test_a_mixed_offer_can_be_authored_and_accepts_either_kind(default_pack):
    collection = a.create_collection("Skills & Powers", contains=[Skill, Power])
    primary = a.section_of(collection, "Primary", 0)
    offer = specs()["ef_offers_choice"].compile(
        {
            "model": "skill",
            "from_section": primary,
            "power_access_collection": collection,
        }
    )
    skill = a.create_skill("Dodge")
    power = a.create_power("Force Blast")
    assert offer.kind_label == "Primary skill or power"
    assert offer.selector().matches(select.matchable(skill))
    assert offer.selector().matches(select.matchable(power))
    skill_only = a.ef_offers_choice(Skill, from_section=primary)
    assert not skill_only.selector().matches(select.matchable(power))
    power_only = a.ef_offers_choice(Power, from_section=primary)
    assert not power_only.selector().matches(select.matchable(skill))


def test_a_mixed_offer_requires_a_skill_offer_and_a_section_in_its_collection(
    default_pack,
):
    collection = a.create_collection("Skills & Powers", contains=[Skill, Power])
    other = a.create_collection("Other collection", contains=[Skill])
    section = a.section_of(other, "Primary", 0)
    with pytest.raises(ValidationError, match="Only a skill offer"):
        a.ef_offers_choice(Power, power_access_collection=collection)
    with pytest.raises(
        ValidationError, match="section from the power access collection"
    ):
        a.ef_offers_choice(
            Skill, from_section=section, power_access_collection=collection
        )


def test_the_content_upgrade_enables_only_standard_advancement_offers(default_pack):
    STANDARD_CONTENT["fighter-actions"].create()
    collection = Collection.objects.get(name="Skills & Powers")
    primary = CollectionSection.objects.get(collection=collection, name="Primary")
    ordinary = a.ef_offers_choice(Skill, from_section=primary)
    standard = Pickable.objects.get(name="Select Primary skill")
    other = a.create_pickable("Other pick", standard.slot_type)
    shared = a.modifier(
        "Extra shared skill offer", a.targets_model(), ordinary, attach_to=standard
    )
    a.attach_modifiers_to(other, [shared])
    offers = OffersChoice.objects.exclude(pk=ordinary.pk)
    assert offers.count() == 5
    offers.update(power_access_collection=None)
    migration = import_module("n26.library.migrations.0120_skill_or_power_offers")
    migration.enable_standard_power_choices(apps, None)
    migration.enable_standard_power_choices(apps, None)
    assert OffersChoice.objects.filter(power_access_collection=collection).count() == 5
    ordinary.refresh_from_db()
    assert ordinary.power_access_collection is None
    a.revise(ordinary, power_access_collection=collection)
    migration.disable_standard_power_choices(apps, None)
    assert not offers.filter(power_access_collection=collection).exists()
    ordinary.refresh_from_db()
    assert ordinary.power_access_collection == collection
    migration.enable_standard_power_choices(apps, None)
    a.detach_modifier(standard, shared)
    assert STANDARD_CONTENT["fighter-actions"].status() == "complete"


def test_a_seeded_offer_shared_with_another_carrier_is_not_rewritten(default_pack):
    STANDARD_CONTENT["fighter-actions"].create()
    collection = Collection.objects.get(name="Skills & Powers")
    standard = Pickable.objects.get(name="Select Primary skill")
    modifier = standard.modifiers.get()
    other = a.create_pickable("Other pick", standard.slot_type)
    a.attach_modifiers_to(other, [modifier])
    offer = modifier.offers_choice
    a.revise(offer, power_access_collection=None)
    migration = import_module("n26.library.migrations.0120_skill_or_power_offers")
    migration.enable_standard_power_choices(apps, None)
    offer.refresh_from_db()
    assert offer.power_access_collection is None
    a.revise(offer, power_access_collection=collection)
    migration.disable_standard_power_choices(apps, None)
    offer.refresh_from_db()
    assert offer.power_access_collection == collection
