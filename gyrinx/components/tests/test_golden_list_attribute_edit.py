"""Golden-equivalence test for the list attribute-edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_attribute_edit_single_select_matches_legacy(user, make_list):
    from django.urls import reverse

    from gyrinx.content.models import ContentAttribute, ContentAttributeValue
    from gyrinx.core.forms.attribute import ListAttributeForm

    lst = make_list("Iron Skulls", owner=user)

    # Single-select attribute with a couple of values (radio-button widget).
    alignment = ContentAttribute.objects.create(name="Alignment", is_single_select=True)
    ContentAttributeValue.objects.create(attribute=alignment, name="Law Abiding")
    ContentAttributeValue.objects.create(attribute=alignment, name="Outlaw")

    request = _request(user)
    manage_url = reverse("core:list-attributes-manage", args=[lst.id])

    # With a return_url: exercises the hidden input, "Back to attributes" and the
    # cancel-to-return_url branch (as reached from the manage-attributes page).
    context = {
        "list": lst,
        "attribute": alignment,
        "form": ListAttributeForm(list_obj=lst, attribute=alignment, request=request),
        "return_url": manage_url,
    }
    assert_equivalent("core/list_attribute_edit.html", context, request)

    # Without a return_url (plain GET): exercises the else branch that links back
    # to the list and cancels to the list URL, with no hidden input.
    context_no_return = {
        "list": lst,
        "attribute": alignment,
        "form": ListAttributeForm(list_obj=lst, attribute=alignment, request=request),
        "return_url": "",
    }
    assert_equivalent("core/list_attribute_edit.html", context_no_return, request)


@pytest.mark.django_db
def test_list_attribute_edit_multi_select_matches_legacy(user, make_list):
    from gyrinx.content.models import ContentAttribute, ContentAttributeValue
    from gyrinx.core.forms.attribute import ListAttributeForm

    lst = make_list("Iron Skulls", owner=user)

    # Multi-select attribute: checkbox widget + "Select multiple options" copy.
    alliance = ContentAttribute.objects.create(name="Alliance", is_single_select=False)
    ContentAttributeValue.objects.create(attribute=alliance, name="Guild")
    ContentAttributeValue.objects.create(attribute=alliance, name="Noble House")

    request = _request(user)
    context = {
        "list": lst,
        "attribute": alliance,
        "form": ListAttributeForm(list_obj=lst, attribute=alliance, request=request),
        "return_url": "",
    }
    assert_equivalent("core/list_attribute_edit.html", context, request)
