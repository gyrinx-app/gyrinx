"""Golden-equivalence test for the fighter rules edit page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_rules_edit_matches_legacy(user, make_list, make_list_fighter):
    from django.core.paginator import Paginator

    from gyrinx.content.models import ContentRule

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)

    # Build the context exactly as the view GET branch does.
    search_query = ""
    rules_qs = ContentRule.objects.with_packs(
        lst.packs.all(), include_archived_items=True
    )
    default_rules = rules_qs.filter(contentfighter=fighter.content_fighter)
    disabled_rule_ids = set(
        rules_qs.filter(disabled_by_fighters=fighter).values_list("id", flat=True)
    )
    default_rules_display = [
        {"rule": rule, "is_disabled": rule.id in disabled_rule_ids}
        for rule in default_rules
    ]
    custom_rules = rules_qs.filter(custom_for_fighters=fighter)
    available_rules = rules_qs.exclude(
        id__in=custom_rules.values_list("id", flat=True)
    ).order_by("name")
    paginator = Paginator(available_rules, 20)
    page_obj = paginator.get_page(1)

    context = {
        "list": lst,
        "fighter": fighter,
        "default_rules_display": default_rules_display,
        "custom_rules": custom_rules,
        "available_rules": available_rules,
        "page_obj": page_obj,
        "search_query": search_query,
    }
    assert_equivalent("core/list_fighter_rules_edit.html", context, request)
