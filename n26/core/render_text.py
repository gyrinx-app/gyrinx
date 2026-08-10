"""A very basic text renderer.

Exists so a human (or a test) can look at what the render structures hold.
Layout is deliberately crude — this is a debugging tool, not a design.
"""

from n26.core.render import build_ledger, render_gang


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
    owner = f"  (owned by {card.owned_by})" if card.owned_by else ""
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
            label = weapon.name
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
                lines.append(f"{indent}      + {accessory.name}")
            for profile in weapon.named_profiles:
                lines.append(
                    f"{indent}      - {profile.name}{_profile_suffix(profile)}"
                )
    if card.skills:
        names = ", ".join(line.name for line in card.skills)
        lines.append(f"{indent}  Skills: {names}")
    if card.rules:
        names = ", ".join(line.name for line in card.rules)
        lines.append(f"{indent}  Rules: {names}")
    if card.powers:
        names = ", ".join(line.name for line in card.powers)
        lines.append(f"{indent}  Powers: {names}")
    for choice in card.questions:
        # Drawn like any other assignable's row; a real UI hangs the picker
        # link here. The provenance is deliberately not shown.
        answer = choice.chosen if choice.is_resolved else "— (not chosen)"
        lines.append(f"{indent}  {choice.kind_label}: {answer}")
    if card.equipment:
        names = ", ".join(line.name for line in card.equipment)
        lines.append(f"{indent}  Equipment: {names}")
    if card.collections:
        names = ", ".join(line.name for line in card.collections)
        lines.append(f"{indent}  Buys from: {names}")
    for effect in card.effects:
        tense = "" if effect.happened else " (when taken)"
        lines.append(f"{indent}  {_sentence(effect.description)}{tense}")
    return lines


def _profile_suffix(profile):
    """What a firing line says after its label: what buying it added,
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
    if sheet.rules:
        names = ", ".join(line.name for line in sheet.rules)
        lines.append(f"Rules: {names}")
    for counter in sheet.counters:
        lines.append(f"{counter.name}: {counter.value}")
    for choice in sheet.choices:
        answer = choice.chosen if choice.is_resolved else "— (not chosen)"
        lines.append(f"{choice.kind_label}: {answer}")
    if sheet.stash:
        lines.append(f"Stash — {sheet.stash_rating}cr")
        for line in sheet.stash:
            rating = f" — {line.rating}cr" if line.rating else ""
            lines.append(f"  {line.name}{rating}")
    for note in sheet.notes:
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
