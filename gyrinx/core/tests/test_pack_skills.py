"""Tests for custom skills in content packs."""

import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.skill import ContentSkill, ContentSkillCategory
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


@pytest.fixture
def custom_content_group():
    group, _ = Group.objects.get_or_create(name="Custom Content")
    return group


@pytest.fixture
def group_user(user, custom_content_group):
    user.groups.add(custom_content_group)
    return user


@pytest.fixture
def pack(group_user):
    return CustomContentPack.objects.create(
        name="Skill Test Pack", owner=group_user, listed=True
    )


@pytest.fixture
def pack_skill_category(pack):
    cat = ContentSkillCategory.objects.create(name="Pack Bravado")
    ct = ContentType.objects.get_for_model(ContentSkillCategory)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=cat.pk, owner=pack.owner
    )
    return cat


@pytest.fixture
def pack_skill(pack, pack_skill_category):
    skill = ContentSkill.objects.create(
        name="Pack Courage", category=pack_skill_category
    )
    ct = ContentType.objects.get_for_model(ContentSkill)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=skill.pk, owner=pack.owner
    )
    return skill


# -- Pack creation UI --


@pytest.mark.django_db
def test_pack_detail_shows_skills_section(client, group_user, pack):
    """Pack detail page shows Skills section (skill trees are grouped within)."""
    client.force_login(group_user)
    response = client.get(reverse("core:pack", args=[pack.id]))
    assert response.status_code == 200
    assert b"Skills" in response.content


@pytest.mark.django_db
def test_create_pack_skill_category(client, group_user, pack):
    """Can create a skill category in a pack."""
    client.force_login(group_user)
    url = reverse("core:pack-add-item", args=[pack.id, "skill-tree"])
    response = client.post(url, {"name": "Custom Bravado"})
    assert response.status_code == 302
    assert (
        ContentSkillCategory.objects.all_content()
        .filter(name="Custom Bravado")
        .exists()
    )


@pytest.mark.django_db
def test_create_pack_skill(client, group_user, pack, pack_skill_category):
    """Can create a skill in a pack."""
    client.force_login(group_user)
    url = reverse("core:pack-add-item", args=[pack.id, "skill"])
    response = client.post(
        url, {"name": "Custom Skill", "category": str(pack_skill_category.pk)}
    )
    assert response.status_code == 302
    assert ContentSkill.objects.all_content().filter(name="Custom Skill").exists()


# -- Fighter form shows pack skills --


@pytest.mark.django_db
def test_fighter_form_shows_pack_skills(
    client, group_user, pack, pack_skill, content_house
):
    """Pack skills appear in the fighter edit form."""
    fighter = ContentFighter.objects.create(
        type="Skill Form Fighter", category="GANGER", house=content_house, base_cost=50
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=fighter.pk, owner=pack.owner
    )
    client.force_login(group_user)
    url = reverse("core:pack-edit-item", args=[pack.id, pack_item.id])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Pack Courage" in response.content


# -- Skill display on list fighters --


@pytest.mark.django_db
def test_pack_skill_shows_in_skilline(pack, pack_skill, content_house, user):
    """Pack skills added to a ContentFighter appear in list fighter's skilline."""
    fighter = ContentFighter.objects.create(
        type="Skilline Fighter", category="GANGER", house=content_house, base_cost=50
    )
    fighter.skills.add(pack_skill)

    lst = List.objects.create(
        name="Skilline List", owner=user, content_house=content_house
    )
    lst.packs.add(pack)

    lf = ListFighter.objects.create(
        name="Skilline Guy", content_fighter=fighter, list=lst, owner=user
    )
    assert "Pack Courage" in lf.skilline()


@pytest.mark.django_db
def test_pack_skill_hidden_without_subscription(pack, pack_skill, content_house, user):
    """Pack skills should NOT show in skilline if the list doesn't subscribe to the pack."""
    fighter = ContentFighter.objects.create(
        type="No Sub Fighter", category="GANGER", house=content_house, base_cost=50
    )
    fighter.skills.add(pack_skill)

    lst = List.objects.create(
        name="No Sub List", owner=user, content_house=content_house
    )
    # NOT subscribing to pack

    lf = ListFighter.objects.create(
        name="No Sub Guy", content_fighter=fighter, list=lst, owner=user
    )
    assert "Pack Courage" not in lf.skilline()


@pytest.mark.django_db
def test_pack_custom_skill_shows_in_skilline(pack, pack_skill, content_house, user):
    """Pack skills added as user-added skills appear in the skilline."""
    fighter = ContentFighter.objects.create(
        type="Custom Skill Fighter",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )

    lst = List.objects.create(
        name="Custom Skill List", owner=user, content_house=content_house
    )
    lst.packs.add(pack)

    lf = ListFighter.objects.create(
        name="Custom Skill Guy", content_fighter=fighter, list=lst, owner=user
    )
    lf.skills.add(pack_skill)
    assert "Pack Courage" in lf.skilline()


# -- Skills edit view --


@pytest.mark.django_db
def test_skills_edit_shows_pack_skills(
    client, pack, pack_skill, pack_skill_category, content_house, user
):
    """Pack skills appear in the skills edit view."""
    fighter = ContentFighter.objects.create(
        type="Edit Skill Fighter",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    fighter.primary_skill_categories.add(pack_skill_category)

    lst = List.objects.create(
        name="Edit Skill List", owner=user, content_house=content_house
    )
    lst.packs.add(pack)

    lf = ListFighter.objects.create(
        name="Edit Skill Guy", content_fighter=fighter, list=lst, owner=user
    )

    client.force_login(user)
    url = reverse("core:list-fighter-skills-edit", args=[lst.id, lf.id])
    response = client.get(url, {"category_filter": "all"})
    assert response.status_code == 200
    assert b"Pack Courage" in response.content


@pytest.mark.django_db
def test_pack_skill_category_in_primary_categories(
    pack, pack_skill_category, content_house, user
):
    """Pack skill categories assigned as primary show in get_primary_skill_categories."""
    fighter = ContentFighter.objects.create(
        type="Primary Cat Fighter",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    fighter.primary_skill_categories.add(pack_skill_category)

    lst = List.objects.create(
        name="Primary Cat List", owner=user, content_house=content_house
    )
    lst.packs.add(pack)

    lf = ListFighter.objects.create(
        name="Primary Cat Guy", content_fighter=fighter, list=lst, owner=user
    )

    primary_cats = lf.get_primary_skill_categories()
    assert pack_skill_category in primary_cats
