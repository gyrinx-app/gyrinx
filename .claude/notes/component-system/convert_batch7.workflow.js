export const meta = {
    name: "convert-batch7",
    description:
        "Convert campaign asset/resource/sub-asset family pages to components",
    phases: [{ title: "Convert" }],
};

const PAGES = [
    {
        slug: "campaign_asset_new",
        template: "core/campaign/campaign_asset_new.html",
        view: "gyrinx/core/views/campaign/assets.py",
    },
    {
        slug: "campaign_asset_edit",
        template: "core/campaign/campaign_asset_edit.html",
        view: "gyrinx/core/views/campaign/assets.py",
    },
    {
        slug: "campaign_asset_remove",
        template: "core/campaign/campaign_asset_remove.html",
        view: "gyrinx/core/views/campaign/assets.py",
        confirm: true,
    },
    {
        slug: "campaign_resource_modify",
        template: "core/campaign/campaign_resource_modify.html",
        view: "gyrinx/core/views/campaign/resources.py",
    },
    {
        slug: "campaign_sub_asset_remove",
        template: "core/campaign/campaign_sub_asset_remove.html",
        view: "gyrinx/core/views/campaign/sub_assets.py",
        confirm: true,
    },
].map((p) => ({
    ...p,
    module: `gyrinx/components/pages/${p.slug}.py`,
    test: `gyrinx/components/tests/test_golden_${p.slug}.py`,
    fixtureArgs: "user, make_campaign",
}));

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST read these already-converted reference files (do not skip):
- gyrinx/components/pages/campaign_resource_type_new.py / _edit.py / _remove.py  (form + confirm patterns)
- gyrinx/components/pages/campaign_attribute_value_new.py / _edit.py / _remove.py (form + confirm, seeded objects)
- gyrinx/components/pages/_shared.py            (back_link / cancel_link)
- gyrinx/components/design/__init__.py          (FormField, PageShell, CsrfInput, Alert, Button)
- gyrinx/components/tests/test_golden_campaign_attribute_value_edit.py  (how to seed campaign sub-objects in a test)
- gyrinx/components/testing.py                  (assert_equivalent; scope="content" default)

THEN read your target template AND its view render() call for the EXACT context keys AND how the view builds the
form/objects in its GET branch (fetch/creates the CampaignAsset / CampaignAssetType / CampaignResourceType /
CampaignSubAsset etc.). Replicate that object construction in the golden test.

KEY RULES:
- Raw HTML tags use SUBSCRIPT tag(attrs)[child]; design components use CALL syntax.
- @register_page("<exact template name>"); fn(context) -> Page.
- Reproduce the template EXACTLY. Whitespace + attribute ORDER don't matter.
- {% csrf_token %} -> CsrfInput(context["request"]).  {% url %} -> reverse(...).  {{ form }} -> raw(str(form_obj)).
  per-field form_field.html -> FormField(form_obj["x"]).  {{ v|safe_rich_text|safe }} -> bridge.safe_rich_text(v).
- Un-ported {% include %} -> raw(render_to_string("<template>", {..context+overrides..}, request=request)).
- back.html -> back_link(context, ...). cancel.html -> cancel_link(context, ...). {% safe_referer 'x' %} -> bridge.safe_referer(request, "x").
- Form shell "col-12 col-md-8 col-lg-6 px-0 vstack gap-3" -> PageShell(kind=FORM_SHELL).
- Page(title=<head_title text>, content=<node>).
- Django AUTO-CALLS methods in templates: {{ x.foo }} => x.foo() if callable. ContentFighter.name is a METHOD; call .name().

THEN write the golden test (build objects/form as the view GET branch does; pass exact context keys; assert_equivalent).
If you cannot construct an object cleanly, keep it minimal but faithful to what the view expects.

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
                    `Golden fixture args: ${page.fixtureArgs} (add more conftest fixtures if the view needs them)\n` +
                    (page.confirm
                        ? "This is a CONFIRM/delete page.\n"
                        : "This is a FORM page.\n") +
                    "Build the object(s) the view fetches in its GET branch (read the view to see how).\n",
                { label: `convert:${page.slug}`, phase: "Convert" },
            ).then((r) => ({ slug: page.slug, report: r })),
    ),
);
return results.filter(Boolean);
