"""Guessing and formatting IANA timezones."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.template import Context, Template
from django.test import RequestFactory
from django.utils import timezone as dj_tz

from gyrinx.timezones import (
    COOKIE_NAME,
    detect_timezone,
    is_valid_timezone,
    timezone_choices,
    timezone_for_country,
    timezone_label,
)


def test_known_country_codes_map_to_zones():
    assert timezone_for_country("GB") == "Europe/London"
    assert timezone_for_country("uk") == "Europe/London"
    assert timezone_for_country("US") == "America/New_York"
    assert timezone_for_country("AU") == "Australia/Sydney"
    assert timezone_for_country("XX") == ""
    assert timezone_for_country("") == ""


def test_is_valid_timezone():
    assert is_valid_timezone("UTC")
    assert is_valid_timezone("America/New_York")
    assert not is_valid_timezone("")
    assert not is_valid_timezone("Not/A_Zone")
    assert not is_valid_timezone(None)


def test_detect_prefers_browser_cookie_over_country_header():
    request = RequestFactory().get("/", HTTP_CF_IPCOUNTRY="GB")
    request.COOKIES[COOKIE_NAME] = "America/Los_Angeles"
    assert detect_timezone(request) == "America/Los_Angeles"


def test_detect_uses_country_header_without_cookie():
    request = RequestFactory().get("/", HTTP_CF_IPCOUNTRY="GB")
    assert detect_timezone(request) == "Europe/London"


def test_detect_uses_cloudflare_timezone_header():
    request = RequestFactory().get("/", HTTP_CF_TIMEZONE="Pacific/Auckland")
    assert detect_timezone(request) == "Pacific/Auckland"


def test_detect_ignores_invalid_cookie():
    request = RequestFactory().get("/", HTTP_CF_IPCOUNTRY="DE")
    request.COOKIES[COOKIE_NAME] = "Nope/Nope"
    assert detect_timezone(request) == "Europe/Berlin"


def test_timezone_choices_offer_common_zones_first():
    choices = timezone_choices()
    assert choices[0][0] == "Common"
    common_values = [value for value, _label in choices[0][1]]
    assert common_values[0] == "UTC"
    assert "Europe/London" in common_values
    assert "America/New_York" in common_values


def test_date_filter_follows_activated_timezone():
    """The campaign log's `j M H:i` format, in Eastern Daylight Time."""
    when = datetime(2026, 8, 29, 6, 27, tzinfo=UTC)
    dj_tz.activate(ZoneInfo("America/New_York"))
    try:
        rendered = Template('{{ t|date:"j M H:i" }}').render(Context({"t": when}))
    finally:
        dj_tz.deactivate()
    assert rendered == "29 Aug 02:27"


def test_timezone_label_names_the_zone():
    assert "UTC" in timezone_label("UTC")
    assert "Europe/London" in timezone_label("Europe/London")
