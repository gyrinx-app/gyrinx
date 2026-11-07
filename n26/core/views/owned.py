"""Manage stored possessions and counter values through owner-authorised operations.

Possession routes identify assignments, which can belong to models, stashes
or weapons. Exclude foundational assignments such as a model's profile and
a gang's type from equipment actions.

Sale, refund and removal are distinct: sales return rating-based proceeds,
refunds return recorded payments, and removal returns nothing. Reassignment
preserves pricing; option changes settle their difference on the owned item.
Accessory purchases attach to a particular weapon.

Confirmation state comes from URL parameters. Ordinary POST responses redirect
to the source page; htmx responses update its existing hosts and deliver
messages as toasts. Determine source rows before operations move or archive
assignments. See n26.core.views.htmx.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from n26.core.owned import (
    DIALOGS,
    EquipHost,
    can_unbolt,
    is_built_in_profile,
    is_detachable,
    is_possession,
    thing_key,
    weapons_on,
    with_query,
)
from n26.core.views.htmx import is_htmx, no_update
from n26.core.views.permissions import _own_assignment_or_404, _safe_redirect
from n26.library.models import marked_name
from n26.library.staged import sees_staged

#: Bound direct tally changes below the integer storage limit.
MOST_A_TALLY_MOVES = 1000


def link_counters(card, back="", *, adjust=False):
    """Add controls for drawn, assigned counters without querying.

    Use the supplied source-page ``back`` rather than the request path: card
    updates can run under POST-only operation URLs. Undrawn counters remain
    available for conditions but receive no editing control.
    """
    for line in card.counters:
        if line.drawn and line.assignment_id:
            line.href = reverse("n26-tally", args=[line.assignment_id])
            line.back = back
            if adjust:
                line.adjust_href = with_query(line.href, back=back)


def _possession_or_404(request, pk):
    """Resolve an owned assignment and reject non-possession kinds with 404.

    Profiles and gang-type assignments are foundational records, so equipment
    routes must not expose sale or removal for them.
    """
    assignment = _own_assignment_or_404(request, pk)
    if not is_possession(assignment.assignable):
        raise Http404("Not something the gang owns")
    return assignment


def _bundled_profile_message(assignment, act):
    """Explain why a weapon's built-in profile cannot be removed separately."""
    name = assignment.assignable.name or str(assignment.assignable)
    weapon = str(assignment.parent.assignable) if assignment.parent_id else "the weapon"
    return f"You cannot {act} {name} on its own. It comes with {weapon}."


def _refuse_bundled_profile(request, assignment, act, back):
    """Return an unchanged response for attempts to remove a bundled profile."""
    if not is_built_in_profile(assignment):
        return None
    messages.error(request, _bundled_profile_message(assignment, act))
    return _unchanged(request, back)


def _held(host, pk):
    """Find an actionable possession in the host's loaded assignment tree.

    Ignore broadcast and suppressed nodes. Gang-broadcast equipment belongs to
    the gang, not the model whose card includes it.
    """
    for root in host.roots:
        for node in root.walk():
            if node.broadcast or node.suppressed:
                continue
            if node.assignment is None:
                continue
            if str(node.assignment.pk) != pk:
                continue
            if not is_possession(node.assignable):
                continue
            return node.assignment
    return None


def _roster(gang):
    from n26.core.models import Miniature

    return list(
        Miniature.objects.filter(
            membership__gang=gang, membership__archived=False
        ).order_by("name")
    )


def _other_models(gang, miniature):
    """List alternative live models on the gang's roster."""
    if miniature is None:
        return _roster(gang)
    return [model for model in _roster(gang) if model.pk != miniature.pk]


def _gang_weapons(gang):
    from n26.core.models import Assignment

    return list(
        Assignment.objects.filter(gang_root=gang, archived=False)
        .exclude(weapon=None)
        .select_related("weapon", "miniature_root")
        .order_by("miniature_root__name", "weapon__name")
    )


def accessory_catalogue(*, include_staged=False):
    """Load selectable accessories and their fit categories once for all weapons.

    Fit checks run in Python; preloading categories prevents a query per accessory.
    """
    from n26.library.models import WeaponAccessory

    return list(
        WeaponAccessory.objects.selectable(include_staged=include_staged)
        .select_related("fits_category")
        .order_by("name")
    )


def fitting_accessories(weapon, catalogue=None, *, include_staged=False):
    """Price selectable accessories compatible with a weapon.

    Reuse ``catalogue`` for multiple weapons. Compatibility narrows suggestions;
    the purchase operation does not prohibit other combinations.
    """
    if catalogue is None:
        catalogue = accessory_catalogue(include_staged=include_staged)
    return [
        {"pk": str(accessory.pk), "name": accessory.name, "price": accessory.price}
        for accessory in catalogue
        if accessory.fits(weapon)
    ]


def _asked(request):
    """Select the first named confirmation in DIALOGS order when several parameters exist."""
    for kind in DIALOGS:
        named = request.GET.get(kind)
        if named:
            return kind, named
    return None, None


#: Fit and Detach confirmation panels submit to the shared reassignment route.
ROUTES = {"fit": "reassign", "detach": "reassign"}


def refunded_credits(gang, paid):
    """Return recorded credit payment only when the gang tracks a credit budget."""
    return 0 if gang.credits_unlimited else paid


def refund_words(gang, paid, trade_points):
    """Describe refundable credits and founding trade points, omitting unused resources."""
    from django.template.defaultfilters import pluralize

    credits = refunded_credits(gang, paid)
    if not trade_points:
        return f"{credits}¢"
    points = f"{trade_points} Trade Point{pluralize(trade_points)}"
    return f"{credits}¢ and {points}" if credits else points


def removal_words(gang, paid, trade_points):
    """Explain that removal returns nothing and identify any available refund alternative."""
    if not gang.credits_unlimited:
        return "No credits are returned. Use Refund instead to recover the amount paid."
    if trade_points:
        return (
            "Nothing comes back. Use Refund instead to get "
            f"{refund_words(gang, paid, trade_points)} back."
        )
    return "Nothing comes back."


def _panel(request, assignment, kind, at):
    """Build shared confirmation fields, preserving catalogue and section navigation state."""
    from n26.core.views.choose import SHOWING, showing_dismissed

    return {
        "kind": kind,
        # Keep the two-slot marker used by the clicked listing label.
        "name": marked_name(assignment.assignable),
        "cancel_url": at,
        "action": reverse(f"n26-{ROUTES.get(kind, kind)}", args=[assignment.pk]),
        "list": request.GET.get("list", ""),
        # Preserve the catalogue section in this separate confirmation form.
        "section": request.GET.get("section", ""),
        "dismissed": SHOWING if showing_dismissed(at) else "",
    }


def panel_response(request, dialog, *, htmx=True):
    """Render a confirmation partial for htmx GETs, otherwise return ``None``.

    Replace the URL so reloads reproduce the open panel. Only callers containing
    all required update hosts may permit partial form submission.
    """
    if request.method != "GET" or not is_htmx(request):
        return None
    response = render(
        request, "n26/includes/equip_panel.html", {"dialog": dialog, "htmx": htmx}
    )
    response["HX-Replace-Url"] = request.get_full_path()
    return response


def accessorise_dialogs(request, host: EquipHost):
    """Build one accessory panel per owned weapon using a shared catalogue query.

    The URL selects which panel starts open. Pre-rendered panels avoid rebuilding
    the listing for each open action; hosts without weapons issue no catalogue read.
    """
    kind, named = _asked(request)
    weapons = weapons_on(host)
    if not weapons:
        return []

    catalogue = accessory_catalogue(include_staged=sees_staged(request.user))
    dialogs = []
    for node in weapons:
        pk = str(node.assignment.pk)
        accessories = fitting_accessories(node.assignable, catalogue)
        panel = _panel(request, node.assignment, "accessorise", host.at)
        dialogs.append(
            panel
            | {
                # Use the assignment identifier shared with the panel-opening control.
                "id": pk,
                "open": kind == "accessorise" and named == pk,
                "title": f"Add an accessory to {panel['name']}",
                "accessories": accessories,
                # Omit the submit control when there are no compatible accessory suggestions.
                "submit_label": "Add accessory" if accessories else "",
                "submit_variant": "success",
            }
        )
    return dialogs


def owned_dialog(request, host: EquipHost):
    """Build the URL-selected confirmation for an actionable possession on this host.

    Unknown assignments and invalid actions display no panel. Accessory purchase
    panels are built separately by ``accessorise_dialogs`` to avoid duplication.
    """
    from n26.core.operations import (
        MINIMUM_PROCEEDS,
        detachable_children,
        refund_of,
        sale_of,
        trade_points_in,
    )

    kind, named = _asked(request)
    if kind is None or kind == "accessorise":
        return None

    gang = host.gang
    assignment = _held(host, named)
    if assignment is None:
        return None
    if kind == "reassign" and assignment.pk in host.bound_items:
        return None
    # Suppress separate removal confirmations for bundled profiles.
    if kind in {"sell", "refund", "remove"} and is_built_in_profile(assignment):
        return None

    # Read recorded payments only when they affect refund availability or wording.
    asks_figures = kind == "refund" or (kind == "remove" and gang.credits_unlimited)
    refunding, paid = refund_of(assignment) if asks_figures else ((), 0)
    points = trade_points_in(refunding)
    # Unlimited-credit purchases with no refundable founding points use removal.
    if kind == "refund" and gang.credits_unlimited and not points:
        kind = "remove"

    name = marked_name(assignment.assignable)
    # Use Remove for nested possessions because their top-level weapon remains.
    is_part = assignment.parent_id is not None
    dialog = _panel(request, assignment, kind, host.at) | {
        "stash_host": host.is_stash,
        # Compute removal wording here using the already-loaded payment figures.
        "remove_note": removal_words(gang, paid, points),
    }

    if kind == "sell":
        # Default proceeds to keeping detachable accessories in the stash.
        # Offer that choice only when a stash exists, matching the sale route.
        keepable = (
            detachable_children(assignment)
            if getattr(gang, "stash", None) is not None
            else []
        )
        _, rating, proceeds = sale_of(assignment, keeping=keepable)
        # Explain whether rounding or the minimum sale price determined proceeds.
        halved = proceeds * 2 <= rating + 1
        sale = dialog | {
            "title": f"Sell {name}?",
            "proceeds": proceeds,
            "rating": rating,
            "sum": (
                f"Half of its {rating}¢ rating, rounded up — {proceeds}¢."
                if halved
                else f"{proceeds}¢: half of its {rating}¢ rating is below the "
                f"{MINIMUM_PROCEEDS}¢ minimum sale price."
            ),
            "submit_label": "Sell",
            "submit_variant": "danger",
        }
        if not keepable:
            return sale
        # Show separate proceeds for selling the detachable accessories too.
        _, _, with_extras = sale_of(assignment)
        word = "accessory" if len(keepable) == 1 else "accessories"
        return sale | {
            # Name the accessories being kept or sold so the choice identifies its contents.
            "keepable": ", ".join(str(child.assignable) for child in keepable),
            "keep_label": f"Stash the {word}",
            "keep_detail": f"Keep to refit later. {proceeds}¢ for the gun alone.",
            "sell_all_label": f"Sell the {word} too",
            "sell_all_detail": f"Everything goes together. {with_extras}¢.",
        }

    if kind == "reassign":
        if host.is_stash and assignment.weapon_accessory_id:
            weapons = _gang_weapons(gang)
            return dialog | {
                "title": f"Fit {name} to a weapon",
                "weapons": [
                    {
                        "pk": str(weapon.pk),
                        "label": (
                            f"{marked_name(weapon.assignable)} "
                            f"({weapon.miniature_root.name})"
                            if weapon.miniature_root_id
                            else f"{marked_name(weapon.assignable)} (stash)"
                        ),
                    }
                    for weapon in weapons
                ],
                "submit_label": "Fit" if weapons else "",
                "submit_variant": "primary",
            }
        models = _other_models(gang, host.miniature)
        return dialog | {
            "title": f"Move {name}",
            "models": models,
            "submit_label": "Move" if host.is_stash or models else "To the stash",
            "submit_variant": "primary",
        }

    if kind == "fit":
        # Reject Fit panels for non-accessories to prevent invalid self-attachment choices.
        if assignment.weapon_accessory_id is None:
            return None
        # Bundled accessories stay with their granting weapon.
        # Enforce this here because the reassignment operation does not reject them.
        if assignment.caused_by_id is not None:
            return None
        # Offer other weapons without compatibility gating, excluding the current parent.
        weapons = [
            node
            for node in weapons_on(host)
            if node.assignment.pk != assignment.parent_id
        ]
        # Hide Fit when an attached accessory has no alternative weapon; loose ones show the empty state.
        if not weapons and assignment.parent_id is not None:
            return None
        return dialog | {
            "title": f"Fit {name} to a weapon",
            "weapons": [
                {"pk": str(node.assignment.pk), "label": marked_name(node.assignable)}
                for node in weapons
            ],
            "submit_label": "Fit" if weapons else "",
            "submit_variant": "primary",
        }

    if kind == "detach":
        # Detach applies only to independently bought, currently attached accessories.
        if not can_unbolt(assignment):
            return None
        parent = assignment.parent.assignable
        return dialog | {
            "title": f"Take {name} off {parent}?",
            "submit_label": "Detach",
            "submit_variant": "primary",
        }

    if kind == "rechoose":
        from n26.core.browse import offered_choices
        from n26.core.listing import pick_group_props, pick_groups
        from n26.core.operations import option_refunds
        from n26.library.models.assignable import Optioned

        thing = assignment.assignable
        if not isinstance(thing, Optioned) or not thing.offers_a_choice:
            return None
        recorded = list(assignment.chosen_options.select_related("default_set"))
        taken = {row.default_set_id for row in recorded}
        choices = pick_groups(offered_choices(thing), thing_key(thing), taken=taken)
        refunds = option_refunds(assignment, [row.default_set for row in recorded])
        return dialog | {
            "title": f"Change {name}'s options",
            "choices": choices,
            "price_preview": {
                "changing": True,
                "choices": pick_group_props(choices),
                "before": sum(row.default_set.price for row in recorded),
                "held": sorted(str(key) for key in taken),
                "refunds": [
                    {
                        "setKey": str(key),
                        "entries": [
                            {"key": str(row.pk), "paid": entry.paid}
                            for row in rows
                            if (entry := getattr(row, "ledger_entry", None)) is not None
                            and entry.paid
                        ],
                    }
                    for key, rows in refunds.items()
                ],
                "resolution": [
                    {
                        "choose": group.choose if group is not None else "one",
                        "options": [
                            {"setKey": str(option.pk), "price": option.price}
                            for option in options
                        ],
                    }
                    for group, options in thing.grouped_options()
                ],
            },
            "submit_label": "Save options",
            "submit_variant": "success",
        }

    if kind == "refund":
        # Refunds use recorded payments rather than catalogue prices, including founding trade points.
        credits = refunded_credits(gang, paid)
        return dialog | {
            "title": f"Refund {name}?",
            "proceeds": credits,
            "trade_points": points,
            "sum": (
                f"You get {refund_words(gang, paid, points)} back — the amount "
                "paid, not its rating."
                if credits or points
                else "Nothing was paid for this, so nothing comes back."
            ),
            "submit_label": "Refund",
            "submit_variant": "danger",
        }

    return dialog | {
        "title": f"{'Remove' if is_part else 'Delete'} {name}?",
        "submit_label": "Remove" if is_part else "Delete",
        "submit_variant": "danger",
    }


def link_stash_actions(sheet, at, *, refunds=True, bound_items=frozenset()):
    """Add stash action URLs from loaded line data, without querying.

    Offer refunds when credits can return or a founding allowance paid trade points.
    """
    from n26.core.listing import DANGER, LINK, SECONDARY, Action

    bound_ids = {str(pk) for pk in bound_items}
    for line in sheet.stash:
        if not line.id:
            continue
        menu = []
        if line.id not in bound_ids:
            menu.append(
                Action(
                    "Fit to a weapon" if line.is_accessory else "Reassign",
                    LINK,
                    with_query(at, reassign=line.id),
                    SECONDARY,
                )
            )
        menu.append(Action("Sell", LINK, with_query(at, sell=line.id), DANGER))
        if refunds or line.paid_trade_points:
            menu.append(
                Action("Refund", LINK, with_query(at, refund=line.id), SECONDARY)
            )
        menu.append(Action("Delete", LINK, with_query(at, remove=line.id), DANGER))
        line.menu = stash_menu(menu)


def stash_menu(actions):
    """Order ordinary links before destructive links, separating each destructive action."""
    from n26.core.listing import DANGER, LINK

    def entry(action, separator_before=False):
        if action.kind != LINK:
            raise ValueError(f"A stash menu draws links only, not {action.kind!r}")
        return {
            "label": action.label,
            "href": action.target,
            "tone": "danger" if action.tone == DANGER else "default",
            "separator_before": separator_before,
        }

    actions = tuple(actions)
    separate = len(actions) > 1
    return tuple(entry(a) for a in actions if a.tone != DANGER) + tuple(
        entry(a, separate) for a in actions if a.tone == DANGER
    )


def link_possession_actions(model_card, host, *, refunds=True):
    """Add equipment action links from the host's loaded possession tree.

    Unassigned grants and preview content remain unlinked. Refund availability
    uses the same credit and founding-allowance rules as catalogue listings.
    """
    from dataclasses import replace

    from n26.core.listing import copy_row
    from n26.core.owned import possessions

    copies, parts = {}, {}
    for held in possessions(host).values():
        for copy in held:
            row = copy_row(copy, refunds=refunds)
            copies[row.id] = row
            for part in row.parts:
                parts[part.id] = part

    def linked(lines):
        return [
            replace(line, sell=row.sell, more=row.more)
            if (row := copies.get(line.id))
            else line
            for line in lines
        ]

    model_card.equipment = linked(model_card.equipment)
    # Apply possession menus to category-specific gear groups too.
    for group in model_card.gear_groups:
        group.lines = linked(group.lines)
    for weapon in model_card.weapons:
        if row := copies.get(weapon.id):
            weapon.sell = row.sell
            weapon.more = row.more
            weapon.accessorise = row.accessorise
        weapon.accessories = [
            replace(line, sell=part.sell, more=part.more)
            if (part := parts.get(line.id))
            else line
            for line in weapon.accessories
        ]
        for profile in weapon.profiles:
            if part := parts.get(profile.id):
                profile.sell = part.sell
                profile.more = part.more


def _back_to(request, assignment, gang):
    """Infer the source screen and navigation state before an assignment moves."""
    if assignment.stash_root_id or assignment.stash_id:
        base = reverse("n26-equip-gang", args=[gang.pk])
    elif assignment.miniature_root_id:
        base = reverse("n26-equip", args=[assignment.miniature_root_id])
    else:
        base = reverse("n26-gang", args=[gang.pk])
    where = {
        key: value
        for key in ("list", "section", "owned", "dismissed")
        if (value := request.POST.get(key, ""))
    }
    return with_query(base, **where) if where else base


def _return_to(request, fallback):
    return _safe_redirect(request, request.POST.get("return"), fallback_url=fallback)


@dataclass(frozen=True)
class _Touched:
    """A changed catalogue key and the model whose listing renders it."""

    key: str
    miniature: object | None


def _row_behind(assignment):
    """Find the top-level listing containing an assignment.

    Read before moving or archiving it, because its source host may change.
    """
    node = assignment
    while node.parent_id is not None:
        node = node.parent
    return _Touched(key=thing_key(node.assignable), miniature=node.miniature_root)


def _unchanged(request, back):
    """Return queued messages without a row update, or redirect an ordinary submission."""
    if not is_htmx(request):
        return _return_to(request, back)
    return no_update(request)


def _acted(request, touched, gang, back, also=""):
    """Update affected htmx rows and close the panel, or redirect to the source page.

    Preserve expanded-row state from POST. ``also`` identifies another changed
    row on that same screen.
    """
    from n26.core.views.equip import render_update

    if not is_htmx(request):
        return _return_to(request, back)

    response = render_update(
        request,
        gang,
        touched.key,
        miniature=touched.miniature,
        list_param=request.POST.get("list", "")[:100],
        expanded_key=request.POST.get("owned", "")[:200],
        at=back,
        closed=True,
        also=also,
    )
    response["HX-Replace-Url"] = back
    return response


@login_required
@require_POST
def sell_assignment(request, pk):
    """Sell a possession through an operation, returning rating-based proceeds.

    Keep detachable accessories in the stash unless POST requests their sale
    or the gang has no stash. Move them before sale so proceeds use the
    remaining item; each move preserves its recorded price.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, detachable_children, operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    back = _back_to(request, assignment, gang)
    if refused := _refuse_bundled_profile(request, assignment, "sell", back):
        return refused
    touched = _row_behind(assignment)

    stash = getattr(gang, "stash", None)
    keeping = (
        []
        if request.POST.get("accessories") == "sell" or stash is None
        else detachable_children(assignment)
    )

    try:
        with operation(gang, actor=request.user) as op:
            # Move kept accessories before sale so they are excluded from sale proceeds.
            for child in keeping:
                op.move(child, stash)
            proceeds = op.sell(assignment)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return _unchanged(request, back)
    if proceeds is None:
        messages.info(request, f"{name} was already removed.")
        return _unchanged(request, back)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.ARCHIVE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=name,
        action="sell",
        proceeds=proceeds,
        stashed=len(keeping),
    )
    if keeping:
        kept = ", ".join(str(child.assignable) for child in keeping)
        messages.success(
            request, f"Sold {name} for {proceeds}¢. {kept} went to the stash."
        )
    else:
        messages.success(request, f"Sold {name} for {proceeds}¢.")
    return _acted(request, touched, gang, back)


@login_required
@require_POST
def reassign_assignment(request, pk):
    """Move a possession without changing its recorded price or rating.

    ``to`` selects stash, miniature, weapon or held. Held detaches an accessory
    onto its weapon's existing model or stash. Reject bundled accessories here;
    operations enforce weapon-profile movement constraints.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import Assignment, Miniature
    from n26.core.operations import Refusal, operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    # Determine the source page before movement changes the assignment host.
    came_from = assignment.miniature_root
    off = str(assignment.parent.assignable) if assignment.parent_id else ""
    back = _back_to(request, assignment, gang)
    touched = _row_behind(assignment)
    name = str(assignment.assignable)

    # Movement restrictions apply to the part independently of its proposed destination.
    stays_on = (
        f"You cannot take {name} off {off}. Only a bought accessory can come off."
    )
    # Bundled accessories stay with their granting weapon.
    # Enforce this here because the reassignment operation does not reject them.
    if (
        assignment.parent_id is not None
        and assignment.caused_by_id is not None
        and is_detachable(assignment.assignable)
    ):
        messages.error(request, stays_on)
        return _unchanged(request, back)

    wanted = request.POST.get("to")
    if wanted == "stash":
        destination = getattr(gang, "stash", None)
    elif wanted == "held":
        # Detach to the weapon's current model or stash, preserving its top-level host.
        if assignment.parent_id is None:
            destination = None
        elif not can_unbolt(assignment):
            messages.error(request, stays_on)
            return _unchanged(request, back)
        elif assignment.miniature_root_id:
            destination = assignment.miniature_root
        else:
            destination = getattr(gang, "stash", None)
    elif wanted == "weapon":
        try:
            destination = (
                Assignment.objects.filter(
                    pk=request.POST.get("weapon", ""),
                    gang_root=gang,
                    archived=False,
                )
                .exclude(weapon=None)
                # Reject the assignment itself and its current parent as weapon destinations.
                .exclude(pk=assignment.pk)
                .exclude(pk=assignment.parent_id)
                .first()
            )
        except ValidationError:
            destination = None
    else:
        try:
            destination = Miniature.objects.filter(
                pk=request.POST.get("miniature", ""),
                membership__gang=gang,
                membership__archived=False,
            ).first()
        except ValidationError:
            destination = None
    if destination is None:
        messages.error(request, f"There is nowhere to move {name} to.")
        return _unchanged(request, back)

    # Fit and Detach can change both the weapon and accessory rows on the same screen.
    if wanted == "held":
        also = thing_key(assignment.assignable)
    else:
        landed = (
            _row_behind(destination) if isinstance(destination, Assignment) else None
        )
        also = landed.key if landed and landed.miniature == touched.miniature else ""

    try:
        with operation(gang, actor=request.user) as op:
            op.reassign(assignment, destination)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return _unchanged(request, back)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.UPDATE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(came_from.pk) if came_from else None,
        thing=name,
        action="reassign",
        to=wanted if wanted in ("stash", "weapon", "held") else "model",
    )
    if wanted == "stash":
        messages.success(request, f"Moved {name} to the stash.")
    elif wanted == "weapon":
        messages.success(request, f"Fitted {name} to {destination.assignable}.")
    elif wanted == "held":
        if came_from is None:
            messages.success(request, f"Took {name} off {off}. It is in the stash.")
        else:
            messages.success(request, f"Took {name} off {off}.")
    else:
        messages.success(request, f"Moved {name} to {destination.name}.")
    if wanted == "held" and came_from is None and is_htmx(request):
        # Detaching in the stash creates a row absent from the current page.
        # Reload because an out-of-band update cannot insert it by a missing identifier.
        response = HttpResponse(status=200)
        response["HX-Redirect"] = back
        return response
    return _acted(request, touched, gang, back, also=also)


@login_required
@require_POST
def rechoose_assignment(request, pk):
    """Replace acquisition options and settle their price difference on the owned item.

    Parse offered options from server-derived content. The operation rolls back
    the whole replacement on refusal. Detect changed option sets independently
    of payment, because two alternatives may have the same price.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.browse import offered_choices
    from n26.core.operations import Refusal, operation
    from n26.core.views.equip import _choices_picked
    from n26.library.models.assignable import Optioned

    assignment = _possession_or_404(request, pk)
    thing = assignment.assignable
    if not isinstance(thing, Optioned) or not thing.offers_a_choice:
        # Only content with offered acquisition alternatives supports rechoosing.
        raise Http404("Nothing to choose")
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    back = _back_to(request, assignment, gang)
    touched = _row_behind(assignment)

    picked = _choices_picked(request.POST, thing_key(thing), offered_choices(thing))
    taken = {row.default_set_id for row in assignment.chosen_options.all()}
    entry = getattr(assignment, "ledger_entry", None)
    before = entry.paid if entry is not None else 0
    try:
        with operation(gang, actor=request.user) as op:
            op.rechoose(assignment, option=[option.default_set for option in picked])
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return _unchanged(request, back)
    if entry is not None:
        entry.refresh_from_db()
    after = entry.paid if entry is not None else 0

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.UPDATE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=str(thing),
        action="rechoose",
        delta=after - before,
    )
    # Compare recorded option sets because a real option change can have zero payment difference.
    now = {row.default_set_id for row in assignment.chosen_options.all()}
    if now == taken:
        messages.success(request, f"{thing}'s options are unchanged.")
        return _unchanged(request, back)
    holds = ", ".join(option.name for option in thing.options_taken(now))
    settled = (
        f" — {after - before}¢ more."
        if after > before
        else f" — {before - after}¢ back."
        if after < before
        else "."
    )
    messages.success(request, f"{thing} now has {holds}{settled}")
    return _acted(request, touched, gang, back)


@login_required
@require_POST
def accessorise_assignment(request, pk):
    """Buy a selectable accessory at its library price under an owned weapon.

    Read identity and price server-side. Compatibility is a catalogue suggestion,
    not an operation restriction.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation
    from n26.library.models import Weapon, WeaponAccessory

    assignment = _possession_or_404(request, pk)
    if not isinstance(assignment.assignable, Weapon):
        # Accessory purchases must target an owned weapon.
        raise Http404("Not a weapon")
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    back = _back_to(request, assignment, gang)
    touched = _row_behind(assignment)

    try:
        accessory = WeaponAccessory.objects.selectable(
            include_staged=sees_staged(request.user)
        ).get(pk=request.POST.get("accessory", ""))
    except WeaponAccessory.DoesNotExist, ValidationError, ValueError:
        # Return stale or invalid selections to the source catalogue.
        messages.error(request, "That accessory does not fit this weapon.")
        return _unchanged(request, back)

    try:
        with operation(gang, actor=request.user) as op:
            bought = op.buy(assignment, thing=accessory)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return _unchanged(request, back)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.CREATE,
        bought,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=accessory.name,
        action="accessorise",
        onto=str(assignment.assignable),
        paid=bought.rating,
    )
    messages.success(
        request,
        f"Fitted {accessory.name} to {assignment.assignable} — "
        f"{bought.ledger_entry.paid}¢.",
    )
    return _acted(request, touched, gang, back)


@login_required
@require_POST
def remove_assignment(request, pk):
    """Archive a possession without returning credits, preserving its purchase history."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    back = _back_to(request, assignment, gang)
    if refused := _refuse_bundled_profile(request, assignment, "remove", back):
        return refused
    touched = _row_behind(assignment)

    try:
        with operation(gang, actor=request.user) as op:
            removed = op.remove(assignment)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return _unchanged(request, back)
    if removed is None:
        messages.info(request, f"{name} was already removed.")
        return _unchanged(request, back)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.ARCHIVE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=name,
        action="remove",
    )
    messages.success(request, f"Removed {name}.")
    return _acted(request, touched, gang, back)


@login_required
@require_POST
def refund_assignment(request, pk):
    """Archive a purchase and return its recorded credits and founding trade points.

    Calculate payments before the operation zeroes ledger entries. Unlimited-credit
    gangs with no refundable founding points use removal instead.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation, refund_of, trade_points_in

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    back = _back_to(request, assignment, gang)
    if refused := _refuse_bundled_profile(request, assignment, "refund", back):
        return refused
    refunding, paid = refund_of(assignment)
    points = trade_points_in(refunding)
    # A gang with no budget pays no credits, so unless a founding
    # allowance paid for this there is nothing to give back: the act
    # behind this address is the removal the dialog promised.
    if gang.credits_unlimited and not points:
        return remove_assignment(request, pk)
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    touched = _row_behind(assignment)

    try:
        with operation(gang, actor=request.user) as op:
            refunded = op.refund(assignment)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return _unchanged(request, back)
    if refunded is None:
        messages.info(request, f"{name} was already removed.")
        return _unchanged(request, back)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.ARCHIVE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=name,
        action="refund",
        refunded=paid,
        trade_points=points,
    )
    messages.success(
        request, f"Refunded {name} — {refund_words(gang, paid, points)} back."
    )
    return _acted(request, touched, gang, back)


def _campaign_counter_update(request, assignment, gang, back, *, close=False):
    """Refresh a gang counter and, when displayed, its campaign table."""
    from urllib.parse import urlsplit

    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute_gang
    from n26.core.render import build_campaign_block
    from n26.core.views.htmx import with_toasts

    card = build_gang_card(gang)
    index = build_modifier_index(carriers(card, *card.members.values()))
    block = build_campaign_block(card, index=index, computed=compute_gang(card, index))
    if block is None:
        return no_update(request)
    link_counters(block, back=back, adjust=True)
    counter = next(
        (line for line in block.counters if line.assignment_id == str(assignment.pk)),
        None,
    )
    if counter is None:
        return no_update(request)
    messages.success(request, f"{counter.name} is now {counter.value}.")

    sheet = None
    if (
        urlsplit(back).path == reverse("n26-campaign", args=[block.campaign_id])
        and request.user.is_authenticated
    ):
        from n26.core.render import render_campaign
        from n26.core.views.campaigns import _fill_addresses
        from n26.core.views.permissions import _any_campaign_or_404

        campaign = _any_campaign_or_404(
            request, block.campaign_id, with_owner_badge=False
        )
        sheet = render_campaign(campaign, viewer=request.user)
        _fill_addresses(
            sheet,
            campaign,
            yours=campaign.owner_id == request.user.pk,
            viewer=request.user,
            request=request,
            current_url=back,
        )
        if close:
            sheet.table_focus_counter = str(assignment.pk)
    return with_toasts(
        request,
        render(
            request,
            "n26/includes/campaign_counter_update.html",
            {
                "counter": counter,
                "sheet": sheet,
                "redrawn": True,
                "close_dialog": close,
                "steps": back == reverse("n26-gang", args=[gang.pk]),
            },
        ),
    )


def _shown_counter_value(assignment, gang, miniature, recorded):
    """Read the displayed total including computed contributions, falling back to storage."""
    if miniature is None:
        from n26.core.card import build_gang_card, build_modifier_index, carriers
        from n26.core.effects import compute_gang
        from n26.core.render import build_campaign_block

        card = build_gang_card(gang)
        index = build_modifier_index(carriers(card, *card.members.values()))
        block = build_campaign_block(
            card, index=index, computed=compute_gang(card, index)
        )
        lines = () if block is None else block.counters
    else:
        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute
        from n26.core.render import build_model_card

        own = build_card(miniature)
        card = build_model_card(
            miniature,
            card=own,
            computed=compute(own, build_modifier_index(carriers(own))),
            rank_summaries=(),
        )
        lines = card.counters
    line = next(
        (item for item in lines if item.assignment_id == str(assignment.pk)),
        None,
    )
    return recorded if line is None else line.value


@login_required
@require_http_methods(["GET", "POST"])
def tally_counter(request, pk):
    """Adjust an authorised counter through an operation, respecting its minimum.

    Ordinary changes use a bounded signed amount. Income editing targets the
    displayed total and derives its stored adjustment from contributions under
    the gang lock; reset restores its minimum. Recheck archived assignments
    inside the operation.

    Gang owners can adjust their counters. Campaign arbitrators can also adjust
    counters caused by the gang's active campaign membership.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import CounterAdjustmentForm, IncomeValueForm
    from n26.core.operations import Refusal, operation
    from n26.core.views.edit import render_card_update
    from n26.core.views.permissions import _campaign_counter_or_404
    from n26.library.models import Counter

    assignment = _campaign_counter_or_404(request, pk)
    if not isinstance(assignment.assignable, Counter):
        raise Http404("Not a counter")
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    from n26.library.income import is_income_counter

    income = miniature is None and is_income_counter(assignment.assignable)
    resetting = request.method == "POST" and "reset" in request.POST
    if resetting and not income:
        raise Http404("Not an income adjustment")
    data = request.GET if request.method == "GET" else request.POST
    back = data.get("back", "")[:500]
    here = reverse("n26-gang", args=[gang.pk])
    adjusting = request.method == "GET" or "adjust" in request.POST
    setting_income = (
        income
        and not resetting
        and (request.method == "GET" or (adjusting and "value" in request.POST))
    )
    if adjusting:
        back = _safe_redirect(request, back, here).url
        if setting_income:
            form = IncomeValueForm(request.POST if request.method == "POST" else None)
        else:
            # Calculate reset under the gang lock; use a valid negative step to enter that branch.
            form = CounterAdjustmentForm(
                {"change": -1}
                if resetting
                else request.POST
                if request.method == "POST"
                else None,
                maximum=MOST_A_TALLY_MOVES,
            )
        field_name = "value" if setting_income else "change"

        def adjustment_page():
            from n26.core.models import CounterValue

            value = (
                CounterValue.objects.filter(assignment=assignment)
                .values_list("value", flat=True)
                .first()
            )
            if value is None:
                value = assignment.assignable.minimum
            total = _shown_counter_value(assignment, gang, miniature, value)
            preview = {
                "value": total,
                "recorded": value,
                "minimum": assignment.assignable.minimum,
                "change": "" if setting_income else str(form["change"].value() or ""),
                "inputValue": str(form["value"].value() or "")
                if setting_income and form.is_bound
                else str(total),
                "errors": list(form[field_name].errors),
                "maximum": MOST_A_TALLY_MOVES,
                "isIncome": income,
            }
            response = render(
                request,
                "n26/includes/campaign_counter_dialog.html"
                if is_htmx(request)
                else "n26/adjust_counter.html",
                {
                    "form": form,
                    "assignment": assignment,
                    "gang": gang,
                    "name": name,
                    "value": value,
                    "counter_preview": preview,
                    "back": back,
                    "maximum": MOST_A_TALLY_MOVES,
                    "reopened": request.method == "POST",
                },
            )
            if is_htmx(request) and request.method == "GET":
                response["HX-Replace-Url"] = request.get_full_path()
            return response

        if request.method == "GET" or not form.is_valid():
            return adjustment_page()
        change = 0 if setting_income else form.cleaned_data["change"]
    else:
        try:
            change = int(request.POST.get("change", ""))
        except ValueError:
            raise Http404("Not a change to make") from None
    if not setting_income and (not change or abs(change) > MOST_A_TALLY_MOVES):
        # Reject zero and oversized direct steps to avoid empty history events and integer overflow.
        raise Http404("Not a change to make")

    try:
        with operation(gang, actor=request.user) as op:
            # Recheck archive state under the operation lock in case an arbitrator removed the counter.
            if (
                type(assignment)
                .objects.filter(pk=assignment.pk, archived=True)
                .exists()
            ):
                raise Refusal(f"{name} is no longer on {gang.name}.")
            if setting_income or (adjusting and change < 0):
                from n26.core.models import CounterValue

                value = (
                    CounterValue.objects.filter(assignment=assignment)
                    .values_list("value", flat=True)
                    .first()
                )
                if value is None:
                    value = assignment.assignable.minimum
                if setting_income:
                    contributions = _shown_counter_value(
                        assignment, gang, miniature, value
                    ) - max(assignment.assignable.minimum, value)
                    adjustment = form.cleaned_data["value"] - contributions
                    if adjustment < assignment.assignable.minimum:
                        raise Refusal(
                            f"Income cannot be lower than {contributions + assignment.assignable.minimum}¢ from contributions and the counter minimum."
                            if assignment.assignable.minimum
                            else f"Income cannot be lower than the total contributions of {contributions}¢."
                        )
                    if adjustment > 2147483647:
                        raise Refusal("The adjustment cannot exceed 2147483647¢.")
                    change = adjustment - value
                elif value == 0 and assignment.assignable.minimum == 0:
                    raise Refusal(
                        "This counter is already 0. Enter a positive amount to increase it."
                    )
                if resetting:
                    change = assignment.assignable.minimum - value
            standing = op.tally(assignment, change) if change else value
    except Refusal as refusal:
        if adjusting:
            form.add_error(field_name, str(refusal))
            return adjustment_page()
        messages.error(request, str(refusal))
        if is_htmx(request):
            # Keep existing page state and deliver the refusal as a toast.
            return no_update(request)
        return _safe_redirect(request, back, here)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.UPDATE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=name,
        action="tally",
        change=change,
    )
    if miniature is not None and is_htmx(request):
        # Inline steps update without a toast; dialog adjustments announce the result and close the panel.
        landing = back or reverse("n26-edit-fighter", args=[miniature.pk])
        if adjusting:
            response = render_card_update(
                request,
                miniature,
                landing,
                close_counter_dialog=True,
                announce_counter=str(assignment.pk),
            )
            response["HX-Replace-Url"] = landing
            return response
        return render_card_update(request, miniature, landing)
    if miniature is None and is_htmx(request):
        response = _campaign_counter_update(
            request, assignment, gang, back or here, close=adjusting
        )
        if adjusting:
            response["HX-Replace-Url"] = back or here
        return response
    if adjusting:
        if setting_income:
            messages.success(request, f"{name} is now {form.cleaned_data['value']}¢.")
        else:
            messages.success(request, f"{name}: recorded value is now {standing}.")
    else:
        messages.success(request, f"{name} is now {standing}.")
    return _safe_redirect(request, back, here)
