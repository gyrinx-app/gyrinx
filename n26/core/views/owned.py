"""What a fighter already owns — selling it, handing it on, taking it off.

Five acts, five addresses, one shape each: a POST names the assignment
in its path, an ``operation`` writes it, and the reader lands back where
they clicked. They are addressed by *assignment* rather than by
fighter, because that is what they are about — a weapon on a fighter, a
sight on that weapon, a crate in the stash are all one row — and because
the next screen that wants them (a gang sheet, a stash page) then needs
no routes of its own.

Which dialog is open is URL state on the screen that opened it
(``?sell=<assignment>``), so an open confirmation is a link, survives a
reload, and is drawn by the server rather than revealed by a script. The
click behind it is a real form to a real address, so it works with
scripting switched off.

An operation that refuses an act answers on the screen it was clicked
from — a control the page drew is owed a sentence, not a traceback — and
nothing is written, because the refusal unwinds the transaction.

The acts are deliberately distinct, and the ledger says which happened:

``sell``
    Half of what the thing is worth, rounded up, into the gang's credits.
    Not a refund: what was paid has nothing to do with it. A gun with
    something bolted to it asks one more question — whether the
    accessories are being sold with it or kept — because those are two
    sales at two prices.
``reassign``
    A move to another model, to the stash, or onto a weapon. No money,
    and no re-pricing. The last of the three is how a stashed accessory
    is fitted to a gun: the same act, one level down the chain.
``refund``
    Undoing the purchase: every credit that was paid comes back. What was
    paid and what the thing is worth part company at the first discount,
    which is why this is not a sale.
``remove``
    Off the card, money stays spent.
``accessorise``
    A purchase, hosted on the weapon rather than on the fighter. The only
    one of the five that adds something.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from n26.core.owned import DIALOGS, is_possession, with_query
from n26.core.views.permissions import _own_assignment_or_404


def _possession_or_404(request, pk):
    """One of the viewer's own rows, and one these acts are *about*.

    ``_own_assignment_or_404`` answers who may act; this answers on what.
    Both are needed, because a gang holds a great deal that is not kit and
    every bit of it is an assignment with a primary key: the row naming a
    model's profile **is** the model, and selling it would take the
    fighter off the roster and everything they carry with them, for half
    the price of the profile and nothing for the kit. The row naming the
    gang's type is the gang. Neither has any business arriving at a shop
    row's Sell button.

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


def _held(card, pk):
    """The stored possession ``pk`` names, if this card is carrying it.

    The card is the fighter's own, so finding a row on it is the whole of
    the permission check for drawing a dialog about it — and it is free,
    where fetching the row again would be a query per click. The gang's
    broadcast rows are skipped: they ride the card so gang-wide rules
    reach it, and they are not this fighter's to sell.

    The same kind test the routes apply, so a URL naming the fighter's own
    profile draws no dialog rather than a confirmation whose click would
    404 — a screen must not ask a question its answer refuses.
    """
    return next(
        (
            node.assignment
            for node in card.all_nodes()
            if not node.broadcast
            and node.assignment is not None
            and str(node.assignment.pk) == pk
            and is_possession(node.assignable)
        ),
        None,
    )


def _other_models(gang, miniature):
    """Everyone else on the roster — where a thing could go instead."""
    from n26.core.models import Miniature

    return list(
        Miniature.objects.filter(
            membership__gang=gang, membership__archived=False
        ).exclude(pk=miniature.pk)
    )


def accessory_catalogue():
    """Every accessory a reader may fit, read in one go.

    The whole table, because a screen showing a fighter's guns needs the
    whole of it: what fits is decided per weapon in Python, so six guns
    cost this one read rather than six. The table is small — a library's
    accessories are counted in dozens where its weapons are counted in
    hundreds.

    ``fits_category`` comes with it. Building an accessory's selector
    reads that row, so leaving it to be fetched later would turn one
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

    ``catalogue`` is the rows to sift, for a caller asking this of
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
    """Which dialog this address is asking for, and about which row.

    One at a time, in :data:`n26.core.owned.DIALOGS` order: a URL naming
    two is answered with whichever comes first there, because two open
    panels is not a state a page can mean.
    """
    for kind in DIALOGS:
        named = request.GET.get(kind)
        if named:
            return kind, named
    return None, None


def _panel(request, assignment, kind, at):
    """What every one of these dialogs says, whatever it is asking."""
    return {
        "kind": kind,
        "name": str(assignment.assignable),
        "cancel_url": at,
        "action": reverse(f"n26-{kind}", args=[assignment.pk]),
        "list": request.GET.get("list", ""),
        # Which section tab the reader had open, carried through the
        # click so the answer lands where the question was asked. The
        # listing's own form does this with a hidden field the picker
        # writes; a dialog is a form of its own and has to say it here.
        "section": request.GET.get("section", ""),
    }


def accessorise_dialogs(request, card, *, at):
    """The accessory question for every weapon on this card, all of them.

    Not only the one the URL names. A page draws the lot — closed, and
    each one addressed by the id of the row it is about — so the click
    that opens one is the browser showing a panel that is already there
    rather than a rebuild of a screen that can run to hundreds of rows.
    The address is still what says which is open: with no script the
    button is a link, and the one it names is the one drawn open here.

    Every weapon costs the same single read of the accessory table.
    Fitting is then arithmetic on rows the card already holds, so a
    fighter carrying six guns asks the database exactly what a fighter
    carrying one does — and a fighter carrying none asks nothing.
    """
    from n26.library.models import Weapon

    kind, named = _asked(request)
    weapons = [
        node
        for node in card.roots
        if not node.broadcast
        and not node.suppressed
        and node.assignment is not None
        and isinstance(node.assignable, Weapon)
    ]
    if not weapons:
        return []

    catalogue = accessory_catalogue()
    dialogs = []
    for node in weapons:
        pk = str(node.assignment.pk)
        accessories = fitting_accessories(node.assignable, catalogue)
        panel = _panel(request, node.assignment, "accessorise", at)
        dialogs.append(
            panel
            | {
                # The row this is about, which is also what the control
                # that opens it names.
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


def owned_dialog(request, card, *, at, miniature, gang):
    """The dialog the URL says is open, as a template's worth of facts.

    One of the query parameters in :data:`n26.core.owned.DIALOGS`, naming
    a row of this card. A name that is not on the card draws nothing at
    all: a stale link is a page without a dialog, not an error worth a
    screen.

    ``accessorise`` is not among them: that question is drawn for every
    weapon on the card by :func:`accessorise_dialogs`, one of which the
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

    # A gang founded without a budget never paid credits, so there is
    # nothing a refund could give back: a refund address asks the remove
    # question instead, exactly as the fighter-level flow answers.
    if kind == "refund" and gang.credits_unlimited:
        kind = "remove"

    assignment = _held(card, named)
    if assignment is None:
        return None

    name = str(assignment.assignable)
    # A part is what hangs off something else — ammo in a gun, a sight
    # bolted to it. It is removed rather than deleted, because what is
    # left afterwards is still the fighter's gun.
    is_part = assignment.parent_id is not None
    dialog = _panel(request, assignment, kind, at)

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
                f"Half of {rating}¢, rounded up — {proceeds}¢."
                if halved
                else f"{proceeds}¢: half of {rating}¢ is less than the "
                f"{MINIMUM_PROCEEDS}¢ a sale never goes under."
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
        models = _other_models(gang, miniature)
        return dialog | {
            "title": f"Move {name}",
            "models": models,
            # With nobody else on the roster the stash is not one of two
            # places it could go — it is the only one, so it stops being
            # a second control and becomes the act.
            "submit_label": "Move" if models else "To the stash",
            "submit_variant": "primary",
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
                f"{paid}¢ comes back — what was paid for it, not what it is worth."
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


def link_refits(sheet, at):
    """Point every stashed accessory at the dialog that fits it to a gun.

    Costs no queries: the line already knows its own row and whether it
    is the sort of thing that goes on a weapon, and this only turns that
    into a URL. A line without one draws as a name with nothing to click,
    which is what a print-out wants.
    """
    for line in sheet.stash:
        if line.can_refit and line.id:
            line.refit_href = with_query(at, refit=line.id)


def refit_dialog(request, gang, at):
    """The "fit this to which gun?" panel, when ``?refit=`` names a stashed row.

    The reverse of the equipment screen's accessory picker: there the
    weapon is known and the accessory chosen, here the accessory is known
    and the weapon chosen. Both end with one row hanging off another.

    Every gun the gang has is offered, not only the ones the accessory
    fits — the same rule as everywhere else, said the other way round.
    Fitting narrows a list of accessories because that list is long; a
    gang's guns are few, and hiding the one a reader meant would be a
    refusal wearing a shorter list as a disguise.

    A name that is not a stashed accessory of this gang's draws nothing:
    a stale link is a page without a dialog rather than an error worth a
    screen.
    """
    from n26.core.models import Assignment

    named = request.GET.get("refit")
    if not named:
        return None
    stash = getattr(gang, "stash", None)
    if stash is None:
        return None
    try:
        accessory = (
            Assignment.objects.filter(pk=named, stash=stash, archived=False)
            .exclude(weapon_accessory=None)
            .select_related("weapon_accessory")
            .first()
        )
    except ValidationError:
        return None
    if accessory is None:
        return None

    # Every live weapon in the gang, wherever it is — a gun in the stash
    # is somewhere to fit a sight as much as one on a fighter is.
    weapons = list(
        Assignment.objects.filter(gang_root=gang, archived=False)
        .exclude(weapon=None)
        .select_related("weapon", "miniature_root")
        .order_by("miniature_root__name", "weapon__name")
    )
    name = str(accessory.assignable)
    return {
        "name": name,
        "title": f"Fit {name} to a weapon",
        "action": reverse("n26-reassign", args=[accessory.pk]),
        "cancel_url": at,
        "weapons": [
            {
                "pk": str(weapon.pk),
                # Whose gun it is, because a gang can hold three autoguns
                # and the answer to "which one" is the fighter carrying it.
                "label": (
                    f"{weapon.assignable} ({weapon.miniature_root.name})"
                    if weapon.miniature_root is not None
                    else f"{weapon.assignable} (stash)"
                ),
            }
            for weapon in weapons
        ],
        "submit_label": "Fit" if weapons else "",
    }


def _back_to(request, miniature, gang):
    """Where a click lands: the screen it was clicked on.

    The fighter's own shopping screen, on the list they were reading and
    the section tab they had open — kitting a fighter out is a run of
    clicks, and one that drops the reader back at the top of the first
    list has undone their place in it. With no fighter to return to, the
    gang's sheet.
    """
    if miniature is None:
        return reverse("n26-gang", args=[gang.pk])
    url = reverse("n26-equip", args=[miniature.pk])
    where = {
        key: value
        for key in ("list", "section")
        if (value := request.POST.get(key, ""))
    }
    return with_query(url, **where) if where else url


@login_required
@require_POST
def sell_assignment(request, pk):
    """Sell something on: it archives, and half its worth comes back.

    Half of what it *is worth*, not of what was paid — see
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
    back = _back_to(request, miniature, gang)

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
        return redirect(back)

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
    return redirect(back)


@login_required
@require_POST
def reassign_assignment(request, pk):
    """Hand something to another model, put it in the stash, or fit it to a gun.

    Nothing is charged and nothing is re-priced: the thing keeps the
    rating it was pinned at, and only where it lives changes.

    Three destinations, told apart by ``to``. ``stash`` and a named
    ``miniature`` are the two a fighter's own row offers. ``weapon``
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
    back = _back_to(request, came_from, gang)
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
        return redirect(back)

    try:
        with operation(gang, actor=request.user) as op:
            op.move(assignment, destination)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(back)

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
    return redirect(back)


@login_required
@require_POST
def accessorise_assignment(request, pk):
    """Bolt an accessory onto a weapon the gang already owns.

    An ordinary purchase at the reference price, hosted on the weapon's
    own row rather than on the fighter — the same shape a gun's paid
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
    back = _back_to(request, miniature, gang)

    try:
        accessory = WeaponAccessory.objects.selectable().get(
            pk=request.POST.get("accessory", "")
        )
    except WeaponAccessory.DoesNotExist, ValidationError, ValueError:
        # A stale dialog or a hand-made click. The screen it came from is
        # the answer, with the list on it as it now stands.
        messages.error(request, "That accessory is not one to fit.")
        return redirect(back)

    try:
        with operation(gang, actor=request.user) as op:
            bought = op.buy(assignment, thing=accessory)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(back)

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
    return redirect(back)


@login_required
@require_POST
def remove_assignment(request, pk):
    """Take something off the card. The money stays spent.

    ``Operation.remove`` archives rather than deletes, so the ledger goes
    on saying the gang once owned this — it simply stops counting.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)
    back = _back_to(request, miniature, gang)

    try:
        with operation(gang, actor=request.user) as op:
            op.remove(assignment)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(back)

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
    return redirect(back)


@login_required
@require_POST
def refund_assignment(request, pk):
    """Undo the purchase: it archives, and every credit paid comes back.

    What was *paid*, not what it is worth — see ``Operation.refund``. The
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
    back = _back_to(request, miniature, gang)

    try:
        with operation(gang, actor=request.user) as op:
            op.refund(assignment)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(back)

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
    return redirect(back)
