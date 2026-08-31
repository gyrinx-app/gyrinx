"""What a fighter already owns — selling it, handing it on, taking it off.

Seven acts, seven addresses, one shape each: a POST names the assignment
in its path, an ``operation`` writes it, and the reader lands back where
they clicked. They are addressed by *assignment* rather than by
fighter, because that is what they are about — a weapon on a fighter, a
sight on that weapon, a crate in the stash are all one assignment — and
because the next screen that wants them (a gang sheet, a stash page) then needs
no routes of its own.

Which dialog is open is URL state on the screen that opened it
(``?sell=<assignment>``), so an open confirmation is a link, survives a
reload, and is drawn by the server rather than revealed by a script. The
click behind it is a real form to a real address, so it works with
scripting switched off.

An operation that refuses an act answers on the screen it was clicked
from — a control the page drew is owed a sentence, not a traceback — and
nothing is written, because the refusal unwinds the transaction.

Each act responds in one of two shapes. A plain submission redirects back to
the screen the click came from. One sent by htmx gets a partial update
instead — the changed row, the money, the panel closed — built by
:func:`n26.core.views.equip.render_update`; the protocol is documented in
:mod:`n26.core.views.htmx`.

The acts are deliberately distinct, and the ledger says which happened:

``sell``
    Half of the thing's rating, rounded up, into the gang's credits.
    Not a refund: what was paid has nothing to do with it. A gun with
    something bolted to it asks one more question — whether the
    accessories are being sold with it or kept — because those are two
    sales at two prices.
``reassign``
    A move to another model, to the stash, or onto a weapon. No money,
    and no re-pricing. The last of the three is how an accessory is
    fitted to a gun: the same act, one level down the chain. It is asked
    as a question of its own — ``?fit=`` rather than ``?reassign=`` —
    because which model holds a thing and which gun it is bolted to are
    not one question, however much they are one act.
``refund``
    Undoing the purchase: every credit that was paid comes back. The amount
    paid and the rating part company at the first discount, which is why
    this is not a sale.
``remove``
    Permanently removed from the gang, with no credit change.
``accessorise``
    A purchase, hosted on the weapon rather than on the fighter. The only
    one that adds something.
``rechoose``
    Taking a thing with different alternatives to the ones it was bought
    with. The difference settles either way, on the thing's own line.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.urls import reverse
from django.views.decorators.http import require_POST

from n26.core.owned import (
    DIALOGS,
    EquipHost,
    is_possession,
    thing_key,
    weapons_on,
    with_query,
)
from n26.core.views.htmx import is_htmx, no_update
from n26.core.views.permissions import _own_assignment_or_404, _safe_redirect

#: The largest step this address will take, either way. Far above any
#: step a control offers, and far below what the column holds.
MOST_A_TALLY_MOVES = 1000


def link_counters(card, back=""):
    """Point every counter line on this card at what changes it.

    Costs no queries: the line already carries the assignment behind it,
    and this only turns it into a URL. A line with none keeps an empty
    href and draws as a number with nothing to click — which is right
    for a card depicting nobody, and for every screen that shows a
    counter without offering to move it.

    ``back`` is the screen the card is drawn on, which the controls carry
    so a reader with no scripting lands there. It is passed rather than
    read off the request because a card redrawn after an act is rendered
    under that act's own address, and a control sent back carrying it
    would return the next reader to a POST-only endpoint.
    """
    for line in card.counters:
        if line.assignment_id:
            line.href = reverse("n26-tally", args=[line.assignment_id])
            line.back = back


def _possession_or_404(request, pk):
    """One of the viewer's own assignments, and one these acts are *about*.

    ``_own_assignment_or_404`` answers who may act; this answers on what.
    Both are needed, because a gang holds a great deal that is not kit and
    every bit of it is an assignment with a primary key: the assignment
    naming a model's profile **is** the model, and selling it would take
    the fighter off the roster and everything they carry with them, for
    half the price of the profile and nothing for the kit. The one naming
    the gang's type is the gang. Neither has any business arriving at a
    listing row's Sell button.

    A 404 rather than a message: no control anywhere draws these
    addresses, so a click that reaches here is a hand-made URL, and the
    honest answer is that there is no such thing to sell. That is
    different from the refusals below, which answer a control that does
    exist with a reason.
    """
    assignment = _own_assignment_or_404(request, pk)
    if not is_possession(assignment.assignable):
        raise Http404("Not something the gang owns")
    return assignment


def _held(host, pk):
    """The stored possession ``pk`` names, if this host is carrying it.

    The host's roots are the whole of the permission check for drawing a
    dialog about it — and it is free, where fetching it again would be a
    query per click. Broadcast assignments are skipped on a fighter's card:
    they ride it so gang-wide rules reach it, and they are not this
    fighter's to sell.

    The same kind test the routes apply, so a URL naming the fighter's own
    profile draws no dialog rather than a confirmation whose click would
    404 — a screen must not ask a question its answer refuses.
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
    """Everyone else on the roster — where a thing could go instead."""
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


def accessory_catalogue():
    """Every accessory a reader may fit, read in one go.

    The whole table, because a screen showing a fighter's guns needs the
    whole of it: what fits is decided per weapon in Python, so six guns
    cost this one read rather than six. The table is small — a library's
    accessories are counted in dozens where its weapons are counted in
    hundreds.

    ``fits_category`` comes with it. Building an accessory's selector
    reads that category, so leaving it to be fetched later would turn one
    query into one per accessory.
    """
    from n26.library.models import WeaponAccessory

    return list(
        WeaponAccessory.objects.selectable()
        .select_related("fits_category")
        .order_by("name")
    )


def fitting_accessories(weapon, catalogue=None):
    """What a reader is offered to bolt onto this weapon, priced.

    Narrowed to what fits — the bracket in the accessory's name, as
    data. That shortens a list; it settles nothing, and
    ``Operation.buy`` will bolt anything to anything, exactly as the
    browse notes read. A shorter list is help, and a refusal would be a
    rule the book does not have.

    ``catalogue`` is the accessories to sift, for a caller asking this of
    several weapons; without one it reads them itself.
    """
    if catalogue is None:
        catalogue = accessory_catalogue()
    return [
        {"pk": str(accessory.pk), "name": accessory.name, "price": accessory.price}
        for accessory in catalogue
        if accessory.fits(weapon)
    ]


def _asked(request):
    """Which dialog this address is asking for, and about which assignment.

    One at a time, in :data:`n26.core.owned.DIALOGS` order: a URL naming
    two is answered with whichever comes first there, because two open
    panels is not a state a page can mean.
    """
    for kind in DIALOGS:
        named = request.GET.get(kind)
        if named:
            return kind, named
    return None, None


#: The act a question submits to, where that is not the question's own
#: name. Fitting an accessory to a gun is asked on its own, because
#: Reassign is about which model holds a thing and this is not, and it is
#: answered by the move that does it.
ROUTES = {"fit": "reassign"}


def _panel(request, assignment, kind, at):
    """What every one of these dialogs says, whatever it is asking."""
    return {
        "kind": kind,
        "name": str(assignment.assignable),
        "cancel_url": at,
        "action": reverse(f"n26-{ROUTES.get(kind, kind)}", args=[assignment.pk]),
        "list": request.GET.get("list", ""),
        # Which section tab the reader had open, carried through the
        # click so the answer lands where the question was asked. The
        # listing's own form does this with a hidden field the picker
        # writes; a dialog is a form of its own and has to say it here.
        "section": request.GET.get("section", ""),
    }


def accessorise_dialogs(request, host: EquipHost):
    """The accessory question for every weapon on this host, all of them.

    Not only the one the URL names. A page draws the lot — closed, and
    each one addressed by the id of the assignment it is about — so the click
    that opens one is the browser showing a panel that is already there
    rather than a rebuild of a screen that can run to hundreds of rows.
    The address is still what says which is open: with no script the
    button is a link, and the one it names is the one drawn open here.

    Every weapon costs the same single read of the accessory table.
    Fitting is then arithmetic on what the host already holds, so a screen
    carrying six guns asks the database exactly what a screen carrying one
    does — and a screen carrying none asks nothing.
    """
    kind, named = _asked(request)
    weapons = weapons_on(host)
    if not weapons:
        return []

    catalogue = accessory_catalogue()
    dialogs = []
    for node in weapons:
        pk = str(node.assignment.pk)
        accessories = fitting_accessories(node.assignable, catalogue)
        panel = _panel(request, node.assignment, "accessorise", host.at)
        dialogs.append(
            panel
            | {
                # The assignment this is about, which is also what the
                # control that opens it names.
                "id": pk,
                "open": kind == "accessorise" and named == pk,
                "title": f"Add an accessory to {panel['name']}",
                "accessories": accessories,
                # Nothing that fits is nothing to click. The panel says so
                # and offers the way out, rather than a green button over an
                # empty list — the commit is the one control that must mean
                # something.
                "submit_label": "Add accessory" if accessories else "",
                "submit_variant": "success",
            }
        )
    return dialogs


def owned_dialog(request, host: EquipHost):
    """The dialog the URL says is open, as a template's worth of facts.

    One of the query parameters in :data:`n26.core.owned.DIALOGS`, naming
    an assignment on this host. A name that is not on the host draws nothing at
    all: a stale link is a page without a dialog, not an error worth a
    screen.

    ``accessorise`` is not among them: that question is drawn for every
    weapon on the host by :func:`accessorise_dialogs`, one of which the
    address opens. Answering it here as well would draw the same panel
    twice.
    """
    from n26.core.operations import (
        MINIMUM_PROCEEDS,
        detachable_children,
        refund_of,
        sale_of,
    )

    kind, named = _asked(request)
    if kind is None or kind == "accessorise":
        return None

    gang = host.gang
    # A gang founded without a budget never paid credits, so there is
    # nothing a refund could give back: a refund address asks the remove
    # question instead, exactly as the fighter-level flow answers.
    if kind == "refund" and gang.credits_unlimited:
        kind = "remove"

    assignment = _held(host, named)
    if assignment is None:
        return None

    name = str(assignment.assignable)
    # A part is what hangs off something else — ammo in a gun, a sight
    # bolted to it. It is removed rather than deleted, because what is
    # left afterwards is still the fighter's gun.
    is_part = assignment.parent_id is not None
    dialog = _panel(request, assignment, kind, host.at) | {
        "stash_host": host.is_stash,
        "can_refund": not gang.credits_unlimited,
    }

    if kind == "sell":
        # Anything bolted on that the gang could keep instead of selling.
        # Keeping them is what the dialog offers first, so it is also what
        # the figures are worked out for: the number a reader is shown is
        # the number the button they are looking at will pay.
        #
        # With nowhere to keep them there is no choice to offer, and the
        # route behind this reads the stash the same way — a screen must
        # not ask a question its answer cannot honour.
        keepable = (
            detachable_children(assignment)
            if getattr(gang, "stash", None) is not None
            else []
        )
        _, rating, proceeds = sale_of(assignment, keeping=keepable)
        # Half of the figure, or the floor — whichever decided it. The
        # arithmetic is stated because the number is money and there is
        # nothing on the page for a reader to check it against.
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
        # The second figure, priced the same way: selling the whole of it
        # pays more, and the choice is not one a reader can make on the
        # strength of a number that describes only one of the answers.
        _, _, with_extras = sale_of(assignment)
        word = "accessory" if len(keepable) == 1 else "accessories"
        return sale | {
            # Named rather than counted: the reader is deciding whether
            # they want *these* back later, and a bare "2 accessories"
            # answers none of that.
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
                            f"{weapon.assignable} ({weapon.miniature_root.name})"
                            if weapon.miniature_root_id
                            else f"{weapon.assignable} (stash)"
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
        # An accessory is the only thing bolted onto anything, so a URL
        # naming something else draws no dialog at all. Without this a
        # gun's own address opens a picker holding that same gun, whose
        # answer would be attaching it to itself — a screen must not ask
        # a question its answer refuses.
        if assignment.weapon_accessory_id is None:
            return None
        # Every gun on the card, and not only the ones the accessory was
        # written for: what fits what is information rather than a gate,
        # and an owner may bolt anything to anything.
        weapons = weapons_on(host)
        return dialog | {
            "title": f"Fit {name} to a weapon",
            "weapons": [
                {"pk": str(node.assignment.pk), "label": node.name} for node in weapons
            ],
            "submit_label": "Fit" if weapons else "",
            "submit_variant": "primary",
        }

    if kind == "rechoose":
        # The same controls the row for sale draws, starting on what this
        # copy took rather than on what a buyer would be handed. What a
        # swap adds is beside each option; what it settles to is on the
        # copy's own line once it is saved, because that is where the
        # figure it changes lives.
        from n26.core.browse import offered_choices
        from n26.core.listing import pick_groups

        thing = assignment.assignable
        taken = {row.default_set_id for row in assignment.chosen_options.all()}
        return dialog | {
            "title": f"Change {name}'s options",
            "choices": pick_groups(
                offered_choices(thing), thing_key(thing), taken=taken
            ),
            "submit_label": "Save options",
            "submit_variant": "success",
        }

    if kind == "refund":
        _, paid = refund_of(assignment)
        # The figure is what the ledger says was handed over, which is not
        # on the page anywhere and is not the price the listing quotes —
        # so the sentence says which number it is as well as what it is.
        return dialog | {
            "title": f"Refund {name}?",
            "proceeds": paid,
            "sum": (
                f"{paid}¢ comes back — the amount paid, not its rating."
                if paid
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


def link_stash_actions(sheet, at, *, refunds=True):
    """Add dialog links without querying; print and read-only sheets stay plain."""
    from n26.core.listing import DANGER, LINK, SECONDARY, Action

    for line in sheet.stash:
        if not line.id:
            continue
        menu = [
            Action(
                "Fit to a weapon" if line.is_accessory else "Reassign",
                LINK,
                with_query(at, reassign=line.id),
                SECONDARY,
            ),
            Action("Sell", LINK, with_query(at, sell=line.id), DANGER),
        ]
        if refunds:
            menu.append(
                Action("Refund", LINK, with_query(at, refund=line.id), SECONDARY)
            )
        menu.append(Action("Delete", LINK, with_query(at, remove=line.id), SECONDARY))
        line.menu = tuple(menu)


def _back_to(request, assignment, gang):
    """Infer the source screen before an operation moves the assignment."""
    if assignment.stash_root_id or assignment.stash_id:
        base = reverse("n26-equip-gang", args=[gang.pk])
    elif assignment.miniature_root_id:
        base = reverse("n26-equip", args=[assignment.miniature_root_id])
    else:
        base = reverse("n26-gang", args=[gang.pk])
    where = {
        key: value
        for key in ("list", "section", "owned")
        if (value := request.POST.get(key, ""))
    }
    return with_query(base, **where) if where else base


def _return_to(request, fallback):
    return _safe_redirect(request, request.POST.get("return"), fallback_url=fallback)


@dataclass(frozen=True)
class _Touched:
    """The row an act changes, and whose equip screen draws it."""

    key: str
    miniature: object | None


def _row_behind(assignment):
    """The row an act on this assignment changes.

    A part is drawn under the thing it hangs from — a gun's ammo, a sight
    bolted to it — so what changes is that thing's row and never one of
    its own.

    Read before the act rather than after: selling archives the
    assignment and a move points it somewhere else, so afterwards it no
    longer says which screen the click came from.
    """
    node = assignment
    while node.parent_id is not None:
        node = node.parent
    return _Touched(key=thing_key(node.assignable), miniature=node.miniature_root)


def _unchanged(request, back):
    """The response for an act that changed nothing on the screen.

    A refusal, or a submission that matched what was already stored. The
    reason is queued as a message; without htmx it lands on the full
    page, with htmx it rides the response as a toast.
    """
    if not is_htmx(request):
        return _return_to(request, back)
    return no_update(request)


def _acted(request, touched, gang, back, also=""):
    """The response for an act that changed a row.

    With htmx: the partial update for the row, with the confirmation
    panel closed, and the address set back to the screen behind the
    panel — the address that renders that screen on a plain visit.
    Without: a redirect to that screen.

    Which row stood open travels with the click — the address holds it,
    and every htmx request carries it along (see
    n26/core/static/n26/htmx_support.js) — so the update draws the row
    in the state the reader left it.

    ``also`` is a second row on the same screen that the act changed as
    well; :func:`n26.core.views.equip.render_update` says when there is
    one.
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
    """Sell something on: it archives, and half its rating comes back.

    Half of its rating, not of what was paid — see
    ``Operation.sell``. The confirmation names the figure because with
    the arithmetic done by the server there is nothing on the page for a
    reader to check it against.

    A gun with an accessory bolted to it is two decisions, and the form
    carries the second: ``accessories=sell`` sells the lot, anything else
    unbolts them into the stash first so they can be fitted to another
    gun later. Kept is the default because it is the recoverable answer
    — a stashed sight can still be sold tomorrow, where a sold one is
    gone.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, detachable_children, operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    back = _back_to(request, assignment, gang)
    touched = _row_behind(assignment)

    stash = getattr(gang, "stash", None)
    keeping = (
        []
        if request.POST.get("accessories") == "sell" or stash is None
        else detachable_children(assignment)
    )

    try:
        with operation(gang, actor=request.user) as op:
            # Unbolted before the sale, so what the buyer is paying for is
            # what is left. Each move is its own event, and none of them
            # re-prices anything.
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
    """Hand something to another model, put it in the stash, or fit it to a gun.

    Nothing is charged and nothing is re-priced: the thing keeps the
    rating it was pinned at, and only where it lives changes.

    Three destinations, told apart by ``to``. ``stash`` and a named
    ``miniature`` are the two a fighter's own listing row offers. ``weapon``
    names another assignment, which is how a stashed accessory is
    bolted back onto a gun — the same act, one level down the chain.

    What may not be moved at all is ``Operation.move``'s answer rather
    than this view's: a weapon's firing line is part of its weapon, and
    the operation says so in a sentence this shows.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import Assignment, Miniature
    from n26.core.operations import Refusal, operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    # Read before the move, because afterwards it names the new home and
    # the reader wants the screen they clicked on.
    came_from = assignment.miniature_root
    back = _back_to(request, assignment, gang)
    touched = _row_behind(assignment)
    name = str(assignment.assignable)

    wanted = request.POST.get("to")
    if wanted == "stash":
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
                # Nothing hangs off itself. The operation says so too, but
                # it says it by raising rather than refusing, so a
                # hand-made click naming its own weapon is answered here
                # with the same sentence as any other impossible
                # destination.
                .exclude(pk=assignment.pk)
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

    # Fitting takes the thing out of a row of its own and draws it under
    # the gun instead, so two rows on the screen change. The gun's row
    # counts only where the reader is looking at it: a stash fit reaches
    # a gun on somebody's card, and that is not the screen this answers.
    landed = _row_behind(destination) if isinstance(destination, Assignment) else None
    also = landed.key if landed and landed.miniature == touched.miniature else ""

    try:
        with operation(gang, actor=request.user) as op:
            op.move(assignment, destination)
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
        to=wanted if wanted in ("stash", "weapon") else "model",
    )
    if wanted == "stash":
        messages.success(request, f"Moved {name} to the stash.")
    elif wanted == "weapon":
        messages.success(request, f"Fitted {name} to {destination.assignable}.")
    else:
        messages.success(request, f"Moved {name} to {destination.name}.")
    return _acted(request, touched, gang, back, also=also)


@login_required
@require_POST
def rechoose_assignment(request, pk):
    """Take something already owned with different options.

    The alternatives were priced when it was bought and they are priced
    the same way now, so changing them settles the difference either
    way: a dearer set is charged, a cheaper one comes back, and the
    figure lands on the thing's own line because an option is a way that
    thing is built rather than a purchase beside it.

    The picks arrive as places in the offer the server re-derives, read
    back by the same parser a purchase uses, so a tampered form can name
    nothing the content does not offer. A gang that cannot afford an
    upgrade is refused and nothing changes — the whole swap unwinds
    together, rather than leaving the old set gone and the new one
    unpaid for.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.browse import offered_choices
    from n26.core.operations import Refusal, operation
    from n26.core.views.equip import _choices_picked
    from n26.library.models.assignable import Optioned

    assignment = _possession_or_404(request, pk)
    thing = assignment.assignable
    if not isinstance(thing, Optioned) or not thing.offers_a_choice:
        # No control draws this address for anything else, and there
        # would be nothing on the panel behind it to pick.
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
    # What changed is read from what is recorded rather than from the
    # money: two options at one price are a real swap that costs nothing,
    # and calling that unchanged would tell a reader their click did not
    # land.
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
    """Bolt an accessory onto a weapon the gang already owns.

    An ordinary purchase at the reference price, hosted on the weapon's
    own assignment rather than on the fighter — the same shape a gun's paid
    ammo is bought in, and for the same reason: an accessory belongs to
    one particular weapon. Selling the gun therefore reaches it, and its
    effects land on that gun's profiles rather than on every gun the
    fighter carries.

    The form submits the accessory's identity and never its price: the
    server reads the price off the library, so a tampered figure buys
    nothing at a figure nobody offered.

    What fits is not checked. The dialog offered a shortened list, which
    is the whole of what fitting does — an owner may bolt anything to
    anything, and the card says where it came from either way.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation
    from n26.library.models import Weapon, WeaponAccessory

    assignment = _possession_or_404(request, pk)
    if not isinstance(assignment.assignable, Weapon):
        # Nothing else is somewhere to fit one, and no control draws this
        # address for anything else.
        raise Http404("Not a weapon")
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    back = _back_to(request, assignment, gang)
    touched = _row_behind(assignment)

    try:
        accessory = WeaponAccessory.objects.selectable().get(
            pk=request.POST.get("accessory", "")
        )
    except WeaponAccessory.DoesNotExist, ValidationError, ValueError:
        # A stale dialog or a hand-made click. The screen it came from is
        # the answer, with the list on it as it now stands.
        messages.error(request, "That accessory is not one to fit.")
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
    """Remove something from the gang without changing credits.

    ``Operation.remove`` archives rather than deletes, so the ledger goes
    on saying the gang once owned this — it simply stops counting.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    back = _back_to(request, assignment, gang)
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
    """Undo the purchase: it archives, and every credit paid comes back.

    What was *paid*, not its rating — see ``Operation.refund``. The
    figure is read before the write, because afterwards every entry in
    the subtree has been settled to zero and there is nothing left to add
    up.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation, refund_of

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    # No budget, no refund: the money never left a budget, so the act
    # behind this address is the removal the dialog promised.
    if gang.credits_unlimited:
        return remove_assignment(request, pk)
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    _, paid = refund_of(assignment)
    back = _back_to(request, assignment, gang)
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
    )
    messages.success(request, f"Refunded {name} — {paid}¢ back.")
    return _acted(request, touched, gang, back)


@login_required
@require_POST
def tally_counter(request, pk):
    """Move one counter up or down.

    ``change`` is signed and the value floors at zero, both of which are
    ``Operation.tally``'s — so a stale control that offers a subtraction
    a later reader has already made impossible takes the value to zero
    rather than below it.

    The same address serves a model's counter and the gang's own: what
    is being changed is the assignment, and who is carrying it is its
    business. Only counters, though — every other assignment has verbs
    of its own, and none of them is a running number.

    A step at a time. The rulebook's own acts move these by more — a
    Spyrer spends four Kill Count on Suit Evolution — and ``change``
    being signed and free is what lets one address serve both.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation
    from n26.core.views.edit import render_card_update
    from n26.library.models import Counter

    assignment = _own_assignment_or_404(request, pk)
    if not isinstance(assignment.assignable, Counter):
        raise Http404("Not a counter")
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    back = request.POST.get("back", "")[:500]
    here = reverse("n26-gang", args=[gang.pk])

    try:
        change = int(request.POST.get("change", ""))
    except ValueError:
        raise Http404("Not a change to make") from None
    if not change or abs(change) > MOST_A_TALLY_MOVES:
        # Zero moves nothing, and writing an event to say so fills a
        # gang's history with rows that record nothing happening. The
        # bound beside it is because a counter's value is a database
        # integer: a number past what one holds would be a 500 rather
        # than a refusal, and no control offers a step anywhere near it.
        raise Http404("Not a change to make")

    try:
        with operation(gang, actor=request.user) as op:
            standing = op.tally(assignment, change)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        if is_htmx(request):
            # Nothing moved, so nothing on the page is redrawn; the
            # refusal reaches the reader as a toast and that is all.
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
        # No message: the number on the card moves where the reader is
        # looking, and a toast for every step of a tally somebody is
        # working through is noise. A refusal still speaks, above.
        return render_card_update(request, miniature, back or here)
    messages.success(request, f"{name} is now {standing}.")
    return _safe_redirect(request, back, here)
