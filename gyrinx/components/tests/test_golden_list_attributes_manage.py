"""Golden-equivalence test for the manage list attributes page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_manage_list_attributes_matches_legacy(user, make_list):
    from gyrinx.content.models import ContentAttribute, ContentAttributeValue
    from gyrinx.core.models.list import ListAttributeAssignment

    lst = make_list("Iron Skulls", owner=user)

    # One attribute with an assigned value (renders the joined names) and one
    # with no assignment (renders the "Not set" span) exercise both table
    # branches; both are unrestricted so they surface in ``all_attributes``.
    alignment = ContentAttribute.objects.create(name="Alignment")
    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment, name="Law Abiding"
    )
    ListAttributeAssignment.objects.create(list=lst, attribute_value=law_abiding)
    ContentAttribute.objects.create(name="Alliance")

    request = _request(user)
    # The view GET branch passes only the List object as ``list``.
    context = {"list": lst}
    assert_equivalent("core/list_attributes_manage.html", context, request)
