"""A very basic text renderer.

Exists so a human (or a test) can look at what the render structures hold.
Layout is deliberately crude — this is a debugging tool, not a design.
"""

from n26.core.render import build_ledger, render_gang
from n26.core.rows import PartKind, choice_rows, part_text, row_text


def render_statline(statline, indent="  "):
    """Each visual group on its own pair of lines: headings, then values."""
    lines = []
    for group in statline.groups():
        headings = "  ".join(
            f"*{cell.short_name:<3}" if cell.highlighted else f"{cell.short_name:<4}"
            for cell in group
        )
        values = "  ".join(
            f"{cell.value + ('†' if cell.modified else ''):<4}" for cell in group
        )
        lines.append(indent + headings.rstrip())
        lines.append(indent + values.rstrip())
    return lines


def render_model_card(card, indent=""):
    # The same sentence the screen and the print card say — "Owned by
    # Yolanda", or "In the stash" for a pet whose collar sits there.
    owner = f"  ({card.owner_line})" if card.owner_line else ""
    lines = [
        f"{indent}{card.name} — {card.rating}cr{owner}",
        *(
            [f"{indent}{card.profile_name}"]
            if card.profile_name and card.profile_name != card.name
            else []
        ),
        f"{indent}{card.type_line}",
        *render_statline(card.statline, indent=indent + "  "),
        f"{indent}  XP: {card.xp_display}",
    ]
    if card.weapons:
        lines.append(f"{indent}  Weapons:")
        for weapon in card.weapons:
            # Costs on a card are rating contributions, so a zero means
            # "added nothing here" — never "this was free". Kit that came
            # with the hire reads zero while being worth plenty, so the
            # number is simply left off rather than claimed.
            label = weapon.name + weapon.slot_mark + weapon.brought_mark
            if weapon.total_rating:
                total = f"{weapon.total_rating}cr"
                if weapon.extras_rating:
                    total += (
                        f" (base {weapon.base_rating} + extras {weapon.extras_rating})"
                    )
                label += f" — {total}"
            # One rule decides the shape: an unnamed profile *is* the
            # weapon, so its stats ride the weapon's own row; every
            # named one gets a row beneath. That produces all four
            # printed shapes — a plain gun, a gun of named modes, and
            # either of those with paid ammo bought onto it — without
            # the renderer knowing anything about what was paid for.
            #
            # The rule lives on WeaponLine because the screen and print
            # cards need the same one, and a template cannot express it.
            if weapon.own_line is not None:
                label += _profile_suffix(weapon.own_line)
            lines.append(f"{indent}    {label}")
            for accessory in weapon.accessories:
                lines.append(
                    f"{indent}      + {accessory.name}{accessory.brought_mark}"
                )
            for profile in weapon.named_profiles:
                lines.append(
                    f"{indent}      - {profile.name}{profile.brought_mark}"
                    f"{_profile_suffix(profile)}"
                )
            for row in choice_rows(weapon.choices, owner=("weapon", weapon.id)):
                lines.append(
                    f"{indent}      {row.label}: {row_text(row, prompts=True)}"
                )
    for row in card.detail_rows:
        if text := row_text(row, prompts=True):
            lines.append(f"{indent}  {row.label}: {text}")
    lines.extend(_item_choice_lines(card.equipment, indent))
    for group in card.gear_groups:
        lines.extend(_item_choice_lines(group.lines, indent))
    if card.collections:
        names = ", ".join(line.name for line in card.collections)
        lines.append(f"{indent}  Buys from: {names}")
    for effect in card.effects:
        tense = "" if effect.happened else " (when taken)"
        lines.append(f"{indent}  {_sentence(effect.description)}{tense}")
    for remark in card.remarks:
        lines.append(f"{indent}  ({remark.text})")
    return lines


def _item_choice_lines(items, indent):
    """Write a carried item's questions with the item that carries them."""
    return [
        f"{indent}    {item.name} — {row.label}: {row_text(row)}"
        for item in items
        for row in choice_rows(item.choices, owner=("item", item.id))
    ]


def _profile_suffix(profile):
    """What a profile says after its label: what buying it added,
    then its stats and traits."""
    added = f" (+{profile.rating}cr)" if profile.rating else ""
    stats = "  ".join(
        f"{cell.short_name} {cell.value}" for cell in profile.statline.cells
    )
    shown = [
        f"{trait.name}†" if trait.provenance.computed else trait.name
        for trait in profile.traits
    ]
    parts = [part for part in (stats, ", ".join(shown)) if part]
    return added + (("   " + "   ".join(parts)) if parts else "")


def _sentence(text):
    """Capitalise the first letter only — ``capitalize`` lowercases names."""
    return text[:1].upper() + text[1:]


def render_gang_sheet(sheet):
    lines = [
        f"{sheet.name} ({sheet.gang_type})",
        f"Rating {sheet.rating}  Credits {sheet.credits}  Wealth {sheet.wealth}",
    ]
    if sheet.rows:
        names = ", ".join(line.name for line in sheet.rows)
        lines.append(f"Gang: {names}")
    for row in sheet.detail_rows:
        if text := row_text(row, prompts=True, skip_xp=False):
            lines.append(f"{row.label}: {text}")
    if sheet.campaign:
        campaign = sheet.campaign
        lines.append(f"Campaign: {campaign.name}")
        for row in [*campaign.detail_rows, *campaign.owned_choice_rows]:
            if row.has_asset_groups and any(
                part.kind == PartKind.ASSET_GROUP and part.value.names
                for part in row.parts
            ):
                lines.append(f"  {row.label}:")
                for part in row.parts:
                    if part.kind == PartKind.ASSET_GROUP and part.value.names:
                        lines.extend(f"    - {name.text}" for name in part.value.names)
                    else:
                        lines.append(f"    - {part_text(part)}")
            else:
                lines.append(f"  {row.label}: {row_text(row, skip_xp=False)}")
    if sheet.stash:
        lines.append(f"Stash — {sheet.stash_rating}cr")
        for line in sheet.stash:
            # The rating is one item's, however many the line stands for.
            rating = f" — {line.rating}cr" if line.rating else ""
            lines.append(
                f"  {line.name}{line.slot_mark}{line.brought_mark}{line.count_mark}{rating}"
            )
    for note in sheet.remarks:
        lines.append(f"({note.text})")
    lines.append("")
    for card in sheet.models:
        lines += render_model_card(card)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def gang_to_text(gang):
    """Convenience: gang in, text out."""
    return render_gang_sheet(render_gang(gang))


def render_ledger(view):
    """The ledger as text: every acquisition, and what happened to it."""
    lines = [
        f"Ledger — {view.gang}",
        f"Budget {view.starting_credits}  Spent {view.total_spent}  "
        f"Remaining {view.credits_remaining}  Rating {view.total_rating}",
        "",
    ]
    for line in view.lines:
        flag = "  [removed]" if line.removed else ""
        pricing = f"{line.paid}cr"
        if line.discount:
            pricing = f"{line.paid}cr (list {line.list_price} - {line.discount})"
        lines.append(
            f"  {line.what} {line.where} — {pricing}, "
            f"rating {line.rating} [{line.reason}]{flag}"
        )
        for event in line.events:
            note = f" — {event.note}" if event.note else ""
            lines.append(
                f"      {event.kind}: {event.credits:+}cr, "
                f"rating {event.rating:+}, by {event.actor}{note}"
            )
    return "\n".join(lines).rstrip() + "\n"


def ledger_to_text(gang):
    """Convenience: gang in, ledger text out."""
    return render_ledger(build_ledger(gang))
