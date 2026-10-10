"""A focused number field must not take the wheel.

Chrome changes the value when the pointer wheels over a focused
``input type=number``. The guard listens on the document, so a shell
that forgets the script leaves every number field on that shell exposed.
Authoring extends the n26 app shell and inherits it from there.
"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import get_template

SCRIPT = "platform/js/number-input-wheel.js"

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


def test_the_listener_can_cancel_the_wheel():
    """A passive listener cannot cancel the event, and on Chrome the
    listener's existence is what opts number fields into changing."""
    found = finders.find(SCRIPT)
    assert found, f"{SCRIPT} is not where the static files are looked for"
    source = Path(found).read_text()
    assert "{ capture: true, passive: false }" in source
    assert "preventDefault()" in source
    assert 'target.type !== "number"' in source
    assert "document.activeElement !== target" in source
    assert "event.ctrlKey" in source
