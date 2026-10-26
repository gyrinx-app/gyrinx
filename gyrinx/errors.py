"""Explicit public messages for expected failures in either edition.

Unexpected exceptions must reach Django's error handler. Do not wrap their
text in a UserFacingError: supply a sentence written for the user instead.
Views read public_message, leaving exception formatting and chained causes
for server-side diagnostics.
"""


class UserFacingError(Exception):
    """An expected failure with a message safe to show to the user."""

    def __init__(self, public_message: str):
        if not isinstance(public_message, str):
            raise TypeError("A public error message must be a string.")
        self.public_message = public_message
        super().__init__(public_message)
