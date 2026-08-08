"""Static gates on django-cotton component CALL SITES.

These are not unit tests of any one component: they are the CI half of the
component contract. Every rule here exists because a real failure mode is
SILENT — cotton renders something plausible, djlint lints it clean, and the
page returns 200 with a control that does not work. In a big-bang migration
touching ~570 button sites in one commit, a silent failure mode with no gate is
a shipped bug.

Run: pytest n23/core/tests/test_cotton_call_site_gates.py
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
# Both trees that hold first-party templates: the platform shell and the n23
# edition package. These gates scan by filesystem walk, so a missing root does
# not error — it just yields nothing and every gate passes vacuously.
TEMPLATE_ROOTS = [REPO_ROOT / "gyrinx", REPO_ROOT / "n23"]
COTTON_DIR = REPO_ROOT / "gyrinx" / "templates" / "cotton"

# <c-name ...>  or  <c-name ... />   (NOT </c-name>), across newlines.
OPEN_TAG_RE = re.compile(
    r"<c-(?P<name>[\w.\-]+)(?P<body>(?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>"
)
# Quote-agnostic on purpose: hardcoding `"` let `:disabled='not can_roll'` --
# the exact "silently ships the control enabled" bug these gates exist for --
# walk straight past every one of them.
ATTR_RE = re.compile(
    r"(?P<colon>:?)(?P<name>[\w.@:\-]+)\s*=\s*"
    r"(?P<q>[\"'])(?P<value>(?:(?!(?P=q)).)*)(?P=q)",
    re.S,
)


def html_files():
    for root in TEMPLATE_ROOTS:
        for path in sorted(root.rglob("*.html")):
            parts = path.relative_to(REPO_ROOT).parts
            if ".claude" in parts or "node_modules" in parts:
                continue
            # Other cotton test modules write throwaway templates into
            # gyrinx/templates/ while they run. They deliberately contain the
            # broken shapes these gates exist to forbid, and they vanish
            # mid-scan under pytest-xdist.
            if path.name.startswith("_cotton_test") or path.name.startswith("_probe"):
                continue
            # The component test harnesses write uuid-named host templates into
            # gyrinx/templates/_cotton_test_host/ and
            # n23/core/templates/cotton_test/, then delete them again; under
            # pytest-xdist they appear and vanish mid-scan. Note the badge
            # harness's directory has no leading underscore and its files are
            # bare uuids, so neither prefix check above catches it.
            if "_cotton_test_host" in parts or "cotton_test" in parts:
                continue
            yield path


def call_sites():
    """Yield (path, component_name, tag_text, attrs_text) for every <c-…> open tag."""
    for path in html_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:  # transient test scratch file
            continue
        for m in OPEN_TAG_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            yield path, m.group("name"), m.group(0), m.group("body"), line


def strip_quoted(body: str) -> str:
    """Blank out quoted attribute values so only attribute-POSITION text remains."""
    return re.sub(r"\"[^\"]*\"|'[^']*'", '""', body)


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


# --------------------------------------------------------------------------
# G1 — a Django tag in ATTRIBUTE POSITION renders as literal text.
# --------------------------------------------------------------------------
def test_no_template_tags_in_component_attribute_position():
    """`<c-btn {% if x %}disabled{% endif %}>` does NOT raise — it renders the
    braces as literal text, and the browser parses `{%`, `if`, `%}disabled{%`
    as junk attributes. The control ships ENABLED. djlint lints it clean and
    reformats it into something that looks correct.

    Use a quoted value (`disabled="{% if x %}1{% endif %}"`) or the `raw_attrs`
    slot instead.
    """
    bad = []
    for path, name, _tag, body, line in call_sites():
        if name == "vars":
            continue
        outside = strip_quoted(body)
        if "{%" in outside or "{{" in outside:
            bad.append(f"{rel(path)}:{line}  <c-{name} …>")
    assert not bad, (
        "Django tags in cotton attribute position (renders as literal text):\n"
        + "\n".join(bad)
    )


# --------------------------------------------------------------------------
# G2 — `:prop` is a variable resolver, not an evaluator.
# --------------------------------------------------------------------------
NON_PATH_RE = re.compile(r"\s|\||==|!=|<|>|\bnot\b|\band\b|\bor\b")


def test_dynamic_props_are_bare_variable_paths():
    """`:disabled="not can_roll"` silently resolves to NOTHING and ships the
    button ENABLED. `:url="back_url|default:pack.get_absolute_url"` silently
    drops both the filter and the fallback (cotton #273). Neither errors.

    Anything that is not a bare dotted path must use string interpolation:
    `disabled="{% if not can_roll %}1{% endif %}"` / `url="{{ a|default:b }}"`.
    """
    bad = []
    for path, name, _tag, body, line in call_sites():
        # <c-vars :map="{...}"> declares a dict DEFAULT (the documented variant-map
        # pattern). That is a literal, not a call-site expression.
        if name == "vars":
            continue
        for m in ATTR_RE.finditer(body):
            if not m.group("colon"):
                continue
            value = m.group("value").strip()
            if NON_PATH_RE.search(value):
                bad.append(
                    f'{rel(path)}:{line}  <c-{name} :{m.group("name")}="{value}">'
                )
    assert not bad, "Expressions in :props silently resolve to nothing:\n" + "\n".join(
        bad
    )


# --------------------------------------------------------------------------
# G3 — `:` on an UNDECLARED attribute is an attribute-injection hole.
# --------------------------------------------------------------------------
def declared_props():
    """{component name -> set of props declared in its <c-vars>}."""
    out = {}
    if not COTTON_DIR.exists():
        return out
    for path in COTTON_DIR.rglob("*.html"):
        name = str(path.relative_to(COTTON_DIR).with_suffix("")).replace("/", ".")
        # Blank {% comment %} blocks first — see the same fix in
        # scripts/check_cotton.py. Doc comments mention <c-vars>, and taking the
        # first match parsed prose and returned {} for six components.
        source = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
            "",
            path.read_text(encoding="utf-8"),
            flags=re.S,
        )
        m = re.search(r"<c-vars([^>]*)/?>", source)
        out[name] = (
            {a.group("name") for a in ATTR_RE.finditer(m.group(1))} if m else set()
        )
    return out


def test_dynamic_props_only_on_declared_props():
    """Declared props render through `{{ prop }}` in the component body and are
    AUTOESCAPED — `:title="x"` is safe. UNDECLARED attributes go out through
    `{{ attrs }}`, which is mark_safe'd and whose ensure_quoted() returns an
    already-quoted value verbatim. Verified: `:id="payload"` with
    `"a" onmouseover=alert(1) "` produced a genuinely parsed onmouseover
    handler.

    So the ban is not a deny-list of attribute names — it is `:` on anything the
    target component does not declare. Use string interpolation instead
    (`id="{{ x }}"`), which is autoescaped on passthrough attributes too.
    """
    props = declared_props()
    bad = []
    for path, name, _tag, body, line in call_sites():
        if name == "vars" or name not in props:
            continue
        for m in ATTR_RE.finditer(body):
            if (
                m.group("colon")
                and m.group("name") not in props[name]
                and m.group("name") != "attrs"
            ):
                bad.append(
                    f"{rel(path)}:{line}  <c-{name} :{m.group('name')}=…>  (not in <c-vars>)"
                )
    assert not bad, (
        "`:` on an undeclared attribute — attribute-injection hole:\n" + "\n".join(bad)
    )


# --------------------------------------------------------------------------
# G4 — c-back / c-cancel read `return_url` AMBIENTLY, on purpose.
# --------------------------------------------------------------------------
def test_back_and_cancel_never_take_return_url_as_an_attribute():
    """`return_url` is deliberately NOT in their <c-vars>, so the 19 bare
    `{% include %}` sites keep inheriting the view-computed value. That also
    means passing it as an attribute would emit a stray HTML attribute instead
    of being consumed. Pass `url=` instead.
    """
    bad = [
        f"{rel(path)}:{line}  <c-{name} …return_url=…>"
        for path, name, tag, body, line in call_sites()
        if name in {"back", "cancel"} and re.search(r":?return_url\s*=", body)
    ]
    assert not bad, "return_url= passed to c-back/c-cancel (use url=):\n" + "\n".join(
        bad
    )


# --------------------------------------------------------------------------
# G5 — icon-only buttons need an accessible name (#2001).
# --------------------------------------------------------------------------
ICON_ONLY_RE = re.compile(
    r"<c-btn(?P<body>(?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>\s*(?:<i\s[^>]*>\s*</i>|<c-icon\b[^>]*/>)\s*</c-btn>",
    re.S,
)


def test_icon_only_buttons_have_an_accessible_name():
    """11 icon-only controls in the estate have neither aria-label, title nor a
    visually-hidden span (#2001 audit). A slot-verbatim rewrite would carry the
    gap across the one moment when every button site is being touched.
    """
    bad = []
    for path in html_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            continue
        for m in ICON_ONLY_RE.finditer(text):
            body = m.group("body")
            if not re.search(r":?(label|aria-label|title|tooltip)\s*=", body):
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{rel(path)}:{line}")
    assert not bad, (
        "icon-only <c-btn> with no accessible name (add label=):\n" + "\n".join(bad)
    )


# --------------------------------------------------------------------------
# G6 — literal variants must be real Bootstrap variants.
# --------------------------------------------------------------------------
VARIANTS = {
    "",
    "primary",
    "secondary",
    "success",
    "danger",
    "warning",
    "info",
    "light",
    "dark",
    "link",
    "outline-primary",
    "outline-secondary",
    "outline-success",
    "outline-danger",
    "outline-warning",
    "outline-info",
    "outline-light",
    "outline-dark",
}


def test_literal_btn_variants_are_in_the_design_system_set():
    """`variant="primry"` renders `btn-primry` silently. Dynamic values
    (`variant="{{ banner.colour }}"`) are deliberately allowed and skipped —
    SiteBanner.colour is constrained at the model layer instead.
    """
    bad = []
    for path, name, _tag, body, line in call_sites():
        if name != "btn":
            continue
        for m in ATTR_RE.finditer(body):
            v = m.group("value")
            if m.group("name") == "variant" and "{" not in v and v not in VARIANTS:
                bad.append(f'{rel(path)}:{line}  variant="{v}"')
    assert not bad, "unknown btn variant:\n" + "\n".join(bad)


# --------------------------------------------------------------------------
# G7 — the whole component estate is one line in INSTALLED_APPS away from
#      rendering as literal text with HTTP 200.
# --------------------------------------------------------------------------
def test_cotton_is_wired_up():
    from django.apps import apps
    from django.conf import settings

    # The app registry, not the INSTALLED_APPS strings: development names cotton
    # through its own AppConfig subclass to drop the cached template loader
    # (gyrinx/cotton_dev.py). Same app, same name, different entry.
    assert apps.is_installed("django_cotton")
    builtins = settings.TEMPLATES[0]["OPTIONS"].get("builtins", [])
    assert any("cotton" in b for b in builtins), builtins


@pytest.mark.django_db
def test_rendered_pages_contain_no_uncompiled_component_tags(client):
    """Cotton compiles in the LOADER. With the app missing — or a typo'd
    component name, or an unclosed tag — `<c-btn>` reaches the browser as
    literal text with no exception and a 200 response.
    """
    for url in ("/", "/accounts/login/", "/accounts/signup/"):
        response = client.get(url, follow=True)
        assert response.status_code == 200, url
        assert b"<c-" not in response.content, f"uncompiled cotton tag in {url}"


# --------------------------------------------------------------------------
# G8 — the static cotton gate runs in CI, not only in pre-commit.
# --------------------------------------------------------------------------
def test_check_cotton_script_passes():
    """scripts/check_cotton.py is the pre-commit half of the component contract.

    Its most important rule — a BoundField/Form prop passed WITHOUT the colon,
    or not passed at all — guards a failure that renders a form with no label,
    no help text and NO ERRORS while returning 200 (#2001). Run it here too so
    a bypassed hook cannot land it.
    """
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(REPO_ROOT / "scripts" / "check_cotton.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# G9 — `{{ form.as_p }}` does NOT reach the project's per-field template.
# --------------------------------------------------------------------------
# Only django/forms/div.html routes fields through gyrinx/templates/django/
# forms/field.html (via as_field_group). p.html / table.html / ul.html inline
# the label, widget and helptext themselves, so those pages keep Django's stock
# rendering and never see <c-form.field>. Three such sites exist, all on
# surfaces the migration leaves alone by design (Django-admin CSS, vendored
# allauth MFA). This list must not grow.
STOCK_RENDER_SITES = {
    "gyrinx/site/templates/admin/gyrinxsite/notification/broadcast.html",
    "gyrinx/templates/mfa/recovery_codes/generate.html",
    "gyrinx/templates/mfa/totp/deactivate_form.html",
}


def test_whole_form_shortcuts_that_bypass_the_field_component_are_pinned():
    found = set()
    for path in html_files():
        text = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
            "",
            path.read_text(encoding="utf-8", errors="replace"),
            flags=re.S,
        )
        if re.search(r"\{\{\s*\w+\.as_(p|table|ul)\s*\}\}", text):
            found.add(rel(path))
    assert found == STOCK_RENDER_SITES, (
        "as_p/as_table/as_ul bypass gyrinx/templates/django/forms/field.html, so "
        "the page keeps Django's stock field rendering. Use {{ form }} (as_div) "
        "unless the page is deliberately out of scope; then add it here.\n"
        f"unexpected: {sorted(found - STOCK_RENDER_SITES)}\n"
        f"gone: {sorted(STOCK_RENDER_SITES - found)}"
    )


def test_no_multiline_hash_comments():
    """Django's ``{# #}`` comment is SINGLE-LINE ONLY.

    Spanning it over two lines does not produce a comment: the template engine
    never recognises it, so the whole thing renders into the page as literal
    text. It shipped a paragraph of implementation notes into the middle of the
    breadcrumb on every campaign-mode gang page.

    Nothing else catches this. It is valid HTML, djlint is happy with it, and the
    text only appears when that branch of the template renders — so a page whose
    tests never exercise the branch stays green. Use ``{% comment %}`` blocks for
    anything longer than one line.
    """
    offenders = []
    for path in html_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"\{#", text):
            close = text.find("#}", match.end())
            if close != -1 and "\n" in text[match.end() : close]:
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{rel(path)}:{line}")
    assert not offenders, (
        "Multi-line {# #} comments render as literal text in the page. "
        "Use {% comment %}...{% endcomment %} instead.\n  " + "\n  ".join(offenders)
    )


def test_declared_props_are_parsed_from_the_real_cvars_not_the_doc_comment():
    """Every component's doc comment discusses `<c-vars>`, and both gates take the
    FIRST match in the file — so without blanking comments they parse prose and
    return an empty prop set.

    That silently blinded the undeclared-prop XSS check on the six busiest
    components. It failed closed (an empty set flags every `:prop`), but it had a
    fail-OPEN twin: a doc comment spelling out `<c-vars foo="">` as an example
    would mark `foo` declared, letting a real `:foo=` reach the mark_safe'd
    `{{ attrs }}`. Adding one sentence of prose to badge/icon/messages flipped all
    three, and nothing noticed — hence this test.
    """
    props = declared_props()
    assert "disabled" in props["btn"], (
        "c-btn declares `disabled`; if this is empty the gate is parsing the doc "
        "comment instead of the real <c-vars>."
    )
    assert {"variant", "state", "class"} <= props["badge"] | {"variant"}
    for name in ("btn", "badge", "back", "cancel", "icon", "messages", "callout"):
        assert props[name], f"{name}: empty prop set means the gate is blind"


def test_gate_regex_is_quote_agnostic():
    """`:disabled='not can_roll'` is the canonical "ships the control enabled"
    bug. A double-quote-only ATTR_RE let it past every gate."""
    single = dict(
        (m.group("name"), m.group("value"))
        for m in ATTR_RE.finditer("""<c-btn :disabled='not can_roll' :id='payload'>""")
    )
    assert single == {"disabled": "not can_roll", "id": "payload"}
    double = dict(
        (m.group("name"), m.group("value"))
        for m in ATTR_RE.finditer('<c-btn :disabled="not can_roll">')
    )
    assert double == {"disabled": "not can_roll"}


def test_raw_markup_ratchet_holds():
    """scripts/check_raw_markup.py counts hand-written Bootstrap markup and fails
    if it rises above scripts/raw_markup_baseline.json.

    Run here as well as in pre-commit so it is a genuine merge gate: it caught
    four raw buttons that arrived on main while this branch was in flight, and a
    ratchet nobody runs is just a file.
    """
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(REPO_ROOT / "scripts" / "check_raw_markup.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
