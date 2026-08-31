# n26 #2371: move a counter in place, without reloading the page

Fast-follow to #2367, which put `−`/`+` on a model's counter lines on the
fighter-edit page. Each click is a plain form post and a full page reload —
right for shipping, wrong for the screen people click these on repeatedly
after a battle.

## Three findings that shape it

**The TinyMCE trap does not exist.** #2371 was filed warning that a card swap
would rebuild the Notes and Lore editors and throw away typing. It would not:
in `cotton/n26/view/model_edit.html` the model card and those boxes are
*siblings* in one grid, not nested. Swapping the whole card touches no editor.

That inverts the design. Rather than surgically replacing one counter line,
replace **the whole card** — simpler, and more correct: it redraws the
statline, the Rules row and the choice rows, which are exactly what a
threshold crossing changes.

**Thresholds are theoretical today.** `CounterAtLeast` has zero rows in prod
(checked). No authored content hangs an effect off a counter value yet, though
the machinery is built and tested and Power Boost content will use it. So this
does not have to solve threshold redraws — it has to not be wrong when they
land, which a card-level swap gives for free.

**htmx 2.0.4 does not read `event.submitter`.** The bundled htmx
(`n26/designsystem/static/designsystem/vendor/htmx.min.js`) contains no
submitter handling. The control today is one form with two submit buttons told
apart by `name="change" value="±1"`: native submission includes the clicked
button, htmx does not. Over htmx that posts no `change` and the view 404s on
every click, silently. `c-n26.dialog` puts `hx-post` on the `<form>` and never
meets this, because its dialogs have one button whose meaning is in the URL.

## Design

**Two forms, one per direction**, each carrying a hidden `change`. Identical
with and without scripting, needs no submitter support, and avoids the
double-submit that `hx-post` on a button inside a submitting form invites. The
cost is a second CSRF token.

**One host, one swap.** A host element with a stable id wraps the card in
`model_edit.html`, drawn always so the gallery demo and the real page agree.
`tally_counter` answers an htmx request with that card alone, carrying
`hx-swap-oob`. The `back` field the control already posts is the address the
redrawn card rebuilds its Equip and Choose hrefs from, and `link_counters` runs
again so the new card keeps its own controls.

**No toast on success.** The number visibly moves, so a toast per click is
noise when someone taps `+` five times. The success message is queued only on
the non-htmx path; a refusal still toasts, because a click that did nothing has
to say why. A deliberate departure from the equip screens, where the changed
row is far from the button that changed it.

**Nothing else swaps.** A tally writes no ledger entry, so rating, credits and
wealth do not move — the same reasoning `equip_update.html` gives for leaving
the model count alone.

## Build

1. `cotton/n26/counter_controls.html` — two forms, hidden `change`, and an
   `htmx` prop putting `hx-post`/`hx-swap="none"` on each, as `c-n26.dialog`
   does.
2. `cotton/n26/view/model_edit.html` — the host element around the card.
3. `n26/fighter_edit.html` — opt in with `:htmx="True"`. The only page that
   may, being the only one that holds the host.
4. `n26/core/views/edit.py` — `render_card_update(request, miniature, at)`:
   derive the sheet again, pick the member, link its slots, skills and
   counters, render the card into an out-of-band include, `with_toasts`.
5. `n26/core/views/owned.py` — `tally_counter` calls it when `is_htmx` and the
   counter sits on a miniature; a gang-hosted counter and a reader with no
   script keep the redirect.
6. Tests: the htmx response carries the host id and the new value; the plain
   path still redirects; a refusal answers `no_update` and says why; and a
   guard that the page opting in holds every id the response addresses.

## Left out

The sibling **Skills & Powers** and **Subtypes & Rules** boxes read their
offers from the same derivation, so a future threshold crossing could leave
them stale until the next full load. Deliberately not swapped: they are forms
the reader may be part-way through, and clobbering half-ticked boxes is worse
than a stale offer. Unreachable today. Revisit when the first `CounterAtLeast`
content is authored.
