"""Explicit JSON facts for equipment catalogues and owned-item panels."""

from dataclasses import asdict

from n26.core.listing import OwnedRow
from n26.core.owned import thing_key


def choices_data(groups, *, taken=None):
    return [
        {
            "choose": group.choose,
            "options": [
                {
                    "key": option.option_key,
                    "name": option.name,
                    "surcharge": option.surcharge,
                    "setKey": str(option.default_set.pk) if option.default_set else "",
                    "price": option.default_set.price if option.default_set else 0,
                    "checked": option.is_default
                    if taken is None
                    else (
                        option.default_set is not None
                        and option.default_set.pk in taken
                    ),
                }
                for option in group.options
            ],
        }
        for group in groups
    ]


def notes_data(notes):
    return [{"text": note.text, "level": note.level} for note in notes]


def listing_data(row, line):
    return {
        "key": row.key,
        "name": row.marked_name,
        "price": row.price,
        "tradePoints": row.trade_points,
        "exclusive": row.is_exclusive,
        "notes": notes_data(row.notes),
        "choices": choices_data(line.choices),
        "parts": [
            {
                "key": thing_key(part.thing),
                "name": option.name,
                "price": option.price,
                "tradePoints": option.trade_points,
                "exclusive": option.is_exclusive,
                "notes": notes_data(option.notes),
            }
            for option, part in zip(row.options, line.parts, strict=True)
        ],
    }


def catalogue_data(catalogue, view):
    if catalogue is None:
        return []
    lines = {thing_key(line.thing): line for line in view.all_lines()} if view else {}

    def entry(row):
        owned = isinstance(row, OwnedRow)
        listing = row.buy if owned else row
        return {
            "key": row.key,
            "name": row.marked_name,
            "basePrice": listing.price if listing is not None else 0,
            "tradePoints": listing.trade_points if listing is not None else None,
            "exclusive": listing.is_exclusive if listing is not None else False,
            "purchase": listing_data(listing, lines[row.key])
            if listing is not None
            else None,
            "count": row.count if owned else 0,
            "expanded": row.expanded if owned else False,
            "copies": [
                {
                    "id": copy.id,
                    "name": copy.marked_name,
                    "rating": copy.rating,
                    "chosen": list(copy.chosen),
                    "actions": [
                        asdict(action) for action in (copy.sell, *copy.more) if action
                    ],
                    "accessorise": asdict(copy.accessorise)
                    if copy.accessorise
                    else None,
                    "parts": [
                        {
                            "id": part.id,
                            "name": part.name,
                            "rating": part.rating,
                            "actions": [
                                asdict(action)
                                for action in (part.sell, *part.more)
                                if action
                            ],
                        }
                        for part in copy.parts
                    ],
                }
                for copy in row.copies
            ]
            if owned
            else [],
        }

    return [
        {
            "name": section.name,
            "categories": [
                {
                    "name": category.name,
                    "entries": [entry(row) for row in category.rows],
                }
                for category in section.categories
            ],
        }
        for section in catalogue.sections
    ]


def dialog_data(dialog, assignment_key, *, choices=None):
    if dialog is None:
        return None
    result = {
        name: value
        for name, value in dialog.items()
        if name not in {"models", "choices", "price_preview"}
    }
    result.setdefault("remove_note", "")
    result["assignment"] = assignment_key
    result["models"] = [
        {"key": str(model.pk), "name": model.name} for model in dialog.get("models", [])
    ]
    result["choices"] = choices or []
    # The preview is the existing JSON-safe contract for option replacement pricing.
    result["pricePreview"] = dialog.get("price_preview")
    return result


def confirmation_data(question):
    return asdict(question)


def owned_description(dialog):
    """Shared consequences for native and React equipment confirmations."""
    kind = dialog["kind"]
    if kind == "accessorise":
        return (
            "Choose an accessory for this weapon. Its effects apply only to this weapon."
            if dialog.get("accessories")
            else "Nothing in the library fits this weapon."
        )
    if kind == "sell":
        return f"{dialog['sum']} The equipment and any accessories sold with it are removed from the gang."
    if kind == "rechoose":
        return "You will be charged or refunded the difference."
    if kind == "reassign":
        return "Moving this equipment does not change its rating."
    if kind == "fit":
        return (
            "Fitting this accessory does not change its rating. Its effects apply only to the selected weapon."
            if dialog.get("weapons")
            else "There is no weapon here to fit it to."
        )
    if kind == "detach":
        return (
            "It stays in the stash. Its rating does not change."
            if dialog.get("stash_host", False)
            else "The model keeps it. Its rating does not change."
        )
    if kind == "refund":
        return f"{dialog['sum']} The equipment and anything attached to it are removed from the gang. This undoes the purchase."
    return f"The equipment and anything attached to it are permanently removed from the gang. {dialog['remove_note']}"


def fighter_data(request, screen, context):
    """Prepare the model card, personal balance and action-flow navigation."""
    from django.contrib.humanize.templatetags.humanize import naturaltime
    from django.urls import reverse

    from n26.core.model_card_display import model_card_props
    from n26.core.navigation import fighter_switcher, model_screen_tabs, switcher_props

    miniature = screen.miniature
    switcher = fighter_switcher(screen.gang, miniature, route="n26-equip")
    budget = screen.budget
    return {
        "name": miniature.name,
        "role": miniature.membership.profile.category.name
        if miniature.membership.profile and miniature.membership.profile.category
        else "",
        "card": model_card_props(
            context["card"],
            rename_href=reverse("n26-edit-fighter", args=[miniature.pk])
            + f"?rename={miniature.pk}",
            status_href=context["status_href"],
        ),
        "tabs": model_screen_tabs(miniature, "equip"),
        "switcher": switcher_props(switcher, hotkey="r"),
        "budget": {
            "activity": str(budget.activity.pk),
            "title": budget.title,
            "actionLabel": budget.action_label,
            "facts": [asdict(fact) for fact in budget.facts],
        }
        if budget
        else None,
        "visitLeft": screen.gang.trade_points_left
        if budget and screen.gang.visiting_trading_post
        else None,
        "panels": [
            {
                "key": panel.action_id,
                "name": panel.name,
                "timing": panel.timing[:1].upper() + panel.timing[1:],
                "flagged": panel.flagged,
                "menu": [
                    {
                        "label": item["label"],
                        "href": item["href"],
                        "tone": item.get("tone", "default"),
                        "separatorBefore": bool(item.get("separator_before")),
                    }
                    for item in panel.menu
                    if item.get("href")
                ],
                "startHref": panel.start_href,
                "prices": [asdict(price) for price in panel.prices],
                "availableUses": panel.available_uses,
                "thresholds": list(panel.earned_thresholds),
                "problem": panel.problem,
                "drafts": [
                    {
                        "key": draft.key,
                        "href": draft.href,
                        "label": draft.label,
                        "variant": draft.variant,
                        "problem": draft.problem,
                        "threshold": draft.earned_threshold,
                        "when": draft.when.isoformat() if draft.when else "",
                        "whenLabel": naturaltime(draft.when) if draft.when else "",
                    }
                    for draft in panel.drafts
                ],
            }
            for panel in context["action_panels"]
        ],
    }
