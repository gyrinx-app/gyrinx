export const meta = {
    name: "convert-form-pages",
    description:
        "Convert a batch of Gyrinx form/edit templates to Python page components with golden tests",
    phases: [{ title: "Convert" }],
};

const PAGES = [
    {
        slug: "list_edit",
        template: "core/list_edit.html",
        module: "gyrinx/components/pages/list_edit.py",
        test: "gyrinx/components/tests/test_golden_list_edit.py",
        view: "gyrinx/core/views/list/views.py",
        formRecipe:
            'from gyrinx.core.forms.list import EditListForm; lst = make_list("Iron Skulls", owner=user); form = EditListForm(instance=lst)',
        fixtureArgs: "user, make_list",
        contextHint:
            'context keys are {form, list, ...} — read the view render() call for the exact keys and pass them (a None/"" for error_message/return_url is fine).',
    },
    {
        slug: "fighter_narrative",
        template: "core/list_fighter_narrative_edit.html",
        module: "gyrinx/components/pages/fighter_narrative.py",
        test: "gyrinx/components/tests/test_golden_fighter_narrative.py",
        view: "gyrinx/core/views/fighter/narrative.py",
        formRecipe:
            'from gyrinx.core.forms.list import EditListFighterNarrativeForm; lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); form = EditListFighterNarrativeForm(instance=fighter)',
        fixtureArgs: "user, make_list, make_list_fighter",
        contextHint:
            "context keys are {form, list, fighter, error_message, ...} — read the view render() call for the exact keys.",
    },
    {
        slug: "fighter_notes",
        template: "core/list_fighter_notes_edit.html",
        module: "gyrinx/components/pages/fighter_notes.py",
        test: "gyrinx/components/tests/test_golden_fighter_notes.py",
        view: "gyrinx/core/views/fighter/narrative.py",
        formRecipe:
            'from gyrinx.core.forms.list import EditListFighterNotesForm; lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); form = EditListFighterNotesForm(instance=fighter)',
        fixtureArgs: "user, make_list, make_list_fighter",
        contextHint:
            "context keys are {form, list, fighter, error_message, ...} — read the view render() call for the exact keys.",
    },
    {
        slug: "campaign_resource_type_new",
        template: "core/campaign/campaign_resource_type_new.html",
        module: "gyrinx/components/pages/campaign_resource_type_new.py",
        test: "gyrinx/components/tests/test_golden_campaign_resource_type_new.py",
        view: "gyrinx/core/views/campaign/resources.py",
        formRecipe:
            'from gyrinx.core.forms.campaign import CampaignResourceTypeForm; campaign = make_campaign("Underhive Wars"); form = CampaignResourceTypeForm()',
        fixtureArgs: "user, make_campaign",
        contextHint:
            "context keys are {form, campaign, ...} — read the view render() call for the exact keys.",
    },
    {
        slug: "campaign_attribute_type_new",
        template: "core/campaign/campaign_attribute_type_new.html",
        module: "gyrinx/components/pages/campaign_attribute_type_new.py",
        test: "gyrinx/components/tests/test_golden_campaign_attribute_type_new.py",
        view: "gyrinx/core/views/campaign/attributes.py",
        formRecipe:
            'campaign = make_campaign("Underhive Wars"); build the form exactly as the view GET branch does (find the form class it imports and how it is constructed)',
        fixtureArgs: "user, make_campaign",
        contextHint:
            "read the view render() call for the exact context keys and how the form is built.",
    },
    {
        slug: "campaign_asset_type_new",
        template: "core/campaign/campaign_asset_type_new.html",
        module: "gyrinx/components/pages/campaign_asset_type_new.py",
        test: "gyrinx/components/tests/test_golden_campaign_asset_type_new.py",
        view: "gyrinx/core/views/campaign/assets.py",
        formRecipe:
            'from gyrinx.core.forms.campaign import CampaignAssetTypeForm; campaign = make_campaign("Underhive Wars"); form = CampaignAssetTypeForm()',
        fixtureArgs: "user, make_campaign",
        contextHint: "read the view render() call for the exact context keys.",
    },
];

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST, read these reference files to learn the patterns and API (do not skip):
- gyrinx/components/pages/campaign_crud.py   (canonical FORM page components: campaign_new/campaign_edit — copy this style)
- gyrinx/components/pages/list_clone.py        (another form page rendering {{ form }})
- gyrinx/components/pages/_shared.py           (back_link / cancel_link helpers)
- gyrinx/components/design/__init__.py         (design components: PageShell, CsrfInput, Button, Alert, ...)
- gyrinx/components/tests/test_golden.py       (how golden tests are written — test_campaign_edit_matches_legacy is the closest model)
- gyrinx/components/testing.py                 (assert_equivalent signature)

THEN read your target template AND its view render() call (in the given view file) to get the EXACT context keys.

KEY RULES:
- Raw HTML tags (div, p, form, a, button, h1, i, span, ...) come from gyrinx.components.tags and use SUBSCRIPT
  syntax for children: tag(attrs)[child]. Design components (PageShell, CsrfInput, ...) use CALL syntax.
- Register with @register_page("<exact template name>"). The function is fn(context) -> Page.
- Reproduce the template EXACTLY: same tags, text, classes, structure, conditionals. Whitespace and attribute
  ORDER do not matter (the golden test normalises them) but every tag/class/text must match.
- {% csrf_token %} -> CsrfInput(context["request"]).  {{ form }} -> raw(str(form_obj)).  {{ form.media }} -> raw(str(form_obj.media)).
  {% url ... %} -> reverse(...).  {% safe_referer 'x' %} -> bridge.safe_referer(context["request"], "x") (import: from .. import bridge).
- {% include "core/includes/back.html" %} -> back_link(context) (add url=/text= to match the include's params).
  {% include "core/includes/cancel.html" %} -> cancel_link(context) (add url=/text= to match).
- The form shell class is "col-12 col-md-8 col-lg-6 px-0 vstack gap-3" (pass as kind= to PageShell).
- Page(title=..., content=...). title = the {% block head_title %} text.
- If the template renders fields individually with {% include "core/includes/form_field.html" with field=form.x %},
  use FormField(form_obj["x"]) from gyrinx.components.design. If it renders {{ form }} whole, use raw(str(form_obj)).

THEN write the golden test (model on test_golden.py's test_campaign_edit_matches_legacy):
  import pytest
  from django.test import RequestFactory
  from gyrinx.components.testing import assert_equivalent
  def _request(user, path="/"):
      request = RequestFactory().get(path); request.user = user; return request
  @pytest.mark.django_db
  def test_<slug>_matches_legacy(<fixtureArgs>):
      <build form + objects per the form recipe>
      request = _request(user)
      context = { ...exact keys the view passes... }
      assert_equivalent("<template>", context, request)

DO NOT run pytest. DO NOT edit any file other than the two you create. Write ONLY the two files. Report one line.
`;

phase("Convert");
const results = await parallel(
    PAGES.map(
        (page) => () =>
            agent(
                `${GUIDE}\n\n=== YOUR ASSIGNMENT ===\n` +
                    `Template: gyrinx/core/templates/${page.template}\n` +
                    `View file (read its render(\"${page.template}\", ...) call): ${page.view}\n` +
                    `Create component module: ${page.module}\n` +
                    `Create golden test: ${page.test}\n` +
                    `Golden fixture args: ${page.fixtureArgs}\n` +
                    `Form/object recipe for the golden test: ${page.formRecipe}\n` +
                    `Context: ${page.contextHint}\n`,
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
