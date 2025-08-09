import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from gyrinx.content.admin import ContentEquipmentAdmin
from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentWeaponProfile,
    ContentWeaponTrait,
)


@pytest.mark.django_db
def test_admin_clone_equipment_preserves_weapon_profile_traits():
    """Test that the admin clone action preserves weapon profile traits."""
    # Create a superuser for the request
    user = User.objects.create_superuser(
        username="admin", email="admin@example.com", password="adminpass"
    )

    # Create equipment category
    weapons_cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons", defaults={"group": "weapon"}
    )

    # Create original equipment
    lasgun = ContentEquipment.objects.create(
        name="Lasgun",
        cost="25",
        category=weapons_cat,
    )

    # Create weapon traits
    rapid_fire = ContentWeaponTrait.objects.create(name="Rapid Fire (1)")
    reliable = ContentWeaponTrait.objects.create(name="Reliable")
    plentiful = ContentWeaponTrait.objects.create(name="Plentiful")

    # Create weapon profiles with traits
    standard_profile = ContentWeaponProfile.objects.create(
        equipment=lasgun,
        name="Standard",
        cost=0,
        strength="3",
        damage="1",
    )
    standard_profile.traits.add(rapid_fire, reliable)

    hot_shot_profile = ContentWeaponProfile.objects.create(
        equipment=lasgun,
        name="Hot-shot",
        cost=20,
        strength="4",
        damage="2",
    )
    hot_shot_profile.traits.add(rapid_fire, plentiful)  # Different traits

    # Setup admin and request
    admin = ContentEquipmentAdmin(ContentEquipment, site)
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = user
    # Add message storage to avoid error
    setattr(request, "session", "session")
    messages = FallbackStorage(request)
    setattr(request, "_messages", messages)

    # Execute the clone action
    queryset = ContentEquipment.objects.filter(id=lasgun.id)
    admin.clone(request, queryset)

    # Find the cloned equipment
    cloned_equipment = ContentEquipment.objects.filter(name="Lasgun (Clone)").first()
    assert cloned_equipment is not None
    assert cloned_equipment.id != lasgun.id

    # Check that profiles were cloned
    cloned_profiles = ContentWeaponProfile.objects.filter(
        equipment=cloned_equipment
    ).order_by("name")
    assert cloned_profiles.count() == 2

    # Check the standard profile and its traits
    cloned_standard = cloned_profiles.filter(name="Standard").first()
    assert cloned_standard is not None
    assert cloned_standard.id != standard_profile.id
    assert cloned_standard.traits.count() == 2
    assert rapid_fire in cloned_standard.traits.all()
    assert reliable in cloned_standard.traits.all()

    # Check the hot-shot profile and its traits
    cloned_hot_shot = cloned_profiles.filter(name="Hot-shot").first()
    assert cloned_hot_shot is not None
    assert cloned_hot_shot.id != hot_shot_profile.id
    assert cloned_hot_shot.traits.count() == 2
    assert rapid_fire in cloned_hot_shot.traits.all()
    assert plentiful in cloned_hot_shot.traits.all()
