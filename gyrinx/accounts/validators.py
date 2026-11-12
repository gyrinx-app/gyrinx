"""Validate the destinations an account makes public."""

import re

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email

from gyrinx.colours import GANG_COLOURS

_url = URLValidator(schemes=["http", "https"])


def social_link_href(value):
    if not isinstance(value, str) or re.search(r"[\x00-\x20\x7f]", value):
        raise ValidationError(
            "Enter a link starting with http:// or https://, or an email address."
        )
    if value.startswith("mailto:"):
        validate_email(value[7:])
        return value
    if "://" in value:
        _url(value)
        return value
    validate_email(value)
    return "mailto:" + value


def validate_social_links(values):
    if not isinstance(values, list) or len(values) > 5:
        raise ValidationError("Add up to five links or email addresses.")
    for value in values:
        social_link_href(value)


def instagram_handle(value):
    raw = value.strip()
    handle = raw.removeprefix("@")
    if raw and not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", handle):
        raise ValidationError(
            "Enter your Instagram handle using letters, numbers, periods or underscores."
        )
    return handle


def validate_profile_location(value):
    if re.search(r"[\x00-\x1f\x7f]", value):
        raise ValidationError("Enter your location on one line.")


def validate_profile_colour(value):
    if value and value not in GANG_COLOURS:
        raise ValidationError("Select a colour from the palette.")
