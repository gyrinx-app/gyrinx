"""A number field must not take "e", "E" or "+".

The browser lets a number input take scientific notation. The guard
listens on the document, so a shell that forgets the script leaves every
number field on that shell taking them. Authoring extends the n26 app
shell and inherits it from there.
"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import get_template

SCRIPT = "platform/js/number-input-characters.js"

SHELLS = (
    "core/layouts/foundation.html",
    "n26/layouts/base.html",
    "designsystem/base.html",
)


def source_of(template_name: str) -> str:
    return Path(get_template(template_name).origin.name).read_text()


def test_every_page_shell_loads_the_guard():
    for name in SHELLS:
        assert SCRIPT in source_of(name), name


def test_the_script_is_where_static_files_are_looked_for():
    assert finders.find(SCRIPT), SCRIPT
