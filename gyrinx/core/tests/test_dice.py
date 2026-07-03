"""Tests for the dice roller view — seed-driven, reproducible rolls."""

import re

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import qt, qt_append, qt_nth

# Rolled dice carry an aria-label the Roll-button icons don't, so this only
# matches dice in the tray, not the D6/D3 button glyphs.
ROLLED_RE = re.compile(r'aria-label="Dice showing ([1-6])"')


def _rolled(response):
    return ROLLED_RE.findall(response.content.decode())


def _placeholders(response):
    return response.content.decode().count("dice-placeholder")


@pytest.mark.django_db
def test_no_seed_shows_placeholders_not_values(client, user):
    client.force_login(user)
    resp = client.get(reverse("core:dice"), {"m": "d6", "d": "3"})
    assert resp.status_code == 200
    assert _rolled(resp) == []  # nothing rolled without a seed
    assert _placeholders(resp) == 3  # one "?" per configured die


@pytest.mark.django_db
def test_seed_produces_a_reproducible_roll(client, user):
    client.force_login(user)
    url = reverse("core:dice")
    params = {"m": "d6", "d": "5", "seed": "abc123"}
    first = _rolled(client.get(url, params))
    second = _rolled(client.get(url, params))
    assert len(first) == 5
    assert first == second  # same URL => same roll


@pytest.mark.django_db
def test_d6_and_d3_stay_in_range(client, user):
    client.force_login(user)
    url = reverse("core:dice")
    d6 = _rolled(client.get(url, {"m": "d6", "d": "20", "seed": "s"}))
    d3 = _rolled(client.get(url, {"m": "d3", "d": "20", "seed": "s"}))
    assert d6 and all(1 <= int(v) <= 6 for v in d6)
    assert d3 and all(1 <= int(v) <= 3 for v in d3)


@pytest.mark.django_db
def test_multiple_groups_roll_all_dice(client, user):
    client.force_login(user)
    resp = client.get(reverse("core:dice"), {"m": "d6", "d": ["2", "3"], "seed": "x"})
    assert len(_rolled(resp)) == 5  # 2 + 3 across the two groups


@pytest.mark.django_db
def test_roll_buttons_carry_a_seed_edits_do_not(client, user):
    client.force_login(user)
    resp = client.get(reverse("core:dice"), {"m": "d6", "d": "2", "seed": "keep"})
    html = resp.content.decode()
    # The Roll buttons embed a fresh seed to roll with...
    assert "seed=" in html
    # ...but the current seed is never propagated into any link, so editing
    # (add die / new group) lands on a seedless URL and hides the values.
    assert "seed=keep" not in html


def test_qt_drop_removes_named_keys():
    """qt_nth / qt_append honour ``drop`` so structure edits shed the seed."""
    req = RequestFactory().get("/?m=d6&d=2&seed=keep")
    nth = qt_nth(req, nth=0, drop="seed", d="3")
    assert "d=3" in nth
    assert "seed" not in nth
    appended = qt_append(req, drop="seed", d="1")
    assert "seed" not in appended
    # Without drop, existing params (including seed) are preserved.
    assert "seed=keep" in qt(req, m="d6")
