export const meta = {
    name: "convert-batch5",
    description:
        "Convert more Gyrinx templates (forms, confirms, page.html layout) to components",
    phases: [{ title: "Convert" }],
};

const PAGES = [
    {
        slug: "fighter_skills_edit",
        template: "core/list_fighter_skills_edit.html",
        module: "gyrinx/components/pages/fighter_skills.py",
        test: "gyrinx/components/tests/test_golden_fighter_skills.py",
        view: "gyrinx/core/views/fighter/skills.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); build the exact context the view GET branch passes',
        fixtureArgs: "user, make_list, make_list_fighter",
    },
    {
        slug: "fighter_psyker_powers_edit",
        template: "core/list_fighter_psyker_powers_edit.html",
        module: "gyrinx/components/pages/fighter_psyker_powers.py",
        test: "gyrinx/components/tests/test_golden_fighter_psyker_powers.py",
        view: "gyrinx/core/views/fighter/powers.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); build the exact context the view GET branch passes',
        fixtureArgs: "user, make_list, make_list_fighter",
    },
    {
        slug: "campaign_asset_type_remove",
        template: "core/campaign/campaign_asset_type_remove.html",
        module: "gyrinx/components/pages/campaign_asset_type_remove.py",
        test: "gyrinx/components/tests/test_golden_campaign_asset_type_remove.py",
        view: "gyrinx/core/views/campaign/assets.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); create a CampaignAssetType like the reference test test_golden_campaign_asset_type_edit.py does; build the remove view GET context',
        fixtureArgs: "user, make_campaign",
        note: "CONFIRM page (delete). Reference pages/campaign_resource_type_remove.py for the near-identical pattern.",
    },
    {
        slug: "list_credits_edit",
        template: "core/list_credits_edit.html",
        module: "gyrinx/components/pages/list_credits_edit.py",
        test: "gyrinx/components/tests/test_golden_list_credits_edit.py",
        view: "gyrinx/core/views/list/views.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); build the exact context the credits-edit view GET branch passes (find the form class)',
        fixtureArgs: "user, make_list",
        note: 'IMPORTANT: this template extends core/layouts/page.html (NOT base.html). It overrides the blocks page_title, page_description, page_content. Return Page(layout="page", title=<head_title text>, description=<page_description content node or "">, content=<page_content node>). The SimplePage layout renders <h1 class="h3 mb-0">{title-as-page_title}</h1> — BUT note page.html\'s page_title is a SEPARATE block from head_title. Read page.html and layout.py SimplePage carefully: SimplePage uses page.title for BOTH the <title> and the <h1>. If head_title and page_title differ in the template, set Page.title to the page_title text and handle head_title via... (they are usually the same). Compare with scope="content" in the golden test if the <title> differs: assert_equivalent(..., ) defaults to content scope which ignores <title>, so focus on getting the #content correct.',
    },
];

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST, read these reference files (do not skip):
- gyrinx/components/pages/campaign_resource_type_new.py / campaign_resource_type_remove.py  (FORM + CONFIRM patterns)
- gyrinx/components/pages/fighter_xp.py / fighter_state.py   (fighter edit pages that bridge list_common_header)
- gyrinx/components/pages/_shared.py                         (back_link / cancel_link)
- gyrinx/components/layout.py                                (the Page dataclass AND SimplePage — for page.html layout)
- gyrinx/components/design/__init__.py                       (FormField, PageShell, CsrfInput, Alert, Button)
- gyrinx/components/tests/test_golden.py                     (golden test examples)
- gyrinx/components/testing.py                               (assert_equivalent — supports scope="content" (default) and scope="page")

THEN read your target template AND its view render() call for the EXACT context keys AND how the view builds
the form/objects in its GET branch — replicate that in the golden test.

KEY RULES:
- Raw HTML tags from gyrinx.components.tags use SUBSCRIPT syntax: tag(attrs)[child]. Design components use CALL syntax.
- @register_page("<exact template name>"); function fn(context) -> Page.
- Reproduce the template EXACTLY (tags/classes/text/structure/conditionals). Whitespace + attribute ORDER don't matter.
- {% csrf_token %} -> CsrfInput(context["request"]).  {% url ... %} -> reverse(...).  {{ form }} -> raw(str(form_obj)).
  {{ form.media }} -> raw(str(form_obj.media)).  per-field form_field.html include -> FormField(form_obj["x"]).
- If a template {% include %}s a shared partial that has NO component port (e.g. list_common_header.html,
  campaign_common_header.html), bridge it: raw(render_to_string("<that template>", {..the include's context+with-overrides..}, request=request)).
- back.html -> back_link(context, url=..., text=...).  cancel.html -> cancel_link(context, ...).  {% safe_referer 'x' %} -> bridge.safe_referer(context["request"], "x").
- Form shell class "col-12 col-md-8 col-lg-6 px-0 vstack gap-3" -> PageShell(kind=FORM_SHELL).
- Page(title=<head_title text>, content=<node>). For a template extending page.html use Page(layout="page", title=..., description=..., content=...).
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
