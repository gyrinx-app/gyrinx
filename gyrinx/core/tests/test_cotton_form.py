"""Tests for the cotton form family (gyrinx/templates/cotton/form/).

TWO TRAPS, both of which fail SILENTLY rather than erroring, and both of which
these tests are shaped to avoid:

1. django-cotton compiles `<c-...>` tags in the template LOADER, so
   `Template("<c-form.field />")` and `engines[...].from_string(...)` emit the
   tag as literal text. Components can only be exercised from disk.

2. `render_to_string("cotton/form/field.html", {"field": f})` does NOT test the
   component. It renders the file as an ordinary template, and the
   `<c-vars field="" />` defaults SHADOW the passed context, so you get an empty
   wrapper and a green-looking test that proves nothing.

`component()` writes a throwaway host template into a directory that is already
on the engine's search path, so every test goes through the real call path.
"""

import re
import uuid
from pathlib import Path

import pytest
from django import forms
from django.template import TemplateSyntaxError
from django.template.loader import render_to_string
from django.test import override_settings

WS = re.compile(r"\s+")

# Host templates live inside gyrinx/templates/, which is already the first
# entry in TEMPLATES["DIRS"].
#
# Do NOT be tempted to use a tempdir plus `engine.dirs.append(...)`. Two
# separate things defeat it, and both fail in ways that look like a component
# bug rather than a harness bug:
#   * Django rebuilds `django.template.engines` on `setting_changed`, so any
#     test anywhere in the suite that uses `override_settings` drops the
#     appended dir -> TemplateDoesNotExist;
#   * cotton's loader resolves its own directory list once, so a dir appended
#     later is invisible to IT while still visible to the plain filesystem
#     loader -> the `<c-...>` tags come back as raw, uncompiled TEXT and the
#     assertions fail with no error at all.
_HOST_DIR = Path(__file__).resolve().parents[2] / "templates" / "_cotton_test_host"


def component(markup, context=None, request=None):
    """Render `markup` (which may contain <c-...> tags) through the loader.

    Each call cleans up only the file it created. Do NOT add a session-scoped
    fixture that empties the directory: under pytest-xdist the first worker to
    finish would delete host templates the other workers are still rendering,
    producing TemplateDoesNotExist in an unrelated test.
    """
    _HOST_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.html"
    path = Path(_HOST_DIR, name)
    path.write_text(markup)
    try:
        return render_to_string(
            f"_cotton_test_host/{name}", context or {}, request=request
        )
    finally:
        path.unlink(missing_ok=True)


def norm(html):
    """Collapse whitespace.

    Cotton leaves a space where `{{ attrs }}` is empty and djlint re-wraps long
    attribute lists, so equivalence is asserted on whitespace-normalised HTML.
    """
    return WS.sub(" ", html).replace(" >", ">").replace("> <", "><").strip()


class DemoForm(forms.Form):
    name = forms.CharField(
        label="Fighter name",
        help_text="Give them a name.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    refund = forms.BooleanField(
        label="Apply refund",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    picks = forms.MultipleChoiceField(
        label="Picks",
        choices=[("a", "A"), ("b", "B")],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    style = forms.ChoiceField(
        label="Style",
        choices=[("x", "X"), ("y", "Y")],
        required=False,
        widget=forms.RadioSelect,
    )


# --------------------------------------------------------------------------
# Equivalence with the markup being replaced
# --------------------------------------------------------------------------


def test_field_matches_legacy_include():
    """<c-form.field> reproduces core/includes/form_field.html (36 sites).

    The single intended difference is the `_helptext` id: Django's own
    build_widget_attrs already points the widget's aria-describedby at it, so
    the legacy include ships a DANGLING aria-describedby at all 36 sites.
    """
    field = DemoForm()["name"]
    legacy = render_to_string("core/includes/form_field.html", {"field": field})
    new = component('<c-form.field :field="field" />', {"field": field})
    assert norm(legacy).replace(
        '<small class="form-text text-secondary">',
        '<small class="form-text text-secondary" id="id_name_helptext">',
    ) == norm(new)


def test_whole_form_render_goes_through_the_component():
    """The django/forms/field.html override moves all 31 `{{ form }}` sites."""
    whole = component("{{ form }}", {"form": DemoForm()})
    assert '<small class="form-text text-secondary"' in whole
    assert 'id="id_name_helptext"' in whole
    assert 'class="form-check"' in whole
    assert "<fieldset" in whole
    # Not the old override's markup.
    assert "helptext form-text" not in whole


def test_stepper_matches_legacy_include():
    """<c-form.stepper> reproduces core/includes/number_stepper.html (4 sites).

    The one intended difference is `aria-hidden="true"` on the decorative
    chevron icons, which the include omits.
    """
    field = DemoForm()["name"]
    legacy = render_to_string(
        "core/includes/number_stepper.html", {"field": field, "label": "credits"}
    )
    new = component(
        '<c-form.stepper :field="field" label="credits" />', {"field": field}
    )
    assert norm(legacy) == norm(new).replace(' aria-hidden="true"></i>', "></i>")


# --------------------------------------------------------------------------
# The variant matrix: branch selection is DERIVED, never a prop
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expect,forbid",
    [
        ("name", '<small class="form-text text-secondary"', 'class="form-check"'),
        ("refund", 'class="form-check"', "<fieldset"),
        ("picks", "<fieldset", 'class="form-check"'),
        ("style", "<fieldset", 'class="form-check"'),
    ],
)
def test_branches(name, expect, forbid):
    out = component('<c-form.field :field="field" />', {"field": DemoForm()[name]})
    assert expect in out
    assert forbid not in out


def test_multi_checkbox_is_a_fieldset_not_a_checkbox():
    """CheckboxSelectMultiple reports input_type == 'checkbox'.

    If use_fieldset is not tested FIRST, a multi-checkbox renders as a single
    form-check and the whole option list collapses.
    """
    out = component('<c-form.field :field="field" />', {"field": DemoForm()["picks"]})
    assert out.count('class="form-check"') == 0
    assert "<legend" in out


def test_checkbox_label_is_a_direct_child_of_form_check():
    """styles.scss `.form-check > label` is a DIRECT-CHILD selector.

    Any wrapper between them silently drops the label styling, with no test
    failure anywhere else.
    """
    out = norm(
        component('<c-form.field :field="field" />', {"field": DemoForm()["refund"]})
    )
    assert '<div class="form-check"><input' in out
    assert '<label class="form-check-label"' in out


def test_legend_carries_the_bootstrap_reset():
    """Bootstrap resets <legend> to float:left; width:100%; ~20px.

    Without float-none w-auto a legend renders as a full-width heading.
    """
    out = component('<c-form.field :field="field" />', {"field": DemoForm()["picks"]})
    assert "float-none w-auto" in out


# --------------------------------------------------------------------------
# #2001: errors are unconditional and unsuppressible
# --------------------------------------------------------------------------


def test_errors_always_rendered():
    form = DemoForm(data={"name": ""})
    assert not form.is_valid()
    out = component('<c-form.field :field="field" />', {"field": form["name"]})
    assert 'class="invalid-feedback d-block"' in out
    assert "This field is required." in out


def test_all_errors_rendered_not_just_the_first():
    """The 11 `{{ f.errors.0 }}` sites hide the 2nd+ error. This cannot."""

    class TwoErrors(forms.Form):
        x = forms.CharField()

        def clean_x(self):
            raise forms.ValidationError(["first problem", "second problem"])

    form = TwoErrors(data={"x": "v"})
    form.is_valid()
    out = component('<c-form.field :field="field" />', {"field": form["x"]})
    assert "first problem" in out
    assert "second problem" in out


def test_no_prop_can_suppress_errors():
    """Every call shape still renders the error block."""
    form = DemoForm(data={"name": ""})
    form.is_valid()
    for markup in [
        '<c-form.field :field="field" />',
        '<c-form.field :field="field" label="Renamed" />',
        '<c-form.field :field="field" class="col-6" />',
        '<c-form.field :field="field" id="x" hidden />',
    ]:
        assert "invalid-feedback d-block" in component(markup, {"field": form["name"]})


def test_cell_renders_every_error():
    form = DemoForm(data={"name": ""})
    form.is_valid()
    out = component(
        '<c-form.cell :field="field" label="Name" />', {"field": form["name"]}
    )
    assert 'class="text-danger fs-7"' in out
    assert "This field is required." in out


# --------------------------------------------------------------------------
# The label override keeps ONE code path
# --------------------------------------------------------------------------


def test_label_override_keeps_for_and_carries_form_label():
    """One label anatomy, everywhere: `form-label`, a real `for`, NO colon.

    This is the normalisation decision the family makes about label copy. It
    lets the 101 hand-rolled `<label class="form-label" for=…>{{ f.label }}</label>`
    sites migrate byte-identically, and it applies equally to the 30
    `{{ form }}` pages through the django/forms/field.html delegation, so the
    two renderings cannot drift apart again.
    """
    out = component(
        '<c-form.field :field="field" label="XP Spend" />',
        {"field": DemoForm()["name"]},
    )
    assert '<label class="form-label" for="id_name">XP Spend</label>' in norm(out)
    assert "XP Spend:" not in out


def test_label_never_carries_a_colon_suffix_even_when_the_form_sets_one():
    class SuffixForm(forms.Form):
        name = forms.CharField(label="Name")

    out = component(
        '<c-form.field :field="field" />',
        {"field": SuffixForm(label_suffix=":")["name"]},
    )
    assert "Name:" not in out
    assert ">Name</label>" in norm(out)


def test_label_override_is_autoescaped():
    out = component(
        '<c-form.field :field="field" label="{{ evil }}" />',
        {"field": DemoForm()["name"], "evil": "<script>alert(1)</script>"},
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_checkbox_label_has_no_colon_suffix():
    """Matches Django's own field template and the 49 form-check-label sites."""
    out = component('<c-form.field :field="field" />', {"field": DemoForm()["refund"]})
    assert "Apply refund<" in norm(out).replace("</label>", "<")
    assert "Apply refund:" not in out


# --------------------------------------------------------------------------
# Attribute forwarding and class handling
# --------------------------------------------------------------------------


def test_class_lands_on_the_wrapper_without_duplicating_the_attribute():
    out = component(
        '<c-form.field :field="field" class="col-6 col-md-3" />',
        {"field": DemoForm()["name"]},
    )
    assert '<div class="col-6 col-md-3"' in norm(out)
    assert out.count("class=") == out.count('class="')


def test_no_empty_class_attribute_when_class_omitted():
    out = component('<c-form.field :field="field" />', {"field": DemoForm()["name"]})
    assert 'class=""' not in out


def test_checkbox_class_appends_to_form_check():
    out = component(
        '<c-form.field :field="field" class="mt-3" />', {"field": DemoForm()["refund"]}
    )
    assert '<div class="form-check mt-3"' in norm(out)


def test_arbitrary_attributes_pass_through_to_the_wrapper():
    out = component(
        '<c-form.field :field="field" id="wrap" data-bs-toggle="collapse" hidden />',
        {"field": DemoForm()["name"]},
    )
    assert 'id="wrap"' in out
    assert 'data-bs-toggle="collapse"' in out
    assert "hidden" in out


def test_actions_forwards_name_and_value_to_the_button():
    out = component('<c-form.actions submit="Save" name="op" value="go" />')
    assert 'name="op"' in out
    assert 'value="go"' in out
    # c-vars props must NOT leak into the HTML.
    assert "intent=" not in out
    assert "cancel_text=" not in out


# --------------------------------------------------------------------------
# Intent -> colour table
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent,expected",
    [
        ("save", "btn-success"),
        ("create", "btn-success"),
        ("confirm", "btn-success"),
        ("apply", "btn-success"),
        ("delete", "btn-danger"),
        ("archive", "btn-danger"),
        ("remove", "btn-danger"),
        ("sell", "btn-danger"),
        ("next", "btn-primary"),
        ("continue", "btn-primary"),
        ("search", "btn-primary"),
        ("filter", "btn-primary"),
        ("capture", "btn-warning"),
        ("discard", "btn-danger"),
        ("destroy", "btn-danger"),
        ("reset", "btn-danger"),
        ("clear", "btn-danger"),
        ("revert", "btn-danger"),
        ("kill", "btn-danger"),
        ("Delete", "btn-danger"),  # case-insensitive: a typo must not go green
        ("restore", "btn-success"),
        ("secondary", "btn-secondary"),
    ],
)
def test_actions_intent_colour(intent, expected):
    out = component(f'<c-form.actions intent="{intent}" submit="Go" />')
    assert expected in out


@override_settings(COTTON_STRICT_COMPONENTS=False)
def test_unknown_intent_degrades_to_secondary_not_success_in_production():
    out = component('<c-form.actions intent="nonsense" submit="Go" />')
    assert "btn-secondary" in out
    assert "btn-success" not in out


def test_actions_icon_prop_covers_the_69_icon_submit_buttons():
    out = component(
        '<c-form.actions intent="capture" icon="person-lock" submit="Mark as Captured" />'
    )
    assert '<i class="bi-person-lock me-1" aria-hidden="true"></i>' in norm(out)
    assert "Mark as Captured" in out
    assert "btn btn-warning" in norm(out)


def test_actions_slot_overrides_submit_text():
    """For the labels that props cannot express: {% trans %}, nested spans."""
    out = component(
        '<c-form.actions intent="confirm">'
        '<span class="d-none d-md-inline">Resurrect</span>'
        "</c-form.actions>"
    )
    assert 'class="d-none d-md-inline"' in out
    assert ">Save<" not in norm(out)


def test_actions_submit_class_lands_on_the_button_not_the_row():
    out = component(
        '<c-form.actions submit="Save" submit_class="w-100" class="hstack gap-2" />'
    )
    assert 'class="btn btn-success w-100"' in norm(out)
    assert '<div class="hstack gap-2">' in norm(out)


def test_actions_after_slot_sits_between_submit_and_cancel():
    out = component(
        '<c-form.actions submit="Save" cancel="/back">'
        '<c-slot name="after"><span id="note">note</span></c-slot>'
        "</c-form.actions>"
    )
    body = norm(out)
    assert body.index("btn-success") < body.index('id="note"') < body.index("btn-link")


def test_actions_omits_cancel_when_no_url_given():
    out = component('<c-form.actions submit="Save" />')
    assert "btn-link" not in out


def test_actions_renders_cancel_when_url_given():
    out = component('<c-form.actions submit="Save" cancel="/back" />')
    assert 'href="/back"' in out
    assert "btn btn-link" in out


# --------------------------------------------------------------------------
# Slots
# --------------------------------------------------------------------------


def test_cell_slot_replaces_the_bare_widget():
    out = component(
        '<c-form.cell :field="field" label="Credits">'
        '<span id="custom">control</span>'
        "</c-form.cell>",
        {"field": DemoForm()["name"]},
    )
    assert 'id="custom"' in out
    assert '<input type="text"' not in out


def test_cell_without_slot_renders_the_widget():
    """`slot.strip` and not `{% if slot %}`.

    djlint's custom_html rule reformats `<c-x>y</c-x>` onto three lines, which
    makes a bare `{% if slot %}` permanently true for whitespace-only content.
    """
    out = component(
        '<c-form.cell :field="field" label="Credits">\n</c-form.cell>',
        {"field": DemoForm()["name"]},
    )
    assert '<input type="text"' in out


def test_cell_note_is_autoescaped():
    out = component(
        '<c-form.cell :field="field" label="Credits" note="{{ evil }}" />',
        {"field": DemoForm()["name"], "evil": "<script>x</script>"},
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_actions_before_slot_holds_hidden_inputs():
    out = component(
        '<c-form.actions submit="Delete" intent="delete">'
        '<c-slot name="before"><input type="hidden" name="archive" value="1"></c-slot>'
        "</c-form.actions>"
    )
    assert norm(out).index('name="archive"') < norm(out).index("btn-danger")


# --------------------------------------------------------------------------
# Form shells: CSRF, return_url, escaping
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Ambient / loop use — the X5 isolation hazard
# --------------------------------------------------------------------------


def test_field_from_an_enclosing_loop():
    """The 3 include sites with no `with field=` must pass `:field` explicitly."""
    out = component(
        '{% for f in form %}<c-form.field :field="f" />{% endfor %}',
        {"form": DemoForm()},
    )
    assert 'id="id_name"' in out
    assert 'class="form-check"' in out
    assert "<fieldset" in out


def test_component_does_not_read_field_from_ambient_context_and_says_so():
    """`field` is declared in c-vars, so it does NOT inherit from the page.

    That is correct (explicit props are the point) but it converts the three
    ambient-context include sites into SILENT BLANKS if they are rewritten
    mechanically. The guard turns the blank into a raise.
    """
    with pytest.raises(TemplateSyntaxError):
        component("<c-form.field />", {"field": DemoForm()["name"]})


# --------------------------------------------------------------------------
# Choices
# --------------------------------------------------------------------------


def test_choices_renders_a_real_fieldset_with_a_legend():
    out = component(
        '<c-form.choices :field="field" label="Card style" />',
        {"field": DemoForm()["style"]},
    )
    assert "<fieldset" in out
    assert "<legend" in out
    assert "Card style" in out
    assert out.count('class="form-check-label"') == 2


def test_choices_hide_legend_keeps_it_for_screen_readers():
    out = component(
        '<c-form.choices :field="field" hide_legend />', {"field": DemoForm()["style"]}
    )
    assert "visually-hidden" in out
    assert "<legend" in out


# --------------------------------------------------------------------------
# The blocker: a stringified BoundField must RAISE, not render a form that
# hides its own errors. (#2001, reintroduced by one missing colon.)
# --------------------------------------------------------------------------


BOUND_FIELD_COMPONENTS = ["form.field", "form.cell", "form.choices", "form.stepper"]


@pytest.mark.parametrize("name", BOUND_FIELD_COMPONENTS)
def test_stringified_field_raises(name):
    """`field="{{ form.name }}"` (no colon) used to render an input with NO
    label, NO help text and NO ERRORS — and return 200.

    The guard used to live inside `field_label`, which is only reached under
    `{% if field.label %}`; a stringified widget has no `.label`, so it never
    ran in the one case it existed for.
    """
    with pytest.raises(TemplateSyntaxError):
        component(
            f'<c-{name} field="{{{{ form.name }}}}" />',
            {"form": DemoForm()},
        )


@pytest.mark.parametrize("name", BOUND_FIELD_COMPONENTS)
def test_missing_field_raises(name):
    with pytest.raises(TemplateSyntaxError):
        component(f"<c-{name} />")


@override_settings(COTTON_STRICT_COMPONENTS=False)
def test_stringified_field_degrades_without_500ing_in_production():
    out = component(
        '<c-form.field field="{{ form.name }}" />',
        {"form": DemoForm()},
    )
    assert "<div>" in norm(out)


def test_static_gate_rejects_a_missing_colon():
    """scripts/check_cotton.py is the pre-commit half of the same guard."""
    import scripts.check_cotton as check  # noqa: PLC0415

    assert check.OBJECT_PROPS["form.field"] == "field"
    assert check.main() == 0


# --------------------------------------------------------------------------
# Intended, pinned differences on the 30 whole-form pages
# --------------------------------------------------------------------------


def test_checkbox_help_text_is_block_level():
    """Inside `.form-check` an inline <small> collapses onto the label line and
    loses `.form-text`'s margin-top, because Bootstrap sets no `display`.

    Live on list_new / list_edit / list_clone (`public`, `show_stash`),
    campaign_new / campaign_edit (`public`) and pack_new / pack_edit
    (`listed`) — the gang- and campaign-creation flows.
    """
    out = norm(
        component('<c-form.field :field="field" />', {"field": HelpCheckForm()["ok"]})
    )
    assert '<div class="form-text text-secondary" id="id_ok_helptext">' in out
    assert "<small" not in out


def test_fieldset_legend_is_styled_and_suffix_free():
    out = norm(
        component('<c-form.field :field="field" />', {"field": DemoForm()["picks"]})
    )
    assert '<legend class="form-label mb-1 float-none w-auto">Picks</legend>' in out


def test_fieldset_does_not_add_a_competing_aria_describedby():
    """Restores the guard Django's own field template carries: a widget that
    already declares aria-describedby keeps ownership of it."""
    out = component(
        '<c-form.field :field="field" />', {"field": OwnAriaForm()["picks"]}
    )
    assert out.count("aria-describedby") == 1


def test_errors_render_after_the_widget_and_inside_invalid_feedback():
    """Pinned because it MOVES on the 30 whole-form pages (they used to render
    a bare errorlist BEFORE the widget). This is the anatomy the 36 include
    sites already use."""
    form = DemoForm({})
    form.is_valid()
    out = norm(component('<c-form.field :field="field" />', {"field": form["name"]}))
    assert out.index("<input") < out.index("invalid-feedback")


# --------------------------------------------------------------------------
# <c-form.cell>: help text, and one label code path
# --------------------------------------------------------------------------


def test_cell_renders_help_text_with_the_helptext_id():
    """Django puts aria-describedby="<id>_helptext" on the widget whenever
    help_text is set. Dropping the help element leaves that dangling AND loses
    the copy, silently — the exact defect this family exists to kill."""
    out = component(
        '<c-form.cell :field="field" label="Name" />', {"field": DemoForm()["name"]}
    )
    assert 'id="id_name_helptext"' in out
    assert "Give them a name." in out


def test_cell_label_goes_through_label_tag_and_never_emits_an_empty_for():
    """`for=""` is worse than no `for`: assistive tech treats the label as
    associated-but-broken and the click target is dead. Every multi-widget
    field (RadioSelect, CheckboxSelectMultiple, SplitDateTime) returns "" from
    id_for_label."""
    out = component(
        '<c-form.cell :field="field" label="Picks" />', {"field": DemoForm()["picks"]}
    )
    assert 'for=""' not in out


def test_cell_note_is_composed_into_the_one_label_path():
    out = norm(
        component(
            '<c-form.cell :field="field" label="Credits" note="(120¢)" />',
            {"field": DemoForm()["name"]},
        )
    )
    assert (
        '<label class="form-label fs-7 mb-1" for="id_name">Credits '
        '<span class="text-secondary">(120¢)</span></label>' in out
    )


# --------------------------------------------------------------------------
# <c-form.choices>: spacing is the caller's
# --------------------------------------------------------------------------


def test_choices_form_check_has_no_baked_in_margin():
    out = component('<c-form.choices :field="field" />', {"field": DemoForm()["style"]})
    assert '<div class="form-check">' in out


def test_choices_check_class_reaches_every_option():
    out = component(
        '<c-form.choices :field="field" inline check_class="mb-0 me-0" />',
        {"field": DemoForm()["style"]},
    )
    assert out.count('class="form-check form-check-inline mb-0 me-0"') == 2


# --------------------------------------------------------------------------
# Search: the two sites the first draft could not express
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Whitespace exactness: golden diffs must be readable
# --------------------------------------------------------------------------


def test_wrapper_has_no_stray_attribute_whitespace():
    """`<div  >` on every field of every form is noise a reviewer learns to
    normalise away — and then stops reading the diff meant to catch the real
    changes."""
    out = component('<c-form.field :field="field" />', {"field": DemoForm()["name"]})
    assert "<div>" in norm(out)
    assert "<div >" not in norm(out)


class HelpCheckForm(forms.Form):
    ok = forms.BooleanField(
        label="Public", required=False, help_text="Anyone can see it."
    )


class OwnAriaForm(forms.Form):
    picks = forms.MultipleChoiceField(
        label="Picks",
        choices=[("a", "A")],
        required=False,
        help_text="Pick some.",
        widget=forms.CheckboxSelectMultiple(attrs={"aria-describedby": "custom-help"}),
    )


# --------------------------------------------------------------------------
# GOLDEN DIFF against the override this delegation replaced.
#
# The dangerous changes in this migration are invisible in a template diff: the
# template only gets SHORTER. This renders the exact markup that used to live in
# gyrinx/templates/django/forms/field.html and diffs it against the component,
# so every difference on the 30 whole-form pages has to be named here to pass.
# The allowlist IS the review artifact.
# --------------------------------------------------------------------------


LEGACY_DJANGO_FIELD = """
{% if field.field.widget.input_type == "checkbox" and not field.use_fieldset %}
    <div class="form-check">
        {{ field }}
        {% if field.label %}
            <label class="form-check-label" for="{{ field.id_for_label }}">{{ field.label }}</label>
        {% endif %}
        {{ field.errors }}
        {% if field.help_text %}
            <div class="helptext form-text"
                 {% if field.auto_id %}id="{{ field.auto_id }}_helptext"{% endif %}>{{ field.help_text }}</div>
        {% endif %}
    </div>
{% elif field.use_fieldset %}
    <fieldset {% if field.help_text and field.auto_id and "aria-describedby" not in field.field.widget.attrs %} aria-describedby="{{ field.auto_id }}_helptext"{% endif %}>
        {% if field.label %}{{ field.legend_tag }}{% endif %}
        {{ field.errors }}
        {{ field }}
        {% if field.help_text %}
            <div class="helptext form-text"
                 {% if field.auto_id %}id="{{ field.auto_id }}_helptext"{% endif %}>{{ field.help_text }}</div>
        {% endif %}
    </fieldset>
{% else %}
    {% if field.label %}{{ field.label_tag }}{% endif %}
    {{ field.errors }}
    {{ field }}
    {% if field.help_text %}
        <div class="helptext form-text"
             {% if field.auto_id %}id="{{ field.auto_id }}_helptext"{% endif %}>{{ field.help_text }}</div>
    {% endif %}
{% endif %}
"""

# Every intended difference, named as a CANONICALISATION. Anything the
# canonicaliser does not erase must match byte-for-byte, so an unnamed change
# fails the test.
#
#  1. Labels gain `form-label`, legends gain the Bootstrap reset
#     (`float-none w-auto`, so a group heading is body-size rather than floated
#     full-width 1.5rem).
#  2. Both lose the trailing `label_suffix` colon.
#  3. Help text becomes one element: `.form-text.text-secondary`, BLOCK-level in
#     the checkbox and fieldset branches where an inline <small> collapses onto
#     the label line.
#  4. (asserted separately, in test_errors_render_after_the_widget_…) errors
#     move from before the widget to after it, inside invalid-feedback.
LABEL_CLASSES = re.compile(
    r'\s*class="(?:form-label|form-label mb-1 float-none w-auto)"'
)
HELP_ELEMENT = re.compile(
    r'<(small|div) class="(?:helptext form-text|form-text text-secondary)[^"]*"'
    r"[^>]*>.*?</\1>",
    re.S,
)


def canon(html):
    html = LABEL_CLASSES.sub("", html)
    html = html.replace(":</label>", "</label>").replace(":</legend>", "</legend>")
    return HELP_ELEMENT.sub("<HELP>", html)


@pytest.mark.parametrize("name", ["name", "refund", "picks", "style"])
def test_golden_diff_against_the_replaced_override(name):
    field = DemoForm()[name]
    old = canon(norm(component(LEGACY_DJANGO_FIELD, {"field": field})))
    new = canon(norm(component('<c-form.field :field="field" />', {"field": field})))
    # The plain branch gains the include's wrapper <div>; the old override
    # emitted a bare fragment and leaned on django/forms/div.html's wrapper.
    if name == "name":
        old = f"<div>{old}</div>"
    assert old == new, f"UNNAMED difference for {name}:\n old: {old}\n new: {new}"


def test_the_golden_canonicaliser_is_not_vacuous():
    """Guard the guard: canon() must not erase a real change."""
    assert canon('<input class="x">') == '<input class="x">'
    assert canon("<b>hi</b>") == "<b>hi</b>"


def test_actions_link_strips_slot_whitespace():
    """djlint reflows a one-line call site onto three, so the slot arrives as
    "\\n    Cost\\n". An <a> is plain inline, so that whitespace renders inside
    the link and takes its underline. .btn and .badge are immune (inline-block);
    this one is not, so the component strips it."""
    out = component('<c-actions.link href="/x">\n    Cost\n</c-actions.link>')
    assert out == '<a href="/x" class="linked-secondary">Cost</a>'


def test_actions_link_variant_maps_to_linked_class():
    assert (
        component('<c-actions.link href="/x" variant="danger">Del</c-actions.link>')
        == '<a href="/x" class="linked-danger">Del</a>'
    )


def test_list_items_mode_has_no_stray_whitespace():
    out = component('<c-list :items="xs" />', {"xs": ["A", "B"]})
    assert out == (
        '<span class="comma-list"><span>A</span><span>,&nbsp;</span><span>B</span></span>'
    )


def test_list_single_item_has_no_trailing_separator():
    out = component('<c-list :items="xs" />', {"xs": ["Solo"]})
    assert out == '<span class="comma-list"><span>Solo</span></span>'


def test_list_slot_mode_collapses_call_site_whitespace():
    """The whole point of the component: the call-site loop's newlines must not
    reach the output as spaces before each comma."""
    out = component(
        "<c-list>\n"
        "    {% for x in xs %}\n"
        "        <span>{{ x }}</span>\n"
        "        {% if not forloop.last %}<c-list.sep />{% endif %}\n"
        "    {% endfor %}\n"
        "</c-list>",
        {"xs": ["A", "B"]},
    )
    assert out == (
        '<span class="comma-list"><span>A</span><span>,&nbsp;</span><span>B</span></span>'
    )


def test_steps_computes_bar_width():
    out = component('<c-steps step="2" total="3" title="Add Vehicle" />')
    assert 'style="width: 67%"' in out
    assert "Step 2 of 3" in out
    assert '<h1 class="h3 mb-0">Add Vehicle</h1>' in out
    assert "<h2" not in out  # no subtitle passed


def test_steps_subtitle_is_optional():
    out = component('<c-steps step="1" total="2" title="T" subtitle="S" />')
    assert '<h2 class="h5 mb-0">S</h2>' in out


def test_strip_filter_escapes_unsafe_input_and_preserves_safe_input():
    """The filter propagates safeness; it never confers it.

    It is deliberately not registered `is_safe=True` — that flag also only
    propagates, so carrying both invited the reading that unsafe input skipped
    escaping. This pins the actual contract: a plain str (a `class` prop holding
    user text, say) is escaped by the engine as normal; only already-safe slot
    output passes through untouched.
    """
    from django.utils.html import conditional_escape
    from django.utils.safestring import mark_safe

    from gyrinx.core.templatetags.custom_tags import strip_filter

    # The defence is escaping the QUOTES: with those gone the payload cannot
    # terminate the attribute it is sitting in, so the words surviving as text is
    # expected and harmless.
    hostile = '" onmouseover=alert(1) x="'
    escaped = conditional_escape(strip_filter(f"  {hostile}  "))
    assert '"' not in escaped
    assert "&quot;" in escaped
    assert conditional_escape(strip_filter(mark_safe('  a="b"  '))) == 'a="b"'
