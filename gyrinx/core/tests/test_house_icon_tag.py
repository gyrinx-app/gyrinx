"""Tests for the gated house_icon template tag."""

from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.template import Context, Template
from django.test import RequestFactory

from gyrinx.core.templatetags.color_tags import HOUSE_ICONS_ALPHA_GROUP

ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
    '<path d="M10 10 L20 20"/></svg>'
).encode("utf-8")

TEMPLATE = Template("{% load color_tags %}{% house_icon house %}")


def _render(house, user):
    request = RequestFactory().get("/")
    request.user = user
    return TEMPLATE.render(Context({"house": house, "request": request}))


@pytest.fixture
def alpha_group(db):
    return Group.objects.get_or_create(name=HOUSE_ICONS_ALPHA_GROUP)[0]


@pytest.fixture
def house_with_icon(content_house, settings, tmp_path):
    # Keep uploaded files out of the project tree.
    settings.MEDIA_ROOT = str(tmp_path)
    content_house.icon.save("vansaar.svg", ContentFile(ICON_SVG), save=False)
    return content_house


@pytest.mark.django_db
def test_member_sees_icon(house_with_icon, user, alpha_group):
    cache.clear()
    user.groups.add(alpha_group)
    result = _render(house_with_icon, user)
    assert 'class="house-icon"' in result
    assert "<svg" in result


@pytest.mark.django_db
def test_non_member_sees_nothing(house_with_icon, user, alpha_group):
    cache.clear()
    # user exists, group exists, but user is not a member
    result = _render(house_with_icon, user)
    assert result.strip() == ""


@pytest.mark.django_db
def test_anonymous_sees_nothing(house_with_icon, alpha_group):
    cache.clear()
    result = _render(house_with_icon, AnonymousUser())
    assert result.strip() == ""


@pytest.mark.django_db
def test_member_with_iconless_house_sees_nothing(content_house, user, alpha_group):
    cache.clear()
    user.groups.add(alpha_group)
    assert content_house.icon.name in (None, "")
    result = _render(content_house, user)
    assert result.strip() == ""


@pytest.mark.django_db
def test_none_house_renders_nothing(user, alpha_group):
    cache.clear()
    user.groups.add(alpha_group)
    result = _render(None, user)
    assert result.strip() == ""


@pytest.mark.django_db
def test_icon_is_sanitised_through_tag(
    content_house, user, alpha_group, settings, tmp_path
):
    cache.clear()
    settings.MEDIA_ROOT = str(tmp_path)
    malicious = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        b'<script>alert(1)</script><rect x="1" y="1" width="2" height="2" '
        b'onload="evil()"/></svg>'
    )
    content_house.icon.save("evil.svg", ContentFile(malicious), save=False)
    user.groups.add(alpha_group)
    result = _render(content_house, user)
    assert "<script" not in result.lower()
    assert "onload" not in result
    assert "alert(1)" not in result


@pytest.mark.django_db
def test_svg_read_and_sanitised_once_then_cached(house_with_icon, user, alpha_group):
    cache.clear()
    user.groups.add(alpha_group)
    with mock.patch(
        "gyrinx.core.templatetags.color_tags.sanitize_house_icon_svg",
        return_value="<svg class='house-icon'></svg>",
    ) as sanitiser:
        _render(house_with_icon, user)
        _render(house_with_icon, user)
    # File read + sanitise happens once; the second render is a cache hit.
    assert sanitiser.call_count == 1
