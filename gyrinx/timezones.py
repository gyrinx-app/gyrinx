"""IANA timezones for account settings, and guessing one from a request.

Timestamps are stored in UTC. Django's ``|date`` / ``|time`` filters and
``timezone.localtime`` follow whichever zone is ``activate``-d for the
request, so the rest of the site does not have to know about this.

A profile timezone is sticky once set — chosen on the account page, or
filled in on the first visit from the browser's zone (cookie) or the
country the request's IP resolved to (CDN / load-balancer headers).
"""

from __future__ import annotations

import zoneinfo
from datetime import datetime
from functools import cache
from urllib.parse import unquote

COOKIE_NAME = "gyrinx_tz"
SESSION_TZ_KEY = "timezone"
SESSION_TZ_USER_KEY = "timezone_user_id"

#: Direct IANA names some fronts already send (Cloudflare Transform Rules
#: can add ``CF-Timezone`` from ``cf.timezone``).
_TIMEZONE_HEADERS = (
    "HTTP_CF_TIMEZONE",
    "HTTP_X_TIMEZONE",
)

#: ISO 3166-1 alpha-2 from the usual CDN / load-balancer GeoIP headers.
_COUNTRY_HEADERS = (
    "HTTP_CF_IPCOUNTRY",
    "HTTP_CLOUDFRONT_VIEWER_COUNTRY",
    "HTTP_X_APPENGINE_COUNTRY",
    "HTTP_X_COUNTRY_CODE",
    "HTTP_X_CLIENT_GEO_COUNTRY",
)

#: Country codes that mean "we could not tell", not a real country.
_UNUSABLE_COUNTRIES = frozenset({"", "XX", "T1", "A1", "A2", "O1"})

#: Capitals / most-populous zones. Multi-zone countries get one default;
#: the browser cookie is preferred and the account page can override.
COUNTRY_TIMEZONES = {
    "AD": "Europe/Andorra",
    "AE": "Asia/Dubai",
    "AF": "Asia/Kabul",
    "AG": "America/Antigua",
    "AI": "America/Anguilla",
    "AL": "Europe/Tirane",
    "AM": "Asia/Yerevan",
    "AO": "Africa/Luanda",
    "AR": "America/Argentina/Buenos_Aires",
    "AS": "Pacific/Pago_Pago",
    "AT": "Europe/Vienna",
    "AU": "Australia/Sydney",
    "AW": "America/Aruba",
    "AX": "Europe/Helsinki",
    "AZ": "Asia/Baku",
    "BA": "Europe/Sarajevo",
    "BB": "America/Barbados",
    "BD": "Asia/Dhaka",
    "BE": "Europe/Brussels",
    "BF": "Africa/Ouagadougou",
    "BG": "Europe/Sofia",
    "BH": "Asia/Bahrain",
    "BI": "Africa/Bujumbura",
    "BJ": "Africa/Porto-Novo",
    "BL": "America/St_Barthelemy",
    "BM": "Atlantic/Bermuda",
    "BN": "Asia/Brunei",
    "BO": "America/La_Paz",
    "BQ": "America/Kralendijk",
    "BR": "America/Sao_Paulo",
    "BS": "America/Nassau",
    "BT": "Asia/Thimphu",
    "BW": "Africa/Gaborone",
    "BY": "Europe/Minsk",
    "BZ": "America/Belize",
    "CA": "America/Toronto",
    "CC": "Indian/Cocos",
    "CD": "Africa/Kinshasa",
    "CF": "Africa/Bangui",
    "CG": "Africa/Brazzaville",
    "CH": "Europe/Zurich",
    "CI": "Africa/Abidjan",
    "CK": "Pacific/Rarotonga",
    "CL": "America/Santiago",
    "CM": "Africa/Douala",
    "CN": "Asia/Shanghai",
    "CO": "America/Bogota",
    "CR": "America/Costa_Rica",
    "CU": "America/Havana",
    "CV": "Atlantic/Cape_Verde",
    "CW": "America/Curacao",
    "CX": "Indian/Christmas",
    "CY": "Asia/Nicosia",
    "CZ": "Europe/Prague",
    "DE": "Europe/Berlin",
    "DJ": "Africa/Djibouti",
    "DK": "Europe/Copenhagen",
    "DM": "America/Dominica",
    "DO": "America/Santo_Domingo",
    "DZ": "Africa/Algiers",
    "EC": "America/Guayaquil",
    "EE": "Europe/Tallinn",
    "EG": "Africa/Cairo",
    "EH": "Africa/El_Aaiun",
    "ER": "Africa/Asmara",
    "ES": "Europe/Madrid",
    "ET": "Africa/Addis_Ababa",
    "FI": "Europe/Helsinki",
    "FJ": "Pacific/Fiji",
    "FK": "Atlantic/Stanley",
    "FM": "Pacific/Chuuk",
    "FO": "Atlantic/Faroe",
    "FR": "Europe/Paris",
    "GA": "Africa/Libreville",
    "GB": "Europe/London",
    "GD": "America/Grenada",
    "GE": "Asia/Tbilisi",
    "GF": "America/Cayenne",
    "GG": "Europe/Guernsey",
    "GH": "Africa/Accra",
    "GI": "Europe/Gibraltar",
    "GL": "America/Godthab",
    "GM": "Africa/Banjul",
    "GN": "Africa/Conakry",
    "GP": "America/Guadeloupe",
    "GQ": "Africa/Malabo",
    "GR": "Europe/Athens",
    "GT": "America/Guatemala",
    "GU": "Pacific/Guam",
    "GW": "Africa/Bissau",
    "GY": "America/Guyana",
    "HK": "Asia/Hong_Kong",
    "HN": "America/Tegucigalpa",
    "HR": "Europe/Zagreb",
    "HT": "America/Port-au-Prince",
    "HU": "Europe/Budapest",
    "ID": "Asia/Jakarta",
    "IE": "Europe/Dublin",
    "IL": "Asia/Jerusalem",
    "IM": "Europe/Isle_of_Man",
    "IN": "Asia/Kolkata",
    "IO": "Indian/Chagos",
    "IQ": "Asia/Baghdad",
    "IR": "Asia/Tehran",
    "IS": "Atlantic/Reykjavik",
    "IT": "Europe/Rome",
    "JE": "Europe/Jersey",
    "JM": "America/Jamaica",
    "JO": "Asia/Amman",
    "JP": "Asia/Tokyo",
    "KE": "Africa/Nairobi",
    "KG": "Asia/Bishkek",
    "KH": "Asia/Phnom_Penh",
    "KI": "Pacific/Tarawa",
    "KM": "Indian/Comoro",
    "KN": "America/St_Kitts",
    "KP": "Asia/Pyongyang",
    "KR": "Asia/Seoul",
    "KW": "Asia/Kuwait",
    "KY": "America/Cayman",
    "KZ": "Asia/Almaty",
    "LA": "Asia/Vientiane",
    "LB": "Asia/Beirut",
    "LC": "America/St_Lucia",
    "LI": "Europe/Vaduz",
    "LK": "Asia/Colombo",
    "LR": "Africa/Monrovia",
    "LS": "Africa/Maseru",
    "LT": "Europe/Vilnius",
    "LU": "Europe/Luxembourg",
    "LV": "Europe/Riga",
    "LY": "Africa/Tripoli",
    "MA": "Africa/Casablanca",
    "MC": "Europe/Monaco",
    "MD": "Europe/Chisinau",
    "ME": "Europe/Podgorica",
    "MF": "America/Marigot",
    "MG": "Indian/Antananarivo",
    "MH": "Pacific/Majuro",
    "MK": "Europe/Skopje",
    "ML": "Africa/Bamako",
    "MM": "Asia/Yangon",
    "MN": "Asia/Ulaanbaatar",
    "MO": "Asia/Macau",
    "MP": "Pacific/Saipan",
    "MQ": "America/Martinique",
    "MR": "Africa/Nouakchott",
    "MS": "America/Montserrat",
    "MT": "Europe/Malta",
    "MU": "Indian/Mauritius",
    "MV": "Indian/Maldives",
    "MW": "Africa/Blantyre",
    "MX": "America/Mexico_City",
    "MY": "Asia/Kuala_Lumpur",
    "MZ": "Africa/Maputo",
    "NA": "Africa/Windhoek",
    "NC": "Pacific/Noumea",
    "NE": "Africa/Niamey",
    "NF": "Pacific/Norfolk",
    "NG": "Africa/Lagos",
    "NI": "America/Managua",
    "NL": "Europe/Amsterdam",
    "NO": "Europe/Oslo",
    "NP": "Asia/Kathmandu",
    "NR": "Pacific/Nauru",
    "NU": "Pacific/Niue",
    "NZ": "Pacific/Auckland",
    "OM": "Asia/Muscat",
    "PA": "America/Panama",
    "PE": "America/Lima",
    "PF": "Pacific/Tahiti",
    "PG": "Pacific/Port_Moresby",
    "PH": "Asia/Manila",
    "PK": "Asia/Karachi",
    "PL": "Europe/Warsaw",
    "PM": "America/Miquelon",
    "PR": "America/Puerto_Rico",
    "PS": "Asia/Gaza",
    "PT": "Europe/Lisbon",
    "PW": "Pacific/Palau",
    "PY": "America/Asuncion",
    "QA": "Asia/Qatar",
    "RE": "Indian/Reunion",
    "RO": "Europe/Bucharest",
    "RS": "Europe/Belgrade",
    "RU": "Europe/Moscow",
    "RW": "Africa/Kigali",
    "SA": "Asia/Riyadh",
    "SB": "Pacific/Guadalcanal",
    "SC": "Indian/Mahe",
    "SD": "Africa/Khartoum",
    "SE": "Europe/Stockholm",
    "SG": "Asia/Singapore",
    "SH": "Atlantic/St_Helena",
    "SI": "Europe/Ljubljana",
    "SJ": "Arctic/Longyearbyen",
    "SK": "Europe/Bratislava",
    "SL": "Africa/Freetown",
    "SM": "Europe/San_Marino",
    "SN": "Africa/Dakar",
    "SO": "Africa/Mogadishu",
    "SR": "America/Paramaribo",
    "SS": "Africa/Juba",
    "ST": "Africa/Sao_Tome",
    "SV": "America/El_Salvador",
    "SX": "America/Lower_Princes",
    "SY": "Asia/Damascus",
    "SZ": "Africa/Mbabane",
    "TC": "America/Grand_Turk",
    "TD": "Africa/Ndjamena",
    "TF": "Indian/Kerguelen",
    "TG": "Africa/Lome",
    "TH": "Asia/Bangkok",
    "TJ": "Asia/Dushanbe",
    "TK": "Pacific/Fakaofo",
    "TL": "Asia/Dili",
    "TM": "Asia/Ashgabat",
    "TN": "Africa/Tunis",
    "TO": "Pacific/Tongatapu",
    "TR": "Europe/Istanbul",
    "TT": "America/Port_of_Spain",
    "TV": "Pacific/Funafuti",
    "TW": "Asia/Taipei",
    "TZ": "Africa/Dar_es_Salaam",
    "UA": "Europe/Kyiv",
    "UG": "Africa/Kampala",
    "UK": "Europe/London",
    "UM": "Pacific/Wake",
    "US": "America/New_York",
    "UY": "America/Montevideo",
    "UZ": "Asia/Tashkent",
    "VA": "Europe/Vatican",
    "VC": "America/St_Vincent",
    "VE": "America/Caracas",
    "VG": "America/Tortola",
    "VI": "America/St_Thomas",
    "VN": "Asia/Ho_Chi_Minh",
    "VU": "Pacific/Efate",
    "WF": "Pacific/Wallis",
    "WS": "Pacific/Apia",
    "XK": "Europe/Belgrade",
    "YE": "Asia/Aden",
    "YT": "Indian/Mayotte",
    "ZA": "Africa/Johannesburg",
    "ZM": "Africa/Lusaka",
    "ZW": "Africa/Harare",
}

#: Offered first in the picker. The rest of the canonical zones follow,
#: grouped by continent.
COMMON_TIMEZONES = (
    "UTC",
    "Europe/London",
    "Europe/Dublin",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Amsterdam",
    "Europe/Stockholm",
    "Europe/Helsinki",
    "Europe/Rome",
    "Europe/Madrid",
    "Europe/Warsaw",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "America/Sao_Paulo",
    "America/Mexico_City",
    "Australia/Sydney",
    "Australia/Melbourne",
    "Pacific/Auckland",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Asia/Hong_Kong",
    "Asia/Kolkata",
    "Asia/Dubai",
)

_SKIP_PREFIXES = (
    "Etc/",
    "SystemV/",
    "US/",
    "Canada/",
    "Brazil/",
    "Mexico/",
    "Chile/",
    "posix/",
    "right/",
)


def is_valid_timezone(name: str | None) -> bool:
    """True if ``name`` is an IANA zone this process can activate."""
    return bool(name) and name in _available_timezones()


@cache
def _available_timezones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def timezone_for_country(code: str | None) -> str:
    """Representative IANA zone for an ISO country code, or empty."""
    if not code:
        return ""
    mapped = COUNTRY_TIMEZONES.get(code.strip().upper(), "")
    return mapped if is_valid_timezone(mapped) else ""


def detect_timezone(request) -> str:
    """Guess a zone from the request, without reading the profile.

    Prefers the browser's own zone (cookie) over IP-derived country, because
    a US visitor in California should not be pinned to New York.
    """
    if request is None:
        return ""
    cookies = getattr(request, "COOKIES", None) or {}
    # encodeURIComponent encodes / as %2F; Django's cookie parser leaves that
    # encoded, so unquote before validating. Harmless for a raw IANA name.
    from_cookie = unquote(cookies.get(COOKIE_NAME, "") or "")
    if is_valid_timezone(from_cookie):
        return from_cookie

    meta = getattr(request, "META", None) or {}
    for header in _TIMEZONE_HEADERS:
        value = (meta.get(header) or "").strip()
        if is_valid_timezone(value):
            return value

    for header in _COUNTRY_HEADERS:
        country = (meta.get(header) or "").strip().upper()
        if country in _UNUSABLE_COUNTRIES:
            continue
        zone = timezone_for_country(country)
        if zone:
            return zone
    return ""


def stored_timezone(user) -> str:
    """The timezone saved on this user's profile, or empty."""
    if user is None or not getattr(user, "is_authenticated", False):
        return ""
    from gyrinx.accounts.models import UserProfile

    try:
        tzname = user.profile.timezone
    except UserProfile.DoesNotExist:
        return ""
    return tzname if is_valid_timezone(tzname) else ""


def persist_timezone(user, tzname: str) -> None:
    """Write ``tzname`` onto the profile if it is still blank.

    Uses ``QuerySet.update`` so an automatic guess does not write a
    history row on every first visit.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return
    if not is_valid_timezone(tzname):
        return
    from gyrinx.accounts.models import UserProfile

    updated = UserProfile.objects.filter(user_id=user.pk, timezone="").update(
        timezone=tzname
    )
    if updated:
        return
    UserProfile.objects.get_or_create(user=user, defaults={"timezone": tzname})


def remember_timezone(request, tzname: str) -> None:
    """Keep the resolved zone in the session so later requests skip a query."""
    session = getattr(request, "session", None)
    if session is None:
        return
    session[SESSION_TZ_KEY] = tzname
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        session[SESSION_TZ_USER_KEY] = user.pk


def resolve_request_timezone(request) -> str:
    """Zone to activate for this request, persisting a guess when we can.

    Impersonation uses the target's saved zone (or a fresh guess) but does
    not write it onto either account or into the admin's session.
    """
    user = getattr(request, "user", None)
    impersonating = getattr(request, "is_impersonating", False)
    authenticated = bool(user is not None and getattr(user, "is_authenticated", False))

    if authenticated and not impersonating:
        session = getattr(request, "session", None) or {}
        if session.get(SESSION_TZ_USER_KEY) == user.pk:
            cached = session.get(SESSION_TZ_KEY) or ""
            if is_valid_timezone(cached):
                return cached
        saved = stored_timezone(user)
        if saved:
            remember_timezone(request, saved)
            return saved
        guessed = detect_timezone(request)
        if guessed:
            persist_timezone(user, guessed)
            remember_timezone(request, guessed)
            return guessed
        return ""

    if authenticated and impersonating:
        saved = stored_timezone(user)
        return saved or detect_timezone(request)

    return detect_timezone(request)


def timezone_label(name: str) -> str:
    """``Europe/London (UTC+01:00)`` using the current offset in that zone."""
    if not is_valid_timezone(name):
        return name
    now = datetime.now(zoneinfo.ZoneInfo(name))
    offset = now.strftime("%z")
    if len(offset) == 5:
        pretty = f"UTC{offset[:3]}:{offset[3:]}"
    else:
        pretty = "UTC"
    return f"{name.replace('_', ' ')} ({pretty})"


def timezone_choices() -> list[tuple[str, list[tuple[str, str]] | str]]:
    """Grouped ``<select>`` choices: common zones, then the rest by region."""
    common = [("UTC", timezone_label("UTC"))]
    seen = {"UTC"}
    for name in COMMON_TIMEZONES:
        if name == "UTC" or not is_valid_timezone(name):
            continue
        common.append((name, timezone_label(name)))
        seen.add(name)

    grouped: dict[str, list[tuple[str, str]]] = {}
    for name in sorted(_canonical_zones()):
        if name in seen:
            continue
        region = name.split("/", 1)[0]
        grouped.setdefault(region, []).append((name, timezone_label(name)))

    choices: list[tuple[str, list[tuple[str, str]] | str]] = [("Common", common)]
    for region in sorted(grouped):
        choices.append((region, grouped[region]))
    return choices


def _canonical_zones() -> list[str]:
    zones = []
    for name in _available_timezones():
        if name == "UTC":
            continue
        if "/" not in name:
            continue
        if name.startswith(_SKIP_PREFIXES):
            continue
        zones.append(name)
    return zones
