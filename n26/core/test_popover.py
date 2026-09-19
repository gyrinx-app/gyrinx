"""The local popover override keeps legacy callers while offering an owned trigger."""

from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str) -> str:
    return Template(CottonCompiler().process(source)).render(Context())


def test_owned_trigger_connects_a_real_button_to_the_dialog():
    html = render(
        '<c-ui.popover trigger_text="Contents" panel_label="On this page">'
        '<a href="#rules">Rules</a></c-ui.popover>'
    )

    document = BeautifulSoup(html, "html.parser")
    button = document.find("button", string=lambda text: text and "Contents" in text)
    dialog = document.find(attrs={"role": "dialog"})

    assert button is not None
    assert button["type"] == "button"
    assert button[":aria-expanded"] == "open"
    assert button.has_attr(":aria-controls")
    assert "rounded-button" in button.get("class", [])
    assert dialog is not None
    assert dialog["aria-label"] == "On this page"
    assert dialog["tabindex"] == "-1"
    assert dialog.has_attr("data-popover-panel")


def test_owned_trigger_focus_and_close_behaviour_is_present():
    html = render(
        '<c-ui.popover trigger_text="Help"><button>First</button></c-ui.popover>'
    )

    assert "toggle($event.detail === 0)" in html
    assert "(target || this.$refs.dialog).focus()" in html
    assert '@keydown.escape.window="doClose(true)"' in html
    assert "this.$refs.trigger.focus({ preventScroll: true })" in html
    assert "event.target.closest('a[href]')" in html
    assert "this.doClose(this.ownsTrigger)" in html


def test_owned_trigger_labels_the_panel_when_no_panel_label_is_given():
    html = render('<c-ui.popover trigger_text="Help">Details.</c-ui.popover>')
    document = BeautifulSoup(html, "html.parser")
    button = document.find("button")
    dialog = document.find(attrs={"role": "dialog"})

    assert button is not None and dialog is not None
    assert button[":id"] == "$id('popover-trigger')"
    assert dialog[":aria-labelledby"] == "$id('popover-trigger')"


def test_panel_is_constrained_to_the_viewport_and_scrolls():
    html = render('<c-ui.popover trigger_text="Help">A long panel.</c-ui.popover>')

    assert "max-w-[calc(100vw-2rem)]" in html
    assert "max-h-[calc(100vh-2rem)]" in html
    assert "overflow-y-auto" in html
    assert "overscroll-contain" in html


def test_legacy_trigger_slot_keeps_the_existing_wrapper_api():
    html = render(
        '<c-ui.popover><c-slot name="trigger"><span>Avatar</span></c-slot>'
        "Profile</c-ui.popover>"
    )

    assert "<span>Avatar</span>" in html
    assert "@click=\"mode === 'click' && toggle()\"" in html
    assert "Profile" in html
    assert "<button" not in html
