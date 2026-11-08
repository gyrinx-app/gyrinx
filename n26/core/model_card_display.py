"""Query-free display data and controls for a linked, stored model card."""

from dataclasses import asdict

from n26.core.model_preview import model_card_facts
from n26.core.rows import PartKind, visible_parts


def choice_control(choice):
    return {
        "key": choice.key,
        "label": choice.kind_label,
        "href": choice.href,
        "dismissHref": choice.dismiss_href,
        "restoreHref": choice.restore_href,
        "back": choice.back,
        "resolved": choice.is_resolved,
        "full": choice.is_full,
        "several": choice.takes_several,
        "followsStatus": choice.follows_status,
    }


def item_controls(source, projected):
    projected["key"] = source.id or source.name
    projected["actions"] = owned_actions(source)
    projected["tiers"] = [
        choice_control(choice) for choice in source.choices if choice.is_tier_ladder
    ]
    for original, data in zip(
        source.other_choice_rows, projected["choices"], strict=True
    ):
        data["controls"] = [choice_control(part.value) for part in original.parts]


def owned_actions(source):
    """Match owned-actions' sale, ordinary actions and separated danger actions."""
    actions = [asdict(source.sell) | {"tone": "default"}] if source.sell else []
    actions.extend(asdict(action) for action in source.more if action.tone != "danger")
    for action in source.more:
        if action.tone == "danger":
            actions.append(
                asdict(action)
                | {"separatorBefore": bool(source.sell or len(source.more) > 1)}
            )
    return actions


def model_card_props(card, *, rename_href, status_href):
    """Project linked card structures without resolving permissions or loading records."""
    data = model_card_facts(card)
    data["stored"] = {
        "id": card.id,
        "renameHref": rename_href,
        "status": card.status,
        "statusLabel": card.status_label,
        "statusColour": card.status_colour,
        "statusHref": status_href,
        "imageHref": card.image_url,
        "modelCardsHref": card.model_cards_href,
        "rankTitles": [
            rank.current_title
            for rank in card.rank_summaries
            if rank.value is not None and rank.current_title
        ],
        "foundingBudget": card.founding_budget,
        "tradePointsLeft": card.trade_points_left,
        "personalAction": card.personal_tp_action,
        "ratingOverride": card.rating_override,
    }
    for original, row in zip(card.detail_rows, data["details"], strict=True):
        row["key"] = original.label + (
            ":" + original.separation.key if original.separation else ""
        )
        row["editHref"] = original.edit_href
        for source, projected in zip(
            visible_parts(original.parts), row["parts"], strict=True
        ):
            if source.kind == PartKind.COUNTER:
                counter = source.value
                projected["key"] = counter.assignment_id or counter.name
                projected["control"] = {
                    "name": counter.name,
                    "href": counter.href,
                    "back": counter.back,
                    "tallied": counter.tallied,
                    "assignment": counter.assignment_id,
                }
            elif source.kind == PartKind.CHOICE:
                projected["key"] = source.value.key
                projected["control"] = choice_control(source.value)
                if source.value.follows_status and projected["prompt"] == "Choose":
                    projected["prompt"] = "Resolve"
            elif source.kind == PartKind.GEAR:
                for line, projected_line in zip(
                    source.value, projected["lines"], strict=True
                ):
                    item_controls(line, projected_line)
    for original, weapon in zip(card.weapons, data["weapons"], strict=True):
        item_controls(original, weapon)
        weapon["accessorise"] = (
            asdict(original.accessorise) if original.accessorise else None
        )
        for source, profile in zip(
            original.named_profiles, weapon["profiles"], strict=True
        ):
            profile["key"] = source.id or source.name
            profile["actions"] = owned_actions(source)
        for source, accessory in zip(
            original.accessories, weapon["accessories"], strict=True
        ):
            item_controls(source, accessory)
    return data
