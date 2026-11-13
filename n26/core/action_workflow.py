"""Locked action commands shared by native forms and the React workflow."""

import json
from dataclasses import dataclass, field
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse

from n26.core.action_stages import (
    StageInput,
    StageNavigation,
    StagePage,
    action_by_hand,
    action_flow,
    action_start,
)
from n26.core.models import ActionRecord, Gang, Miniature, ModelChoiceReceipt
from n26.core.operations import Refusal, operation
from n26.write_pause import guarded_write

FORMAT = "fighter-action-v1"
BUSINESS_FIELDS = (
    "request_key",
    "revision",
    "outcome",
    "allowance",
    "selection",
    "pickable_id",
    "skill_id",
    "skill_set_id",
    "roll_mode",
    "rolled",
    "previous_roll",
    "review",
    "decline_promotion",
)


@dataclass(frozen=True)
class ActionTarget:
    kind: str
    key: str
    step: str = ""
    allowance: str | None = None
    pick: str | None = None

    @property
    def query(self):
        return {
            name: value
            for name, value in {"allowance": self.allowance, "pick": self.pick}.items()
            if value is not None
        }

    def payload(self):
        return {
            "kind": self.kind,
            "key": self.key,
            "step": self.step,
            "allowance": self.allowance,
            "pick": self.pick,
        }


def target_from(data):
    return ActionTarget(
        data.get("target_kind", ""),
        data.get("target_id", ""),
        data.get("target_step", ""),
        data.get("target_allowance", "")
        if data.get("target_allowance_present") == "1"
        else None,
        data.get("target_pick", "") if data.get("target_pick_present") == "1" else None,
    )


def fighter_for(actor, pk, *, recover=False):
    try:
        fighter = get_object_or_404(
            Miniature.objects.select_related(
                "membership__gang__owner",
                "membership__gang__gang_type",
                "membership__gang__stash",
                "membership__profile__category",
            ),
            pk=pk,
            membership__gang__owner=actor,
        )
    except ValidationError:
        raise Http404("No such model") from None
    if not recover and (fighter.membership.archived or fighter.gang.archived):
        raise Http404("No such model")
    return fighter


def stage(command, fighter, target):
    if target.kind == "start":
        return action_start(command, fighter, target.key)
    if target.kind == "by-hand":
        return action_by_hand(command, fighter, target.key)
    if target.kind == "flow":
        return action_flow(command, fighter, target.key, target.step)
    raise Http404("No such action flow")


def read(actor, pk, target, *, recover=False, gang_id=""):
    try:
        fighter = fighter_for(actor, pk, recover=recover)
    except Http404:
        if not recover or not gang_id:
            raise
        try:
            gang = get_object_or_404(Gang, pk=gang_id, owner=actor)
        except ValidationError:
            raise Http404("No such gang") from None
        if not ModelChoiceReceipt.objects.filter(
            gang=gang, actor=actor, payload__fighter=str(pk)
        ).exists():
            raise Http404("No such model") from None
        from types import SimpleNamespace

        from n26.core.action_forms import EmptyActionForm

        return StagePage(
            {
                "miniature": SimpleNamespace(pk=pk, name="Removed model", gang=gang),
                "gang": gang,
                "action": "Recover action",
                "stage": "unavailable",
                "form": EmptyActionForm(),
                "recovery_only": True,
            }
        )
    if recover and (fighter.membership.archived or fighter.gang.archived):
        from n26.core.action_forms import EmptyActionForm

        return StagePage(
            {
                "miniature": fighter,
                "gang": fighter.gang,
                "action": "Recover action",
                "stage": "unavailable",
                "form": EmptyActionForm(),
                "recovery_only": True,
            }
        )
    try:
        command = StageInput({}, target.query, actor)
        response = stage(command, fighter, target)
        if isinstance(response, StageNavigation):
            response.notices = command.notices
        return response
    except Http404:
        if not recover:
            raise
        from n26.core.action_forms import EmptyActionForm

        return StagePage(
            {
                "miniature": fighter,
                "gang": fighter.gang,
                "action": "Recover action",
                "stage": "unavailable",
                "form": EmptyActionForm(),
                "recovery_only": True,
            }
        )


@dataclass
class ActionResult:
    saved: bool = False
    replayed: bool = False
    terminal: bool = False
    review_url: str = ""
    conflict: bool = False
    code: str = ""
    errors: dict = field(default_factory=dict)
    page: StagePage | None = None
    next_url: str = ""
    facts: dict = field(default_factory=dict)
    notices: list = field(default_factory=list)


class RejectedStage(Exception):
    def __init__(self, page):
        self.page = page


def _request_key(data, target, actor, fighter):
    supplied = data.get("command_key") or data.get("request_key")
    if supplied:
        try:
            return UUID(str(supplied))
        except ValueError:
            raise Refusal("Reload this page before continuing.") from None
    # Old confirmation forms already identify an immutable signed revision.
    # Other old forms cannot distinguish a delayed retry from a new intent.
    if data.get("review") and target.step in {"review", "undo"}:
        exact = {name: data.get(name, "") for name in BUSINESS_FIELDS if name in data}
        return uuid5(
            NAMESPACE_URL,
            json.dumps(
                [FORMAT, str(actor.pk), str(fighter.pk), target.payload(), exact],
                sort_keys=True,
            ),
        )
    raise Refusal("Reload this page before continuing. Nothing changed.")


def _saved_facts(record):
    from n26.core.action_stages import _selection_summary

    skill = getattr(record, "skill_selection", None) if record else None
    return {
        "action": str(record.action) if record else "Action",
        "record": str(record.pk) if record else "",
        "revision": record.revision if record else None,
        "state": record.state if record else "",
        "outcome": str(record.outcome) if record and record.outcome_id else "",
        "selection": _selection_summary(record, "done") if record else "",
        "terms": record.terms if record else {},
        "review": record.review if record else {},
        "rolls": list(record.ledger_events.filter(kind="rolled").values("roll", "dice"))
        if record
        else [],
        "attempts": skill.random_attempts if skill else [],
    }


def _current_review_url(gang, pk, saved):
    if gang.archived:
        return reverse("n26-gangs")
    current_model = Miniature.objects.filter(
        pk=pk, membership__gang=gang, membership__archived=False
    ).exists()
    record = saved.get("facts", {}).get("record")
    if (
        current_model
        and record
        and ActionRecord.objects.filter(pk=record, fighter_id=pk, gang=gang).exists()
    ):
        return saved["next_url"]
    return reverse("n26-gang", args=[gang.pk])


def _terminal(op, key, payload, result):
    result.conflict = True
    result.code = "unavailable"
    result.terminal = True
    result.review_url = (
        reverse("n26-gangs")
        if op.gang.archived
        else reverse("n26-gang", args=[op.gang.pk])
    )
    result.errors = {
        "__all__": [
            "This action is no longer available. The earlier request changed nothing."
        ]
    }
    op.record_model_choice_receipt(
        key,
        payload,
        {
            "format": FORMAT,
            "outcome": "unavailable",
            "errors": result.errors,
            "review_url": result.review_url,
        },
    )


@guarded_write
def change(actor, pk, target, data):
    """Recall saved facts under current ownership, before mutable stage lookup.

    The outer gang lock also serialises terminal refusals with delayed writers.
    A failed operation rolls back before a no-write receipt can be recorded.
    """
    result = ActionResult()
    try:
        fighter = fighter_for(actor, pk, recover=True)
    except Http404:
        # A saved receipt can prove the old model scope after deletion. An
        # unconfirmed body alone cannot establish authority over a missing model.
        try:
            gang = get_object_or_404(Gang, pk=data.get("gang_id"), owner=actor)
            prior = ModelChoiceReceipt.objects.filter(
                gang=gang,
                actor=actor,
                payload__fighter=str(pk),
            ).exists()
        except ValidationError:
            raise Http404("No such model") from None
        if not prior:
            raise Http404("No such model") from None
        fighter = None
    else:
        gang = fighter.gang
    try:
        # The missing-model case is accepted only for recall of an already saved
        # explicit key; no cached identity is invented after target deletion.
        if fighter is None:
            request_key = UUID(str(data.get("command_key") or data.get("request_key")))
        else:
            request_key = _request_key(data, target, actor, fighter)
        raw = {
            name: list(data.getlist(name)) if hasattr(data, "getlist") else [data[name]]
            for name in BUSINESS_FIELDS
            if name in data
        }
        payload = {
            "format": FORMAT,
            "actor": str(actor.pk),
            "fighter": str(pk),
            "target": target.payload(),
            "input": raw,
        }
        with transaction.atomic():
            gang = get_object_or_404(Gang.objects.select_for_update(), pk=gang.pk)
            if gang.owner_id != actor.pk:
                raise Http404("No such model")
            previous = ModelChoiceReceipt.objects.filter(
                gang=gang, request_key=request_key
            ).first()
            if previous:
                if previous.actor_id != actor.pk or previous.payload != payload:
                    result.conflict = True
                    result.code = "key_conflict"
                    result.errors = {
                        "__all__": [
                            "This save belongs to a different action. Review the current flow before continuing."
                        ]
                    }
                    return result
                result.replayed = True
                if previous.result.get("outcome") == "unavailable":
                    result.conflict = True
                    result.code = "unavailable"
                    result.terminal = True
                    result.review_url = (
                        reverse("n26-gangs")
                        if gang.archived
                        else reverse("n26-gang", args=[gang.pk])
                    )
                    result.errors = previous.result["errors"]
                else:
                    result.saved = True
                    result.next_url = previous.result["next_url"]
                    result.facts = previous.result["facts"]
                    result.review_url = _current_review_url(gang, pk, previous.result)
                    result.notices = previous.result.get("notices", [])
                return result
            if fighter is None:
                raise Http404("No such model")
            fighter = fighter_for(actor, pk, recover=True)
            if fighter.gang.pk != gang.pk:
                raise Http404("No such model")
            terminal = gang.archived or fighter.membership.archived
            if target.kind == "flow":
                record = ActionRecord.objects.filter(
                    pk=target.key, fighter=fighter, gang=gang
                ).first()
                terminal = terminal or record is None
            elif target.kind in {"start", "by-hand"}:
                from n26.library.models import Action

                terminal = terminal or not Action.objects.filter(pk=target.key).exists()
            else:
                raise Http404("No such action flow")
            if terminal:
                with operation(gang, actor=actor) as op:
                    _terminal(op, request_key, payload, result)
                return result
            if (
                target.kind == "flow"
                and "revision" in data
                and str(record.revision) != data["revision"]
            ):
                result.conflict = True
                result.code = "revision_conflict"
                result.review_url = reverse(
                    "n26-action-flow", args=[fighter.pk, target.key, "resume"]
                )
                result.errors = {
                    "__all__": [
                        "This flow changed in another tab. Review the current flow before continuing."
                    ]
                }
                return result
            with operation(gang, actor=actor) as op:
                command = StageInput(data, target.query, actor, submitted=True, op=op)
                response = stage(command, fighter, target)
                if isinstance(response, StagePage):
                    raise RejectedStage(response)
                assert isinstance(response, StageNavigation)
                record = (
                    ActionRecord.objects.filter(pk=target.key, fighter=fighter).first()
                    if target.kind == "flow"
                    else ActionRecord.objects.filter(
                        fighter=fighter,
                        action_id=target.key,
                        request_key=data.get("request_key"),
                    ).first()
                )
                if record is None and target.kind == "start":
                    from n26.core.action_records import active_action_record
                    from n26.library.models import Action

                    record = active_action_record(
                        fighter, Action.objects.get(pk=target.key)
                    )
                facts = _saved_facts(record)
                stored = {
                    "format": FORMAT,
                    "next_url": response.href,
                    "facts": facts,
                    "notices": command.notices,
                }
                op.record_model_choice_receipt(request_key, payload, stored)
            # Settlement can still refuse. Publish success only after it exits.
            result.saved = True
            result.next_url = response.href
            result.facts = facts
            result.notices = command.notices
    except RejectedStage as rejection:
        result.page = rejection.page
        form = result.page.context.get("form")
        result.errors = dict(form.errors) if form is not None else {}
        if not result.errors:
            result.errors = {
                "__all__": [
                    "This action is no longer available. Review the current flow before continuing."
                ]
            }
    except Refusal as refusal:
        return ActionResult(errors={"__all__": [str(refusal)]})
    except ValidationError, ValueError:
        return ActionResult(
            errors={
                "__all__": [
                    "This form is not recognised. Reload this page and try again."
                ]
            }
        )
    return result
