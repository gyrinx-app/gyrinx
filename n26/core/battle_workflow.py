"""Shared form validation and durable saves for battle creation and editing."""

import json
from dataclasses import dataclass
from uuid import uuid4

from django import forms
from django.urls import reverse

from n26 import flags
from n26.core import schedule as s
from n26.core.campaigns import campaign_operation
from n26.core.cycle_data import ref_data, ref_from_data
from n26.core.forms import BattleForm
from n26.core.models import BattleCommand, CampaignSchedule
from n26.core.operations import Refusal


@dataclass
class Submission:
    form: BattleForm
    battle: object = None
    replayed: bool = False
    conflict: bool = False
    current: dict | None = None


def _normalise(data):
    result = data.copy()
    for field in ("gangs", "winners"):
        values = data.getlist(field)
        if len(values) == 1 and values[0].startswith("["):
            try:
                selected = json.loads(values[0])
            except ValueError:
                continue
            if isinstance(selected, list) and all(
                isinstance(identity, str) for identity in selected
            ):
                result.setlist(field, selected)
    return result


def form_for(campaign, actor, playing, *, data=None, battle=None, catalogue=None):
    prepared = _normalise(data) if data is not None else None
    if prepared is not None and not prepared.get("request_key"):
        prepared["request_key"] = str(uuid4())
    form = BattleForm(
        prepared,
        playing=playing,
        battle=battle,
        **({"catalogue": catalogue} if catalogue is not None else {}),
    )
    form.fields["request_key"] = forms.UUIDField(required=False)
    form.initial["request_key"] = str(uuid4())
    if flags.enabled(flags.CYCLE_TRACKING, actor):
        form.fields["cycle"] = forms.JSONField(required=False)
        cycle_id = (
            battle.cycle_id
            if battle
            else CampaignSchedule.objects.filter(campaign=campaign)
            .values_list("current_cycle_id", flat=True)
            .first()
        )
        form.initial["cycle"] = (
            ref_data(s.SavedCycleRef(str(cycle_id))) if cycle_id else None
        )
    return form


def perform(campaign, actor, playing, data, *, battle=None, catalogue=None):
    form = form_for(
        campaign, actor, playing, data=data, battle=battle, catalogue=catalogue
    )
    submitted = Submission(form)
    key_form = forms.UUIDField(required=False)
    try:
        key = key_form.clean(data.get("request_key")) or uuid4()
    except forms.ValidationError:
        form.is_valid()
        return submitted
    inputs = {
        name: data.getlist(name)
        for name in sorted(data)
        if name not in ("csrfmiddlewaretoken", "request_key")
    }
    kind = "edit" if battle else "create"
    with campaign_operation(campaign, actor=actor) as act:
        act._require_recorder()
        if battle is not None and act.campaign.owner_id != actor.pk:
            raise Refusal("Only the arbitrator can edit a battle.")
        previous = (
            BattleCommand.objects.select_related("battle")
            .filter(campaign=campaign, request_key=key)
            .first()
        )
        if previous:
            form.is_valid()
            if (
                previous.actor_id != actor.pk
                or previous.kind != kind
                or previous.inputs != inputs
                or (battle and previous.battle_id != battle.pk)
            ):
                form.add_error(
                    None,
                    "A different change was saved from this form. Reload the battle.",
                )
                return submitted
            submitted.battle, submitted.replayed = previous.battle, True
            return submitted
        if not form.is_valid():
            return submitted
        if "cycle" in data and "cycle" not in form.fields:
            form.add_error(None, "Cycle tracking is not available to this account.")
            return submitted
        values = dict(form.cleaned_data)
        values.pop("request_key", None)
        if "cycle" not in data:
            values.pop("cycle", None)
        if "cycle" in values:
            try:
                values["cycle"] = (
                    ref_from_data(values["cycle"])
                    if values["cycle"] is not None
                    else None
                )
            except s.ScheduleError as exc:
                form.add_error("cycle", str(exc))
                return submitted
        if battle is not None:
            from n26.core.models import Battle

            current = Battle.objects.get(pk=battle.pk, campaign=campaign)
            if current.revision != values["revision"]:
                submitted.conflict = True
                submitted.current = {
                    "revision": current.revision,
                    "scenario": current.scenario,
                    "date": current.date.isoformat(),
                }
                form.add_error(
                    None, "This battle changed. Review it before saving your changes."
                )
                return submitted
        try:
            # A refusal must roll back prefix saving and any stake transfer together.
            from django.db import transaction

            with transaction.atomic():
                saved = (
                    act.edit_battle(battle, **values)
                    if battle
                    else act.record_battle(**values)
                )
                BattleCommand.objects.create(
                    campaign=campaign,
                    actor=actor,
                    battle=saved,
                    request_key=key,
                    kind=kind,
                    inputs=inputs,
                    revision=saved.revision,
                )
        except Refusal as exc:
            form.add_error(None, exc.public_message)
            return submitted
        submitted.battle = saved
    return submitted


def next_url(campaign, battle):
    return reverse("n26-battle", args=[campaign.pk, battle.pk])


def editor_props(
    campaign,
    actor,
    form,
    *,
    battle=None,
    catalogue=None,
    csrf_token,
    conflict=False,
    current=None,
):
    from n26.core.cycle_selection import options
    from n26.core.views.scenario_props import battle_scenario_props

    values = {}
    for name in form.fields:
        value = form[name].value()
        values[name] = (
            json.dumps([str(item) for item in value or []])
            if name in ("gangs", "winners")
            else ""
            if value is None
            else str(value)
        )
        if name == "cycle":
            try:
                values[name] = json.dumps(
                    json.loads(values[name]), separators=(",", ":")
                )
            except ValueError:
                pass
    scenario = (
        battle_scenario_props(
            {name: values[name] for name in form.scenario_keys}, catalogue
        )
        if battle is None
        else None
    )
    if scenario is not None:
        values.update(scenario["rolls"])
    selected = None
    if "cycle" in values:
        try:
            selected = json.loads(values["cycle"])
        except ValueError:
            pass
    choices = {}
    for name in ("gangs", "winners", "result", "stake", "stake_awarded_to"):
        if name in form.fields:
            choices[name] = [
                {"value": str(value), "label": str(label)}
                for value, label in form.fields[name].choices
            ]
    if "stake_awarded_to" in choices:
        choices["stake_awarded_to"] = [
            {"value": "", "label": "Not awarded"},
            *choices["gangs"],
        ]
    action = (
        reverse("n26-campaign-edit-battle", args=[campaign.pk, battle.pk])
        if battle
        else reverse("n26-campaign-add-battle", args=[campaign.pk])
    )
    back = (
        next_url(campaign, battle)
        if battle
        else reverse("n26-campaign", args=[campaign.pk])
    )
    command = (
        reverse("n26-battle-save", args=[campaign.pk, battle.pk])
        if battle
        else reverse("n26-battle-create", args=[campaign.pk])
    )
    return {
        "campaignName": campaign.name,
        "campaignHref": reverse("n26-campaign", args=[campaign.pk]),
        "heading": "Edit battle" if battle else "Record a battle",
        "editing": bool(battle),
        "action": action,
        "commandHref": command,
        "back": back,
        "csrfToken": csrf_token,
        "values": values,
        "choices": choices,
        "labels": {name: field.label or name for name, field in form.fields.items()},
        "errors": {name: list(messages) for name, messages in form.errors.items()},
        "initialConflict": conflict,
        "current": current,
        "recoveryKey": f"battle:{actor.pk}:{campaign.pk}:{battle.pk if battle else 'new'}",
        "cycles": options(campaign, selected=selected)
        if "cycle" in form.fields
        else None,
        "cycleOptionsHref": reverse("n26-battle-cycle-options", args=[campaign.pk])
        if "cycle" in form.fields
        else "",
        "scenario": scenario,
    }
