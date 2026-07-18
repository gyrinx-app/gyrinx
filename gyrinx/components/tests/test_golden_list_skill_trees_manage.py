"""Golden-equivalence test for the gang skill-trees management page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_skill_trees_manage_matches_legacy(user, make_list):
    from gyrinx.content.models import ContentSkillCategory
    from gyrinx.core.models.list import ListSkillTreeAssignment

    lst = make_list("Iron Skulls", owner=user)

    agility = ContentSkillCategory.objects.create(name="Agility")
    brawn = ContentSkillCategory.objects.create(name="Brawn")
    ListSkillTreeAssignment.objects.create(list=lst, slot=1, skill_category=agility)
    ListSkillTreeAssignment.objects.create(list=lst, slot=2, skill_category=brawn)

    request = _request(user)
    context = {
        "list": lst,
        "assignments": lst.active_skill_trees_cached,
    }
    assert_equivalent("core/list_skill_trees_manage.html", context, request)
