"""Tests for the cotton badge components.

HARNESS RULE: cotton compiles in the template LOADER, so ``Template("<c-badge>")``
and ``engines["django"].from_string(...)`` pass component tags through as literal
text with no error and any assertion against them passes vacuously. Every test
here must render a real file from disk via ``render_to_string``.
"""

import html.parser
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.test import override_settings

from gyrinx.core.models.battle import Battle
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.crew import Crew
from gyrinx.core.models.list import ListFighter

COTTON_DIR = Path(settings.BASE_DIR) / "gyrinx" / "templates" / "cotton"
BADGE = COTTON_DIR / "badge.html"
# Every component, not a hardcoded list: the two guards below must cover any
# component added later, since the whole point is that nothing else in the
# toolchain is watching this directory.
ALL_COMPONENTS = sorted(COTTON_DIR.rglob("*.html"))

# Written into a directory that is already on the template search path.
FIXTURES = Path(settings.BASE_DIR) / "gyrinx" / "core" / "templates" / "cotton_test"


@pytest.fixture
def render():
    """Render a snippet from a real on-disk template. See HARNESS RULE above.

    Filenames must be globally unique: Django wraps the loaders in
    cached.Loader, so reusing a name serves a stale compiled template and the
    test silently asserts against the wrong markup.
    """
    FIXTURES.mkdir(parents=True, exist_ok=True)
    written = []

    def _render(body, context=None):
        path = FIXTURES / f"f{uuid.uuid4().hex}.html"
        path.write_text(body)
        written.append(path)
        return render_to_string(f"cotton_test/{path.name}", context or {})

    yield _render
    for path in written:
        path.unlink(missing_ok=True)


class _Collector(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def parse(markup):
    collector = _Collector()
    collector.feed(markup)
    return collector.tags


# --------------------------------------------------------------------------
# variants
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    ["primary", "secondary", "success", "warning", "danger", "info", "light", "dark"],
)
def test_variant_emits_text_bg(render, variant):
    out = render(f'<c-badge variant="{variant}">X</c-badge>')
    assert out == f'<span class="badge text-bg-{variant}">X</span>'


def test_default_is_secondary_span(render):
    assert (
        render("<c-badge>X</c-badge>")
        == '<span class="badge text-bg-secondary">X</span>'
    )


def test_ghost_emits_no_colour(render):
    out = render('<c-badge variant="ghost">X</c-badge>')
    assert out == '<span class="badge text-body border fw-normal">X</span>'
    assert "text-bg-" not in out


def test_variant_accepts_context_variable(render):
    """The _status_indicator.html mechanic: variant="{{ color }}"."""
    out = render('<c-badge variant="{{ color }}">X</c-badge>', {"color": "success"})
    assert 'text-bg-success"' in out


@pytest.mark.parametrize("flag,expected", [(True, "success"), (False, "secondary")])
def test_variant_accepts_inline_if(render, flag, expected):
    """The home/campaign_row.html mechanic, invisible to a text-bg-<word> grep."""
    out = render(
        '<c-badge variant="{% if flag %}success{% else %}secondary{% endif %}">X</c-badge>',
        {"flag": flag},
    )
    assert f"text-bg-{expected}" in out


# --------------------------------------------------------------------------
# state table
# --------------------------------------------------------------------------

EXPECTED_STATES = {
    # ListFighter.injury_state
    "active": "success",
    "recovery": "warning",
    "convalescence": "warning",
    "in_repair": "warning",
    "dead": "danger",
    # capture pseudo-states (model properties, not injury_state values)
    "captured": "warning",
    "sold_to_guilders": "secondary",
    # Crew.status
    "draft": "secondary",
    "locked": "success",
    # Battle.status
    "pre_battle": "secondary",
    "in_progress": "success",
    "post_battle": "secondary",
    # Campaign.status
    "pre_campaign": "secondary",
    "post_campaign": "secondary",
    # aliases kept for prior-art call sites
    "injured": "warning",
    "sold": "secondary",
    "archived": "secondary",
}


@pytest.mark.parametrize("state,tone", sorted(EXPECTED_STATES.items()))
def test_state_resolves(render, state, tone):
    out = render(f'<c-badge state="{state}">S</c-badge>')
    assert out == f'<span class="badge text-bg-{tone}">S</span>'


def test_state_beats_variant(render):
    out = render('<c-badge state="dead" variant="success">S</c-badge>')
    assert "text-bg-danger" in out


def test_blank_state_falls_through_to_variant(render):
    out = render('<c-badge state="" variant="success">S</c-badge>')
    assert "text-bg-success" in out


def test_unknown_state_is_never_colourless(render):
    """The structural guard: a state badge can never render without a colour."""
    out = render('<c-badge state="a_state_nobody_has_added_yet">S</c-badge>')
    assert re.search(r"\btext-bg-\w+\b|\btext-body\b", out)


def test_state_table_covers_model_choices():
    """Model-drift guard.

    The state prop fails SILENTLY for an unrecognised value -- it falls through
    to `variant`, whose default is secondary. That is fine for a blank state and
    fatal for a real one: a green pill turns grey. This test is what stops it,
    by asserting the table stays total over every status vocabulary that is
    rendered as a badge.
    """
    source = BADGE.read_text()
    keys = set(re.findall(r"'([a-z_]+)':\s*'[a-z]+'", source))
    assert keys == set(EXPECTED_STATES), "badge.html state table drifted from this test"

    model_values = set()
    model_values.update(value for value, _ in ListFighter.INJURY_STATE_CHOICES)
    model_values.update(value for value, _ in Crew.STATUS_CHOICES)
    model_values.update(
        {Battle.PRE_BATTLE, Battle.IN_PROGRESS, Battle.POST_BATTLE},
    )
    model_values.update(
        {Campaign.PRE_CAMPAIGN, Campaign.IN_PROGRESS, Campaign.POST_CAMPAIGN},
    )
    missing = model_values - keys
    assert not missing, (
        f"These status values would render a grey badge: {sorted(missing)}. "
        "Add them to the state table in gyrinx/templates/cotton/badge.html."
    )


# --------------------------------------------------------------------------
# escaping / safety
# --------------------------------------------------------------------------

# A value that both starts and ends with a quote: cotton's ensure_quoted()
# returns it verbatim, so routing it through {{ attrs }} injects a handler.
INJECTION = '"Boss" onmouseover=alert(document.domain) x="'


@pytest.mark.parametrize("prop", ["title", "tooltip", "class"])
def test_declared_props_cannot_inject_an_attribute(render, prop):
    out = render(f'<c-badge {prop}="{{{{ p }}}}">n</c-badge>', {"p": INJECTION})
    _, attrs = parse(out)[0]
    assert "onmouseover" not in attrs


def test_dynamic_title_is_also_safe(render):
    """title is a declared prop, so even the colon form routes through
    autoescaping rather than the mark_safe'd attrs string."""
    out = render('<c-badge :title="p">n</c-badge>', {"p": INJECTION})
    _, attrs = parse(out)[0]
    assert "onmouseover" not in attrs


def test_slot_is_escaped(render):
    out = render("<c-badge>{{ s }}</c-badge>", {"s": '<b>Ash</b> "W" & Co'})
    assert "&lt;b&gt;" in out and "&amp;" in out
    assert "<b>" not in out


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "//evil.example/x",
        "http://evil.example/x",
        "data:text/html,x",
    ],
)
def test_unsafe_href_does_not_become_a_link(render, href):
    out = render('<c-badge href="{{ h }}">h</c-badge>', {"h": href})
    tag, attrs = parse(out)[0]
    assert tag == "span"
    assert "href" not in attrs


def test_root_relative_href_links(render):
    out = render('<c-badge href="/list/1">h</c-badge>')
    assert (
        out
        == '<a href="/list/1" class="badge text-bg-secondary text-decoration-none">h</a>'
    )


def test_tag_is_constrained_not_interpolated(render):
    """Autoescaping does nothing in tag-name position."""
    out = render(
        '<c-badge tag="{{ t }}">g</c-badge>', {"t": "span onmouseover=alert(1)"}
    )
    assert out == '<span class="badge text-bg-secondary">g</span>'


# --------------------------------------------------------------------------
# attribute forwarding
# --------------------------------------------------------------------------


def test_attrs_proxy_forwards(render):
    out = render(
        '<c-badge id="z" aria-label="L" data-bs-toggle="tooltip" data-bs-title="T">x</c-badge>'
    )
    _, attrs = parse(out)[0]
    assert attrs["id"] == "z"
    assert attrs["aria-label"] == "L"
    assert attrs["data-bs-toggle"] == "tooltip"


def test_bare_valueless_attribute_survives(render):
    """fighter_card_content_inner.html:78 carries a bare `bs-tooltip`."""
    out = render("<c-badge bs-tooltip>x</c-badge>")
    assert " bs-tooltip>" in out
    assert 'bs-tooltip="True"' not in out


def test_no_stray_space_when_only_declared_props_are_passed(render):
    """A bare `{% if attrs %}` is ALWAYS true -- c-vars keys stay in the mapping.
    The guard must be `attrs.attrs_dict`."""
    out = render('<c-badge variant="primary" class="ms-2">P</c-badge>')
    assert " >" not in out
    assert "  " not in out


def test_class_is_merged_not_duplicated(render):
    out = render('<c-badge variant="danger" class="ms-2">x</c-badge>')
    assert out.count("class=") == 1
    assert 'class="badge text-bg-danger ms-2"' in out


def test_class_accepts_template_expressions(render):
    out = render(
        '<c-badge class="d-none d-{{ bp }}-inline-block align-middle">L</c-badge>',
        {"bp": "md"},
    )
    assert "d-md-inline-block" in out


def test_tooltip_emits_a_real_title(render):
    """X4: no prop may depend on JS. data-bs-title alone is inert markup."""
    out = render(
        '<c-badge tooltip="{{ t }}">T</c-badge>', {"t": "Captured by <b>X</b>"}
    )
    _, attrs = parse(out)[0]
    assert attrs["title"] == "Captured by <b>X</b>"
    assert attrs["data-bs-toggle"] == "tooltip"


def test_tooltip_beats_title(render):
    out = render('<c-badge tooltip="tt" title="xx">T</c-badge>')
    _, attrs = parse(out)[0]
    assert attrs["title"] == "tt"


# --------------------------------------------------------------------------
# whitespace
# --------------------------------------------------------------------------


def test_no_padding_around_the_slot(render):
    """Protects the ~10 mid-sentence sites and battle_summary_card.html:8."""
    assert (
        render("A<c-badge>X</c-badge>B")
        == 'A<span class="badge text-bg-secondary">X</span>B'
    )


def test_adjacent_badges_in_a_loop_have_no_whitespace_between_them(render):
    """campaign_action_outcome.html:22 butts dice-result badges together.

    A trailing newline in the component file collapses to a rendered space
    between two inline-block elements. This is why the cotton directory is
    excluded from djlint --reformat and from pre-commit's end-of-file-fixer.
    """
    out = render(
        "{% for x in xs %}<c-badge>{{ x }}</c-badge>{% endfor %}", {"xs": [4, 6, 2]}
    )
    assert "</span><span" in out
    assert "\n" not in out


def test_nbsp_run_survives_byte_for_byte(render):
    """blank_fighter_card.html: the &nbsp; count sets the printed box width."""
    out = render(
        '<c-badge variant="ghost" tag="div">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</c-badge>'
    )
    assert (
        out
        == '<div class="badge text-body border fw-normal">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</div>'
    )


def test_nested_markup_keeps_deliberate_absence_of_a_space(render):
    out = render(
        '<c-badge variant="danger">{{ v }}<span class="ms-1">•</span></c-badge>',
        {"v": 5},
    )
    assert '>5<span class="ms-1">' in out


# --------------------------------------------------------------------------
# element switching
# --------------------------------------------------------------------------


def test_tag_div(render):
    assert (
        render('<c-badge tag="div">d</c-badge>')
        == '<div class="badge text-bg-secondary">d</div>'
    )


def test_href_wins_over_tag(render):
    assert parse(render('<c-badge tag="div" href="/x">d</c-badge>'))[0][0] == "a"


def test_pill_precedes_the_colour_token(render):
    out = render('<c-badge variant="danger" pill class="ms-auto">3</c-badge>')
    assert out == '<span class="badge rounded-pill text-bg-danger ms-auto">3</span>'


# --------------------------------------------------------------------------
# composites
# --------------------------------------------------------------------------


class _Capture:
    def __init__(self, name):
        self.capturing_list = type("L", (), {"name": name})()


class _Fighter:
    def __init__(self, injury="active", captured_by=None, sold=False, vehicle=False):
        self.injury_state = injury
        self.is_active = injury == "active"
        self.is_captured = captured_by is not None
        self.is_sold_to_guilders = sold
        self.is_vehicle = vehicle
        self.capture_info = _Capture(captured_by) if captured_by else None

    def get_injury_state_display(self):
        return self.injury_state.replace("_", " ").title()


# --------------------------------------------------------------------------
# isolation + toolchain
# --------------------------------------------------------------------------


def test_output_is_identical_under_context_isolation(render):
    """None of the three components reads ambient context. Guards the property
    for the day a cotton release makes isolation cheap enough to enable."""
    snippet = '<c-badge state="dead" class="ms-2" title="{{ t }}">D</c-badge>'
    before = render(snippet, {"t": "x"})
    with override_settings(COTTON_ENABLE_CONTEXT_ISOLATION=True):
        after = render(snippet, {"t": "x"})
    assert before == after


def test_djlint_leaves_the_component_files_alone():
    """Both the `djlint:off` guard and the extend_exclude path matter: without
    the guard djlint parses the component names in the docstrings as real tags
    and reflows the prose; without the exclusion --reformat appends a trailing
    newline while reporting "0 files were updated"."""
    before = {p: p.read_bytes() for p in ALL_COMPONENTS}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "djlint",
            "--profile=django",
            "--reformat",
            str(COTTON_DIR),
        ],
        capture_output=True,
        cwd=settings.BASE_DIR,
        check=False,
    )
    for path, content in before.items():
        assert path.read_bytes() == content, f"djlint modified {path}"


def test_component_files_have_no_trailing_newline():
    """A component emits its file content verbatim, so a trailing newline lands
    after the closing tag and collapses to a rendered space -- between adjacent
    inline badges, or before the full stop in `mid<c-badge>x</c-badge>.`.

    This guard exists because the rule is otherwise unenforceable:
    gyrinx/templates/cotton/ is excluded from djlint AND from pre-commit's
    end-of-file-fixer (that exclusion is what lets these files stay
    newline-free), so no formatter will ever catch a regression here. Any
    editor with "insert final newline" silently reintroduces the bug.
    """
    offenders = [
        str(p.relative_to(COTTON_DIR))
        for p in ALL_COMPONENTS
        if p.read_bytes().endswith(b"\n")
    ]
    assert not offenders, (
        "cotton components must not end with a newline: "
        + ", ".join(offenders)
        + ". See .claude/notes/cotton-whitespace-and-toolchain-decisions.md"
    )
