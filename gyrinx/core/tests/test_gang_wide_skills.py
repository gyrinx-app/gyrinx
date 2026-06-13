"""Tests for gang-wide skill-tree selection (issue #1817)."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.urls import reverse

from gyrinx.content.models import (
    ContentHouse,
    ContentHouseSkillRankAccess,
    ContentSkillCategory,
)
from gyrinx.core.forms.skill_tree import ListSkillTreeForm
from gyrinx.core.models.list import List, ListFighter, ListSkillTreeAssignment
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.models import FighterCategoryChoices


def _add_to_pack(pack, obj):
    """Attach a content object to a pack (makes it pack-scoped)."""
    ct = ContentType.objects.get_for_model(type(obj))
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=obj.pk, owner=pack.owner
    )


@pytest.fixture
def skill_trees(db):
    """Four skill trees the gang can rank."""
    return [
        ContentSkillCategory.objects.create(name=name)
        for name in ["Agility", "Brawn", "Cunning", "Ferocity"]
    ]


@pytest.fixture
def gang_house(db):
    """A house that uses gang-wide skills, picking 4 ranked trees."""
    return ContentHouse.objects.create(
        name="House Venator",
        gang_wide_skills=True,
        gang_skill_tree_count=4,
    )


@pytest.fixture
def rank_rules(gang_house):
    """BoP-style rules: Leaders/Champions 1&2 primary, 3&4 secondary;
    Gangers 1 primary, 2&3 secondary."""

    def rule(category, slot, role):
        return ContentHouseSkillRankAccess.objects.create(
            house=gang_house, fighter_category=category, slot=slot, role=role
        )

    for cat in [FighterCategoryChoices.LEADER, FighterCategoryChoices.CHAMPION]:
        rule(cat, 1, "primary")
        rule(cat, 2, "primary")
        rule(cat, 3, "secondary")
        rule(cat, 4, "secondary")
    rule(FighterCategoryChoices.GANGER, 1, "primary")
    rule(FighterCategoryChoices.GANGER, 2, "secondary")
    rule(FighterCategoryChoices.GANGER, 3, "secondary")


@pytest.fixture
def gang_list(db, user, gang_house):
    return List.objects.create_with_facts(
        name="My Venators", content_house=gang_house, owner=user
    )


def _make_fighter(make_content_fighter, gang_house, gang_list, user, category):
    cf = make_content_fighter(
        type=f"Venator {category}",
        category=category,
        house=gang_house,
        base_cost=100,
    )
    return ListFighter.objects.create(
        list=gang_list, name=f"{category} fighter", content_fighter=cf, owner=user
    )


def _pick(gang_list, slot, category):
    ListSkillTreeAssignment.objects.create(
        list=gang_list, slot=slot, skill_category=category
    )


@pytest.mark.django_db
def test_leader_gets_primary_and_secondary_by_rank(
    make_content_fighter, gang_house, gang_list, rank_rules, skill_trees, user
):
    agility, brawn, cunning, ferocity = skill_trees
    _pick(gang_list, 1, agility)
    _pick(gang_list, 2, brawn)
    _pick(gang_list, 3, cunning)
    _pick(gang_list, 4, ferocity)

    leader = _make_fighter(
        make_content_fighter, gang_house, gang_list, user, FighterCategoryChoices.LEADER
    )

    assert leader.get_primary_skill_categories() == {agility, brawn}
    assert leader.get_secondary_skill_categories() == {cunning, ferocity}


@pytest.mark.django_db
def test_ganger_gets_different_mapping_than_leader(
    make_content_fighter, gang_house, gang_list, rank_rules, skill_trees, user
):
    agility, brawn, cunning, ferocity = skill_trees
    _pick(gang_list, 1, agility)
    _pick(gang_list, 2, brawn)
    _pick(gang_list, 3, cunning)
    _pick(gang_list, 4, ferocity)

    ganger = _make_fighter(
        make_content_fighter, gang_house, gang_list, user, FighterCategoryChoices.GANGER
    )

    assert ganger.get_primary_skill_categories() == {agility}
    assert ganger.get_secondary_skill_categories() == {brawn, cunning}


@pytest.mark.django_db
def test_unpicked_slots_yield_no_categories(
    make_content_fighter, gang_house, gang_list, rank_rules, skill_trees, user
):
    agility, brawn, cunning, ferocity = skill_trees
    # Only pick slots 1 and 2; leader's secondary (slots 3,4) stay empty.
    _pick(gang_list, 1, agility)
    _pick(gang_list, 2, brawn)

    leader = _make_fighter(
        make_content_fighter, gang_house, gang_list, user, FighterCategoryChoices.LEADER
    )

    assert leader.get_primary_skill_categories() == {agility, brawn}
    assert leader.get_secondary_skill_categories() == set()


@pytest.mark.django_db
def test_no_picks_is_graceful(
    make_content_fighter, gang_house, gang_list, rank_rules, user
):
    leader = _make_fighter(
        make_content_fighter, gang_house, gang_list, user, FighterCategoryChoices.LEADER
    )
    assert leader.get_primary_skill_categories() == set()
    assert leader.get_secondary_skill_categories() == set()


@pytest.mark.django_db
def test_promotion_changes_resolved_trees(
    make_content_fighter, gang_house, gang_list, rank_rules, skill_trees, user
):
    """A ganger promoted to champion (category_override) resolves by current rank."""
    agility, brawn, cunning, ferocity = skill_trees
    _pick(gang_list, 1, agility)
    _pick(gang_list, 2, brawn)
    _pick(gang_list, 3, cunning)
    _pick(gang_list, 4, ferocity)

    fighter = _make_fighter(
        make_content_fighter, gang_house, gang_list, user, FighterCategoryChoices.GANGER
    )
    assert fighter.get_primary_skill_categories() == {agility}

    fighter.category_override = FighterCategoryChoices.CHAMPION
    fighter.save()
    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert fighter.get_primary_skill_categories() == {agility, brawn}
    assert fighter.get_secondary_skill_categories() == {cunning, ferocity}


@pytest.mark.django_db
def test_non_gang_wide_house_uses_fighter_template(
    make_content_fighter, content_house, make_list, skill_trees, user
):
    """Non-gang-wide house ignores gang picks and uses the template M2Ms."""
    agility, brawn, cunning, ferocity = skill_trees
    lst = make_list("Normal gang", content_house=content_house)
    cf = make_content_fighter(
        type="Normal Leader",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=100,
    )
    cf.primary_skill_categories.add(agility)
    cf.secondary_skill_categories.add(brawn)
    fighter = ListFighter.objects.create(
        list=lst, name="Leader", content_fighter=cf, owner=user
    )

    assert fighter.get_primary_skill_categories() == {agility}
    assert fighter.get_secondary_skill_categories() == {brawn}


@pytest.mark.django_db
def test_clone_preserves_skill_tree_picks(gang_list, skill_trees):
    agility, brawn, cunning, ferocity = skill_trees
    _pick(gang_list, 1, agility)
    _pick(gang_list, 2, brawn)

    clone = gang_list.clone(name="Clone")

    picks = {
        a.slot: a.skill_category
        for a in clone.listskilltreeassignment_set.filter(archived=False)
    }
    assert picks == {1: agility, 2: brawn}


# --- View / form tests ---


@pytest.mark.django_db
def test_edit_view_saves_picks(client, user, gang_list, skill_trees):
    agility, brawn, cunning, ferocity = skill_trees
    client.force_login(user)
    url = reverse("core:list-skill-trees-edit", args=[gang_list.id])

    resp = client.get(url)
    assert resp.status_code == 200

    resp = client.post(
        url,
        {
            "slot_1": agility.id,
            "slot_2": brawn.id,
            "slot_3": "",
            "slot_4": "",
        },
    )
    assert resp.status_code == 302

    picks = {
        a.slot: a.skill_category
        for a in gang_list.listskilltreeassignment_set.filter(archived=False)
    }
    assert picks == {1: agility, 2: brawn}


@pytest.mark.django_db
def test_edit_view_rejects_duplicate_picks(client, user, gang_list, skill_trees):
    agility, brawn, cunning, ferocity = skill_trees
    client.force_login(user)
    url = reverse("core:list-skill-trees-edit", args=[gang_list.id])

    resp = client.post(
        url,
        {"slot_1": agility.id, "slot_2": agility.id, "slot_3": "", "slot_4": ""},
    )
    assert resp.status_code == 200  # re-rendered with error
    assert gang_list.listskilltreeassignment_set.filter(archived=False).count() == 0


@pytest.mark.django_db
def test_edit_view_404_for_non_gang_wide_house(client, user, make_list, content_house):
    lst = make_list("Normal gang", content_house=content_house)
    client.force_login(user)
    url = reverse("core:list-skill-trees-edit", args=[lst.id])
    resp = client.get(url)
    # Redirects back to the list with an error message.
    assert resp.status_code == 302


@pytest.mark.django_db
def test_creation_redirects_to_skill_trees_for_gang_wide_house(
    client, user, gang_house
):
    client.force_login(user)
    resp = client.post(
        reverse("core:lists-new") + "?skip_packs=1",
        {
            "name": "Fresh Venators",
            "content_house": gang_house.id,
            "public": "on",
        },
    )
    assert resp.status_code == 302
    new_list = List.objects.get(name="Fresh Venators")
    assert resp.url == reverse("core:list-skill-trees-edit", args=[new_list.id])


@pytest.mark.django_db
def test_edit_page_shows_skill_trees_link_only_for_gang_wide_house(
    client, user, gang_list, make_list, content_house
):
    client.force_login(user)

    # Gang-wide house: the list edit page links to the skill-tree manager.
    resp = client.get(reverse("core:list-edit", args=[gang_list.id]))
    assert resp.status_code == 200
    assert (
        reverse("core:list-skill-trees-manage", args=[gang_list.id])
        in resp.content.decode()
    )

    # Normal house: no skill-tree section.
    normal = make_list("Normal gang", content_house=content_house)
    resp = client.get(reverse("core:list-edit", args=[normal.id]))
    assert resp.status_code == 200
    assert (
        reverse("core:list-skill-trees-manage", args=[normal.id])
        not in resp.content.decode()
    )


@pytest.mark.django_db
def test_restricted_trees_hidden_by_default_revealed_by_filter(client, user, gang_list):
    restricted = ContentSkillCategory.objects.create(
        name="Secret Tree", restricted=True
    )
    client.force_login(user)
    url = reverse("core:list-skill-trees-edit", args=[gang_list.id])

    resp = client.get(url)
    assert restricted.id not in [
        c.pk for c in resp.context["form"].fields["slot_1"].queryset
    ]

    resp = client.get(url + "?include_restricted=1")
    assert restricted.id in [
        c.pk for c in resp.context["form"].fields["slot_1"].queryset
    ]


# --- DB constraints (PR feedback: active uniqueness) ---


@pytest.mark.django_db
def test_duplicate_active_slot_is_rejected(gang_list, skill_trees):
    agility, brawn, *_ = skill_trees
    ListSkillTreeAssignment.objects.create(
        list=gang_list, slot=1, skill_category=agility
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ListSkillTreeAssignment.objects.create(
                list=gang_list, slot=1, skill_category=brawn
            )


@pytest.mark.django_db
def test_duplicate_active_category_is_rejected(gang_list, skill_trees):
    agility, *_ = skill_trees
    ListSkillTreeAssignment.objects.create(
        list=gang_list, slot=1, skill_category=agility
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ListSkillTreeAssignment.objects.create(
                list=gang_list, slot=2, skill_category=agility
            )


@pytest.mark.django_db
def test_archived_rows_do_not_block_new_active_picks(gang_list, skill_trees):
    agility, *_ = skill_trees
    old = ListSkillTreeAssignment.objects.create(
        list=gang_list, slot=1, skill_category=agility
    )
    old.archived = True
    old.save()

    # Re-picking the same slot + tree is fine once the old row is archived.
    ListSkillTreeAssignment.objects.create(
        list=gang_list, slot=1, skill_category=agility
    )
    assert (
        gang_list.listskilltreeassignment_set.filter(archived=False, slot=1).count()
        == 1
    )


# --- Pack-authored skill trees (PR feedback: pool must be pack-aware) ---


@pytest.mark.django_db
def test_pool_includes_pack_authored_trees(gang_list, user):
    pack = CustomContentPack.objects.create(name="Skill Pack", owner=user, listed=True)
    pack_cat = ContentSkillCategory.objects.create(name="Pack Tree")
    _add_to_pack(pack, pack_cat)
    gang_list.packs.add(pack)

    form = ListSkillTreeForm(list_obj=gang_list, request=None)
    pool = set(form.fields["slot_1"].queryset)
    assert pack_cat in pool


@pytest.mark.django_db
def test_explicit_pool_is_pack_aware_and_respects_restricted_filter(
    gang_house, gang_list, skill_trees, user
):
    agility, *_ = skill_trees
    restricted = ContentSkillCategory.objects.create(
        name="Restricted Tree", restricted=True
    )
    pack = CustomContentPack.objects.create(name="Skill Pack", owner=user, listed=True)
    pack_cat = ContentSkillCategory.objects.create(name="Pack Tree")
    _add_to_pack(pack, pack_cat)
    gang_list.packs.add(pack)

    # Explicit pool contains a normal tree, a restricted tree, and a pack tree.
    gang_house.gang_skill_tree_choices.set([agility, restricted, pack_cat])

    # Default: restricted hidden, but the pack-authored tree is still pickable.
    form = ListSkillTreeForm(list_obj=gang_list, request=None, include_restricted=False)
    pool = set(form.fields["slot_1"].queryset)
    assert agility in pool
    assert pack_cat in pool
    assert restricted not in pool

    # Reveal filter on: restricted tree now appears too.
    form = ListSkillTreeForm(list_obj=gang_list, request=None, include_restricted=True)
    pool = set(form.fields["slot_1"].queryset)
    assert restricted in pool
    assert pack_cat in pool


@pytest.mark.django_db
def test_resolution_with_pack_authored_tree(
    make_content_fighter, gang_house, gang_list, rank_rules, user
):
    pack = CustomContentPack.objects.create(name="Skill Pack", owner=user, listed=True)
    pack_cat = ContentSkillCategory.objects.create(name="Pack Tree")
    _add_to_pack(pack, pack_cat)
    gang_list.packs.add(pack)
    _pick(gang_list, 1, pack_cat)

    leader = _make_fighter(
        make_content_fighter, gang_house, gang_list, user, FighterCategoryChoices.LEADER
    )
    assert pack_cat in leader.get_primary_skill_categories()
