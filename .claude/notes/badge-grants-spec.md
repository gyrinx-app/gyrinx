# Badges the content team can define, upload artwork for, and grant

Status: **built**. Written 2026-08-16, revised the same day to make badges
admin-authored rather than code-defined, then implemented.

Decisions taken while building: granted badges rank below the Patreon tiers, so
somebody who is both a supporter and a playtester keeps showing their supporter badge;
grants do not expire; the tester cohort is compiled by hand and pasted into the admin.

## Why

Badge eligibility today is entirely *derived*: `UserProfile` computes it live from
`patreon_status` and `User.is_staff` (`gyrinx/accounts/models.py:98-159`), against a
four-entry in-code registry (`gyrinx/badges.py`). There is no way to say "this person gets
this badge", no way to hand one to a cohort, and no way to add a badge without a deploy.

The goal: the content team defines a badge in the admin, uploads its artwork, and grants
it — to a person, to a cohort, or to everyone. The immediate use is a badge for the people
who tested n26.

## This is mostly assembly, not new invention

An earlier draft of this spec argued for keeping badge definitions in code because the
artwork is inlined with `mark_safe` and admin-uploaded SVG would be a stored-XSS surface.
That objection is obsolete — the codebase already solved it, twice over:

- **`gyrinx/svg.py`** — `sanitize_inline_svg`, a platform-owned bleach allowlist built for
  exactly this. Strips `<script>`, `<style>`, `<foreignObject>`, every `on*` handler and
  the `style` attribute; restricts `<use href>` to same-document fragments. Its docstring
  says it is platform-owned rather than an edition's precisely so the boundary does not
  exist twice and drift.
- **`n26/library/artwork.py`** — upload-or-paste-an-address handling for gang type icons.
  Resolves addresses against our own storage and refuses everything else (no outbound
  fetch, so no SSRF), caps size at 256KB, caches reads, and sanitises at *render* time so
  tightening the allowlist re-secures artwork already stored.

So the answer is yes, and the security work is done. What follows is mostly wiring
existing parts together, plus one genuine design decision about colour.

## Colour and crisp edges — decided, and one of them is a live bug

`sanitize_inline_svg` does two things beyond sanitising that matter here. Verified by
running it over the four committed badge SVGs:

- It **forces monochrome**: `_COLOR_ATTR_RE` rewrites every concrete `fill`/`stroke` to
  `currentColor`, preserving only `none` and `url(…)`. `scummer.svg`'s `fill="#B18…"`
  accents are flattened — the Patreon badges are two-tone today.
- It **drops `shape-rendering="crispEdges"`**, which is not in `_PRESENTATION_ATTRS`. The
  badges are 24×24 pixel art, so they would go soft at small sizes.

**The `shape-rendering` drop is already hurting production.** The gang type icons are
pixel art too, and they go through this sanitiser on every render — so they are being
drawn with antialiased edges right now. Adding `shape-rendering` to `_PRESENTATION_ATTRS`
is a fix for existing n26 artwork, not preparation for badges, and it should land on its
own rather than waiting behind this work.

Decisions taken:

1. **Preserve colour.** `sanitize_inline_svg` gets a `preserve_colour=True` option that
   skips `_COLOR_ATTR_RE`, and badge rendering passes it. Safe — colour values are inert,
   and the attribute allowlist (which excludes `style`) is what actually holds the line.
   One tightening to do on that path: `_normalise_color` currently preserves *any* value
   starting with `url(`, so the colour-preserving path must restrict it to `url(#` or
   stored artwork could name an external paint server.
2. **Add `shape-rendering` to `_PRESENTATION_ATTRS`.** Purely presentational, no attack
   surface, fixes gang type icons as a side effect.
3. **Do not route the four committed badges through the sanitiser.** They are trusted repo
   assets and inlining them verbatim is both cheaper and lossless. Two render paths is the
   correct answer here, not an accident.

Monochrome stays available to anyone who wants it — draw the artwork in `currentColor`
and nothing rewrites it.

## Promote the artwork module to the platform

`n26/library/artwork.py` is an n26 module, but badges are platform-owned — both editions
render them through `gyrinx/site/templatetags/badge_tags.py`. Move it to `gyrinx/artwork.py`
alongside `gyrinx/svg.py`, whose docstring already makes exactly this argument for exactly
this reason. The module has no n26 imports; only the module-level `UPLOAD_PREFIX =
"gang-type-icons/"` and some docstring wording are edition-flavoured.

Changes needed: make the prefix a parameter of `store(upload, prefix=…)` so badges land
under `badges/`, and leave `n26.library.artwork` importing from the platform so nothing in
n26 has to change at once.

`clean_onto(form, cleaned, "artwork_url", "artwork_upload")` then gives the badge admin
the same upload-or-paste-an-address control the gang type admin already has, with the same
rule (an upload wins, so there is never a state where the two controls disagree).

## Models

Both in `gyrinx/accounts/models.py`, beside `UserProfile`. Badges are account flair, not
game content, so they are not pack-aware and do not inherit `Content`.

```python
class Badge(Base):
    """A badge the content team defined. Artwork lives in our storage."""

    slug = models.SlugField(max_length=50, unique=True)
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=200)   # the hover tooltip
    artwork_url = models.CharField(max_length=500, blank=True, default="")
    rank = models.IntegerField(default=0)   # below the Patreon tiers
    auto_display = models.BooleanField(default=False)
    archived = ...          # from Archived, so a retired badge stops appearing
    history = HistoricalRecords()
```

```python
class BadgeGrant(Base):
    class Audience(models.TextChoices):
        USER = "user", "A single user"
        EVERYONE = "everyone", "Everyone"

    badge = models.ForeignKey(Badge, on_delete=models.CASCADE,
                              related_name="grants")
    audience = models.CharField(max_length=20, choices=Audience.choices,
                                default=Audience.USER)
    user = models.ForeignKey("auth.User", null=True, blank=True,
                             on_delete=models.CASCADE, related_name="badge_grants")
    granted_by = models.ForeignKey("auth.User", null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="badges_granted")
    reason = models.TextField(blank=True, default="")   # internal note, never rendered

    history = HistoricalRecords()
```

`Base` supplies the UUID pk and `created`/`modified`, so there is no separate `granted_at`.
`HistoricalRecords` gives the audit trail, which means grants can be hard-deleted rather
than carrying a `revoked_at` — the deletion is recorded.

**The FK is doing real security work.** In the earlier draft, `badge` was a slug string and
needed a `grantable` flag on the registry, because otherwise a grant row naming the slug
`staff` would hand out staff flair and bypass `is_staff`. With grants pointing at `Badge`
rows, and the Patreon and staff badges living in code and *not* as `Badge` rows, that hole
is structurally impossible rather than defended against. Keep it that way: the four derived
badges must never be seeded into the `Badge` table.

Constraints on `BadgeGrant`:

- Check: `user` is non-null iff `audience == USER`.
- Partial unique on `(badge, user)` where `audience = 'user'`.
- Partial unique on `(badge)` where `audience = 'everyone'`.

Any `get_or_create` in the bulk-grant paths must use lookup fields matching those partial
constraints exactly, or it will miss an existing row and then trip the constraint — the
same shape as the `Lower("name")` trap hit twice in #2164.

`Badge.clean()` must reject a slug that collides with the code registry, since
`UserProfile.selected_badge` stores a bare slug and the two namespaces share it.

## Two providers, one shape

`display_badge` and the template tags should not care where a badge came from. Give the
DB model the same shape the `BadgeDef` dataclass has (`slug`, `title`, `description`,
`rank`, `auto_display`, plus a way to get its SVG source) and resolve both through one
lookup:

- `all_badges()` — the code registry plus every non-archived `Badge` row, keyed by slug.
- Artwork: code badges read from staticfiles and inline verbatim (existing `_badge_svg`);
  DB badges go `artwork.read(address)` → `sanitize_inline_svg`. Both already cache.

`gyrinx/badges.py` keeps the four derived badges because their *eligibility* is code
anyway — the Patreon title-to-rank mapping and `is_staff` — and their artwork ships with
the app. Nothing is gained by moving them into the table and the two-tone palette is lost.

## Eligibility

`UserProfile` gains a third source, unioned with the existing two:

```python
@property
def granted_badges(self) -> list[Badge]:
    return [g.badge for g in self.active_badge_grants]

@property
def available_badges(self):
    badges = list(self.unlocked_badges)
    if self.user.is_staff:
        badges.append(STAFF_BADGE)
    badges.extend(self.granted_badges)
    return badges
```

`active_badge_grants` = this user's grants plus every EVERYONE grant, excluding any
whose badge is archived. Grants do not expire, so there is no clock in the read path.

`display_badge` needs one change — the default pick considers only auto-display badges:

```python
defaults = [b for b in available if b.auto_display]
return max(defaults, key=lambda b: b.rank) if defaults else None
```

An explicit selection still wins, whether or not the badge auto-displays.

Everything downstream is already generic: the picker at `/accounts/badge/` builds its
choices from `available_badges`, so a new badge appears with no template change, and
`clean_selected_badge` re-checks eligibility so a tampered POST is still rejected.

**Revocation needs no cleanup.** Deleting a grant leaves a stale `selected_badge`, and
`display_badge` already falls through to the default in that case. That is the payoff of
deriving on read; don't replace it with a signal that rewrites profiles.

## Granting to everyone

One row: `audience=EVERYONE`, no user. USER and EVERYONE only — a GROUP audience is the
obvious third and the shape leaves room, but each audience adds a read path.

The thing to get right is that **granting to everyone must not change what anybody
displays.** With a few thousand profiles, a badge that auto-displays would appear beside
every username overnight. Hence `auto_display`, which defaults to `False` on `Badge` for
this reason: an everyone-grant widens the picker without touching a rendered page. The
admin should state the affected-user count before the row is written.

For the n26 tester badge the opposite is right — `auto_display=True`, so testers see it
without having to discover the picker.

## The hot path

This is the real constraint, more than the models are.

`user_badge` renders once per row on the list, campaign and pack indexes, and today costs
zero queries beyond the profile that call sites already `select_related` — the tag's
docstring says so. Three new sources, with very different risk:

- **The `Badge` table.** Tens of rows at most. Cache the whole table as one slug-keyed
  dict, invalidated on `post_save`/`post_delete`. Effectively free, and a safe thing to
  cache: small, bounded, invalidated on write.
- **Everyone-grants.** Not per-user, so the same treatment — one cached global lookup.
- **Per-user grants.** The N+1 risk. Prefetch at the call sites
  (`prefetch_related("owner__badge_grants__badge")`) and pin it with a query-count test
  against the existing snapshot at `n23/core/tests/fixtures/performance_view_queries.json`.
  That turns a silent N+1 into a failing test, which is the part that matters — the failure
  mode is a missed prefetch on a page nobody profiled.

If profiling later demands it, a `UserProfile.has_badge_grants` boolean maintained by
signals would skip the query for the overwhelming majority of users with none. Do not
denormalise the granted badges themselves onto the profile — that is the content-cache
pattern #1860 spent a programme deleting.

Plumbing detail: the FK's `related_name` sits on `User`, so the prefetch path is
`owner__badge_grants` while the property reading it lives on `UserProfile` and goes through
`self.user.badge_grants.all()`.

## Admin

- `BadgeAdmin` — the content team's surface. `slug`, `title`, `description`, `rank`,
  `auto_display`, plus the artwork pair: an `artwork_url` text field and an
  `artwork_upload` file field wired through `artwork.clean_onto`, copying `GangTypeForm`
  (`n26/library/admin.py:31`). A rendered preview in the changelist is worth the few lines
  — badge artwork is unreadable as a URL.
- `BadgeGrantAdmin` — list by badge / audience / user / created / granted_by / expires_at;
  filter by badge and audience; `autocomplete_fields` on user; `granted_by` set from
  `request.user` on save.
- Bulk action on `UserAdmin` and `UserProfileAdmin`: "Grant badge to selected users", with
  an intermediate page to pick the badge. Mirror the existing `add_users_to_group` action
  (`gyrinx/accounts/admin.py:18`, template `core/admin/add_users_to_group.html`) rather
  than inventing a shape.
- A paste-a-list page taking usernames or emails, since the tester cohort probably lives in
  a spreadsheet rather than in a queryset. It must report unmatched identifiers back rather
  than silently skipping them.

Bulk grants use `get_or_create` so re-running is idempotent.

**Permissions.** Defining a badge and granting one are different powers — a grant to
everyone is site-wide. Give the content team `add`/`change_badge` freely; consider keeping
`add_badgegrant` for the EVERYONE audience narrower, or at minimum make the confirmation
step state the blast radius.

## Build order

1. `shape-rendering` in the allowlist, and a `preserve_colour` option on
   `sanitize_inline_svg` (with `url(` tightened to `url(#` on that path). Small,
   self-contained, testable — and the allowlist half fixes the gang type icons, so it need
   not wait for the rest.
2. Promote `artwork.py` to the platform with a `prefix` parameter; n26 imports from there.
3. `Badge` + `BadgeGrant` + migration + admin + bulk actions.
4. Eligibility union on `UserProfile`, `auto_display` filter in `display_badge`, two-provider
   badge lookup in the template tags.
5. Prefetch at the call sites the tag docstring lists; query-count test.
6. Content team creates the playtester badge; grant the cohort.

Steps 1–5 ship with no user-visible change, so they can land ahead of any decision about
the badge itself.

## Tests

Extend the three existing files rather than adding a fourth: `n23/core/tests/test_badges.py`
(eligibility), `n23/core/tests/test_badge_views.py` (picker and tamper rejection),
`n26/tests/test_badges.py` (renders in both editions).

Cases worth pinning:

- The four committed badges still render byte-for-byte as they do today (they must not
  start going through the sanitiser).
- Uploaded artwork carrying `<script>`, an `on*` handler and a `<foreignObject>` renders
  none of them.
- With `preserve_colour`, concrete fills survive and `shape-rendering` survives; without
  it, existing behaviour is unchanged. A `fill="url(https://…)"` is refused on the
  colour-preserving path.
- A grant whose badge is archived grants nothing.
- An EVERYONE grant with `auto_display=False` widens the picker and changes no rendered
  page.
- Revoking a grant that was the selected badge falls back to the default rather than
  rendering an empty span.
- A `Badge` slug colliding with a code-registry slug is rejected.
- Query count on a list index does not scale with row count.

## What is left

Nothing in the code. The remaining steps are content work, done in the admin:

1. Create the playtester badge and upload its artwork.
2. Set `auto_display` on it, so testers see it without finding the picker.
3. Paste the tester list into "Grant to a list of people".

One thing worth knowing: an "N26 Testers" group already exists, planted by the data
migration `accounts/0002_n26_testers_group`, and nothing reads it. If the cohort is
already in it, the changelist can be filtered by that group and the selection-based
action used instead of pasting.
