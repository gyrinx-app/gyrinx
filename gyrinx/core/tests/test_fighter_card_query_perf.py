"""Tests for per-fighter query reductions on the fighter card / list pages."""

import pytest

from gyrinx.core.models import ListFighterAdvancement


@pytest.mark.django_db
def test_active_advancement_count_excludes_archived(
    make_list, make_list_fighter, make_content_skill
):
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Alpha")
    skill = make_content_skill("Nerves of Steel")

    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=skill,
        xp_cost=10,
        cost_increase=5,
    )
    archived_adv = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=skill,
        xp_cost=10,
        cost_increase=5,
    )
    archived_adv.archived = True
    archived_adv.save()

    # Non-prefetched path.
    assert fighter.active_advancement_count == 1


@pytest.mark.django_db
def test_active_advancement_count_uses_prefetch(
    make_list, make_list_fighter, make_content_skill, django_assert_num_queries
):
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Alpha")
    skill = make_content_skill("Nerves of Steel")
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=skill,
        xp_cost=10,
        cost_increase=5,
    )

    # When fighters come through the prefetch suite, active_advancement_count
    # must not issue an additional query.
    prefetched = lst.fighters_cached
    target = next(f for f in prefetched if f.id == fighter.id)
    with django_assert_num_queries(0):
        assert target.active_advancement_count == 1


@pytest.mark.django_db
def test_archived_fighters_count_cached(make_list, make_list_fighter):
    lst = make_list("Test Gang")
    make_list_fighter(lst, "Active")
    archived = make_list_fighter(lst, "Archived")
    archived.archived = True
    archived.save()

    assert lst.archived_fighters_count_cached == 1
