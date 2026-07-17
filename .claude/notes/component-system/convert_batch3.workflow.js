export const meta = {
    name: "convert-fighter-pages",
    description:
        "Convert a batch of Gyrinx fighter/list edit + confirm templates to components with golden tests",
    phases: [{ title: "Convert" }],
};

const PAGES = [
    {
        slug: "list_fighter_xp_edit",
        template: "core/list_fighter_xp_edit.html",
        module: "gyrinx/components/pages/fighter_xp.py",
        test: "gyrinx/components/tests/test_golden_fighter_xp.py",
        view: "gyrinx/core/views/fighter/xp.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user)',
        fixtureArgs: "user, make_list, make_list_fighter",
    },
    {
        slug: "list_fighter_state_edit",
        template: "core/list_fighter_state_edit.html",
        module: "gyrinx/components/pages/fighter_state.py",
        test: "gyrinx/components/tests/test_golden_fighter_state.py",
        view: "gyrinx/core/views/fighter/state.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user)',
        fixtureArgs: "user, make_list, make_list_fighter",
    },
    {
        slug: "list_fighter_resurrect",
        template: "core/list_fighter_resurrect.html",
        module: "gyrinx/components/pages/fighter_resurrect.py",
        test: "gyrinx/components/tests/test_golden_fighter_resurrect.py",
        view: "gyrinx/core/views/fighter/crud.py",
        objects:
            'lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user)',
        fixtureArgs: "user, make_list, make_list_fighter",
        note: 'This is a CONFIRM page (no form). Context includes {fighter, list, fighter_cost, target_state, target_state_display, reason}. Read the view render() call to get the EXACT keys and reasonable values (e.g. target_state=ListFighter.ACTIVE, target_state_display=dict(ListFighter.INJURY_STATE_CHOICES).get(target_state, ""), reason=""). IMPORTANT: in Python, ContentFighter.name is a METHOD — call it as fighter.content_fighter.name(); use fighter.fully_qualified_name (a property) where the template uses it.',
    },
    {
        slug: "campaign_resource_type_edit",
        template: "core/campaign/campaign_resource_type_edit.html",
        module: "gyrinx/components/pages/campaign_resource_type_edit.py",
        test: "gyrinx/components/tests/test_golden_campaign_resource_type_edit.py",
        view: "gyrinx/core/views/campaign/resources.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); build the resource type + form exactly as the view GET branch does (read the view to see how it fetches the CampaignResourceType and builds the form with instance=...)',
        fixtureArgs: "user, make_campaign",
    },
    {
        slug: "campaign_asset_type_edit",
        template: "core/campaign/campaign_asset_type_edit.html",
        module: "gyrinx/components/pages/campaign_asset_type_edit.py",
        test: "gyrinx/components/tests/test_golden_campaign_asset_type_edit.py",
        view: "gyrinx/core/views/campaign/assets.py",
        objects:
            'campaign = make_campaign("Underhive Wars"); build the asset type + form exactly as the view GET branch does (read the view).',
        fixtureArgs: "user, make_campaign",
    },
];

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST, read these reference files (do not skip):
- gyrinx/components/pages/campaign_crud.py     (canonical FORM page: campaign_new/edit)
- gyrinx/components/pages/campaign_resource_type_new.py  (FORM page using FormField per field + h2 campaign name)
- gyrinx/components/pages/fighter.py            (canonical CONFIRM pages: list_fighter_delete / list_fighter_kill)
- gyrinx/components/pages/_shared.py            (back_link / cancel_link)
- gyrinx/components/design/__init__.py          (design components incl. FormField, PageShell, CsrfInput, Alert, Button)
- gyrinx/components/tests/test_golden.py        (golden test examples)
- gyrinx/components/testing.py                  (assert_equivalent)

THEN read your target template AND its view render() call (in the given view file) for the EXACT context keys
AND how the view builds the form / objects in its GET branch — replicate that in the golden test.

KEY RULES:
- Raw HTML tags (div, p, form, a, button, h1, h2, i, span, label, select, option, input_ ...) from gyrinx.components.tags
  use SUBSCRIPT syntax for children: tag(attrs)[child]. Design components (PageShell, CsrfInput, FormField, Alert...) use CALL syntax.
- Register with @register_page("<exact template name>"). Function is fn(context) -> Page.
- Reproduce the template EXACTLY (tags/classes/text/structure/conditionals). Whitespace + attribute ORDER don't matter.
- {% csrf_token %} -> CsrfInput(context["request"]).  {% url ... %} -> reverse(...).
- {{ form }} -> raw(str(form_obj)).  {{ form.media }} -> raw(str(form_obj.media)).
- Per-field {% include "core/includes/form_field.html" with field=form.x %} -> FormField(form_obj["x"]).
- {% include "core/includes/back.html" %} -> back_link(context) (match url=/text= params). cancel.html -> cancel_link(context).
- {% safe_referer 'x' %} -> bridge.safe_referer(context["request"], "x")  (from .. import bridge).
- The form shell class is "col-12 col-md-8 col-lg-6 px-0 vstack gap-3" (pass as kind= to PageShell).
- Page(title=<head_title text>, content=<node>).
- Django templates AUTO-CALL methods: {{ x.foo }} where foo is a method renders x.foo(). In Python you must call it:
  x.foo(). ContentFighter.name is a method (call .name()); ListFighter has .fully_qualified_name (a property).

THEN write the golden test modeled on test_golden.py:
  import pytest
  from django.test import RequestFactory
  from gyrinx.components.testing import assert_equivalent
  def _request(user, path="/"):
      request = RequestFactory().get(path); request.user = user; return request
  @pytest.mark.django_db
  def test_<slug>_matches_legacy(<fixtureArgs>):
      <build objects + form exactly as the view GET branch does>
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
                    `View file (read its render("${page.template}", ...) call + GET branch): ${page.view}\n` +
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
