"""Validate and retain model option changes independently of their HTTP adapter."""

from dataclasses import dataclass, field
from uuid import uuid4

from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, prefetch_related_objects

from n26.core.hire import build_hire_entry
from n26.core.hire_workflow import (
    SelectionField,
    UnavailableHire,
    chosen_sets,
    resolve_picks,
    resolve_sets,
)
from n26.core.operations import Refusal, operation

SALT = "n26.model-options"


class OptionsForm(forms.Form):
    gang = forms.CharField(
        widget=forms.HiddenInput,
        error_messages={"required": "Reload this page before saving these options."},
    )
    selection = SelectionField(required=False, widget=forms.HiddenInput)
    snapshot = forms.CharField(
        widget=forms.HiddenInput,
        error_messages={"required": "Reload this page before saving these options."},
    )
    request_key = forms.UUIDField(
        widget=forms.HiddenInput,
        error_messages={
            "required": "Reload this page before saving these options.",
            "invalid": "Reload this page before saving these options.",
        },
    )


def option_groups(entry, taken):
    """Retain explicit stable choices, including the head of an unchosen one-of group."""
    groups = []
    for index, group in enumerate(entry.groups):
        selected = [
            option
            for option in group.options
            if option.default_set is not None and str(option.default_set.pk) in taken
        ]
        if not selected and group.choose == "one":
            selected = [option for option in group.options if option.is_default]
        groups.append(
            {
                "key": str(index),
                "choose": group.choose,
                "visible": group.offers_a_choice,
                "options": [
                    {
                        "key": option.option_key,
                        "name": option.name,
                        "price": option.price,
                        "checked": option in selected,
                    }
                    for option in group.options
                    if option.default_set is not None
                ],
            }
        )
    return groups


def profile_groups(profile, taken):
    """Prepare the option controls without building an unused preview per choice."""
    grouped = profile.grouped_offers()
    if not grouped or grouped[0][0] is not None:
        grouped = [(None, []), *grouped]
    fixed = {
        offered[0].default_set_id
        for group, offered in grouped
        if len(offered) == 1 and (group is None or group.choose == "one")
    }
    result = []
    for index, (group, offered) in enumerate(grouped):
        choose = group.choose if group else "one"
        selected = {
            option.default_set_id
            for option in offered
            if str(option.default_set_id) in taken
        }
        # A fixed default cannot identify the explicit pick when an alternative is held.
        if choose in {"one", "one-or-none"} and len(selected) > 1:
            selected -= fixed
        known = bool(selected)
        result.append(
            {
                "key": str(index),
                "choose": choose,
                "visible": len(offered) > 1 or choose != "one",
                "options": [
                    {
                        "key": str(option.pk),
                        "name": option.name,
                        "price": option.default_set.price,
                        "checked": option.default_set_id in selected
                        or (not known and choose == "one" and position == 0),
                    }
                    for position, option in enumerate(offered)
                ],
            }
        )
    return result


def baseline(miniature):
    carrier = miniature.membership
    from n26.library.models import Option

    prefetch_related_objects(
        [carrier.profile],
        Prefetch(
            "options", queryset=Option.objects.select_related("default_set", "group")
        ),
    )
    options = list(carrier.profile.options.all())
    chosen = list(carrier.chosen_options.select_related("default_set"))
    entry = getattr(carrier, "ledger_entry", None)
    return {
        "model": str(miniature.pk),
        "membership": str(carrier.pk),
        "profile": str(carrier.profile_id),
        "taken": sorted(str(row.default_set_id) for row in chosen),
        "recorded": sorted(
            [[str(row.default_set_id), row.default_set.price] for row in chosen]
        ),
        "payment": entry.paid if entry else None,
        "rating": entry.rating_contribution if entry else None,
        "order": [
            [str(group.pk) if group else "", [str(option.pk) for option in offered]]
            for group, offered in carrier.profile.grouped_offers()
        ],
        "offers": sorted(
            [
                [
                    str(option.pk),
                    str(option.default_set_id),
                    option.default_set.price,
                    str(option.group_id or ""),
                    option.group.choose if option.group else "one",
                ]
                for option in options
            ]
        ),
    }


def initial(miniature, actor):
    state = baseline(miniature)
    groups = profile_groups(miniature.membership.profile, set(state["taken"]))
    return OptionsForm(
        initial={
            "gang": str(miniature.gang.pk),
            "selection": [
                option["key"]
                for group in groups
                if group["visible"]
                for option in group["options"]
                if option["checked"]
            ],
            "snapshot": signing.dumps({"actor": actor.pk, **state}, salt=SALT),
            "request_key": str(uuid4()),
        }
    ), groups


@dataclass
class OptionsResult:
    form: OptionsForm
    saved: bool = False
    replayed: bool = False
    changed: bool = False
    conflict: bool = False
    message: str = ""
    delta: int = 0
    model_name: str = ""
    current: dict | None = None
    facts: dict = field(default_factory=dict)
    subject: object | None = None


def change(gang, actor, model_key, data):
    from n26.core.models import Miniature, ModelChoiceReceipt

    form = OptionsForm(data)
    result = OptionsResult(form)
    if not form.is_valid():
        return result
    if form.cleaned_data["gang"] != str(gang.pk):
        form.add_error(None, "This form belongs to another gang. Reload the page.")
        return result
    payload = {
        "action": "options",
        "model": str(model_key),
        "snapshot": form.cleaned_data["snapshot"],
        "selection": sorted(form.cleaned_data["selection"] or [])
        if "selection" in data
        else None,
        "indexed": {key: data.getlist(key) for key in sorted(data) if ":" in key}
        if "selection" not in data
        else {},
    }
    try:
        with operation(gang, actor=actor) as op:
            gang.refresh_from_db()
            gang.forget_open_activities()
            if not actor.is_authenticated or gang.owner_id != actor.pk or gang.archived:
                raise Refusal("You can no longer change this gang's model options.")
            previous = ModelChoiceReceipt.objects.filter(
                gang=gang, request_key=form.cleaned_data["request_key"]
            ).first()
            if previous is not None:
                if previous.actor_id != actor.pk or previous.payload != payload:
                    raise Refusal(
                        "This form was already used for another selection. Reload the page."
                    )
                result.saved = True
                result.replayed = True
                result.message = previous.result["message"]
                result.delta = previous.result["delta"]
                result.model_name = previous.result["model_name"]
                return result
            try:
                miniature = Miniature.objects.select_related(
                    "membership__profile", "membership__ledger_entry"
                ).get(
                    pk=model_key,
                    membership__gang=gang,
                    membership__archived=False,
                )
            except Miniature.DoesNotExist, ValidationError:
                raise Refusal("This model is no longer in the gang.") from None
            try:
                snapshot = signing.loads(form.cleaned_data["snapshot"], salt=SALT)
            except signing.BadSignature:
                raise Refusal(
                    "This form could not be verified. Reload the page."
                ) from None
            current = baseline(miniature)
            if (
                not isinstance(snapshot, dict)
                or snapshot.get("actor") != actor.pk
                or snapshot.get("model") != str(miniature.pk)
                or snapshot.get("membership") != str(miniature.membership_id)
                or set(snapshot) != {"actor", *current}
            ):
                raise Refusal(
                    "This form belongs to another model or account. Reload the page."
                )
            profile = miniature.membership.profile

            def conflict():
                result.conflict = True
                current_groups = profile_groups(profile, set(current["taken"]))
                result.current = {
                    "name": miniature.name,
                    "options": [
                        option["name"]
                        for group in current_groups
                        if group["visible"]
                        for option in group["options"]
                        if option["checked"]
                    ],
                }
                form.add_error(
                    None,
                    "These options or their prices changed while you were editing. Review the current options before saving.",
                )
                return result

            try:
                if payload["selection"] is not None:
                    selected = resolve_sets(profile, payload["selection"])
                else:
                    selected = chosen_sets(
                        resolve_picks(
                            data, profile, build_hire_entry(profile, with_cards=False)
                        )
                    )
                desired = profile.resolve_selection(selected)
            except UnavailableHire, ValueError:
                previously_offered = {option[0] for option in snapshot["offers"]}
                if (
                    payload["selection"] is not None
                    and set(payload["selection"]) <= previously_offered
                    and snapshot["offers"] != current["offers"]
                ):
                    return conflict()
                form.add_error(
                    "selection", "Choose from the options currently offered."
                )
                return result
            same = sorted(str(option.pk) for option in desired) == current["taken"]
            compared = {"actor": actor.pk, **current}
            indexed_reordered = (
                payload["selection"] is None and snapshot["order"] != current["order"]
            )
            if payload["selection"] is not None:
                snapshot = {
                    key: value for key, value in snapshot.items() if key != "order"
                }
                compared = {
                    key: value for key, value in compared.items() if key != "order"
                }
            if indexed_reordered or (not same and snapshot != compared):
                return conflict()
            before = current["payment"] or 0
            op.rechoose(miniature.membership, option=selected)
            entry = getattr(miniature.membership, "ledger_entry", None)
            if entry:
                entry.refresh_from_db()
            after = entry.paid if entry else 0
            result.delta = after - before
            result.changed = not same
            result.model_name = miniature.name
            result.subject = miniature
            result.message = (
                f"Options saved. {result.delta}¢ charged."
                if result.delta > 0
                else f"Options saved. {-result.delta}¢ returned."
                if result.delta < 0
                else "Options saved."
            )
            result.facts = {"options": True, "delta": result.delta}
            op.record_model_choice_receipt(
                form.cleaned_data["request_key"],
                payload,
                {
                    "message": result.message,
                    "delta": result.delta,
                    "model_name": result.model_name,
                },
            )
        result.saved = True
    except Refusal as error:
        gang.refresh_from_db()
        gang.forget_open_activities()
        form.add_error(None, error.public_message)
    return result
