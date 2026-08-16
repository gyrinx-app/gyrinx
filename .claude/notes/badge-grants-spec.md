# BadgeGrant — awarding badges to people, not deriving them

Status: spec, not built. Written 2026-08-16.

## Why

Badge eligibility today is entirely *derived*: `UserProfile` computes it live from
`patreon_status` and `User.is_staff` (`gyrinx/accounts/models.py:98-159`). That is a good
property — lapsed supporters and ex-staff lose their badge with no cleanup job — but it
means there is no way to say "this person gets this badge", and no way to hand a badge to
a cohort. The immediate need is a badge for the people who tested n26. The general need is
awarding badges without a deploy.

The split this proposes: **what a badge is stays in code, who has it moves to the
database.**

## The code/database line

Keep `gyrinx/badges.py` as the authority on artwork, title, rank and tooltip copy. Adding
a badge stays a small PR — one SVG plus one registry line.

Do *not* move badge definitions into an admin-managed table. The artwork is read from
static files and inlined with `mark_safe`, guarded by an explicit comment that these are
trusted repo assets and not user uploads (`gyrinx/site/templatetags/badge_tags.py`). An
admin-uploaded SVG is a stored-XSS surface that would need real sanitisation before it
could be inlined. The registry is also what keeps both editions in step — n26 asks the
platform which badge to draw and gets a `BadgeDef` back.

So: artwork and copy in code (needs a deploy, rarely changes), grants in the database
(no deploy, changes often). That split is what makes "more of this in future" cheap
without opening the hole.

## Registry changes

Two fields on `BadgeDef`, both defaulted so the existing four entries are untouched:

```python
@dataclass(frozen=True)
class BadgeDef:
    slug: str
    title: str
    rank: int
    svg: str
    description: str
    grantable: bool = False    # may be awarded via BadgeGrant
    auto_display: bool = True  # shows by default when available, without being picked
```

`grantable` is load-bearing, not decoration. Without it, a grant row carrying the slug
`staff` would hand staff flair to anyone and bypass `is_staff` entirely. The four existing
badges keep `grantable=False`; only registry entries that opt in can ever be named by a
grant. Enforced in `BadgeGrant.clean()` and by restricting the admin's choices.

`auto_display` decides whether a badge can be the *default* shown for someone who has not
picked. This is what makes granting to everyone safe — see below.

Rank bands, so the ordering stays legible: 1–3 Patreon tiers, 10–99 granted badges, 100
staff. Rank only orders the default pick among auto-display badges; it is not a hierarchy.

## The model

Lives in `gyrinx/accounts/models.py` beside `UserProfile` — badges are platform-owned and
both editions consume them through the template-tag seam.

```python
class BadgeGrant(Base):
    class Audience(models.TextChoices):
        USER = "user", "A single user"
        EVERYONE = "everyone", "Everyone"

    badge = models.CharField(max_length=50)          # a registry slug
    audience = models.CharField(max_length=20, choices=Audience.choices,
                                default=Audience.USER)
    user = models.ForeignKey("auth.User", null=True, blank=True,
                             on_delete=models.CASCADE, related_name="badge_grants")
    granted_by = models.ForeignKey("auth.User", null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="badges_granted")
    reason = models.TextField(blank=True, default="")   # internal note, never rendered
    expires_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()
```

`Base` already supplies the UUID pk and `created`/`modified`, so there is no separate
`granted_at`. `HistoricalRecords` gives the audit trail, which is the project idiom and
means grants can be hard-deleted rather than carrying a `revoked_at` flag — the deletion
is recorded.

Constraints:

- Check: `user` is non-null iff `audience == USER`.
- Partial unique on `(badge, user)` where `audience = 'user'`.
- Partial unique on `(badge)` where `audience = 'everyone'`.

Any `get_or_create` in the bulk-grant paths must use lookup fields that match those
partial constraints exactly, or it will miss an existing row and then trip the constraint
— the same shape as the `Lower("name")` trap hit twice in #2164.

`badge` is validated against the registry in `clean()` rather than by a DB constraint,
because the registry is code. A grant naming a slug that no longer exists is inert: the
eligibility union filters against the registry on read, so deleting a badge from
`badges.py` cannot resurrect anything.

## Eligibility

`UserProfile` gains a third source, unioned with the existing two:

```python
@property
def granted_badges(self) -> list[BadgeDef]:
    slugs = {g.badge for g in self.active_badge_grants}
    return [b for b in ALL_BADGES if b.grantable and b.slug in slugs]

@property
def available_badges(self) -> list[BadgeDef]:
    badges = list(self.unlocked_badges)
    if self.user.is_staff:
        badges.append(STAFF_BADGE)
    badges.extend(self.granted_badges)
    return badges
```

`active_badge_grants` = this user's grants plus every EVERYONE grant, excluding anything
with `expires_at` in the past.

`display_badge` needs one change — the default pick considers only auto-display badges:

```python
defaults = [b for b in available if b.auto_display]
if not defaults:
    return None
return max(defaults, key=lambda b: b.rank)
```

An explicit selection still wins as it does today, whether or not the badge auto-displays.

Everything downstream is already generic. The picker at `/accounts/badge/` builds its
choices from `available_badges`, so a new badge appears with no template change, and
`clean_selected_badge` re-checks eligibility so a tampered POST is still rejected.

**Revocation needs no cleanup.** Deleting a grant leaves a stale `selected_badge` on the
profile, and `display_badge` already handles that case — a selection that is no longer
eligible falls through to the default. This is the payoff of deriving on read, and it
should stay that way rather than being replaced by a signal that rewrites profiles.

## Granting to everyone

One row: `audience=EVERYONE`, no user. The generalisation is deliberately narrow — USER
and EVERYONE only. A GROUP audience is the obvious third, and the model shape leaves room
for it, but nothing needs it yet and each audience adds a read path.

The thing to get right is that **granting to everyone must not change what anybody
displays.** With a few thousand profiles, a badge that auto-displays would silently appear
beside every username overnight. Hence `auto_display`: an everyone-grant should almost always
name a badge with `auto_display=False`, which widens the picker without touching a single
rendered page. The admin should show the affected-user count on the confirmation step so
the blast radius is stated before the row is written.

For the n26 tester badge the opposite is right — `auto_display=True`, so testers see it
without having to discover the picker.

## The hot path

This is the real design constraint, more than the model is.

`user_badge` renders once per row on the list, campaign and pack indexes. Today it costs
zero queries beyond the profile that call sites already `select_related` — the tag's
docstring says so explicitly. Two new sources, with very different risk:

**Everyone-grants are not per-user.** One query for the whole request, and the result is
tiny and bounded, so cache it globally under a key invalidated by `post_save`/`post_delete`
on `BadgeGrant`. Effectively free, and a safe thing to cache — it is a handful of rows,
not a derived money value.

**Per-user grants are the N+1 risk.** Options:

1. Prefetch at the call sites (`prefetch_related("owner__badge_grants")`) and add a
   query-count regression test against the existing snapshot at
   `n23/core/tests/fixtures/performance_view_queries.json`. This turns a silent N+1 into
   a failing test, which is the part that matters — the failure mode here is a missed
   prefetch on a page nobody profiled.
2. A `UserProfile.has_badge_grants` boolean maintained by signals, so the query is skipped
   for the overwhelming majority of users with no grants.
3. Denormalise the granted slugs onto the profile.

Go with 1. Hold 2 in reserve if profiling asks for it. Do not do 3 — it is a content cache
of exactly the kind #1860 spent a programme deleting.

Note the plumbing detail: the FK's `related_name` sits on `User`, so the prefetch path is
`owner__badge_grants` while the property reading it lives on `UserProfile` and goes through
`self.user.badge_grants.all()`. That works with the prefetch present and falls back to a
query without it, which is the behaviour the query-count test is there to police.

A per-request memo keyed by user id would additionally collapse repeats on pages where
every row has the same owner (the "my lists" page). Worth having eventually; not part of
the first cut.

## Admin

- `BadgeGrantAdmin` — list by badge / audience / user / created / granted_by / expires_at;
  filter by badge and audience; `autocomplete_fields` on user; `badge` rendered as a choice
  field built from the grantable registry entries; `granted_by` set from `request.user` on
  save.
- Bulk action on `UserAdmin` and `UserProfileAdmin`: "Grant badge to selected users",
  with an intermediate page to pick the badge. This mirrors the existing
  `add_users_to_group` action (`gyrinx/accounts/admin.py:17`, template
  `core/admin/add_users_to_group.html`) — copy that shape rather than inventing one.
- A paste-a-list page taking usernames or emails, since the tester cohort probably lives
  in a spreadsheet rather than in a queryset. It must report unmatched identifiers back
  rather than silently skipping them.
- Granting to everyone goes through the same admin, with the affected-user count shown
  before confirmation.

Bulk grants use `get_or_create` so re-running is idempotent.

## Build order

1. `grantable` / `auto_display` on `BadgeDef` — inert, no behaviour change.
2. `BadgeGrant` + migration + admin + bulk actions.
3. Eligibility union on `UserProfile`, plus the `auto_display` filter in `display_badge`.
4. Prefetch at the call sites the tag docstring already lists; query-count test.
5. Playtester SVG + registry entry; grant the cohort.

Steps 1–4 ship with no user-visible change, which makes them safe to land ahead of any
decision about the badge itself.

## Tests

Extend the three existing files rather than adding a fourth: `n23/core/tests/test_badges.py`
(eligibility), `n23/core/tests/test_badge_views.py` (picker and tamper rejection),
`n26/tests/test_badges.py` (renders in both editions).

New cases worth pinning:

- A grant for a `grantable=False` slug grants nothing (the staff bypass).
- An expired grant grants nothing.
- An EVERYONE grant with `auto_display=False` widens the picker and changes no rendered
  page.
- Revoking a grant that was the selected badge falls back to the default rather than
  rendering an empty span.
- Query count on a list index does not scale with row count.

## Open questions

- Should the tester badge outrank the Patreon tiers for someone who is both? Rank band
  decides it, and it is easier to pick now than to change later once people have seen it.
- Is `expires_at` wanted now? It is cheap to include and awkward to retrofit, but it does
  add a clause to every read.
- Where does the list of n26 testers actually come from? Nothing in the schema records
  "tested n26", so the cohort has to be assembled from whatever tracked it.
