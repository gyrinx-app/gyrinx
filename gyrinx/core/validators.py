"""Custom validators for the core app."""

from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import ngettext_lazy


@deconstructible
class HTMLTextMaxLengthValidator:
    """
    Validator that checks the length of text content within HTML.

    Strips HTML tags and counts only the visible text characters.
    This is useful for fields that use WYSIWYG editors which store HTML,
    but where the character limit should apply to the user-visible text only.
    """

    message = ngettext_lazy(
        "Ensure this value has at most %(limit_value)d character (it has %(show_value)d).",
        "Ensure this value has at most %(limit_value)d characters (it has %(show_value)d).",
        "limit_value",
    )
    code = "max_length"

    def __init__(self, limit_value, message=None):
        self.limit_value = limit_value
        if message:
            self.message = message

    def __call__(self, value):
        if not value:
            return

        # Strip HTML tags and get plain text
        soup = BeautifulSoup(value, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        text_length = len(text)

        if text_length > self.limit_value:
            raise ValidationError(
                self.message,
                code=self.code,
                params={
                    "limit_value": self.limit_value,
                    "show_value": text_length,
                },
            )

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__)
            and self.limit_value == other.limit_value
            and self.message == other.message
            and self.code == other.code
        )
