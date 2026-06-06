"""Tests for the house_icon template tag."""

from unittest import mock

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.template import Context, Template

ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
    '<path d="M10 10 L20 20"/></svg>'
).encode("utf-8")

TEMPLATE = Template("{% load color_tags %}{% house_icon house %}")


def _render(house):
    return TEMPLATE.render(Context({"house": house}))


@pytest.fixture
def house_with_icon(content_house, settings, tmp_path):
    # Keep uploaded files out of the project tree.
    settings.MEDIA_ROOT = str(tmp_path)
    content_house.icon.save("vansaar.svg", ContentFile(ICON_SVG), save=False)
    return content_house


@pytest.mark.django_db
def test_icon_is_rendered(house_with_icon):
    cache.clear()
    result = _render(house_with_icon)
    assert 'class="house-icon"' in result
    assert "<svg" in result


@pytest.mark.django_db
def test_iconless_house_renders_nothing(content_house):
    cache.clear()
    assert content_house.icon.name in (None, "")
    result = _render(content_house)
    assert result.strip() == ""


@pytest.mark.django_db
def test_none_house_renders_nothing():
    cache.clear()
    result = _render(None)
    assert result.strip() == ""


@pytest.mark.django_db
def test_icon_is_sanitised_through_tag(content_house, settings, tmp_path):
    cache.clear()
    settings.MEDIA_ROOT = str(tmp_path)
    malicious = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        b'<script>alert(1)</script><rect x="1" y="1" width="2" height="2" '
        b'onload="evil()"/></svg>'
    )
    content_house.icon.save("evil.svg", ContentFile(malicious), save=False)
    result = _render(content_house)
    assert "<script" not in result.lower()
    assert "onload" not in result
    assert "alert(1)" not in result


@pytest.mark.django_db
def test_svg_read_and_sanitised_once_then_cached(house_with_icon):
    cache.clear()
    with mock.patch(
        "gyrinx.core.templatetags.color_tags.sanitize_house_icon_svg",
        return_value="<svg class='house-icon'></svg>",
    ) as sanitiser:
        _render(house_with_icon)
        _render(house_with_icon)
    # File read + sanitise happens once; the second render is a cache hit.
    assert sanitiser.call_count == 1
