"""Plain crew editor data for the initial page and explicit recovery reads."""

import json
from urllib.parse import urlencode
from uuid import uuid4

from django.urls import reverse


def picker_field(field):
    return {
        "name": field.html_name,
        "id": field.id_for_label,
        "value": field.value(),
        "errors": list(field.errors),
        "choices": [
            {"value": str(value), "label": str(label)}
            for value, label in field.field.choices
        ],
    }


def models_for(form):
    return [
        {
            "id": str(entry.miniature.pk),
            "name": entry.miniature.name,
            "profile": str(entry.miniature.membership.profile)
            if entry.miniature.membership
            else "",
            "fullRating": entry.miniature.rating,
            "savedSource": entry.saved_source,
            "search": entry.search,
            "warning": entry.warning,
            "mayOverride": entry.may_override,
            "available": entry.available,
            "role": picker_field(entry.role),
            "card": picker_field(entry.card),
            "override": {
                "name": entry.override.html_name,
                "id": entry.override.id_for_label,
                "value": bool(entry.override.value()),
                "errors": list(entry.override.errors),
            },
        }
        for entry in form.models
    ]


def editor(
    *,
    campaign,
    battle,
    gang,
    actor,
    form,
    crew,
    csrf_token,
    crew_help,
    draw_help,
    conflict=False,
    read_only=False,
    acknowledgement=None,
    roster_refusal=None,
):
    args = [campaign.pk, battle.pk, gang.pk]
    models = models_for(form)
    values = {}
    for name in form.fields:
        value = form[name].value()
        values[name] = (
            form.data.get(name, "")
            if form.is_bound
            else ("on" if value else "")
            if name.startswith("override_")
            else ""
            if value is None
            else str(value)
        )
    if form.is_bound:
        for name in form.data:
            if name.startswith(("role_", "card_", "override_")) and name not in values:
                values[name] = form.data[name]
    roster_changed = form.is_bound and (
        any(
            name.startswith("role_")
            and name not in form.fields
            and form.data[name] != "out"
            for name in form.data
        )
        or any(
            name.startswith("role_") and name not in form.data for name in form.fields
        )
    )
    values["request_key"] = form.data.get("request_key") or str(uuid4())
    values["action"] = form.data.get("action", "save")
    values["submitted_snapshot"] = form.data.get("submitted_snapshot") or json.dumps(
        [
            {
                "id": model["id"],
                "name": model["name"],
                "profile": model["profile"],
                "cards": model["card"]["choices"],
            }
            for model in models
        ]
    )
    return {
        "campaignName": campaign.name,
        "campaignUrl": reverse("n26-campaign", args=[campaign.pk]),
        "battleName": battle.title,
        "battleUrl": reverse("n26-battle", args=[campaign.pk, battle.pk]),
        "gangName": gang.name,
        "revision": crew.revision if crew else None,
        "models": models,
        "values": values,
        "errors": {name: list(errors) for name, errors in form.errors.items()},
        "crewHelp": crew_help,
        "drawHelp": draw_help,
        "action": reverse("n26-battle-crew", args=args),
        "commandHref": reverse("n26-battle-crew-command", args=args),
        "displayHref": reverse("n26-battle-crew-display", args=args),
        "csrfToken": csrf_token,
        "signInHref": reverse("account_login")
        + "?"
        + urlencode({"next": reverse("n26-battle-crew", args=args) + "?recover=1"}),
        "recoveryKey": f"crew:{actor.pk}:{battle.pk}:{gang.pk}",
        "initialConflict": conflict,
        "rosterChanged": roster_changed,
        "rosterRefusal": roster_refusal,
        "readOnly": read_only,
        "current": {
            "revision": crew.revision if crew else 0,
            "selections": [
                {
                    "name": member.miniature_name,
                    "role": member.get_role_display(),
                    "card": member.card_name,
                }
                for member in crew.members.all()
            ]
            if crew
            else [],
        },
        "acknowledgement": acknowledgement,
    }
