"""Buy equipment for models or the gang stash through a shared purchase parser.

Both pages derive the current offer, validate submitted selections and prices,
and write through operations. Confirmation objects let callers choose between
full pages and htmx panels without duplicating purchase logic.

_screen supplies the same card, collection and budget derivation for ordinary
pages and partial updates. Updates replace changed rows and shared figures
while preserving controls elsewhere on the listing. See n26.core.views.htmx.
"""

import re
from dataclasses import dataclass, replace
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.template.defaultfilters import pluralize

from n26.core.activities import founding_blocks_visit
from n26.core.confirm import CONFIRM_FIELD, Confirmation, carried
from n26.core.listing import choice_field as _choice_field
from n26.core.listing import parts_field as _parts_field
from n26.core.listing import price_field as _price_field
from n26.core.owned import thing_key as _thing_key
from n26.core.views.htmx import is_htmx, no_update, with_toasts
from n26.core.views.permissions import (
    _own_gang_or_404,
    _own_miniature_or_404,
    credits_href,
    may_mark_status,
    may_see_founding,
    status_href,
    trade_points_href,
)
from n26.library.staged import sees_staged

#: Bound hand-entered payment per line independently of gang credit affordability.
PRICE_CEILING = 100_000

#: Accept only ASCII decimal digits and an optional minus; int() alone also
#: accepts plus signs, underscores and non-ASCII digits.
_WHOLE_CREDITS = re.compile(r"-?[0-9]+")


class BadPrice(Exception):
    """A submitted price is outside the accepted whole-credit range."""


def _parts_picked(data, key, line):
    """Resolve submitted part indices against the current line and retain their positions.

    Reject duplicates, negative values and out-of-range indices. Positions also
    identify each part's submitted price field.
    """
    picked, seen = [], set()
    for value in data.getlist(_parts_field(key)):
        # Reject negative indices before Python can index from the end.
        if not value.isdigit():
            raise Http404("No such option")
        index = int(value)
        if index >= len(line.parts) or index in seen:
            raise Http404("No such option")
        seen.add(index)
        picked.append((index, line.parts[index]))
    return picked


def _choices_picked(data, key, groups):
    """Resolve alternative indices against the supplied offer groups.

    Reject duplicate or invalid indices. Empty values select no member of an
    optional group. Reuse this parser for purchases and changes to owned options.
    """
    picked = []
    for index, group in enumerate(groups):
        seen = set()
        for value in data.getlist(_choice_field(key, index)):
            if value == "":
                continue
            # Reject negative indices before Python can index from the end.
            if not value.isdigit():
                raise Http404("No such option")
            position = int(value)
            if position >= len(group.options) or position in seen:
                raise Http404("No such option")
            seen.add(position)
            picked.append(group.options[position])
    return picked


def price_typed(data, field, quoted, name):
    """Parse a submitted whole-credit price, using the quote for an absent or blank field.

    Accept plain ASCII digits with an optional minus. The minimum is zero or the
    negative quoted price, whichever is lower; PRICE_CEILING bounds the maximum.
    Reject an invalid amount without clamping or changing it.
    """
    raw = data.get(field)
    if raw is None or not raw.strip():
        return quoted
    raw = raw.strip()
    floor = price_floor(quoted)
    typed = int(raw) if _WHOLE_CREDITS.fullmatch(raw) else None
    if typed is None or not floor <= typed <= PRICE_CEILING:
        raise BadPrice(
            f"{name}: a price is a whole number of credits, "
            f"from {floor} to {PRICE_CEILING}."
        )
    return typed


def price_floor(quoted):
    """Allow zero or the negative quoted price, whichever is lower."""
    return min(0, quoted)


def _price_typed(data, field, line):
    return price_typed(data, field, line.credits, line.name)


#: Use the same rating checkbox field and value as hiring.
RATE_FIELD, RATE_AT_PAID = "rate", "paid"


def _full_price(line, surcharge=0):
    """Use the greater of listing and reference price, plus option surcharges.

    For negatively priced content, retain the listing price as its rating basis.
    """
    if line.credits < 0:
        return line.credits + surcharge
    return max(line.credits, line.thing.reference_price()) + surcharge


def _charge(line, paid, surcharge=0, *, rate_at_paid=False):
    """Build recorded payment, list price and discount for one purchase line.

    Add option surcharge to both payment and full price. Normally rating follows
    full price; rate_at_paid adds an explicit lower rating only when payment is
    below full price. Preserve list price for purchase-history interpretation.
    """
    full = _full_price(line, surcharge)
    paid = paid + surcharge
    charge = {"paid": paid, "list_price": full, "discount": full - paid}
    if rate_at_paid and paid < full:
        # Preserve full list price: history uses zero list price to identify free bundled profiles.
        charge["rating"] = paid
    return charge


def _rating_box(request, charges):
    """Ask whether to rate discounted lines at their actual payment.

    Include only underpriced lines and omit the question after confirmation.
    """
    from n26.core.confirm import Checkbox

    if request.POST.get(CONFIRM_FIELD):
        return None
    below = [
        (line.name, line_paid + surcharge, _full_price(line, surcharge))
        for line, line_paid, surcharge in charges
    ]
    below = [(name, paid, full) for name, paid, full in below if paid < full]
    if not below:
        return None
    # Identify every discounted line separately because only selected parts may need lower ratings.
    names = " and ".join(name for name, _, _ in below)
    paid = sum(paid for _, paid, _ in below)
    full = sum(full for _, _, full in below)
    one = len(below) == 1
    keeps, its = ("keeps", "its") if one else ("keep", "their")
    return Checkbox(
        name=RATE_FIELD,
        value=RATE_AT_PAID,
        label="Match rating to price",
        description=(
            f"By default, {names} {keeps} {its} full rating of {full}¢ even "
            f"though you pay {paid}¢. If your group agrees that something "
            "bought for less is worth only what you paid — for example, one "
            f"given to you for free — tick this box to set {its} rating to "
            f"{paid}¢."
        ),
    )


def _rating_question(request, line, spent, checkbox, back):
    """Build a separate rating confirmation when no overspend confirmation already carries it."""
    from n26.core.confirm import Confirmation, carried

    return Confirmation(
        title="Choose the rating",
        lead=f"{line.name} — {spent}¢.",
        heading="You are paying less than the full price",
        body=(
            "Choose whether the gang's rating goes up by the full price or "
            "by the price you pay."
        ),
        variant="info",
        checkbox=checkbox,
        confirm_label=f"Buy {line.name}",
        action=request.get_full_path(),
        cancel_url=back,
        carry=carried(request.POST, leave_out={RATE_FIELD}),
        confirm_value="1",
    )


LIST_SUFFIX = "equipment list"


def _trade_points_asked(line, picked):
    """Sum trade points charged by this line and selected parts.

    Options are credit surcharges only. Lines with no trade-point price charge
    zero points even when their collection uses Trading Post terms.
    """
    asked = line.trade_points if line.charges_trade_points else 0
    return (asked or 0) + sum(
        part.trade_points or 0 for _, part in picked if part.charges_trade_points
    )


def _counted_against(gang, line, budget=None):
    """Attribute trade-point purchases to a personal allowance or the gang's open visit.

    Credit-only purchases have no activity. Personal founding allowances take
    precedence over a simultaneous visit.
    """
    if not line.charges_trade_points:
        return None
    return budget.activity if budget is not None else gang.open_visit


def _overspend(request, gang, line, asked, back, budget=None, holder=""):
    """Ask for confirmation when trade points exceed the current allowance.

    Use personal-budget figures when supplied, otherwise the open visit.
    Without an activity, warn that points will be recorded against none.
    An explicitly confirmed overspend remains permitted.
    """
    from n26.core.confirm import Aside, Fact, carried

    if not asked or request.POST.get(CONFIRM_FIELD) == "tp-overspend":
        return None
    visit = None if budget is not None else gang.open_visit
    open_activity = budget is not None or visit is not None
    if budget is not None:
        brought, spent = budget.granted, budget.spent
    elif visit is not None:
        # Read visit spend once so spent and remaining figures use the same value.
        brought, spent = (visit.trade_points or 0), gang.trade_points_spent
    else:
        brought, spent = 0, 0
    left = brought - spent
    if asked <= left:
        return None
    # Use the model as the personal allowance holder and the gang for an open visit.
    whose = holder if budget is not None and holder else gang.name
    if budget is not None:
        left_over = (
            f"What {whose} has left goes below zero, and stays there until "
            "the action is finished."
        )
    elif visit is not None:
        left_over = (
            "What the action has left goes below zero, and stays there "
            "until it is finished."
        )
    else:
        left_over = "The purchase records the Trade Points against no action."
    return Confirmation(
        title="Not enough Trade Points",
        lead=f"{line.name} — {asked} Trade Point{pluralize(asked)}.",
        heading="You don't have enough TP for this purchase",
        body=(
            f"{line.name} uses {asked} Trade Point{pluralize(asked)}, and "
            f"{whose} has {left}."
        ),
        aside=Aside(lead="You can buy it anyway.", rest=left_over),
        facts=(
            Fact(
                "Available",
                str(brought),
                sub="" if open_activity else "no action open",
            ),
            Fact("Spent", str(spent)),
            Fact("Remaining", str(left), ruled=True, strong=True),
            Fact("This purchase", str(asked)),
            Fact("Remaining after", str(left - asked), ruled=True, strong=True),
        ),
        confirm_label=f"Buy {line.name} anyway",
        action=request.get_full_path(),
        cancel_url=back,
        carry=carried(request.POST),
        confirm_value="tp-overspend",
    )


def _tab_label(collection):
    """Remove a redundant equipment-list suffix while retaining an otherwise empty name."""
    name = str(collection)
    if not name.lower().endswith(LIST_SUFFIX):
        return name
    return name[: -len(LIST_SUFFIX)].strip(" -–—:") or name


def buyable_lists(held):
    """Select held collections containing gear and place the standard Trading Post last.

    Collection assignments also include skill sets, so filter by content family.
    Resolve the standard post within the default pack; same-named custom posts
    remain available only through their ordinary held-collection access.
    """
    from n26.library.models import Collection, Family, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    held = list(held)
    buyable = set(
        Collection.objects.filter(pk__in=[c.pk for c in held])
        .containing(Family.GEAR)
        .values_list("pk", flat=True)
    )
    collections = [c for c in held if c.pk in buyable]
    post = Collection.objects.filter(
        name=TRADING_POST_COLLECTION, pack=get_default_pack()
    ).first()
    if post is not None:
        collections = [c for c in collections if c.pk != post.pk] + [post]
    return collections


def collection_tabs(collections, chosen):
    """Build collection tabs, shortening names unless that creates duplicate labels.

    Include the full name as a tooltip only when shortened.
    """
    labels = [_tab_label(collection) for collection in collections]
    if len(set(labels)) != len(labels):
        labels = [str(collection) for collection in collections]
    return [
        {
            "label": label,
            "title": "" if label == str(collection) else str(collection),
            "href": f"?list={collection.pk}",
            "current": chosen is not None and collection.pk == chosen.pk,
        }
        for label, collection in zip(labels, collections, strict=True)
    ]


@dataclass(frozen=True)
class Screen:
    """The shared card, budget and catalogue derivation for an equipment surface."""

    gang: object
    miniature: object | None
    card: object
    computed: object
    collections: list
    chosen: object | None
    view: object | None
    #: The personal allowance supplying activity and confirmation figures; absent for stash views.
    budget: object | None = None

    def host(self, at):
        """Resolve model or stash assignment roots using the supplied page URL."""
        from n26.core.owned import EquipHost

        if self.miniature is not None:
            return EquipHost.fighter(self.gang, self.card, self.miniature, at=at)
        return EquipHost.stash(self.gang, self.card, at=at)


def _screen(gang, miniature=None, list_param="", budgets=True, *, include_staged=False):
    """Derive the current equipment view for a model or the gang stash.

    A model view includes usability notes and an optional founding budget.
    ALL_SCOPE browses unrestricted gear priced through held lists. STASH_SCOPE
    shows only holdings on the gang screen. Apply staged-content access throughout.
    """
    from n26.core.access import collections_for, gang_collections, hidden_categories_for
    from n26.core.browse import (
        all_gear,
        browse,
        narrow,
        priced_from,
        usability_for,
        with_use_notes,
    )
    from n26.core.card import (
        build_card,
        build_gang_card,
        build_modifier_index,
        carriers,
    )
    from n26.core.effects import compute, compute_gang
    from n26.core.founding import budget_for

    def chosen_from(collections):
        """Choose the named held collection or the first available collection."""
        named = next((c for c in collections if str(c.pk) == list_param), None)
        return named or (collections[0] if collections else None)

    if miniature is not None:
        # Load option provenance for owned-copy controls and statlines for the displayed model card.
        card = build_card(miniature, with_statlines=True, with_options=True)
        index = build_modifier_index(carriers(card))
        computed = compute(card, index)
        # Load personal budgets only when needed; each collection determines whether it charges points.
        budget = budget_for(gang, miniature, computed) if budgets else None
        collections = buyable_lists(
            access.collection
            for access in collections_for(miniature, card=card, computed=computed)
        )
        if list_param == ALL_SCOPE:
            # Price unrestricted gear through held collections and retain model usability notes.
            chosen = None
            view = priced_from(
                all_gear(
                    ALL_LABEL,
                    for_use_notes=True,
                    include_staged=include_staged,
                ),
                [
                    browse(collection, include_staged=include_staged)
                    for collection in collections
                ],
            )
        else:
            chosen = chosen_from(collections)
            view = (
                narrow(
                    browse(chosen, include_staged=include_staged),
                    exclude_categories=hidden_categories_for(chosen, computed),
                )
                if chosen is not None
                else None
            )
        if view is not None:
            view = with_use_notes(view, usability_for(computed))
        return Screen(
            gang, miniature, card, computed, collections, chosen, view, budget
        )

    card = build_gang_card(gang, with_statlines=False)
    index = build_modifier_index(carriers(card))
    computed = compute_gang(card, index)
    collections = buyable_lists(
        access.collection
        for access in gang_collections(gang, card=card, computed=computed)
    )
    if list_param == STASH_SCOPE:
        chosen, view = None, None
    elif list_param == ALL_SCOPE:
        chosen = None
        view = priced_from(
            all_gear(ALL_LABEL, include_staged=include_staged),
            [
                browse(collection, include_staged=include_staged)
                for collection in collections
            ],
        )
    else:
        chosen = chosen_from(collections)
        # Usability notes apply to models, not stashes.
        view = (
            browse(chosen, include_staged=include_staged)
            if chosen is not None
            else None
        )
    return Screen(gang, None, card, computed, collections, chosen, view)


def render_update(
    request,
    gang,
    key,
    *,
    miniature=None,
    list_param="",
    expanded_key="",
    at="",
    closed=False,
    also="",
):
    """Rebuild affected catalogue rows and shared panels after an equipment operation.

    Use the same _screen derivation as the page. Preserve at, expanded_key and
    list_param in returned controls. closed clears the confirmation panel;
    also identifies a second affected row on this screen. A missing owned-only
    row is removed when its final copy leaves.
    """
    from n26.core.listing import listing_row, owned_row, owned_row_manage_only
    from n26.core.owned import possessions
    from n26.core.views.owned import accessorise_dialogs

    founding_seen = may_see_founding(gang, request.user)
    screen = _screen(
        gang,
        miniature=miniature,
        list_param=list_param,
        budgets=founding_seen,
        include_staged=sees_staged(request.user),
    )
    host = screen.host(at)
    held = possessions(host)
    refunds = not gang.credits_unlimited

    def row_for(row_key):
        copies = held.get(row_key)
        expanded = row_key == expanded_key
        if screen.view is None:
            # Remove an owned-only row when the final copy leaves; catalogue rows retain their offer.
            return (
                owned_row_manage_only(
                    row_key, copies, refunds=refunds, expanded=expanded
                )
                if copies
                else None
            )
        line = next(
            (
                line
                for line in screen.view.all_lines()
                if _thing_key(line.thing) == row_key
            ),
            None,
        )
        if line is None:
            # Do not update catalogue keys this screen does not display.
            return None
        row = listing_row(line)
        return (
            owned_row(row, copies, refunds=refunds, expanded=expanded)
            if copies
            else row
        )

    rows = [(key, row_for(key))]
    if also and also != key:
        rows.append((also, row_for(also)))

    response = render(
        request,
        "n26/includes/equip_update.html",
        {
            "rows": rows,
            "gang": gang,
            **_card_context(request, screen, host, at=at),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
            "held_label": host.held_label,
            "miniature": miniature,
            "founding_budget": screen.budget,
            "closed": closed,
            # Rebuild accessory panels because newly bought weapons need hosts and removed weapons must lose them.
            "accessorise": accessorise_dialogs(request, host),
        },
    )
    return with_toasts(request, response)


def carried_confirmation(request):
    """Detect a submission returned from a confirmation panel."""
    return bool(request.POST.get(CONFIRM_FIELD))


def render_confirmation(request, confirmation):
    """Render an htmx confirmation panel with queued toast messages."""
    response = render(
        request,
        "n26/includes/equip_overspend.html",
        {"confirmation": confirmation},
    )
    return with_toasts(request, response)


def _buy_clicked(
    request, gang, holder, view, *, into, collection, at="", event=None, budget=None
):
    """Validate and perform a purchase for a model or stash.

    Resolve the line and selected parts from the current view. Validate every
    price before writing, then ask any overspend or rating questions.
    Recheck a model's founding activity under the gang lock before charging it.

    Return the affected key on success, None after a refusal, or a Confirmation
    requiring another submission. Callers choose the HTTP response shape.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation

    key = request.POST.get("thing", "")
    line = next((row for row in view.all_lines() if _thing_key(row.thing) == key), None)
    if line is None:
        messages.error(request, "That item is not on this list.")
        return None
    picked = _parts_picked(request.POST, key, line)
    picks = _choices_picked(request.POST, key, line.choices)
    surcharge = sum(option.surcharge for option in picks)
    # Validate payment for the weapon and every selected part before writing any purchase.
    try:
        paid = _price_typed(request.POST, _price_field(key), line)
        paid_for = [
            (part, _price_typed(request.POST, _price_field(key, index), part))
            for index, part in picked
        ]
    except BadPrice as refusal:
        messages.error(request, str(refusal))
        return None
    # An absent rating checkbox keeps the full rating.
    rate_at_paid = request.POST.get(RATE_FIELD) == RATE_AT_PAID
    charge = _charge(line, paid, surcharge, rate_at_paid=rate_at_paid)
    # Combine rating and overspend questions into one confirmation before writing.
    asked = _trade_points_asked(line, picked)
    expected_personal = request.POST.get("personal_activity")
    if (
        asked
        and expected_personal is not None
        and expected_personal != (str(budget.activity.pk) if budget is not None else "")
    ):
        messages.error(
            request, "This spending action has changed. Reload the page before buying."
        )
        return None
    checkbox = _rating_box(
        request,
        [
            (line, paid, surcharge),
            *((part, part_paid, 0) for part, part_paid in paid_for),
        ],
    )
    confirmation = _overspend(request, gang, line, asked, at, budget, into)
    if confirmation is not None:
        return replace(
            confirmation,
            checkbox=checkbox,
            # Remove a carried rating value so it cannot override an unchecked confirmation control.
            carry=carried(
                request.POST, leave_out={RATE_FIELD} if checkbox is not None else ()
            ),
        )
    if checkbox is not None:
        spent = charge["paid"] + sum(part_paid for _, part_paid in paid_for)
        return _rating_question(request, line, spent, checkbox, at)
    try:
        with operation(gang, actor=request.user) as op:
            from n26.core.models import Miniature

            if (
                asked
                and isinstance(holder, Miniature)
                and may_see_founding(gang, request.user)
            ):
                from n26.core.card import build_card, build_modifier_index, carriers
                from n26.core.effects import compute
                from n26.core.founding import budget_for

                # Recheck allowance identity and lifetime spend after acquiring the gang lock.
                current = Miniature.objects.select_related("membership").get(
                    pk=holder.pk
                )
                card = build_card(current, with_statlines=False, with_options=True)
                index = build_modifier_index(carriers(card))
                fresh_budget = budget_for(gang, current, compute(card, index))
                if (
                    current.membership.archived
                    or current.membership.gang_id != gang.pk
                    or (
                        budget is not None
                        and (
                            fresh_budget is None
                            or fresh_budget.activity.pk != budget.activity.pk
                        )
                    )
                ):
                    raise Refusal(
                        "This spending action has changed. Reload the page before buying."
                    )
                budget = fresh_budget
                confirmation = _overspend(request, gang, line, asked, at, budget, into)
                if confirmation is not None:
                    if budget is not None:
                        confirmation = replace(
                            confirmation,
                            carry=(
                                *carried(request.POST, leave_out={"personal_activity"}),
                                ("personal_activity", str(budget.activity.pk)),
                            ),
                        )
                    return confirmation
            # Materialise selected options through the purchase; unselected pick-one groups use their default.
            bought = op.buy(
                holder,
                line=line,
                option=[option.default_set for option in picks],
                activity=_counted_against(gang, line, budget),
                **charge,
            )
            # Host paid profiles on the newly bought weapon, pricing each from its own listing line.
            for part, part_paid in paid_for:
                op.buy(
                    bought,
                    line=part,
                    activity=_counted_against(gang, part, budget),
                    **_charge(part, part_paid, rate_at_paid=rate_at_paid),
                )
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return None
    except ValueError:
        # Reject invalid option combinations after individual index parsing.
        raise Http404("No such option") from None
    spent = charge["paid"] + sum(part_paid for _, part_paid in paid_for)
    # Record one purchase analytics event with part and option counts.
    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.CREATE,
        bought,
        gang_id=str(gang.pk),
        thing=line.name,
        collection=collection,
        paid=spent,
        trade_points=asked,
        parts=len(paid_for),
        options=len(picks),
        **(event or {}),
    )
    extras = [
        *(option.name for option in picks),
        *(part.thing.name for part, _ in paid_for),
    ]
    price = f"{spent}¢" + (f" and {asked} TP" if asked else "")
    if extras:
        messages.success(
            request,
            f"Bought {line.name} with {', '.join(extras)} for {into} — {price}.",
        )
    else:
        messages.success(request, f"Bought {line.name} for {into} — {price}.")
    return key


@login_required
def equip(request, pk):
    """Buy and manage equipment on an owned model's current catalogue.

    Keep collection, section and expanded-row state in navigation destinations.
    Use _buy_clicked for typed payment, optional parts and acquisition options.
    Each purchase is atomic, with paid weapon profiles hosted on that weapon.

    Build owned-copy controls from the same computed card as the catalogue.
    Return confirmations or partial updates for htmx; ordinary requests render
    or redirect through the same purchase behaviour.
    """
    from n26.core.listing import build_catalogue
    from n26.core.owned import possessions, with_query
    from n26.core.views.choose import SHOW_DISMISSED, SHOWING, showing_dismissed
    from n26.core.views.owned import (
        accessorise_dialogs,
        owned_dialog,
        panel_response,
    )

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang
    founding_seen = may_see_founding(gang, request.user)

    wanted = request.GET.get("list", "")
    everything = wanted == ALL_SCOPE
    screen = _screen(
        gang,
        miniature=miniature,
        list_param=wanted,
        budgets=founding_seen,
        include_staged=sees_staged(request.user),
    )
    collections, chosen, view = screen.collections, screen.chosen, screen.view

    # Carry section state through POST and redirects; unknown tabs fall back in the picker.
    section = request.POST.get("section", request.GET.get("section", ""))[:100]
    expanded_key = request.POST.get("owned", request.GET.get("owned", ""))[:200]

    dismissed_shown = showing_dismissed(request.get_full_path())

    def here(collection):
        params = []
        if everything:
            params.append(("list", ALL_SCOPE))
        elif collection is not None:
            params.append(("list", collection.pk))
        if section:
            params.append(("section", section))
        if expanded_key:
            params.append(("owned", expanded_key))
        if dismissed_shown:
            params.append((SHOW_DISMISSED, SHOWING))
        return f"{request.path}?{urlencode(params)}" if params else request.path

    if request.method == "POST" and view is not None:
        hx = is_htmx(request)
        key = _buy_clicked(
            request,
            gang,
            miniature,
            view,
            into=miniature.name,
            collection=ALL_LABEL if everything else chosen.name,
            at=here(chosen),
            event={"miniature_id": str(miniature.pk)},
            budget=screen.budget,
        )
        if isinstance(key, Confirmation):
            if not hx:
                return render(
                    request,
                    "n26/confirm.html",
                    {"gang": gang, "confirmation": key},
                )
            return render_confirmation(request, key)
        if not hx:
            return redirect(here(chosen))
        if key is None:
            return no_update(request)
        return render_update(
            request,
            gang,
            key,
            miniature=miniature,
            list_param=wanted,
            expanded_key=expanded_key,
            at=here(chosen),
            closed=carried_confirmation(request),
        )

    # Index owned possessions from the existing card rather than querying per catalogue line.
    at = here(chosen)
    host = screen.host(at)
    owned = possessions(host)

    dialog = owned_dialog(request, host)
    if (panel := panel_response(request, dialog)) is not None:
        return panel

    # Build the linked model card only after an early panel-only response has been ruled out.
    card = _card_context(request, screen, host, at=at)

    catalogue = (
        build_catalogue(
            view,
            owned,
            refunds=not gang.credits_unlimited,
            expanded_key=expanded_key,
        )
        if view is not None
        else None
    )
    tabs = list_tabs(collections, chosen, everything)
    # Preserve dismissal visibility in the action URL; section and expanded-row state use form fields.
    if everything:
        action = f"{request.path}?list={ALL_SCOPE}"
        browsing = ALL_BROWSING
    elif chosen is not None:
        action = f"{request.path}?list={chosen.pk}"
        browsing = str(chosen)
    else:
        action = request.path
        browsing = ""
    if dismissed_shown:
        action = with_query(action, **{SHOW_DISMISSED: SHOWING})
    from n26.core.render import roster as gang_roster
    from n26.core.render import summarise_roster

    roster = gang_roster(gang)

    picker = picker_context(catalogue, view, gang, screen.budget)
    tp_href = trade_points_href(gang, request.user)
    # Show personal allowance and visit figures separately; purchases use the personal allowance first.
    visit_beside_founding = bool(
        screen.budget is not None and tp_href and gang.visiting_trading_post
    )
    return render(
        request,
        "n26/equip.html",
        {
            "miniature": miniature,
            "gang": gang,
            "role": (
                miniature.membership.profile.category.name
                if miniature.membership.profile
                and miniature.membership.profile.category
                else ""
            ),
            "summary": summarise_roster(roster),
            "trade_points_href": tp_href,
            "credits_href": credits_href(gang, request.user),
            "collections": collections,
            "collection_tabs": tabs,
            "everything": everything,
            "action": action,
            "browsing": browsing,
            "chosen": chosen,
            "catalogue": catalogue,
            # Enable htmx only because the page includes every required out-of-band update host.
            "htmx": True,
            "dialog": dialog,
            "accessorise": accessorise_dialogs(request, host),
            "founding_budget": screen.budget,
            "visit_beside_founding": visit_beside_founding,
            "visit_trade_points_left": (
                gang.trade_points_left if visit_beside_founding else None
            ),
            # Check founding restrictions only when rendering an invitation to open a Trading Post visit.
            "founding_blocks_visit": (
                founding_blocks_visit(gang, founding_seen)
                if picker["post_is_shut"]
                else False
            ),
            **card,
            **picker,
        },
    )


def _card_context(request, screen, host, *, at):
    """Build linked model-card and action props from the screen's existing computation.

    Stash screens return no model-card context.
    """
    from n26.core.views.edit import action_panel_context, link_model_card

    if screen.miniature is None:
        return {}
    gang, miniature = screen.gang, screen.miniature
    return {
        **action_panel_context(miniature, screen.card, screen.computed),
        "card": link_model_card(
            gang, miniature, screen.card, screen.computed, host, back=at
        ),
        "status_href": (
            status_href(gang, miniature, back="edit")
            if may_mark_status(gang, request.user)
            else ""
        ),
    }


def picker_context(catalogue, view, gang=None, budget=None):
    """Build catalogue navigation, filter registrations and price ranges.

    Use browsed lines for price limits and only visible trade-point figures for
    that slider. A personal budget suppresses the no-open-visit notice.
    """
    sections = catalogue.sections if catalogue is not None else []
    lines = list(view.all_lines()) if view is not None else []
    trade_points = [
        line.trade_points
        for line in lines
        if line.shows_trade_points and line.trade_points is not None
    ]
    return {
        # A closed-post notice informs the owner but does not block purchasing.
        "post_is_shut": bool(
            gang is not None
            and budget is None
            and not gang.visiting_trading_post
            and any(line.charges_trade_points for line in lines)
        ),
        # Match filter registration keys, using section names for unnamed categories.
        # Deduplicate names shared across sections.
        "categories": list(
            dict.fromkeys(
                category.name or section.name
                for section in sections
                for category in section.categories
            )
        ),
        "category_options": [
            {"value": name, "label": name}
            for name in dict.fromkeys(
                category.name
                for section in sections
                for category in section.categories
                if category.name
            )
        ],
        # Include every rendered section in navigation so none becomes unreachable.
        "sections": [section.name for section in sections],
        "price_floor": min((line.credits for line in lines), default=0),
        "price_ceiling": max((line.credits for line in lines), default=0),
        "tp_ceiling": max(trade_points, default=0),
        "has_trade_points": bool(trade_points),
        # Expose the enforced server price ceiling as an input hint too.
        "price_cap": PRICE_CEILING,
    }


#: Reserved non-ULID query value for unrestricted gear browsing.
ALL_SCOPE = "all"

ALL_LABEL = "Unrestricted"

ALL_BROWSING = "all equipment"

#: Reserved query value for owned stash content absent from the current catalogue.
STASH_SCOPE = "stash"

STASH_LABEL = "In stash"


def library_tab(everything):
    """Build the unrestricted-library tab shared by model and stash catalogues."""
    return {
        "label": ALL_LABEL,
        "title": "",
        "href": f"?list={ALL_SCOPE}",
        "current": everything,
    }


def list_tabs(collections, chosen, everything):
    """Append unrestricted library browsing after held catalogue tabs."""
    tabs = collection_tabs(collections, chosen)
    tabs.append(library_tab(everything))
    return tabs


def gang_tabs(collections, chosen, everything, *, stash=False):
    """Prepend stash holdings to the catalogue and unrestricted-library tabs."""
    tabs = list_tabs(collections, chosen, everything)
    tabs.insert(
        0,
        {
            "label": STASH_LABEL,
            "title": "",
            "href": f"?list={STASH_SCOPE}",
            "current": stash,
        },
    )
    return tabs


@login_required
def equip_gang(request, pk):
    """Buy into the owned gang's stash and manage its stored possessions.

    The stash tab includes gear absent from held catalogues. ALL_SCOPE browses
    the unrestricted library. Stash listings omit model-specific usability notes.
    """
    from n26.core.listing import build_catalogue, build_stash_catalogue
    from n26.core.owned import possessions
    from n26.core.render import roster as gang_roster
    from n26.core.render import summarise_roster
    from n26.core.views.owned import (
        accessorise_dialogs,
        owned_dialog,
        panel_response,
    )

    gang = _own_gang_or_404(request, pk)

    wanted = request.POST.get("list", request.GET.get("list", ""))
    stash_tab = wanted == STASH_SCOPE
    everything = wanted == ALL_SCOPE
    screen = _screen(gang, list_param=wanted, include_staged=sees_staged(request.user))
    collections, chosen, view = screen.collections, screen.chosen, screen.view

    section = request.POST.get("section", request.GET.get("section", ""))[:100]
    expanded_key = request.POST.get("owned", request.GET.get("owned", ""))[:200]

    params = []
    if stash_tab:
        params.append(("list", STASH_SCOPE))
    elif everything:
        params.append(("list", ALL_SCOPE))
    elif chosen is not None:
        params.append(("list", chosen.pk))
    if section:
        params.append(("section", section))
    if expanded_key:
        params.append(("owned", expanded_key))
    here = f"{request.path}?{urlencode(params)}" if params else request.path

    if request.method == "POST" and view is not None:
        hx = is_htmx(request)
        key = _buy_clicked(
            request,
            gang,
            gang.stash,
            view,
            into="the stash",
            collection=ALL_LABEL if everything else chosen.name,
            at=here,
        )
        if isinstance(key, Confirmation):
            if not hx:
                return render(
                    request,
                    "n26/confirm.html",
                    {"gang": gang, "confirmation": key},
                )
            return render_confirmation(request, key)
        if not hx:
            return redirect(here)
        if key is None:
            return no_update(request)
        return render_update(
            request,
            gang,
            key,
            list_param=wanted,
            expanded_key=expanded_key,
            at=here,
            closed=carried_confirmation(request),
        )

    host = screen.host(here)
    owned = possessions(host)
    refunds = not gang.credits_unlimited

    dialog = owned_dialog(request, host)
    if (panel := panel_response(request, dialog)) is not None:
        return panel

    if stash_tab:
        catalogue = build_stash_catalogue(
            owned,
            STASH_LABEL,
            refunds=refunds,
            expanded_key=expanded_key,
        )
        browsing = STASH_LABEL
    elif view is not None:
        catalogue = build_catalogue(
            view,
            owned,
            refunds=refunds,
            expanded_key=expanded_key,
        )
        browsing = ALL_BROWSING if everything else str(chosen or "")
    else:
        catalogue = None
        browsing = ""

    stash_picker = picker_context(catalogue, view, gang)
    return render(
        request,
        "n26/gang_equip.html",
        {
            "gang": gang,
            "action": here,
            "collection_tabs": gang_tabs(
                collections,
                chosen,
                everything,
                stash=stash_tab,
            ),
            "browsing": browsing,
            "catalogue": catalogue,
            "stash_tab": stash_tab,
            "everything": everything,
            "htmx": True,
            "held_label": host.held_label,
            "dialog": dialog,
            "accessorise": accessorise_dialogs(request, host),
            "summary": summarise_roster(gang_roster(gang)),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
            "founding_blocks_visit": (
                founding_blocks_visit(gang, may_see_founding(gang, request.user))
                if stash_picker["post_is_shut"]
                else False
            ),
            **stash_picker,
        },
    )
