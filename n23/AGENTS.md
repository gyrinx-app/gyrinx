# N23 development instructions

N23 is server rendered. Django renders page state and forms, while Bootstrap
and the project's Cotton components provide the UI. Read the instructions under
`core/` before changing models, views, templates or static assets.

## URL-driven UI

Put any state that changes the visible form variant, fields, choices, section,
modal or tab in the URL. Use a path segment or query parameter. The view then
builds the matching form and context.

- Render variant selectors as links or GET forms pointing to the same view.
- Build conditional fields and choices on the server, and decide there which
  fields are required. Remove fields that do not apply to the current variant.
- Do not use JavaScript `change` handlers to swap options, hide form groups, or
  alter validation.
- JavaScript may add live previews, search, asynchronous hints and autocomplete
  over a server-rendered set. It may also manage focus and scrolling. The page
  must remain usable and linkable without JavaScript.

Use `add_house_rule` and `house_rule_form.html` as the variant-picker example.
The `gyrinx-conventions` skill explains why the URL, view and template have
these responsibilities.

## Archived content pack behaviour

Setting `archived` on a `CustomContentPack` or `CustomContentPackItem` hides it
from the owner's administration and discovery pages. Existing subscribers
retain the content in their lists and campaigns.

- Subscriber read paths driven by `list.packs` or `campaign.packs` must not
  filter archived packs or items. Use
  `ContentQuerySet.with_packs(..., include_archived_items=True)`.
- Pack-owner libraries, galleries, featured listings, new-subscription pickers,
  and live-item uniqueness checks must exclude archived rows.
- Apply this rule to every pack-aware content type, including fighters,
  equipment, assignments, profiles, accessories, skills, rules and psyker
  content.

When extending pack behaviour, test the distinction between an existing
subscriber and an owner or new subscriber.

## N23 implementation rules

- The fighter list is performance-sensitive. When `ListFighter` fetches a new
  relation, follow the prefetch rule in [`core/AGENTS.md`](core/AGENTS.md).
- Use the existing fixtures in the root `conftest.py`; N23 tests are module-level
  pytest functions marked with `@pytest.mark.django_db`.
- Use the design-system and microcopy skills before editing rendered UI or
  user-facing strings.
- Detailed cost-system references live in
  [`docs/n23/fighter-cost-system-reference.md`](../docs/n23/fighter-cost-system-reference.md)
  and [`docs/n23/technical-design/cost-propagation-architecture.md`](../docs/n23/technical-design/cost-propagation-architecture.md).
