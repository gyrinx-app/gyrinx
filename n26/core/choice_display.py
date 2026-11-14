"""JSON-safe display facts for computed choices and their recorded rolls."""

from dataclasses import replace
from urllib.parse import urlencode

from django.middleware.csrf import get_token
from django.urls import reverse

from n26.core.owned import with_query
from n26.library.staged import sees_staged


def offer_data(offer):
    return {
        "label": offer.label,
        "takesSeveral": offer.takes_several,
        "empty": offer.is_empty,
        "groups": [
            {
                "name": group.name,
                "caption": group.caption,
                "lifted": group.lifted,
                "options": [
                    {
                        "key": option.key,
                        "name": option.name,
                        "band": option.band,
                        "current": option.is_current,
                        "remark": option.remark,
                        "summary": option.summary,
                        "rating": option.rating,
                        "removalRating": option.removal_rating,
                        "control": option.control,
                    }
                    for option in group.options
                ],
            }
            for group in offer.groups
        ],
    }


def picker(
    request,
    gang,
    slot_key,
    found,
    *,
    form,
    here,
    back,
    returning="",
    terminal=False,
    context=None,
    dialog=None,
    roll_key=None,
):
    from n26.core.choice_workflow import _roll_at, _roll_result, _roll_table
    from n26.core.navigation import fighter_switcher, switcher_props
    from n26.core.people import person_link
    from n26.core.render import build_choice_offer, lift_landing

    shown = sees_staged(request.user)
    offer = (
        build_choice_offer(found.slot, found.computed, include_staged=shown)
        if found
        else None
    )
    table = _roll_table(found) if found else None
    event = (
        _roll_at(
            request.GET.get("roll", "") if roll_key is None else roll_key, gang, found
        )
        if found
        else None
    )
    roll = None
    if event is not None:
        roll, landed = _roll_result(event, found, offer, include_staged=shown)
        addable = [
            option
            for group in offer.groups
            for option in group.options
            if option.key in landed and option.control in {"choose", "both"}
        ]
        if not roll.is_spent and len(addable) == 1 and len(landed) == 1:
            roll = replace(roll, add=addable[0])
        elif not roll.is_spent:
            offer = lift_landing(offer, landed, threshold=roll.threshold)
    if context is not None:
        context.update(
            offer=offer,
            roll=roll,
            roll_table=table if roll is None or roll.is_spent else None,
            miniature=found.miniature if found else None,
            back=back,
            returning=returning,
            choice_action=here,
        )
    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    values = {name: str(form[name].value() or "") for name in form.fields}
    if not form.is_bound:
        values["returning"] = returning
        values["roll"] = roll.key if roll and not roll.is_spent else ""
        if offer is not None and not offer.takes_several:
            values["thing"] = next(
                (
                    option.key
                    for group in offer.groups
                    for option in group.options
                    if option.is_current
                ),
                "",
            )
    if not form.is_bound and offer is not None and offer.takes_several:
        values["thing"] = ""
    values["summary"] = (
        str(request.POST.get("summary", ""))[:2000] if form.is_bound else ""
    )
    dialog = (
        request.GET.get("dialog") == "campaign"
        and request.headers.get("HX-Request") == "true"
        if dialog is None
        else dialog
    )
    recovery_href = with_query(
        here, recover="1", **({"roll": event.pk} if event else {})
    )
    props = {
        "title": offer.label if offer else "Recover choice",
        "lead": found.slot.slot.introduction if found and found.slot.slot else "",
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "back": back,
        "switcher": switcher_props(fighter_switcher(gang, found.miniature))
        if found and found.miniature
        else None,
        "offer": offer_data(offer) if offer else None,
        "rollTable": {
            "dice": table.dice_label,
            "lowest": table.lowest,
            "highest": table.highest,
        }
        if table and (roll is None or roll.is_spent)
        else None,
        "roll": {
            "key": roll.key,
            "total": roll.total,
            "dice": roll.dice_label,
            "faces": list(roll.faces),
            "landed": list(roll.landed),
            "entered": roll.entered,
            "applied": roll.applied,
            "threshold": roll.threshold,
            "add": {"key": roll.add.key, "name": roll.add.name} if roll.add else None,
        }
        if roll
        else None,
        "values": values,
        "errors": dict(form.errors) if form.is_bound else {},
        "action": here,
        "commandHref": with_query(
            reverse("n26-choice-command", args=[gang.pk, slot_key]),
            dialog="campaign",
            **({"display": "dialog"} if dialog else {}),
        )
        if request.GET.get("dialog") == "campaign"
        else reverse("n26-choice-command", args=[gang.pk, slot_key]),
        "csrfToken": get_token(request),
        "recoveryKey": f"n26-choice:{request.user.pk}:{gang.pk}:{slot_key}",
        "arrivalRecoveryKey": f"n26-arrivals:{request.user.pk}:{gang.pk}",
        "recoveryHref": recovery_href,
        "signInHref": reverse("account_login")
        + "?"
        + urlencode({"next": recovery_href}),
        "recoveryOnly": found is None,
        "terminal": terminal,
        "dialog": dialog,
        "messages": queued_messages(request),
    }
    return props


def arrivals(request, gang, read, form, *, keys, back, terminal=False):
    from n26.core.arrivals import next_url
    from n26.core.people import person_link

    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    values = {name: str(form[name].value() or "") for name in form.fields}
    if not form.is_bound:
        values["selection"] = "{}"
    values["summary"] = str(request.POST.get("summary", ""))[:2000]
    recovery_href = with_query(next_url(gang, keys, back), recover="1")
    return {
        "title": f"Choices for {gang.name}",
        "lead": "",
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "back": back,
        "switcher": None,
        "offer": None,
        "rollTable": None,
        "roll": None,
        "blocks": [
            {
                "heading": block.heading,
                "description": block.description,
                "skippable": block.skippable,
                "questions": [
                    {
                        "key": question.key,
                        "headingId": question.heading_id,
                        "label": question.label,
                        "bearer": question.bearer,
                        "chosen": question.chosen,
                        "settled": question.settled,
                        "rollHref": question.roll_href,
                        "offer": offer_data(question.offer),
                    }
                    for question in block.questions
                ],
            }
            for block in read.screen.blocks
        ],
        "mayContinue": read.screen.may_continue,
        "outstanding": read.screen.outstanding_words,
        "skipHref": read.screen.skip_url,
        "values": values,
        "errors": dict(form.errors) if form.is_bound else {},
        "action": next_url(gang, keys, back),
        "commandHref": reverse("n26-next-command", args=[gang.pk])
        + "?"
        + urlencode([*(("ask", key) for key in keys), ("next", back)]),
        "csrfToken": get_token(request),
        "recoveryKey": f"n26-arrivals:{request.user.pk}:{gang.pk}",
        "recoveryHref": recovery_href,
        "signInHref": reverse("account_login")
        + "?"
        + urlencode({"next": recovery_href}),
        "recoveryOnly": not read.screen.blocks,
        "terminal": terminal,
        "dialog": False,
        "messages": queued_messages(request),
    }


def queued_messages(request):
    from django.contrib.messages import get_messages

    return [
        {"text": str(message), "tone": message.level_tag or "info"}
        for message in get_messages(request)
    ]
