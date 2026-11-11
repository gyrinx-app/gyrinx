"""Shared keyed draft commands for the HTML and React post-battle editors."""

import json
from dataclasses import dataclass, field
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core.exceptions import ValidationError

from n26.core.models.post_battle import (
    PostBattleCommandReceipt,
    PostBattleReport,
    PostBattleRevision,
)
from n26.core.operations import Refusal
from n26.core.post_battle import (
    _locked,
    _require_editor,
    apply_report,
    normalise,
    preview_report,
    save_draft,
    xp_eligible_models,
)
from n26.core.post_battle_forms import (
    ReportVersionForm,
    change_draft,
    keep_recorded_xp,
    posted_payload,
)


@dataclass
class ReportCommand:
    report: PostBattleReport
    payload: dict
    errors: list[str] = field(default_factory=list)
    status: int = 200
    acknowledged: dict | None = None
    sequence: int | None = None
    replayed: bool = False
    newer: bool = False
    conflict: bool = False


def command(report, actor, data):
    """Recall the exact command before consulting mutable report or catalogue facts."""
    payload = posted_payload(data)
    result = ReportCommand(report, payload)
    version = ReportVersionForm(data)
    if not version.is_valid():
        result.status = 422
        result.errors = [
            "This form's version is missing or invalid. Reload the saved draft before continuing."
        ]
        return result
    values = version.cleaned_data
    intent = data.get("intent", "save")
    inputs = {
        "generation": str(values["generation"]),
        "revision": values["revision"],
        "submission_key": str(values["submission_key"]),
        "review": values["review"],
        "intent": intent,
        "payload": payload,
    }
    # Cached native forms have no command key. Their immutable request identifies
    # a retry; every later draft revision identifies a new intentional save.
    raw_key = data.get("command_key")
    try:
        key = (
            UUID(raw_key)
            if raw_key
            else uuid5(
                NAMESPACE_URL,
                json.dumps([str(report.pk), actor.pk, inputs], sort_keys=True),
            )
        )
    except ValueError, AttributeError:
        result.status = 422
        result.errors = [
            "This save's reference is invalid. Reload the saved draft before continuing."
        ]
        return result
    try:
        with _locked(report.gang, report.battle, report) as (_, _, locked):
            _require_editor(locked, actor)
            result.report = locked
            prior = PostBattleCommandReceipt.objects.filter(request_key=key).first()
            if prior is not None:
                if (
                    prior.report_id != locked.pk
                    or prior.actor_id != actor.pk
                    or prior.inputs != inputs
                ):
                    result.status = 409
                    result.errors = [
                        "This save reference belongs to a different change. Retry the original save before continuing."
                    ]
                    return result
                saved = prior.result
                result.acknowledged = saved
                result.payload = saved["payload"]
                result.sequence = saved.get("sequence")
                result.replayed = True
                result.newer = (
                    str(locked.generation) != saved["generation"]
                    or locked.draft_revision != saved["revision"]
                )
                return result
            if intent == "apply":
                earlier = PostBattleRevision.objects.filter(
                    submission_key=values["submission_key"]
                ).first()
                if earlier is not None:
                    # Legacy revisions stored cleaned gameplay inputs, not the raw
                    # command. Preserve their keyed receipt contract without
                    # recomputing results against today's mutable catalogue.
                    if earlier.report_id != locked.pk or earlier.actor_id != actor.pk:
                        result.status = 409
                        result.errors = [
                            "This submission reference belongs to different results. Retry the original submission before continuing."
                        ]
                        return result
                    result.sequence = earlier.sequence
                    result.replayed = True
                    result.acknowledged = {
                        "generation": str(locked.generation),
                        "revision": locked.draft_revision,
                        "payload": normalise(earlier.inputs),
                        "sequence": earlier.sequence,
                    }
                    result.payload = result.acknowledged["payload"]
                    return result
            payload = change_draft(
                payload,
                intent,
                xp_eligible=xp_eligible_models(locked, actor=actor, payload=payload)
                if intent.startswith("xp-step:")
                else frozenset(),
            )
            if intent == "autosave":
                plan = preview_report(locked, actor=actor, payload=payload)
                payload, _ = keep_recorded_xp(payload, plan)
            result.payload = payload
            locked = save_draft(
                locked,
                actor=actor,
                generation=values["generation"],
                revision=values["revision"],
                payload=payload,
            )
            sequence = None
            if intent == "apply":
                applied = apply_report(
                    locked,
                    actor=actor,
                    generation=locked.generation,
                    revision=locked.draft_revision,
                    submission_key=values["submission_key"],
                    review=values["review"],
                )
                sequence = applied.sequence
            saved = {
                "generation": str(locked.generation),
                "revision": locked.draft_revision,
                "payload": payload,
                "sequence": sequence,
            }
            PostBattleCommandReceipt.objects.create(
                report=locked, actor=actor, request_key=key, inputs=inputs, result=saved
            )
            result.report = locked
            result.payload = payload
            result.sequence = sequence
            result.acknowledged = saved
    except (Refusal, ValidationError) as exc:
        result.report.refresh_from_db()
        result.errors = (
            exc.messages if isinstance(exc, ValidationError) else [exc.public_message]
        )
        result.status = 409
        result.conflict = (
            str(result.report.generation) != str(values["generation"])
            or result.report.draft_revision != values["revision"]
            or result.report.state != PostBattleReport.State.DRAFT
        )
    return result


def prepared(report, actor, payload):
    """Keep blocked XP awards consistent on initial display and command refreshes."""
    payload = normalise(payload)
    plan = preview_report(report, actor=actor, payload=payload)
    payload, changed = keep_recorded_xp(payload, plan)
    if changed:
        plan = preview_report(report, actor=actor, payload=payload)
    return payload, plan
