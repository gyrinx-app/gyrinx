"""Public error text is independent of exception diagnostics."""

import pytest

from gyrinx.errors import UserFacingError


def test_public_message_excludes_chained_exception_and_diagnostic_arguments():
    try:
        try:
            raise RuntimeError("SELECT secret FROM private_table")
        except RuntimeError as cause:
            raise UserFacingError("Reload this page before saving.") from cause
    except UserFacingError as error:
        error.args = ("Internal diagnostic detail",)
        assert error.public_message == "Reload this page before saving."
        assert str(error) == "Internal diagnostic detail"
        assert str(error.__cause__) == "SELECT secret FROM private_table"


def test_exception_string_formatting_is_not_the_public_message():
    class DiagnosticError(UserFacingError):
        def __str__(self):
            return "Internal diagnostic detail"

    error = DiagnosticError("Reload this page before saving.")
    assert error.public_message == "Reload this page before saving."
    assert str(error) == "Internal diagnostic detail"


@pytest.mark.parametrize("message", [RuntimeError("secret"), None, 123])
def test_public_messages_require_explicit_text(message):
    with pytest.raises(TypeError, match="A public error message must be a string"):
        raise UserFacingError(message)


def test_unexpected_exceptions_are_not_public_errors():
    assert not isinstance(RuntimeError("secret"), UserFacingError)
