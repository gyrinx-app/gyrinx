"""JSON-safe display facts for the model card shown before a hire.

The card builder remains authoritative. This projection follows the existing
Cotton preview, including informative choice prompts, without exposing records
or owner-only actions. Stored-card editors need their own command contracts.
"""

from n26.core.render import ModelCard
from n26.core.rows import PartKind, visible_parts


def _stat(cell):
    explanation = ""
    if cell.modified:
        explanation = f"{cell.short_name} changed by {cell.changed_by}"
        if cell.held_note:
            explanation += f". {cell.held_note}"
    return {
        "shortName": cell.short_name,
        "fullName": cell.full_name,
        "value": cell.value,
        "highlighted": cell.highlighted,
        "firstOfGroup": cell.first_of_group,
        "explanation": explanation,
    }


def _item_choices(line):
    return [
        {
            "label": row.label,
            "values": [part.value.chosen or "—" for part in row.parts],
        }
        for row in line.other_choice_rows
    ]


def _line(line):
    return {
        "text": (
            line.name
            + line.slot_mark
            + line.tier_mark
            + line.brought_mark
            + line.count_mark
        ),
        "explanation": (
            line.provenance.description if line.provenance.annotated else ""
        ),
        "choices": _item_choices(line),
    }


def _part(part):
    match part.kind:
        case PartKind.NAMES | PartKind.GEAR:
            return {"kind": part.kind.value, "lines": [_line(x) for x in part.value]}
        case PartKind.COUNTER:
            return {"kind": "counter", "value": part.value.value}
        case PartKind.CHOICE:
            choice = part.value
            if part.named_prompt:
                prompt = f"Choose {choice.kind_label.lower()}"
            elif choice.is_full:
                prompt = ""
            elif choice.takes_several:
                prompt = "Add"
            elif not choice.is_resolved:
                prompt = "Choose"
            else:
                prompt = ""
            return {
                "kind": "choice",
                "chosen": None if part.named_prompt else choice.chosen,
                "prompt": prompt,
            }
    raise ValueError(f"Unsupported model preview part: {part.kind!r}")


def model_preview_props(card: ModelCard):
    """Project an already built hire card without reads, writes or HTML."""
    if card.id:
        raise ValueError("Model previews require an unstored card.")
    groups = card.statline.groups()
    return {
        "name": card.name,
        "rating": card.rating,
        "profileName": card.profile_name if card.profile_name != card.name else "",
        "ownerLine": card.owner_line,
        "typeLine": card.type_line,
        "xp": card.xp,
        "xpTarget": card.xp_target if card.xp_target is not None else "–",
        "statGroups": [[_stat(cell) for cell in group] for group in groups],
        "typeSpan": max(1, len(groups[0]) - len(groups[-1]) - 1) if groups else 1,
        "details": [
            {"label": row.label, "parts": [_part(x) for x in visible_parts(row.parts)]}
            for row in card.detail_rows
        ],
        "weaponColumns": [_stat(cell) for cell in card.weapon_columns],
        "weapons": [
            {
                "name": (
                    weapon.name
                    + weapon.slot_mark
                    + weapon.tier_mark
                    + weapon.brought_mark
                ),
                "stats": [_stat(cell) for cell in weapon.own_stats],
                "traits": [_line(x) for x in weapon.own_line.traits]
                if weapon.own_line
                else [],
                "profiles": [
                    {
                        "name": profile.name + profile.brought_mark,
                        "stats": [_stat(cell) for cell in profile.statline.cells],
                        "traits": [_line(x) for x in profile.traits],
                    }
                    for profile in weapon.named_profiles
                ],
                "accessories": [_line(x) for x in weapon.accessories],
                "choices": _item_choices(weapon),
            }
            for weapon in card.weapons
        ],
    }
