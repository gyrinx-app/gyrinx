import pytest

from gyrinx.content.models import (
    ContentPack,
    ContentRule,
    ContentSkillCategory,
    ContentWeaponTrait,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_contentpack_creation(user):
    """Test basic ContentPack creation with required fields."""
    pack = ContentPack.objects.create(
        owner=user,
        name="My Custom Pack",
        description="A collection of custom content",
        color="#FF5733",
        is_public=False,
    )

    assert pack.name == "My Custom Pack"
    assert pack.description == "A collection of custom content"
    assert pack.color == "#FF5733"
    assert pack.is_public is False
    assert pack.owner == user
    assert str(pack) == "My Custom Pack"


@pytest.mark.django_db
def test_contentpack_default_values(user):
    """Test ContentPack creation with minimal fields uses defaults."""
    pack = ContentPack.objects.create(
        owner=user,
        name="Minimal Pack",
    )

    assert pack.description == ""
    assert pack.color == "#000000"
    assert pack.is_public is False


@pytest.mark.django_db
def test_contentpack_manytomany_relationships(
    user,
    content_house,
    make_content_fighter,
    make_equipment,
    make_weapon_profile,
    make_weapon_accessory,
):
    """Test adding content to a ContentPack through ManyToMany relationships."""
    # Create ContentPack
    pack = ContentPack.objects.create(
        owner=user,
        name="Test Pack with Content",
        is_public=True,
    )

    # Create content items
    skill_category = ContentSkillCategory.objects.create(
        name="Custom Skills",
        restricted=False,
    )

    rule = ContentRule.objects.create(
        name="Custom Rule",
    )

    fighter = make_content_fighter(
        type="Custom Fighter",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=150,
    )

    weapon_trait = ContentWeaponTrait.objects.create(
        name="Custom Trait",
    )

    equipment = make_equipment(
        name="Custom Equipment",
    )

    weapon_profile = make_weapon_profile(
        equipment=equipment,
        name="Custom Profile",
    )

    weapon_accessory = make_weapon_accessory(
        name="Custom Accessory",
    )

    # Add items to pack
    pack.houses.add(content_house)
    pack.skill_categories.add(skill_category)
    pack.rules.add(rule)
    pack.fighters.add(fighter)
    pack.weapon_traits.add(weapon_trait)
    pack.equipment.add(equipment)
    pack.weapon_profiles.add(weapon_profile)
    pack.weapon_accessories.add(weapon_accessory)

    # Verify relationships
    assert pack.houses.count() == 1
    assert content_house in pack.houses.all()

    assert pack.skill_categories.count() == 1
    assert skill_category in pack.skill_categories.all()

    assert pack.rules.count() == 1
    assert rule in pack.rules.all()

    assert pack.fighters.count() == 1
    assert fighter in pack.fighters.all()

    assert pack.weapon_traits.count() == 1
    assert weapon_trait in pack.weapon_traits.all()

    assert pack.equipment.count() == 1
    assert equipment in pack.equipment.all()

    assert pack.weapon_profiles.count() == 1
    assert weapon_profile in pack.weapon_profiles.all()

    assert pack.weapon_accessories.count() == 1
    assert weapon_accessory in pack.weapon_accessories.all()


@pytest.mark.django_db
def test_contentpack_reverse_relationships(user, content_house):
    """Test accessing ContentPacks from related content models."""
    pack1 = ContentPack.objects.create(
        owner=user,
        name="Pack 1",
    )
    pack2 = ContentPack.objects.create(
        owner=user,
        name="Pack 2",
    )

    # Add the same house to both packs
    pack1.houses.add(content_house)
    pack2.houses.add(content_house)

    # Test reverse relationship
    assert content_house.content_packs.count() == 2
    assert pack1 in content_house.content_packs.all()
    assert pack2 in content_house.content_packs.all()


@pytest.mark.django_db
def test_contentpack_query_with_content(user, content_house):
    """Test querying ContentPacks that contain specific content."""
    # Create packs
    pack_with_house = ContentPack.objects.create(
        owner=user,
        name="Pack with House",
        is_public=True,
    )
    pack_without_house = ContentPack.objects.create(
        owner=user,
        name="Pack without House",
        is_public=True,
    )

    # Add house to only one pack
    pack_with_house.houses.add(content_house)

    # Query packs containing the house
    packs_with_specific_house = ContentPack.objects.filter(houses=content_house)

    assert pack_with_house in packs_with_specific_house
    assert pack_without_house not in packs_with_specific_house
    assert packs_with_specific_house.count() == 1


@pytest.mark.django_db
def test_contentpack_ownership_and_visibility(user, make_user):
    """Test ContentPack ownership and public/private visibility."""
    user2 = make_user()

    # Create packs with different owners and visibility
    public_pack = ContentPack.objects.create(
        owner=user,
        name="Public Pack",
        is_public=True,
    )

    private_pack = ContentPack.objects.create(
        owner=user,
        name="Private Pack",
        is_public=False,
    )

    other_user_pack = ContentPack.objects.create(
        owner=user2,
        name="Other User's Pack",
        is_public=True,
    )

    # Test filtering by owner
    user_packs = ContentPack.objects.filter(owner=user)
    assert public_pack in user_packs
    assert private_pack in user_packs
    assert other_user_pack not in user_packs

    # Test filtering by visibility
    public_packs = ContentPack.objects.filter(is_public=True)
    assert public_pack in public_packs
    assert private_pack not in public_packs
    assert other_user_pack in public_packs


@pytest.mark.django_db
def test_contentpack_with_appbase_features(user):
    """Test ContentPack inherits AppBase features like archive and history."""
    pack = ContentPack.objects.create(
        owner=user,
        name="Test AppBase Features",
    )

    # Test archive functionality (from Archived mixin)
    assert pack.archived is False
    assert pack.archived_at is None

    pack.archive()
    pack.refresh_from_db()

    assert pack.archived is True
    assert pack.archived_at is not None

    # Test that it has history tracking
    assert hasattr(pack, "history")

    # Test owner tracking (from Owned mixin)
    assert pack.owner == user
