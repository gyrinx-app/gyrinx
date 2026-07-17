export const meta = {
    name: "convert-confirm-pages",
    description:
        "Convert a batch of Gyrinx confirm/simple templates to Python page components with golden tests",
    phases: [{ title: "Convert" }],
};

// Each page: template name, the module file to CREATE, the golden test file to
// CREATE, the view context keys, and a fixture recipe for the golden test.
const PAGES = [
    {
        slug: "fighter_restore",
        template: "core/list_fighter_restore_confirm.html",
        module: "gyrinx/components/pages/fighter_restore.py",
        test: "gyrinx/components/tests/test_golden_fighter_restore.py",
        contextKeys: "{fighter, list, fighter_cost}",
        fixtures: `lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); context = {"list": lst, "fighter": fighter, "fighter_cost": fighter.cost_int()}`,
        fixtureArgs: "user, make_list, make_list_fighter",
    },
    {
        slug: "fighter_captured",
        template: "core/list_fighter_mark_captured.html",
        module: "gyrinx/components/pages/fighter_captured.py",
        test: "gyrinx/components/tests/test_golden_fighter_captured.py",
        contextKeys: "{fighter, list, capturing_lists}",
        fixtures: `lst = make_list("Iron Skulls", owner=user); fighter = make_list_fighter(lst, "Boss", owner=user); context = {"list": lst, "fighter": fighter, "capturing_lists": []}`,
        fixtureArgs: "user, make_list, make_list_fighter",
        note: "The template uses fighter.term_proximal_demonstrative|lower and a <select> over capturing_lists (empty list is fine). Reproduce the |lower with str(...).lower().",
    },
    {
        slug: "list_archive",
        template: "core/list_archive.html",
        module: "gyrinx/components/pages/list_archive.py",
        test: "gyrinx/components/tests/test_golden_list_archive.py",
        contextKeys: "{list, is_in_active_campaign, active_campaigns}",
        fixtures: `lst = make_list("Iron Skulls", owner=user); context = {"list": lst, "is_in_active_campaign": False, "active_campaigns": []}`,
        fixtureArgs: "user, make_list",
        note: "Has an archived/not-archived branch and an is_in_active_campaign branch. The golden test uses a non-archived list not in a campaign, so only that branch renders — reproduce BOTH branches in the component (mirror campaign_archive in pages/campaign.py) but the test only exercises one. The top back link and bottom cancel link both use back.html/cancel.html with NO url (referer fallback) — use back_link(context) and cancel_link(context).",
    },
];

const GUIDE = `
You are converting ONE legacy Django template into a Python page component in the
gyrinx.components system, plus a golden-equivalence test proving byte-identical output.

FIRST, read these reference files to learn the exact patterns and API (do not skip):
- gyrinx/components/pages/fighter.py         (canonical page components: list_fighter_delete, list_fighter_kill)
- gyrinx/components/pages/campaign.py         (campaign_archive shows the archived/not-archived branch pattern)
- gyrinx/components/pages/_shared.py          (back_link / cancel_link helpers — use these, they port back.html/cancel.html)
- gyrinx/components/design/__init__.py        (available design components: Alert, Button, PageShell, CsrfInput, etc.)
- gyrinx/components/layout.py (the Page dataclass only — class Page near the top)
- gyrinx/components/tests/test_golden.py      (how golden tests are written)
- gyrinx/components/testing.py                (assert_equivalent signature)

KEY RULES:
- Raw HTML tags (div, p, form, ul, li, a, button, i, strong, span, select, option, label, h1, h3, input_ ...)
  are imported from gyrinx.components.tags and use the SUBSCRIPT syntax for children: tag(attrs)[child, child].
  Design components (Alert, Button, PageShell, ...) use the CALL syntax: Alert("text", variant="warning").
- Register with @register_page("<exact template name>").
- The component is a function(context) -> Page. Read the target template AND the view's render(...) call
  (grep the template name under gyrinx/core/views/) to confirm the exact context keys.
- Reproduce the template EXACTLY: same tags, text, classes, structure, and conditionals. Whitespace and
  attribute order do NOT matter (the golden test normalises them) but every tag/class/text must match.
- Use back_link(context, url=..., text=...) / cancel_link(context, url=..., text=...) exactly as the template's
  {% include "core/includes/back.html" %} / cancel.html do (match their url= / text= params; if the include has
  no url, call back_link(context) with no url so it uses the referer fallback).
- CSRF: replace {% csrf_token %} with CsrfInput(context["request"]).
- reverse(...) for all {% url %} tags. The form shell class is "col-12 col-md-8 col-lg-6 px-0 vstack gap-3".
- For Django form objects render with raw(str(form)); for {{ form.media }} use raw(str(form.media)).
- Alerts: the design Alert renders <div class="alert alert-{variant} alert-icon" role="alert"><i class="bi-..."></i><div>...children...</div></div>.
  Match the legacy alert's variant + extra classes via class_="mb-0" etc. If the legacy alert body is a <div> with
  a <strong> title and a <p>, pass those as children (a fragment).

THEN write the golden test file. Model it on test_golden.py exactly:
  import pytest
  from django.test import RequestFactory
  from gyrinx.components.testing import assert_equivalent
  def _request(user, path="/"):
      request = RequestFactory().get(path); request.user = user; return request
  @pytest.mark.django_db
  def test_<slug>_matches_legacy(<fixtureArgs>):
      <fixtures>
      request = _request(user)
      assert_equivalent("<template>", context, request)

DO NOT run pytest (a central run verifies everything). DO NOT edit any file other than the two you create.
Write ONLY the two files. Report a one-line status.
`;

phase("Convert");
const results = await parallel(
    PAGES.map(
        (page) => () =>
            agent(
                `${GUIDE}\n\n=== YOUR ASSIGNMENT ===\n` +
                    `Template: ${page.template}\n` +
                    `Create component module: ${page.module}\n` +
                    `Create golden test: ${page.test}\n` +
                    `View context keys: ${page.contextKeys}\n` +
                    `Golden test fixture args: ${page.fixtureArgs}\n` +
                    `Golden test fixture setup: ${page.fixtures}\n` +
                    (page.note ? `Notes: ${page.note}\n` : "") +
                    `\nRead the target template at gyrinx/core/templates/${page.template} and the matching view, then write both files.`,
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
