export const meta = {
    name: "convert-more-pages",
    description:
        "Convert more Gyrinx form/confirm templates to components with golden tests",
    phases: [{ title: "Convert" }],
};

const PAGES = [
    {
        slug: "list_new",
        template: "core/list_new.html",
        module: "gyrinx/components/pages/list_new.py",
        test: "gyrinx/components/tests/test_golden_list_new.py",
        view: "gyrinx/core/views/list/views.py",
        objects:
            "build the form/context exactly as the new-list view GET branch does (find the form class it imports, e.g. NewListForm, and construct it the same way). If the view needs no object, just instantiate the form.",
        fixtureArgs: "user",
        note: 'Read the view render("core/list_new.html", ...) call. If it needs extra fixtures (content_house), add them: fixtureArgs can include content_house.',
    },
    {
        slug: "fighter_stats_edit",
        template: "core/list_fighter_stats_edit.html",
        module: "gyrinx/components/pages/fighter_stats.py",
        test: "gyrinx/components/tests/test_golden_fighter_stats.py",
        view: "gyrinx/core/views/fighter/stats.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); build the form exactly as the view GET branch does',
        fixtureArgs: "user, make_list, make_list_fighter",
    },
    {
        slug: "fighter_rules_edit",
        template: "core/list_fighter_rules_edit.html",
        module: "gyrinx/components/pages/fighter_rules.py",
        test: "gyrinx/components/tests/test_golden_fighter_rules.py",
        view: "gyrinx/core/views/fighter/rules.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); build the form exactly as the view GET branch does',
        fixtureArgs: "user, make_list, make_list_fighter",
    },
    {
        slug: "campaign_resource_type_remove",
        template: "core/campaign/campaign_resource_type_remove.html",
        module: "gyrinx/components/pages/campaign_resource_type_remove.py",
        test: "gyrinx/components/tests/test_golden_campaign_resource_type_remove.py",
        view: "gyrinx/core/views/campaign/resources.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); create a CampaignResourceType exactly as the reference test test_golden_campaign_resource_type_edit.py does (read it); build the context the remove view GET branch passes',
        fixtureArgs: "user, make_campaign",
        note: "This is a CONFIRM page (delete). Look at pages/campaign.py campaign_archive / pages/fighter.py for the confirm pattern.",
    },
    {
        slug: "campaign_attribute_type_remove",
        template: "core/campaign/campaign_attribute_type_remove.html",
        module: "gyrinx/components/pages/campaign_attribute_type_remove.py",
        test: "gyrinx/components/tests/test_golden_campaign_attribute_type_remove.py",
        view: "gyrinx/core/views/campaign/attributes.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); create the CampaignAttributeType the same way the attribute edit test/view does (read pages/campaign_attribute_type_new.py + the view); build the remove view context',
        fixtureArgs: "user, make_campaign",
        note: "CONFIRM page. Reference the confirm pattern in pages/fighter.py.",
    },
];

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST, read these reference files (do not skip):
- gyrinx/components/pages/campaign_resource_type_new.py  (FORM page: FormField per field, h1 + h2 campaign name)
- gyrinx/components/pages/campaign_resource_type_edit.py (FORM page with an existing instance)
- gyrinx/components/pages/fighter.py                     (CONFIRM pages: delete / kill)
- gyrinx/components/pages/campaign.py                    (campaign_archive/remove_list confirm patterns)
- gyrinx/components/pages/_shared.py                     (back_link / cancel_link)
- gyrinx/components/design/__init__.py                   (FormField, PageShell, CsrfInput, Alert, Button)
- gyrinx/components/tests/test_golden.py                 (golden test examples)
- gyrinx/components/tests/test_golden_campaign_resource_type_edit.py  (how to seed a resource type in a test)
- gyrinx/components/testing.py                           (assert_equivalent)

THEN read your target template AND its view render() call for the EXACT context keys AND how the view builds
the form/objects in its GET branch — replicate that in the golden test.

KEY RULES:
- Raw HTML tags from gyrinx.components.tags use SUBSCRIPT syntax: tag(attrs)[child]. Design components use CALL syntax.
- @register_page("<exact template name>"); function fn(context) -> Page.
- Reproduce the template EXACTLY (tags/classes/text/structure/conditionals). Whitespace + attribute ORDER don't matter.
- {% csrf_token %} -> CsrfInput(context["request"]).  {% url ... %} -> reverse(...).  {{ form }} -> raw(str(form_obj)).
  {{ form.media }} -> raw(str(form_obj.media)).  per-field form_field.html include -> FormField(form_obj["x"]).
- back.html -> back_link(context, url=..., text=...).  cancel.html -> cancel_link(context, ...).  {% safe_referer 'x' %} -> bridge.safe_referer(context["request"], "x").
- Form shell class "col-12 col-md-8 col-lg-6 px-0 vstack gap-3" -> PageShell(kind=FORM_SHELL).
- Page(title=<head_title text>, content=<node>).
- Django templates AUTO-CALL methods: {{ x.foo }} calls x.foo() if foo is a method. In Python you must call it.
  ContentFighter.name is a METHOD (.name()); ListFighter.fully_qualified_name is a property.

THEN write the golden test modeled on test_golden.py (build objects/form exactly as the view GET branch does,
pass the exact context keys, call assert_equivalent("<template>", context, request)).

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
