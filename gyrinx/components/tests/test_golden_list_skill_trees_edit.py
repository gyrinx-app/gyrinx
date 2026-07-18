"""Golden-equivalence test: list skill trees edit page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_skill_trees_edit_matches_legacy(user, make_list, content_house):
    from gyrinx.content.models.skill import ContentSkillCategory
    from gyrinx.core.forms.skill_tree import ListSkillTreeForm

    # House uses gang-wide skills so the form renders a ranked slot per tree.
    content_house.gang_wide_skills = True
    content_house.gang_skill_tree_count = 2
    content_house.save()

    ContentSkillCategory.objects.create(name="Agility")
    ContentSkillCategory.objects.create(name="Brawn")

    lst = make_list("Iron Skulls", owner=user)

    request = _request(user)
    include_restricted = False
    form = ListSkillTreeForm(
        list_obj=lst, request=request, include_restricted=include_restricted
    )

    context = {
        "list": lst,
        "form": form,
        "include_restricted": include_restricted,
        "return_url": "",
    }
    assert_equivalent("core/list_skill_trees_edit.html", context, request)
