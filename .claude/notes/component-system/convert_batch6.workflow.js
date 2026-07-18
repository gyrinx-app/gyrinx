export const meta = {
    name: "convert-batch6",
    description:
        "Convert campaign attribute-value pages + list content pages to components",
    phases: [{ title: "Convert" }],
};

const PAGES = [
    {
        slug: "campaign_attribute_value_new",
        template: "core/campaign/campaign_attribute_value_new.html",
        module: "gyrinx/components/pages/campaign_attribute_value_new.py",
        test: "gyrinx/components/tests/test_golden_campaign_attribute_value_new.py",
        view: "gyrinx/core/views/campaign/attributes.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); create a CampaignAttributeType (see pages test test_golden_campaign_attribute_type_edit.py / the attribute views for how); build the value-new view GET context + form',
        fixtureArgs: "user, make_campaign",
        note: "Reference the ALREADY-CONVERTED pages/campaign_attribute_type_new.py + pages/campaign_attribute_type_remove.py for the exact patterns. The attribute_value form uses attribute_value_form_fields.html — port each field with FormField.",
    },
    {
        slug: "campaign_attribute_value_edit",
        template: "core/campaign/campaign_attribute_value_edit.html",
        module: "gyrinx/components/pages/campaign_attribute_value_edit.py",
        test: "gyrinx/components/tests/test_golden_campaign_attribute_value_edit.py",
        view: "gyrinx/core/views/campaign/attributes.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); create a CampaignAttributeType + a CampaignAttributeValue; build the value-edit view GET context + form(instance=value)',
        fixtureArgs: "user, make_campaign",
        note: "Reference pages/campaign_attribute_type_edit.py for the edit pattern.",
    },
    {
        slug: "campaign_attribute_value_remove",
        template: "core/campaign/campaign_attribute_value_remove.html",
        module: "gyrinx/components/pages/campaign_attribute_value_remove.py",
        test: "gyrinx/components/tests/test_golden_campaign_attribute_value_remove.py",
        view: "gyrinx/core/views/campaign/attributes.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); create a CampaignAttributeType + CampaignAttributeValue; build the value-remove view GET context',
        fixtureArgs: "user, make_campaign",
        note: "CONFIRM page. Reference pages/campaign_attribute_type_remove.py.",
    },
    {
        slug: "list_about",
        template: "core/list_about.html",
        module: "gyrinx/components/pages/list_about.py",
        test: "gyrinx/components/tests/test_golden_list_about.py",
        view: "gyrinx/core/views/list/views.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); build the exact context the list_about view GET branch passes',
        fixtureArgs: "user, make_list",
        note: "A DISPLAY page (gang lore). Likely bridges list_common_header.html and uses {{ ...|safe_rich_text|safe }} — for that use bridge.safe_rich_text(value) (from .. import bridge). Read the template carefully and reproduce every include/tag; bridge un-ported includes via raw(render_to_string(...)).",
    },
    {
        slug: "list_notes",
        template: "core/list_notes.html",
        module: "gyrinx/components/pages/list_notes.py",
        test: "gyrinx/components/tests/test_golden_list_notes.py",
        view: "gyrinx/core/views/list/views.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); build the exact context the list_notes view GET branch passes',
        fixtureArgs: "user, make_list",
        note: "A DISPLAY page (gang notes). Same guidance as list_about: bridge.safe_rich_text for rich text, bridge un-ported includes via raw(render_to_string(...)).",
    },
];

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST read these reference files (do not skip):
- gyrinx/components/pages/campaign_attribute_type_new.py / _type_edit.py / _type_remove.py  (near-identical patterns)
- gyrinx/components/pages/fighter_xp.py           (bridges list_common_header via raw(render_to_string(...)))
- gyrinx/components/pages/_shared.py              (back_link / cancel_link)
- gyrinx/components/bridge.py                     (safe_rich_text, list_with_theme, etc.)
- gyrinx/components/design/__init__.py            (FormField, PageShell, CsrfInput, Alert, Button)
- gyrinx/components/tests/test_golden.py + test_golden_campaign_attribute_type_edit.py   (golden test + seeding examples)
- gyrinx/components/testing.py                    (assert_equivalent; scope="content" default)

THEN read your target template AND its view render() call for the EXACT context keys AND how the view builds
form/objects in its GET branch — replicate in the golden test.

KEY RULES:
- Raw HTML tags use SUBSCRIPT syntax tag(attrs)[child]; design components use CALL syntax.
- @register_page("<exact template name>"); fn(context) -> Page.
- Reproduce the template EXACTLY. Whitespace + attribute ORDER don't matter (golden normalises them).
- {% csrf_token %} -> CsrfInput(context["request"]).  {% url %} -> reverse(...).  {{ form }} -> raw(str(form_obj)).
  per-field form_field.html -> FormField(form_obj["x"]).  {{ v|safe_rich_text|safe }} -> bridge.safe_rich_text(v).
- Un-ported {% include %} -> raw(render_to_string("<template>", {..include context+overrides..}, request=request)).
- back.html -> back_link(context, ...). cancel.html -> cancel_link(context, ...). {% safe_referer 'x' %} -> bridge.safe_referer(request, "x").
- Form shell "col-12 col-md-8 col-lg-6 px-0 vstack gap-3" -> PageShell(kind=FORM_SHELL).
- Page(title=<head_title text>, content=<node>).
- Django AUTO-CALLS methods in templates: {{ x.foo }} => x.foo() if callable. ContentFighter.name is a METHOD; call .name().

THEN write the golden test (build objects/form as the view GET branch does; pass exact context keys; assert_equivalent).

DO NOT run pytest. DO NOT edit any file other than the two you create. Write ONLY the two files. Report one line.
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
                    `Golden fixture args: ${page.fixtureArgs}\n` +
                    `Golden object/form recipe: ${page.objects}\n` +
                    (page.note ? `Notes: ${page.note}\n` : ""),
                { label: `convert:${page.slug}`, phase: "Convert" },
            ).then((r) => ({
                slug: page.slug,
                module: page.module,
                test: page.test,
                report: r,
            })),
    ),
);
return results.filter(Boolean);
