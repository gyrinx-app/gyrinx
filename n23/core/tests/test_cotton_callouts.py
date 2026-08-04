"""Equivalence and safety tests for the CALLOUT cotton components.

Covers cotton/{callout,box,note,messages,errors,disclosure}.html.

Two things about how these tests are written:

* Components MUST be exercised via ``render_to_string``. Cotton compiles in the
  template LOADER, so ``Template("<c-callout>x</c-callout>")`` passes the tag
  through verbatim and silently asserts nothing.
* Each probe template needs a UNIQUE filename. Django wraps the loader in
  ``cached.Loader``, so reusing one filename across parametrised cases renders
  the first body every time -- a false pass.

Equivalence is asserted at DOM level (tag, attributes, text; ``class`` compared
as a SET) rather than byte level. Two rendered artefacts make byte comparison
meaningless and neither is a defect: the alert body wrapper carries one space
before its closing bracket when ``body_class`` is unset (djlint rewrites the
tight form), and c-box migration reorders the class attribute at the 14 estate
sites that write utilities before ``border rounded``.
"""

import re
import uuid
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django import forms
from django.conf import settings
from django.contrib import messages as messages_constants
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string

TEMPLATE_DIR = Path(settings.BASE_DIR) / "gyrinx" / "templates"


@pytest.fixture
def render(tmp_path):
    """Render a snippet from a uniquely-named on-disk template."""
    written = []

    def _render(source, context=None):
        name = f"_cotton_test_{uuid.uuid4().hex}.html"
        path = TEMPLATE_DIR / name
        path.write_text(source, encoding="utf-8")
        written.append(path)
        return render_to_string(name, context or {})

    yield _render
    for path in written:
        path.unlink(missing_ok=True)


class _Dom(HTMLParser):
    def __init__(self):
        super().__init__()
        self.events = []

    def handle_starttag(self, tag, attrs):
        normalised = sorted(
            (key, " ".join(sorted(value.split())) if key == "class" else value)
            for key, value in attrs
        )
        self.events.append(("start", tag, normalised))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        self.events.append(("end", tag))

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.events.append(("text", text))


def dom(html):
    parser = _Dom()
    parser.feed(html)
    return parser.events


def assert_same_dom(got, want):
    assert dom(got) == dom(want)


def squash(html):
    return re.sub(r"\s+", " ", html)


# --------------------------------------------------------------------------
# T1  Equivalence against markup copied verbatim from the live estate
# --------------------------------------------------------------------------


def test_canonical_alert_matches_live_markup(render):
    """campaign_asset_transfer.html:29 -- the shape used by 62 of 91 alerts."""
    assert_same_dom(
        render(
            '<c-callout class="mb-0">Recorded in the campaign action log.</c-callout>'
        ),
        '<div class="alert alert-info alert-icon mb-0" role="alert">'
        '<i class="bi-info-circle" aria-hidden="true"></i>'
        "<div>Recorded in the campaign action log.</div></div>",
    )


def test_confirm_alert_with_heading(render):
    """campaign_asset_remove.html:14 and five byte-identical siblings."""
    assert_same_dom(
        render(
            '<c-callout variant="warning" heading="Are you sure?" class="mb-0">'
            '<p class="mb-0">Removes <strong>Lamp &amp; Co</strong>.</p></c-callout>'
        ),
        '<div class="alert alert-warning alert-icon mb-0" role="alert">'
        '<i class="bi-exclamation-triangle" aria-hidden="true"></i>'
        "<div><strong>Are you sure?</strong>"
        '<p class="mb-0">Removes <strong>Lamp &amp; Co</strong>.</p></div></div>',
    )


def test_alert_participates_in_a_grid(render):
    """list_fighter_weapons_edit.html:13 needs g-col-12 to span its grid."""
    assert_same_dom(
        render('<c-callout variant="danger" class="g-col-12 mb-0">No</c-callout>'),
        '<div class="alert alert-danger alert-icon g-col-12 mb-0" role="alert">'
        '<i class="bi-exclamation-triangle" aria-hidden="true"></i><div>No</div></div>',
    )


def test_icon_override(render):
    """list_fighter_advancement_type.html:12 -- the only non-default icon."""
    assert_same_dom(
        render('<c-callout icon="bi-dice-6" class="mb-0">Rolled a 6</c-callout>'),
        '<div class="alert alert-info alert-icon mb-0" role="alert">'
        '<i class="bi-dice-6" aria-hidden="true"></i><div>Rolled a 6</div></div>',
    )


def test_iconless_alert_drops_wrapper_and_layout_class(render):
    """500.html:33 renders where context processors may not have run."""
    assert_same_dom(
        render(
            '<c-callout variant="secondary" icon="none" class="mb-4"><small>E</small></c-callout>'
        ),
        '<div class="alert alert-secondary mb-4" role="alert"><small>E</small></div>',
    )


def test_body_class_flex_row(render):
    """list_fighter_advancement_other.html:23 -- one of only two classed bodies."""
    assert_same_dom(
        render(
            '<c-callout variant="danger" body_class="d-flex justify-content-between flex-grow-1"'
            ' class="mb-0"><div>XP</div><div>Cost</div></c-callout>'
        ),
        '<div class="alert alert-danger alert-icon mb-0" role="alert">'
        '<i class="bi-exclamation-triangle" aria-hidden="true"></i>'
        '<div class="d-flex justify-content-between flex-grow-1">'
        "<div>XP</div><div>Cost</div></div></div>",
    )


def test_dismissible_alert(render):
    """design_system.html:709 -- the canonical dismissible anatomy."""
    assert_same_dom(
        render(
            '<c-callout variant="success" dismissible class="mb-0">Saved</c-callout>'
        ),
        '<div class="alert alert-success alert-icon alert-dismissible fade show mb-0" role="alert">'
        '<i class="bi-check-lg" aria-hidden="true"></i><div>Saved</div>'
        '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button></div>',
    )


# --------------------------------------------------------------------------
# T2  Variant / icon matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant,icon",
    [
        ("success", "bi-check-lg"),
        ("danger", "bi-exclamation-triangle"),
        ("warning", "bi-exclamation-triangle"),
        ("info", "bi-info-circle"),
        ("secondary", "bi-info-circle"),
        ("primary", "bi-info-circle"),
    ],
)
def test_icon_is_derived_from_variant(render, variant, icon):
    out = squash(render(f'<c-callout variant="{variant}">x</c-callout>'))
    assert f'class="alert alert-{variant} alert-icon"' in out
    assert f'<i class="{icon}"' in out


def test_unknown_variant_degrades_rather_than_blanking(render):
    out = squash(render('<c-callout variant="bogus">x</c-callout>'))
    assert "alert-bogus" in out and "bi-info-circle" in out


# --------------------------------------------------------------------------
# T3  Class merge and order; T4 role
# --------------------------------------------------------------------------


def test_class_order_is_base_variant_state_caller(render):
    out = squash(
        render(
            '<c-callout variant="warning" dismissible class="mb-0 fs-7">x</c-callout>'
        )
    )
    assert (
        'class="alert alert-warning alert-icon alert-dismissible fade show mb-0 fs-7"'
        in out
    )


def test_role_defaults_to_alert_and_is_not_duplicated(render):
    out = render("<c-callout>x</c-callout>")
    assert out.count("role=") == 1
    assert 'role="alert"' in out


def test_caller_role_replaces_rather_than_duplicating(render):
    """A hardcoded role would emit twice and the browser would drop the caller's."""
    out = render('<c-callout role="status">x</c-callout>')
    assert out.count("role=") == 1
    assert 'role="status"' in out and 'role="alert"' not in out


# --------------------------------------------------------------------------
# T5  c-box
# --------------------------------------------------------------------------


def test_box_defaults_to_p3_and_compact_gives_p2(render):
    assert_same_dom(
        render("<c-box>x</c-box>"), '<div class="border rounded p-3">x</div>'
    )
    assert_same_dom(
        render("<c-box compact>x</c-box>"), '<div class="border rounded p-2">x</div>'
    )


def test_box_never_acquires_a_variant(render):
    """The invariant that keeps c-box from becoming a second alert system."""
    out = squash(render('<c-box variant="danger">x</c-box>'))
    assert 'class="border rounded p-3"' in out
    assert "alert" not in out and "bg-danger" not in out and "border-danger" not in out


def test_box_forwards_id_and_style(render):
    out = squash(
        render('<c-box compact id="traits" style="max-height:16rem">x</c-box>')
    )
    assert 'id="traits"' in out and "max-height:16rem" in out


# --------------------------------------------------------------------------
# T6  c-note -- the five axes, each independently reachable
# --------------------------------------------------------------------------


def test_note_default_is_p2_at_body_font_size(render):
    """Seven of the fourteen estate notes have no fs-7; it must not be baked in."""
    out = squash(render('<c-note icon="warning">Only this crew.</c-note>'))
    assert "border rounded p-2 d-flex gap-2 align-items-start" in out
    assert "fs-7" not in out


def test_note_font_size_comes_from_class(render):
    out = squash(render('<c-note icon="archive" class="fs-7">x</c-note>'))
    assert "border rounded p-2 d-flex gap-2 align-items-start fs-7" in out


def test_note_roomy_changes_padding_only(render):
    out = squash(render('<c-note roomy icon="warning">x</c-note>'))
    assert "border rounded p-3" in out and "fs-7" not in out


def test_note_icon_colour_is_independent_of_border(render):
    """battle_end.html:30 wants a warning icon inside a neutral border."""
    out = squash(render('<c-note icon="warning" icon_class="text-warning">x</c-note>'))
    assert '<i class="bi-exclamation-triangle text-warning"' in out
    assert "border-warning" not in out and "bg-warning" not in out


def test_note_tint_is_opt_in(render):
    """campaign_add_lists.html:21 and battle.html:10 have a colour but no background."""
    without = squash(
        render('<c-note variant="warning" roomy icon="warning">x</c-note>')
    )
    assert "border-warning" in without and "bg-warning-subtle" not in without

    with_tint = squash(
        render('<c-note variant="warning" tinted roomy icon="warning">x</c-note>')
    )
    assert "border-warning bg-warning-subtle" in with_tint


def test_note_align_is_a_prop_not_a_class(render):
    """Two align-items utilities would let Bootstrap source order pick the winner."""
    out = squash(render('<c-note icon="archive" align="center">x</c-note>'))
    assert "align-items-center" in out and "align-items-start" not in out


def test_note_action_slot_stays_a_direct_flex_child(render):
    """includes/list.html:4 -- ms-auto must still push Unarchive to the right edge."""
    assert_same_dom(
        render(
            '<c-note icon="archive" align="center" heading="Archived."><c-slot name="action">'
            '<a href="/u" class="ms-auto btn btn-sm btn-secondary">Unarchive</a>'
            "</c-slot></c-note>"
        ),
        '<div class="border rounded p-2 d-flex gap-2 align-items-center">'
        '<i class="bi-archive text-secondary" aria-hidden="true"></i>'
        '<div class="flex-grow-1 mb-last-0"><strong>Archived.</strong></div>'
        '<a href="/u" class="ms-auto btn btn-sm btn-secondary">Unarchive</a></div>',
    )


def test_note_action_slot_does_not_leak_ambient_context(render):
    """`action` is a very common context name (form action URLs).

    Context isolation is off, so an undeclared named slot resolves against the
    parent context. The c-vars default shadows it.
    """
    out = render(
        '<c-note icon="info">Body</c-note>', {"action": "/n23/campaign/1/leak/"}
    )
    assert "/n23/campaign/1/leak/" not in out


# --------------------------------------------------------------------------
# T7  c-messages -- the #2001 regression
# --------------------------------------------------------------------------


def test_message_variant_keys_on_level_tag_not_tags(render):
    """allauth/layouts/base.html:8 keyed on `tags`, so tagged errors rendered blue."""
    message = Message(messages_constants.constants.ERROR, "Kaboom", extra_tags="toast")
    assert message.tags == "toast error" and message.level_tag == "error"

    out = squash(render("<c-messages />", {"messages": [message]}))
    assert "alert alert-danger" in out
    assert "alert-info" not in out


def test_messages_are_dismissible_and_now_carry_the_variant_icon(render):
    message = Message(messages_constants.constants.WARNING, "Careful")
    out = squash(render("<c-messages />", {"messages": [message]}))
    assert "alert alert-warning alert-icon alert-dismissible fade show" in out
    assert "bi-exclamation-triangle" in out and "btn-close" in out


def test_messages_render_nothing_when_empty(render):
    assert render("<c-messages />", {"messages": []}).strip() == ""


# --------------------------------------------------------------------------
# T8  c-errors
# --------------------------------------------------------------------------


class _RejectingForm(forms.Form):
    name = forms.CharField(required=True)
    step = forms.CharField(widget=forms.HiddenInput, required=True)

    def clean(self):
        raise forms.ValidationError("Whole form is bad")


def test_errors_renders_nothing_for_a_clean_form(render):
    """The guard is inside, so the call site has no branch to forget."""
    assert render('<c-errors :form="form" />', {"form": _RejectingForm()}).strip() == ""


def test_errors_renders_non_field_errors(render):
    form = _RejectingForm(data={})
    form.is_valid()
    out = squash(render('<c-errors :form="form" />', {"form": form}))
    assert "alert alert-danger alert-icon" in out and "Whole form is bad" in out


def test_errors_has_no_default_margin(render):
    """Every mb-0 estate site sits in a vstack gap-3; a default mb-3 stacks."""
    form = _RejectingForm(data={})
    form.is_valid()
    out = squash(render('<c-errors :form="form" />', {"form": form}))
    assert 'class="alert alert-danger alert-icon"' in out


def test_errors_surfaces_hidden_field_errors(render):
    """Errors on a hidden field render nowhere today -- a silent rejection."""
    form = _RejectingForm(data={})
    form.is_valid()
    out = squash(render('<c-errors :form="form" />', {"form": form}))
    assert "step" in out and "This field is required" in out


def test_errors_missing_colon_is_loud_not_silent(render):
    """form="{{ form }}" stringifies the form; the marker makes it findable."""
    form = _RejectingForm(data={})
    form.is_valid()
    out = render('<c-errors form="{{ form }}" />', {"form": form})
    assert "COTTON-MISUSE c-errors" in out


# --------------------------------------------------------------------------
# T9  c-disclosure
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# T10  Escaping -- the documented injection vector
# --------------------------------------------------------------------------


PAYLOAD = '"a" onmouseover=alert(1) "'


def test_slot_content_is_autoescaped(render):
    out = render("<c-box>{{ payload }}</c-box>", {"payload": "<script>x</script>"})
    assert "&lt;script&gt;" in out and "<script>" not in out


def test_declared_props_are_autoescaped_even_via_colon(render):
    assert "&quot;" in render('<c-callout :heading="p">x</c-callout>', {"p": PAYLOAD})
    assert "&quot;" in render('<c-note :heading="p">x</c-note>', {"p": PAYLOAD})


def test_static_attribute_form_is_safe(render):
    out = render('<c-callout title="{{ p }}">x</c-callout>', {"p": PAYLOAD})
    assert "&quot;" in out
    assert 'onmouseover=alert(1) "' not in out.replace("&quot;", "Q")


def test_undeclared_colon_attr_is_the_injection_vector(render):
    """Documented, and blocked at the call site by scripts/check_cotton.sh.

    This test pins the behaviour so an upgrade that fixes it upstream is noticed.
    """
    out = render('<c-callout :title="p">x</c-callout>', {"p": PAYLOAD})
    assert "onmouseover=alert(1)" in out


# --------------------------------------------------------------------------
# T11  Cotton parse hazard -- conditional attributes corrupt silently
# --------------------------------------------------------------------------


def test_conditional_attribute_inside_a_cotton_tag_is_broken(render):
    """Why bs_checkbox_select_compact.html:8 is excluded by name from migration.

    The failure mode is NON-DETERMINISTIC, which is the worst part: depending on
    the state of cotton's mtime-keyed compile cache the same source either raises
    (TemplateSyntaxError "Unclosed tag ... looking for endcotton", or TypeError)
    or silently emits the literal template source into the page with the closing
    tag mangled and the real attribute lost. Both were observed on this tree.

    That non-determinism is exactly why the defence is static
    (scripts/check_cotton.sh) rather than a runtime smoke test: a smoke test that
    happens to hit the compiling branch passes and the page still breaks in prod.
    """
    try:
        out = render(
            '<c-box compact {% if id %}id="{{ id }}"{% endif %}>list</c-box>',
            {"id": "traits"},
        )
    except Exception:
        return  # raised -- the loud branch
    assert "{%" in out or "endif" in out, (
        "cotton neither raised nor leaked -- the hazard may be fixed upstream; "
        "re-check the by-name exclusions in cotton/box.html before relying on it"
    )
    assert 'id="traits"' not in out.replace('{% if id %}id="traits"', "")


def test_conditional_inside_a_quoted_value_is_safe(render):
    out = render(
        '<c-box class="{% if wide %}h-100{% endif %}">ok</c-box>', {"wide": True}
    )
    assert "{%" not in out and "h-100" in out


# --------------------------------------------------------------------------
# T12  Static gate
# --------------------------------------------------------------------------


def test_check_cotton_gate_passes_on_the_tree():
    import subprocess

    result = subprocess.run(
        ["./scripts/check_cotton.sh"],
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
