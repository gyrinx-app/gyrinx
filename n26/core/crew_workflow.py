"""Crew validation and durable commands shared by native and JSON adapters."""

import json
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from django import forms

from n26.core.crew_forms import CrewForm
from n26.core.crews import crew_roster, locked_crew, save_crew
from n26.core.models.crew import CrewCommandReceipt
from n26.core.operations import Refusal
from n26.write_pause import guarded_write

MESSAGES = {
    "draw": "Draw saved.",
    "save": "Crew saved.",
    "draft": "Crew draft saved.",
}


@dataclass
class Submission:
    form: CrewForm | None = None
    crew: object = None
    receipt: CrewCommandReceipt | None = None
    replayed: bool = False
    conflict: bool = False
    key_conflict: bool = False
    newer: bool = False
    read_only: bool = False
    status: int = 422

    @property
    def saved(self):
        return self.receipt is not None

    @property
    def message(self):
        return MESSAGES[self.receipt.result["action"]]


def raw_inputs(data):
    return {
        name: data.getlist(name)
        for name in sorted(data)
        if name not in {"csrfmiddlewaretoken", "request_key", "submitted_snapshot"}
    }


def snapshot(crew, *, action, drawn):
    return {
        "version": 1,
        "action": action,
        "revision": crew.revision,
        "confirmed": crew.confirmed,
        "draw_number": crew.draw_number,
        "last_draw": crew.last_draw,
        "drawn": list(drawn),
        "selections": [
            {
                "id": str(member.miniature_id) if member.miniature_id else "",
                "name": member.miniature_name,
                "role": member.role,
                "card": member.card_name,
                "equipment_ids": member.equipment_ids,
                "rating": member.rating,
                "source": member.source,
                "card_source": member.card_source,
                "eligibility_override": member.eligibility_override,
            }
            for member in crew.members.all()
        ],
    }


@guarded_write
def perform(*, battle, gang, actor, data, require_key=False):
    """Recall a successful command before validating today's roster and cards."""
    submitted = Submission()
    with locked_crew(battle=battle, gang=gang, actor=actor) as (
        campaign,
        battle,
        gang,
        crew,
    ):
        submitted.crew = crew
        submitted.read_only = campaign.archived or battle.archived or gang.archived
        inputs = raw_inputs(data)
        try:
            key = forms.UUIDField(required=require_key).clean(data.get("request_key"))
        except forms.ValidationError:
            key = None
            key_error = True
        else:
            key_error = False
            if key is None:
                key = uuid5(
                    NAMESPACE_URL,
                    json.dumps(
                        [actor.pk, str(battle.pk), str(gang.pk), inputs], sort_keys=True
                    ),
                )
        if not key_error:
            prior = CrewCommandReceipt.objects.filter(
                gang=gang, request_key=key
            ).first()
            if prior is not None:
                if (
                    prior.battle_id != battle.pk
                    or prior.actor_id != actor.pk
                    or prior.inputs != inputs
                ):
                    submitted.key_conflict = True
                else:
                    submitted.receipt = prior
                    submitted.replayed = True
                    submitted.status = 200
                    submitted.newer = (
                        crew is None or crew.revision != prior.result["revision"]
                    )
                    return submitted
        form = CrewForm(data, roster=crew_roster(gang, crew), crew=crew)
        submitted.form = form
        form.is_valid()
        if key_error:
            form.add_error(
                None,
                "This save's reference is missing or invalid. Reload the crew before continuing.",
            )
            return submitted
        if submitted.key_conflict:
            submitted.status = 409
            form.add_error(
                None,
                "This save reference belongs to a different change. Retry the original save before continuing.",
            )
            return submitted
        if "revision" in form.cleaned_data and form.cleaned_data["revision"] != (
            crew.revision if crew else 0
        ):
            submitted.status = 409
            submitted.conflict = True
            form.add_error(
                None,
                "This crew changed while you were editing it. Reload the saved crew before saving again.",
            )
            return submitted
        if form.errors:
            return submitted
        action = data.get("action", "save")
        if action not in MESSAGES:
            form.add_error(None, "Select Save crew, Save draft or Draw.")
            return submitted
        if action == "draw" and not form.cleaned_data["random_count"]:
            form.add_error("random_count", "Enter the number of models to draw.")
            return submitted
        try:
            saved = save_crew(
                battle=battle,
                gang=gang,
                actor=actor,
                revision=form.cleaned_data["revision"],
                selections=form.cleaned_data["selections"],
                confirm=action == "save",
                random_count=form.cleaned_data["random_count"]
                if action == "draw"
                else 0,
                random_role=form.cleaned_data["random_role"],
            )
        except Refusal as exc:
            form.add_error(None, exc.public_message)
            submitted.status = 409
            submitted.conflict = form.cleaned_data.get("revision") != (
                crew.revision if crew else 0
            )
            return submitted
        submitted.crew = saved.crew
        submitted.receipt = CrewCommandReceipt.objects.create(
            gang=gang,
            battle=battle,
            actor=actor,
            request_key=key,
            inputs=inputs,
            result=snapshot(saved.crew, action=action, drawn=saved.drawn),
        )
        submitted.status = 200
    return submitted
