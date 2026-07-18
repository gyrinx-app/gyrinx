"""Golden-equivalence test for the fighter skills edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_skills_edit_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.content.models import ContentSkill
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    # Mirror the view GET branch: fighter fetched with related data.
    fighter = ListFighter.objects.with_related_data().get(
        id=fighter.id, list=lst, owner=lst.owner
    )

    # Scope skill queries to the list's packs, exactly as the view does.
    skills_qs = ContentSkill.objects.with_packs(
        lst.packs.all(), include_archived_items=True
    )
    default_skills = skills_qs.filter(contentfighter=fighter.content_fighter)
    disabled_skill_ids = set(
        skills_qs.filter(disabled_for_fighters=fighter).values_list("id", flat=True)
    )
    default_skills_display = [
        {"skill": skill, "is_disabled": skill.id in disabled_skill_ids}
        for skill in default_skills
    ]
    user_added_skills = skills_qs.filter(listfighter=fighter)

    request = _request(user)
    context = {
        "fighter": fighter,
        "list": lst,
        "default_skills_display": default_skills_display,
        "user_added_skills": user_added_skills,
        "categories": [],
        "search_query": "",
        "category_filter": "primary-secondary-only",
    }
    assert_equivalent("core/list_fighter_skills_edit.html", context, request)
