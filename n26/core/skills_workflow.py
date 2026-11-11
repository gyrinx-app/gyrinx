"""Placed skill and power offers with retry-safe selection commands."""

from dataclasses import dataclass, field
from uuid import uuid4

from django import forms
from django.core.exceptions import ValidationError

from n26.core import skill_selection
from n26.core.operations import Refusal, operation
from n26.library.staged import sees_staged


class SkillSelectionForm(forms.Form):
    gang = forms.CharField(
        widget=forms.HiddenInput,
        error_messages={
            "required": "Reload this page before selecting a skill or power."
        },
    )
    collection = forms.CharField(required=False, widget=forms.HiddenInput)
    thing = forms.CharField(error_messages={"required": "Select a skill or power."})
    request_key = forms.UUIDField(
        widget=forms.HiddenInput,
        error_messages={
            "required": "Reload this page before selecting a skill or power.",
            "invalid": "Reload this page before selecting a skill or power.",
        },
    )


@dataclass
class SkillScreen:
    card: object
    computed: object
    collections: list
    chosen: object | None = None
    offer: object | None = None


def prepare(miniature, actor, collection_key=""):
    from n26.core.access import selectable_for
    from n26.core.browse import (
        EQUIPMENT_LIST,
        browse,
        narrow,
        placements_for,
        regrouped_by_placement,
        usability_for,
        with_use_notes,
    )
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute
    from n26.core.render import offer_from_view

    card = build_card(miniature)
    computed = compute(card, build_modifier_index(carriers(card)))
    collections = selectable_for(computed)
    result = SkillScreen(card, computed, collections)
    if not collections:
        return result
    chosen = next(
        (one for one in collections if str(one.pk) == collection_key), collections[0]
    )
    placements = placements_for(computed, chosen)
    listed = narrow(
        with_use_notes(
            regrouped_by_placement(
                browse(chosen, EQUIPMENT_LIST, include_staged=sees_staged(actor)),
                placements,
                fallback=chosen.default_section(),
                name=str(chosen),
            ),
            usability_for(computed),
        ),
        sections=[placement.section.name for placement in placements.values()],
    )
    result.chosen = chosen
    result.offer = skill_selection.mark_known(
        offer_from_view(listed, label=str(chosen)), skill_selection.known_on(card)
    )
    return result


def initial(gang, screen):
    return SkillSelectionForm(
        initial={
            "gang": str(gang.pk),
            "collection": str(screen.chosen.pk) if screen.chosen else "",
            "thing": "",
            "request_key": str(uuid4()),
        }
    )


@dataclass
class SkillResult:
    form: SkillSelectionForm
    saved: bool = False
    replayed: bool = False
    removed: bool = False
    message: str = ""
    subject: object | None = None
    facts: dict = field(default_factory=dict)


def change(gang, actor, model_key, data):
    from n26.core.models import Miniature, ModelChoiceReceipt

    form = SkillSelectionForm(data)
    result = SkillResult(form)
    if not form.is_valid():
        return result
    if form.cleaned_data["gang"] != str(gang.pk):
        form.add_error(None, "This form belongs to another gang. Reload the page.")
        return result
    payload = {
        "action": "skill",
        "model": str(model_key),
        "collection": form.cleaned_data["collection"],
        "thing": form.cleaned_data["thing"],
    }
    try:
        with operation(gang, actor=actor) as op:
            gang.refresh_from_db()
            gang.forget_open_activities()
            if not actor.is_authenticated or gang.owner_id != actor.pk or gang.archived:
                raise Refusal(
                    "You can no longer select skills or powers for this gang."
                )
            previous = ModelChoiceReceipt.objects.filter(
                gang=gang, request_key=form.cleaned_data["request_key"]
            ).first()
            if previous is not None:
                if previous.actor_id != actor.pk or previous.payload != payload:
                    raise Refusal(
                        "This form was already used for another selection. Reload the page."
                    )
                result.replayed = True
                if previous.result.get("outcome") == "removed":
                    result.removed = True
                    result.message = previous.result["message"]
                    form.add_error(None, result.message)
                    return result
                result.saved = True
                result.message = previous.result["message"]
                return result
            try:
                miniature = Miniature.objects.select_related(
                    "membership__gang", "membership__profile"
                ).get(pk=model_key, membership__gang=gang)
            except Miniature.DoesNotExist, ValidationError:
                miniature = None
            if miniature is None or miniature.membership.archived:
                from n26.core.model_choice_recovery import target_for

                target = target_for(model_key, actor, action="skill")
                if target is None or target.gang.pk != gang.pk:
                    raise Refusal("This model is no longer in the gang.")
                result.removed = True
                result.message = "This model was removed before this selection was saved. This save was not applied."
                op.record_model_choice_receipt(
                    form.cleaned_data["request_key"],
                    payload,
                    {
                        "outcome": "removed",
                        "message": result.message,
                        "model_name": target.name,
                    },
                )
                form.add_error(None, result.message)
                return result
            screen = prepare(miniature, actor, payload["collection"])
            if screen.chosen is None or (
                payload["collection"] and str(screen.chosen.pk) != payload["collection"]
            ):
                form.add_error(
                    "thing",
                    "This skill list is no longer available. Reload the page to review the current choices.",
                )
                return result
            picked = next(
                (
                    option
                    for group in screen.offer.groups
                    for option in group.options
                    if option.key == payload["thing"]
                ),
                None,
            )
            if picked is None:
                form.add_error(
                    "thing", "That skill or power is not available to select."
                )
                return result
            if picked.key in skill_selection.known_on(screen.card):
                form.add_error("thing", f"{miniature.name} already has {picked.name}.")
                return result
            offers = skill_selection.open_offers(screen.computed)
            lists = {
                id(slot): skill_selection.offered_keys(
                    slot, screen.computed, include_staged=sees_staged(actor)
                )
                for slot in offers
            }
            selected = skill_selection.select_from_offer(
                op, miniature, picked.thing, offers, lists
            )
            result.subject = selected
            result.facts = {
                "gang_id": str(gang.pk),
                "miniature_id": str(miniature.pk),
                "thing": picked.name,
                "collection": screen.chosen.name,
            }
            result.message = f"{miniature.name} selected {picked.name}."
            op.record_model_choice_receipt(
                form.cleaned_data["request_key"],
                payload,
                {"message": result.message, "model_name": miniature.name},
            )
        result.saved = True
    except Refusal as error:
        gang.refresh_from_db()
        gang.forget_open_activities()
        form.add_error(None, error.public_message)
    return result
