"""Load the number-input wheel guard in every page shell."""

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
    """Register a non-passive wheel listener so preventDefault can cancel value changes."""
    found = finders.find(SCRIPT)
    assert found, f"{SCRIPT} is not where the static files are looked for"
    source = Path(found).read_text()
    assert "{ capture: true, passive: false }" in source
    assert "preventDefault()" in source
    assert 'target.type !== "number"' in source
    assert "document.activeElement !== target" in source
    assert "event.ctrlKey" in source
