"""Computed choice commands shared by native forms and React.

A request key identifies one deliberate pick, removal or roll. Its receipt is
read under current ownership before mutable choices are resolved. A vanished
choice consumes the key with a terminal refusal, preventing a delayed request
from applying after its carrier or ownership period returns.
"""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from uuid import uuid4

from django import forms
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse

from n26.core.models.dismissed_offer import identity_key
from n26.core.operations import Refusal
from n26.core.owned import with_query
from n26.library.staged import sees_staged

FORMAT = "computed-choice-v1"


class ChoiceForm(forms.Form):
    request_key = forms.UUIDField(
        error_messages={"required": "Reload this page before saving this choice."}
    )
    act = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Choose"),
            ("choose", "Choose"),
            ("remove", "Remove"),
            ("roll", "Roll"),
            ("enter", "Enter"),
            ("dismiss", "Dismiss"),
            ("restore", "Restore"),
        ],
    )
    thing = forms.CharField(required=False)
    remove = forms.CharField(required=False)
    roll = forms.CharField(required=False)
    rolled = forms.CharField(required=False)
    returning = forms.CharField(required=False)


def initial(found=None):
    current = ""
    if found is not None:
        from n26.core.render import option_key

        if found.slot.resolved_with is not None:
            current = option_key(found.slot.resolved_with.assignable)
    return ChoiceForm(initial={"request_key": uuid4(), "thing": current})


@dataclass
class ChoiceResult:
    form: forms.Form
    saved: bool = False
    terminal: bool = False
    replayed: bool = False
    message: str = ""
    next_url: str = ""
    facts: dict = field(default_factory=dict)


def write_pick(op, gang, actor, slot_key, wanted, *, dropped="", roll=""):
    """Validate against the current offer under the caller's choice locks."""
    from n26.core.action_records import battle_action_for_slot
    from n26.core.allowances import require_allowance_available
    from n26.core.render import NONE_KEY, build_choice_offer

    found = find_slot(gang, slot_key)
    offer = build_choice_offer(
        found.slot, found.computed, include_staged=sees_staged(actor)
    )
    battle_action = battle_action_for_slot(found.anchor)
    if battle_action is not None:
        require_allowance_available(battle_action.allowance)
        raise Refusal("Choose this result through its earned action flow.")
    rolled_on = _roll_at(roll, gang, found)
    if wanted == NONE_KEY and not dropped:
        if not any(
            option.key == NONE_KEY for group in offer.groups for option in group.options
        ):
            raise NotOnTheList
        for pick in _settled(found):
            op.remove(pick.assignment)
        return found, offer, None
    picked = next(
        (
            option
            for group in offer.groups
            for option in group.options
            if option.key == wanted
        ),
        None,
    )
    if picked is None or (dropped and _pick_of(found, wanted) is None):
        raise NotOnTheList
    if dropped:
        op.remove(_pick_of(found, wanted).assignment)
    elif (
        offer.takes_several
        and _pick_of(found, wanted) is not None
        and not (
            found.slot.slot is not None and found.slot.slot.slot_type.allows_repeats
        )
    ):
        pass
    else:
        if not offer.takes_several:
            for pick in _settled(found):
                op.remove(pick.assignment)
        elif found.slot.is_full:
            raise Refusal(
                f"{offer.label} holds all the picks it will take. Take one back to make room."
            )
        op.choose(
            found.anchor,
            picked.thing,
            slot=found.slot.slot,
            offer=found.slot.offer,
            roll=rolled_on,
            **_host(found),
        )
    return found, offer, picked


def _arrival_keys(gang, op, actor):
    from n26.core.arrivals import any_interstitials, asking

    return (
        asking(gang, op.written, include_staged=sees_staged(actor))
        if op.written and any_interstitials(include_staged=sees_staged(actor))
        else []
    )


def destination(gang, actor, op, slot_key, found, offer, *, here, back):
    from n26.core.arrivals import toward

    keys = _arrival_keys(gang, op, actor)
    if (
        found.slot.slot
        and found.slot.slot.slot_type.is_lasting_effect
        and found.miniature
    ):
        back = reverse("n26-edit-fighter", args=[found.miniature.pk])
    elif offer.takes_several:
        if not keys:
            return here
        try:
            if not find_slot(gang, slot_key).slot.is_full:
                back = here
        except Http404:
            pass
    return toward(gang, keys, back) if keys else back


def change(gang, actor, slot_key, data, *, here, back, campaign_dialog=False):
    """Apply one actor-bound command, retaining its canonical result atomically.

    The adapters validate here and back as local navigation. Neither credentials
    nor browser display labels are part of the retained business input.
    """
    from n26.core.models import DismissedOffer, ModelChoiceReceipt

    form = ChoiceForm(data)
    result = ChoiceResult(form)
    if not form.is_valid():
        return result
    values = form.cleaned_data
    intent = values["act"] or ("remove" if values["remove"] else "choose")
    payload = {
        "action": "computed-choice",
        "format": FORMAT,
        "slot": slot_key,
        "intent": intent,
        "thing": values["thing"],
        "remove": values["remove"],
        "roll": values["roll"],
        "rolled": values["rolled"],
        "here": here,
        "back": back,
        "campaign_dialog": campaign_dialog,
    }
    try:
        with choice_operation(gang, [slot_key], actor=actor) as op:
            gang.refresh_from_db()
            if not actor.is_authenticated or gang.owner_id != actor.pk or gang.archived:
                raise Refusal("You can no longer change this gang's choices.")
            previous = ModelChoiceReceipt.objects.filter(
                gang=gang, request_key=values["request_key"]
            ).first()
            if previous is not None:
                if previous.actor_id != actor.pk or previous.payload != payload:
                    raise Refusal(
                        "This form was already used for another choice. Reload the page."
                    )
                if previous.result.get("format") != FORMAT:
                    raise Refusal(
                        "This saved choice could not be verified. Reload the page."
                    )
                stored = previous.result
                result.replayed = True
            else:
                try:
                    found = find_slot(gang, slot_key)
                except Http404:
                    found = None
                if found is None and intent != "restore":
                    stored = {
                        "format": FORMAT,
                        "outcome": "unavailable",
                        "message": "This choice was removed before the save was applied. This save was not applied.",
                        "next_url": back,
                        "facts": {},
                    }
                else:
                    if campaign_dialog and found is not None:
                        _campaign_label_or_404(gang, found)
                    message = ""
                    facts = {"action": intent}
                    next_url = here
                    if intent == "restore":
                        DismissedOffer.objects.filter(
                            gang=gang, slot_key=slot_key
                        ).delete()
                        label = found.slot.kind_label if found else "the choice"
                        message = f"Restored {label}."
                        facts["offer"] = label
                        next_url = back
                    elif intent == "dismiss":
                        label = found.slot.kind_label
                        if not found.slot.allow_dismissal:
                            raise Refusal(
                                f"You cannot dismiss {label}. This choice must stay available."
                            )
                        if found.slot.is_resolved:
                            held = (
                                "It has a pick. Take the pick back first."
                                if len(found.slot.picks) == 1
                                else "It has picks. Take them all back first."
                            )
                            raise Refusal(f"You cannot dismiss {label}. {held}")
                        if found.slot.is_full:
                            raise Refusal(
                                f"You cannot dismiss {label}. It offers nothing to choose."
                            )
                        DismissedOffer.objects.get_or_create(
                            gang=gang, slot_key=slot_key
                        )
                        where = (
                            "Dismissed choices on the model’s Edit page"
                            if found.miniature
                            else "the Dismissed choices tab on the gang’s Edit page"
                        )
                        message = f"Dismissed {label}. You can restore it from {where}."
                        facts["offer"] = label
                        next_url = back
                    elif intent in {"roll", "enter"}:
                        from n26.core.action_records import battle_action_for_slot
                        from n26.core.allowances import require_allowance_available

                        battle_action = battle_action_for_slot(found.anchor)
                        if battle_action is not None:
                            require_allowance_available(battle_action.allowance)
                            raise Refusal(
                                "Choose this result through its earned action flow."
                            )
                        if found.slot.slot is None or not found.slot.slot.picklist.dice:
                            raise Refusal("This choice has no roll table.")
                        if found.slot.is_full:
                            raise Refusal(
                                f"{found.slot.kind_label} holds all the picks it will take. Take one back before rolling."
                            )
                        rolled = None
                        if intent == "enter":
                            try:
                                rolled = int(values["rolled"])
                            except ValueError:
                                form.add_error("rolled", "Enter the number you rolled.")
                                return result
                        event = op.roll(
                            found.slot.slot,
                            miniature=found.miniature,
                            campaign_asset=found.slot.holding,
                            rolled=rolled,
                        )
                        next_url = with_query(here, roll=event.pk)
                        facts.update(
                            offer=found.slot.kind_label, entered=rolled is not None
                        )
                    else:
                        status_before = (
                            found.miniature.status if found.miniature else None
                        )
                        dropped = values["remove"] or (
                            values["thing"] if intent == "remove" else ""
                        )
                        found, offer, picked = write_pick(
                            op,
                            gang,
                            actor,
                            slot_key,
                            dropped or values["thing"],
                            dropped=dropped,
                            roll=values["roll"],
                        )
                        message = pick_message(picked, offer, dropped)
                        if found.miniature:
                            found.miniature.refresh_from_db(fields=["status"])
                            if found.miniature.status != status_before:
                                from n26.core.status import label_for

                                primary = next(
                                    (
                                        node.assignable
                                        for node in found.computed.card.all_nodes()
                                        if node.is_primary_profile
                                    ),
                                    None,
                                )
                                vehicle = (
                                    primary is not None
                                    and primary.profile_type.name == "Vehicle"
                                )
                                message += f" {found.miniature.name} is now {label_for(found.miniature.status, vehicle)}."
                        facts.update(
                            action="none" if picked is None else intent,
                            offer=offer.label,
                            picked="None" if picked is None else picked.name,
                        )
                        next_url = destination(
                            gang,
                            actor,
                            op,
                            slot_key,
                            found,
                            offer,
                            here=here,
                            back=back,
                        )
                    stored = {
                        "format": FORMAT,
                        "outcome": "saved",
                        "message": message,
                        "next_url": next_url,
                        "facts": facts,
                        "written": [str(key) for key in op.written],
                    }
                op.record_model_choice_receipt(values["request_key"], payload, stored)
            result.message = stored["message"]
            result.next_url = stored["next_url"]
            result.facts = stored["facts"]
            if result.replayed and result.next_url.startswith(here):
                try:
                    find_slot(gang, slot_key)
                except Http404:
                    result.next_url = back
            result.terminal = stored["outcome"] == "unavailable"
            result.saved = not result.terminal
            if result.terminal:
                form.add_error(None, result.message)
    except NotOnTheList:
        form.add_error("thing", "That is not one of the things available to pick.")
    except Http404:
        form.add_error("roll", "That roll is no longer available for this choice.")
    except Refusal as error:
        result.saved = False
        result.terminal = False
        gang.refresh_from_db()
        form.add_error(None, error.public_message)
    return result


@dataclass
class ArrivalRead:
    screen: object
    found: dict
    here: str


def prepare_arrivals(gang, actor, keys, back):
    """Resolve URL-selected questions once and group their authored screens."""
    from n26.core.arrivals import interstitials_on, next_url
    from n26.core.render import (
        ArrivalBlock,
        ArrivalQuestion,
        ArrivalScreen,
        build_choice_offers,
        is_tier_ladder,
    )

    located = {
        key: found
        for key, found in find_slots(gang, keys).items()
        if found.slot.slot is not None
        and found.slot.max_picks > 0
        and not is_tier_ladder(found.slot)
    }
    located = {key: located[key] for key in keys if key in located}
    shown = sees_staged(actor)
    carrying = interstitials_on(
        {found.slot.slot.pk for found in located.values()}, include_staged=shown
    )
    grouped = {}
    for order, (key, found) in enumerate(located.items()):
        for attachment in carrying.get(found.slot.slot.pk, ()):
            item = attachment.interstitial
            grouped.setdefault(item.pk, (item, []))[1].append(
                (attachment.position, found.slot.slot.name.lower(), order, key)
            )
    grouped = {
        pk: (item, [key for *_, key in sorted(placed)])
        for pk, (item, placed) in grouped.items()
    }
    screened = {key for _, group in grouped.values() for key in group}
    located = {key: found for key, found in located.items() if key in screened}
    here = next_url(gang, list(located), back)
    offers = {}
    computations = {}
    for key, found in located.items():
        computations.setdefault(id(found.computed), []).append((key, found))
    for group in computations.values():
        built = build_choice_offers(
            [found.slot for _, found in group],
            group[0][1].computed,
            include_staged=shown,
        )
        offers.update(
            (key, offer) for (key, _), offer in zip(group, built, strict=True)
        )
    blocks = []
    for order, (item, group) in enumerate(
        sorted(
            grouped.values(), key=lambda pair: (pair[0].position, pair[0].name.lower())
        ),
        1,
    ):
        questions = []
        for key in group:
            found, offer = located[key], offers[key]
            slot = found.slot
            roll_href = (
                with_query(
                    reverse("n26-choose", args=[gang.pk, key]), **{"return": here}
                )
                if slot.slot.picklist.dice and not slot.is_full
                else ""
            )
            questions.append(
                ArrivalQuestion(
                    key=key,
                    label=slot.kind_label,
                    bearer=found.miniature.name if found.miniature else gang.name,
                    chosen=slot.chosen_name,
                    settled=len(slot.picks) >= slot.min_picks or offer.is_empty,
                    offer=offer,
                    roll_href=roll_href,
                    under=str(order),
                )
            )
        blocks.append(
            ArrivalBlock(
                heading=item.heading,
                description=item.description,
                questions=tuple(questions),
                skippable=item.skippable,
            )
        )
    return ArrivalRead(
        ArrivalScreen(blocks=tuple(blocks), next_url=back), located, here
    )


class ArrivalForm(forms.Form):
    asks = forms.JSONField(required=False)
    next = forms.CharField(required=False)
    request_key = forms.UUIDField(
        error_messages={"required": "Reload this page before saving these choices."}
    )
    selection = forms.JSONField(required=False)
    choice = forms.CharField(required=False)
    act = forms.ChoiceField(
        required=False,
        choices=[("continue", "Continue"), ("choose", "Choose"), ("remove", "Remove")],
    )
    thing = forms.CharField(required=False)
    remove = forms.CharField(required=False)


def arrival_initial(keys=(), back=""):
    return ArrivalForm(
        initial={
            "request_key": uuid4(),
            "selection": {},
            "act": "continue",
            "asks": list(keys),
            "next": back,
        }
    )


def change_arrivals(gang, actor, keys, data, *, back):
    """Settle selected arrival questions atomically through the picker writer."""
    import json

    from n26.core.arrivals import next_url
    from n26.core.models import ModelChoiceReceipt

    prepared = data.copy()
    if "selection" not in prepared:
        prepared["selection"] = json.dumps(
            {
                key.split(":", 1)[1]: data[key]
                for key in data
                if key.startswith("thing:")
            }
        )
        for field in data:
            if field.startswith("remove:") and data[field]:
                prepared["choice"], prepared["remove"], prepared["act"] = (
                    field.split(":", 1)[1],
                    data[field],
                    "remove",
                )
                break
    form = ArrivalForm(prepared)
    result = ChoiceResult(form)
    if not form.is_valid():
        return result
    values = form.cleaned_data
    if values["asks"] is not None:
        from n26.core.arrivals import MAX_ASKS

        if (
            not isinstance(values["asks"], list)
            or len(values["asks"]) > MAX_ASKS
            or not all(isinstance(key, str) for key in values["asks"])
        ):
            form.add_error("asks", "These choices could not be read. Reload the page.")
            return result
        keys = list(dict.fromkeys(values["asks"]))
    selection = values["selection"] or {}
    if not isinstance(selection, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in selection.items()
    ):
        form.add_error("selection", "These choices could not be read. Reload the page.")
        return result
    payload = {
        "action": "computed-choice",
        "format": "computed-arrivals-v1",
        "keys": keys,
        "selection": selection,
        "choice": values["choice"],
        "intent": values["act"] or "continue",
        "thing": values["thing"],
        "remove": values["remove"],
        "back": back,
    }
    try:
        with choice_operation(gang, keys, actor=actor) as op:
            gang.refresh_from_db()
            if not actor.is_authenticated or gang.owner_id != actor.pk or gang.archived:
                raise Refusal("You can no longer change this gang's choices.")
            previous = ModelChoiceReceipt.objects.filter(
                gang=gang, request_key=values["request_key"]
            ).first()
            if previous is not None:
                if previous.actor_id != actor.pk or previous.payload != payload:
                    raise Refusal(
                        "This form was already used for other choices. Reload the page."
                    )
                stored = previous.result
                if stored.get("format") != "computed-arrivals-v1":
                    raise Refusal(
                        "These saved choices could not be verified. Reload the page."
                    )
                result.replayed = True
            else:
                read = prepare_arrivals(gang, actor, keys, back)
                picks = {key: value for key, value in selection.items() if value}
                wanted_key = values["choice"]
                if wanted_key:
                    picks = {wanted_key: values["remove"] or values["thing"]}
                missing = set(picks) - set(read.found)
                if missing:
                    stored = {
                        "format": "computed-arrivals-v1",
                        "outcome": "unavailable",
                        "message": "A choice was removed before these picks were saved. This save was not applied.",
                        "next_url": back,
                        "facts": {},
                    }
                else:
                    picks = {key: picks[key] for key in read.found if key in picks}
                    confirmations = []
                    facts = []
                    individual = False
                    if not wanted_key:
                        from n26.core.render import build_choice_offer

                        wanted_key = next(
                            (
                                key
                                for key in picks
                                if build_choice_offer(
                                    read.found[key].slot,
                                    read.found[key].computed,
                                    include_staged=sees_staged(actor),
                                ).takes_several
                            ),
                            "",
                        )
                    for key, wanted in picks.items():
                        found = read.found[key]
                        from n26.core.render import build_choice_offer

                        offered = build_choice_offer(
                            found.slot,
                            found.computed,
                            include_staged=sees_staged(actor),
                        )
                        dropped = values["remove"] if wanted_key == key else ""
                        if not wanted_key and offered.takes_several:
                            wanted_key = key
                        if wanted_key and wanted_key != key:
                            continue
                        individual = bool(wanted_key)
                        found, offer, picked = write_pick(
                            op, gang, actor, key, wanted, dropped=dropped
                        )
                        confirmations.append(pick_message(picked, offer, dropped))
                        facts.append(
                            {
                                "offer": offer.label,
                                "picked": "None" if picked is None else picked.name,
                                "action": "none"
                                if picked is None
                                else "remove"
                                if dropped
                                else "choose",
                            }
                        )
                        if individual:
                            break
                    brought = [
                        key
                        for key in _arrival_keys(gang, op, actor)
                        if key not in read.found
                    ]
                    next_keys = [*read.found, *brought] if individual else brought
                    stored = {
                        "format": "computed-arrivals-v1",
                        "outcome": "saved",
                        "message": " ".join(confirmations),
                        "next_url": next_url(gang, next_keys, back)
                        if next_keys
                        else back,
                        "facts": {"choices": facts},
                        "written": [str(key) for key in op.written],
                    }
                op.record_model_choice_receipt(values["request_key"], payload, stored)
            result.message, result.next_url, result.facts = (
                stored["message"],
                stored["next_url"],
                stored["facts"],
            )
            result.terminal = stored["outcome"] == "unavailable"
            result.saved = not result.terminal
            if result.terminal:
                form.add_error(None, result.message)
    except NotOnTheList:
        form.add_error("selection", "That is not one of the things available to pick.")
    except Http404:
        form.add_error(None, "That choice is no longer available.")
    except Refusal as error:
        result.saved = False
        result.terminal = False
        gang.refresh_from_db()
        form.add_error(None, error.public_message)
    return result


@contextmanager
def choice_operation(gang, keys, *, actor=None):
    """Lock holding campaigns in stable order before the gang operation.

    Ordinary assignment choices require only the gang lock. Resolve choices again
    inside these locks before writing.
    """
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignAsset
    from n26.core.models.dismissed_offer import HOLDING_SLOT_HOST
    from n26.core.operations import operation

    campaigns = {}
    for key in keys:
        where, _, rest = key.partition(":")
        if where != HOLDING_SLOT_HOST:
            continue
        holding_pk = rest.partition(":")[0].partition("@")[0]
        try:
            holding = (
                CampaignAsset.objects.select_related("campaign")
                .filter(pk=holding_pk)
                .first()
            )
        except ValidationError:
            raise Http404("No such holding") from None
        if holding is not None:
            campaigns[holding.campaign_id] = holding.campaign
    with ExitStack() as locks:
        for campaign_pk in sorted(campaigns, key=str):
            locks.enter_context(campaign_operation(campaigns[campaign_pk], actor=actor))
        with operation(gang, actor=actor) as op:
            yield op


@dataclass(frozen=True)
class _Found:
    """A resolved computed choice, its computation, carrier and optional target model."""

    slot: object
    computed: object
    anchor: object
    #: The model whose card displays the choice; None for a gang choice.
    miniature: object = None


def find_slot(gang, key):
    """Recompute the addressed card and resolve the current choice, otherwise return 404."""
    from n26.core.card import (
        build_card,
        build_gang_card,
        build_modifier_index,
        carriers,
    )
    from n26.core.effects import compute, compute_gang
    from n26.core.models import Miniature
    from n26.core.models.dismissed_offer import HOLDING_SLOT_HOST, holding_slot_key
    from n26.core.render import GANG_SLOT_HOST

    where, _, rest = key.partition(":")
    anchor_pk, _, offer_pk = rest.partition(":")
    if not (where and anchor_pk and offer_pk):
        raise Http404("No such choice")

    miniature = None
    if where in (GANG_SLOT_HOST, HOLDING_SLOT_HOST):
        card = build_gang_card(gang)
    else:
        try:
            miniature = get_object_or_404(
                Miniature,
                pk=where,
                membership__gang=gang,
                membership__archived=False,
            )
        except ValidationError:
            # Convert malformed model identifiers into missing-choice responses.
            raise Http404("No such fighter") from None
        card = build_card(miniature)

    index = build_modifier_index(carriers(card))
    computed = compute_gang(card, index) if miniature is None else compute(card, index)

    for slot in computed.choices:
        if slot.holding is not None:
            if holding_slot_key(slot.holding, slot.identity.pk) == key:
                return _Found(slot=slot, computed=computed, anchor=slot.holding)
            continue
        anchor = getattr(slot.anchor, "assignment", None)
        if anchor is None or slot.identity is None:
            continue
        identity = identity_key(slot.identity.pk, slot.status_revision)
        if str(anchor.pk) == anchor_pk and identity == offer_pk:
            return _Found(
                slot=slot, computed=computed, anchor=anchor, miniature=miniature
            )
    raise Http404("No such choice")


def find_slots(gang, keys):
    """Resolve many choice addresses through one gang-card derivation.

    Return a key-to-Found mapping, omitting malformed, missing and vanished choices.
    Canonicalise model identifiers for lookup without rewriting the requested keys.
    """
    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute, compute_gang
    from n26.core.models import Miniature
    from n26.core.models.dismissed_offer import HOLDING_SLOT_HOST, holding_slot_key
    from n26.core.render import GANG_SLOT_HOST

    wanted = {}
    for key in keys:
        where, _, rest = key.partition(":")
        anchor_pk, _, offer_pk = rest.partition(":")
        if not (where and anchor_pk and offer_pk):
            continue
        if where not in (GANG_SLOT_HOST, HOLDING_SLOT_HOST):
            try:
                # Canonicalise model ULIDs for dictionary lookup because the field also accepts UUID spelling.
                # Match carrier and offer identifiers exactly, preserving the original URL key.
                where = str(Miniature._meta.pk.to_python(where))
            except ValidationError:
                # Convert malformed model identifiers into missing-choice responses.
                continue
        wanted.setdefault(where, {})[(anchor_pk, offer_pk)] = key
    if not wanted:
        return {}

    gang_card = build_gang_card(gang)
    cards = gang_card.members
    index = build_modifier_index(carriers(gang_card, *cards.values()))
    computed = {}
    if GANG_SLOT_HOST in wanted or HOLDING_SLOT_HOST in wanted:
        done = compute_gang(gang_card, index)
        for where in (GANG_SLOT_HOST, HOLDING_SLOT_HOST):
            if where in wanted:
                computed[where] = (done, None)
    named = [
        where for where in wanted if where not in (GANG_SLOT_HOST, HOLDING_SLOT_HOST)
    ]
    if named:
        miniatures = Miniature.objects.filter(
            pk__in=named, membership__gang=gang, membership__archived=False
        )
        members = {str(m.pk): m for m in miniatures}
        for where, miniature in members.items():
            card = cards.get(miniature.pk)
            if card is not None:
                computed[where] = (compute(card, index), miniature)

    found = {}
    for where, (done, miniature) in computed.items():
        for slot in done.choices:
            if slot.holding is not None:
                if where == HOLDING_SLOT_HOST:
                    _, anchor_key, identity = holding_slot_key(
                        slot.holding, slot.identity.pk
                    ).split(":")
                    key = wanted[where].get((anchor_key, identity))
                    if key is not None:
                        found[key] = _Found(
                            slot=slot, computed=done, anchor=slot.holding
                        )
                continue
            anchor = getattr(slot.anchor, "assignment", None)
            if anchor is None or slot.identity is None:
                continue
            identity = identity_key(slot.identity.pk, slot.status_revision)
            key = wanted[where].get((str(anchor.pk), identity))
            if key is not None:
                found[key] = _Found(
                    slot=slot, computed=done, anchor=anchor, miniature=miniature
                )
    return found


def _settled(found):
    """Read stored picks from the computed choice's scoped and adopted picks."""
    return [pick for pick in found.slot.picks if pick.assignment is not None]


def _pick_of(found, wanted):
    """Find a stored settled pick matching an option identity, or return None."""
    from n26.core.render import option_key

    return next(
        (pick for pick in _settled(found) if option_key(pick.assignable) == wanted),
        None,
    )


def _roll_table(found):
    """Build roll controls for a non-full choice with an authored die."""
    from n26.core.render import RollTable
    from n26.library.models import Dice

    slot = found.slot.slot
    if slot is None or not slot.picklist.dice or found.slot.is_full:
        # Full choices cannot accept another roll until a pick is removed.
        return None
    dice = Dice(slot.picklist.dice)
    rolls = Dice.rolls(dice)
    return RollTable(dice_label=dice.label, lowest=rolls[0], highest=rolls[-1])


def _roll_at(key, gang, found, select_related=()):
    """Resolve a roll scoped to this gang, choice, model and revision context.

    Holding ownership and status-follow-up revisions prevent reuse after their
    context changes. Invalid or unrelated identifiers return 404.
    """
    from n26.core.models import LedgerEvent

    if not key or found.slot.slot is None:
        return None
    try:
        return get_object_or_404(
            LedgerEvent.objects.select_related(*select_related),
            pk=key,
            gang=gang,
            kind=LedgerEvent.Kind.ROLLED,
            slot=found.slot.slot,
            miniature=found.miniature,
            campaign_asset=found.slot.holding,
            holding_revision=found.slot.holding.ownership_revision
            if found.slot.holding
            else None,
            **(
                {"status_revision": found.slot.status_revision}
                if found.slot.slot.follows_status
                else {}
            ),
        )
    except ValidationError:
        raise Http404("No such roll") from None


def _roll_result(event, found, offer, *, include_staged=False):
    """Describe a recorded roll and identify the visible picklist results it reaches.

    Apply archive and staged visibility through picklist_lines. An archived pick
    releases its roll for reuse. Prefer the recorded die, falling back to the
    current table for unknown stored values.
    """
    from django.db.models import F

    from n26.core.browse import picklist_lines
    from n26.core.operations import ROLL_ENTERED, ROLL_ENTERED_BEFORE
    from n26.core.render import RollResult, option_key
    from n26.library.models import Dice, RollSelects

    picklist = found.slot.slot.picklist
    # Read visible results in the same roll order as the displayed picklist.
    members = picklist_lines(picklist, include_staged=include_staged).order_by(
        F("roll_low").asc(nulls_last=True), "position", "pickable__name"
    )
    landed = picklist.landing(event.roll, members)
    keys = {option_key(member.pickable) for member in landed}
    named = {
        option.key: option.name for group in offer.groups for option in group.options
    }
    # Only live picks consume a roll; removing a pick releases it.
    spent = event.picks.filter(archived=False).select_related("pickable").first()
    # Prefer the recorded die, falling back to the current table for unknown values.
    dice = Dice(picklist.dice)
    try:
        dice = Dice(event.dice) if event.dice else dice
    except ValueError:
        pass
    result = RollResult(
        key=str(event.pk),
        total=event.roll,
        dice_label=dice.label,
        faces=Dice.faces(dice, event.roll),
        landed=tuple(named.get(option_key(m.pickable), m.label) for m in landed),
        entered=event.note in (ROLL_ENTERED, ROLL_ENTERED_BEFORE),
        applied=str(spent.assignable) if spent is not None else "",
        threshold=picklist.roll_selects == RollSelects.THRESHOLD,
    )
    return result, keys


def _host(found):
    """Identify the target model for choices broadcast from gang-held assignments."""
    if (
        found.miniature is not None
        and found.slot.anchor is not None
        and found.slot.anchor.broadcast
    ):
        return {"miniature": found.miniature}
    return {}


def _campaign_label_or_404(gang, found):
    from n26.core.models import CampaignMembership

    membership = CampaignMembership.objects.filter(gang=gang, left__isnull=True).first()
    if membership is None or found.miniature is not None:
        raise Http404("No such campaign label")
    carriers = {membership.type_carrier_id, membership.additions_carrier_id}
    if found.slot.holding is not None:
        raise Http404("No such campaign label")
    anchor = found.anchor
    seen = set()
    while anchor is not None and anchor.pk not in seen:
        if anchor.pk in carriers:
            return
        seen.add(anchor.pk)
        anchor = anchor.caused_by
    raise Http404("No such campaign label")


class NotOnTheList(Exception):
    """A stale or invalid submitted option requiring the current picker to be redisplayed."""


def pick_message(picked, offer, dropped):
    """Describe choice, addition or removal using the offer's single- or multi-pick terms."""
    if picked is None:
        return f"Chose none — {offer.label}."
    if dropped:
        verb = "Removed"
    elif offer.takes_several:
        verb = "Added"
    else:
        verb = "Chose"
    return f"{verb} {picked.name} — {offer.label}."
