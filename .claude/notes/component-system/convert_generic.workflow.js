export const meta = {
    name: "convert-generic",
    description:
        "Convert a parameterised batch of Gyrinx templates to page components with golden tests",
    phases: [{ title: "Convert" }],
};

// args: [{ slug, template, view, confirm?, fixtureArgs?, note? }, ...]
const _args = typeof args === "string" ? JSON.parse(args) : args || [];
const PAGES = _args.map((p) => ({
    fixtureArgs: "user",
    ...p,
    module: `gyrinx/components/pages/${p.slug}.py`,
    test: `gyrinx/components/tests/test_golden_${p.slug}.py`,
}));

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST read a few already-converted reference files that match your page shape (do not skip):
- FORM pages: gyrinx/components/pages/campaign_crud.py, campaign_resource_type_new.py, list_clone.py
- CONFIRM pages: gyrinx/components/pages/fighter.py (delete/kill), campaign.py (archive/remove_list), campaign_resource_type_remove.py
- pages that bridge a shared partial (list_common_header etc.): gyrinx/components/pages/fighter_xp.py, list_about.py
- gyrinx/components/pages/_shared.py (back_link/cancel_link), bridge.py (safe_rich_text, list_with_theme, safe_referer)
- gyrinx/components/design/__init__.py (FormField, PageShell, CsrfInput, Alert, Button, Badge, etc.)
- gyrinx/components/tests/test_golden.py + a matching test_golden_*.py (golden test + object-seeding examples)
- gyrinx/components/testing.py (assert_equivalent; scope="content" is the default and ignores the <title>/shell)

THEN read your target template AND its view render() call for the EXACT context keys AND how the view builds the
form/objects in its GET branch. Replicate that object/form construction in the golden test using conftest fixtures
(user, make_user, content_house, content_fighter, make_content_fighter, make_list, make_list_fighter, make_campaign,
campaign, list_with_campaign) plus any objects you create inline as the view does.

KEY RULES:
- Raw HTML tags (div, p, form, a, button, h1, h2, h3, i, span, ul, li, label, select, option, input_, table, tr, td, th ...)
  come from gyrinx.components.tags and use SUBSCRIPT syntax for children: tag(attrs)[child]. Design components use CALL syntax.
- @register_page("<exact template name>"); the function is fn(context) -> Page.
- Reproduce the template EXACTLY (tags/classes/text/structure/conditionals/loops). Whitespace + attribute ORDER do
  NOT matter (the golden test normalises them, and neutralises CSRF + {% cachebuster %} tokens).
- {% csrf_token %} -> CsrfInput(context["request"]).  {% url ... %} -> reverse(...).  {{ form }} -> raw(str(form_obj)).
  {{ form.media }} -> raw(str(form_obj.media)).  per-field {% include "core/includes/form_field.html" %} -> FormField(form_obj["x"]).
- Un-ported {% include %} (list_common_header.html, campaign_common_header.html, filter partials, form-fields partials
  you can't easily rebuild) -> raw(render_to_string("<that template>", {..the include's context + with-overrides..}, request=request)).
- {% include "core/includes/back.html" %} -> back_link(context, url=..., text=...) matching the include's params (no url => referer fallback).
  cancel.html -> cancel_link(context, ...).  {% safe_referer 'x' %} -> bridge.safe_referer(context["request"], "x").
- Form shell class "col-12 col-md-8 col-lg-6 px-0 vstack gap-3" -> PageShell(kind=FORM_SHELL) (define FORM_SHELL as that string).
- Page(title=<block head_title text>, content=<node>). For a template extending page.html use Page(layout="page", ...).
- Django AUTO-CALLS methods in templates: {{ x.foo }} renders x.foo() when foo is callable. In Python you MUST call it.
  ContentFighter.name is a METHOD (fighter.content_fighter.name()); ListFighter.fully_qualified_name is a property.

THEN write the golden test (build objects/form exactly as the view GET branch does; pass the exact context keys;
call assert_equivalent("<template>", context, request)). If the page's <title> is hard to match, rely on the default
scope="content" which ignores it.

DO NOT run pytest (a central run verifies everything). DO NOT edit any file other than the two you create.
Write ONLY the two files. Report a one-line status.
`;

phase("Convert");
const results = await parallel(
    PAGES.map(
        (page) => () =>
            agent(
                `${GUIDE}\n\n=== YOUR ASSIGNMENT ===\n` +
                    `Template: gyrinx/core/templates/${page.template}\n` +
                    `View file: ${page.view}\n` +
                    `Create component module: ${page.module}\n` +
                    `Create golden test: ${page.test}\n` +
                    `Golden fixture args (start point; add more conftest fixtures as needed): ${page.fixtureArgs}\n` +
                    (page.confirm
                        ? "This is a CONFIRM/delete page.\n"
                        : "This is likely a FORM or display page — inspect the template.\n") +
                    (page.note ? `Notes: ${page.note}\n` : ""),
                { label: `convert:${page.slug}`, phase: "Convert" },
            ).then((r) => ({ slug: page.slug, report: r })),
    ),
);
return results.filter(Boolean);
