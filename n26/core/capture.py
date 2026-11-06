"""Capture player-visible gang facts for conversion equivalence checks.

Build on ``render_gang`` and compare plain primitives with equality.
Include names, values, choices and selections. Preserve meaningful order,
such as statline columns, and sort unordered groups such as rules.

Omit action URLs and provenance wording, which may change during a content
conversion. Retain model keys so differences identify the affected fighter.
"""

from n26.core.render import group_campaign_assets, render_gang


def _each(lines):
    """Every assignment a run of lines stands for.

    A card draws several of one thing as one line with a count; the
    capture writes that line once per assignment, so a gang holding two
    of a thing never compares equal to a gang holding one, and a
    conversion that lost the second is a difference rather than a
    silence.
    """
    for line in lines:
        for _ in range(line.count):
            yield line


def _line_label(line):
    """Include the names of pets created by this equipment in its captured label."""
    return str(line.name) + line.brought_mark


def _names(lines):
    return sorted(_line_label(line) for line in _each(lines))


def _assets(lines):
    """What the campaign gave, each with the label it is drawn under and
    the income printed beside it."""
    return sorted(
        (str(line.type_label), str(line.name), str(line.income)) for line in lines
    )


def _asset_groups(block):
    """Display groups with canonical type and name order for comparison."""
    lines = [*block.lines, *block.holdings]
    names = {}
    for line in lines:
        names.setdefault(line.asset_type_id, []).append(str(line.name))
    type_names = {key: tuple(sorted(values)) for key, values in names.items()}
    ordered = sorted(
        lines,
        key=lambda line: (
            str(line.type_plural),
            type_names[line.asset_type_id],
            str(line.name),
        ),
    )
    return sorted(
        (group.label, tuple((str(item.name), item.count) for item in group.names))
        for group in group_campaign_assets(ordered, types=block.asset_types)
    )


def _rated(lines):
    """Lines whose printed figure matters as much as their name."""
    return sorted((_line_label(line), line.rating) for line in _each(lines))


def _item_choices(lines):
    """Every question filed beneath its exact carried item."""
    return sorted(
        (_line_label(line), tuple(_choices(line.choices)))
        for line in _each(lines)
        if line.choices
    )


def _choices(lines):
    """Each question as (what the card calls it, what settled it)."""
    return sorted((line.kind_label, line.chosen or "") for line in lines)


def _statline(statline):
    return [(cell.short_name, str(cell.value)) for cell in statline.cells]


def _weapons(lines):
    return sorted(
        (
            _line_label(weapon),
            weapon.base_rating,
            tuple(
                (
                    _line_label(profile),
                    profile.rating,
                    _statline(profile.statline),
                    tuple(sorted(t.name for t in profile.traits)),
                )
                for profile in weapon.profiles
            ),
            tuple(sorted(_line_label(a) for a in weapon.accessories)),
            tuple(_choices(weapon.choices)),
        )
        for weapon in lines
    )


def _remarks(notes):
    return sorted(str(note.text) for note in notes)


def _model_state(card):
    return {
        "name": card.name,
        "rating": card.rating,
        "profile": card.profile_name,
        "type_line": card.type_line,
        # Capture pet ownership so a changed or missing cause alters the comparison.
        "owner": card.owner_line,
        "statline": _statline(card.statline),
        "subtypes": _names(card.subtypes),
        "weapons": _weapons(card.weapons),
        "skills": _names(card.skills),
        "powers": _names(card.powers),
        "rules": _names(card.rules),
        "equipment": _rated(card.equipment),
        "equipment_choices": _item_choices(card.equipment),
        # Preserve category headings and their order. Names are unique only
        # within sections, so a dictionary keyed by heading would merge distinct
        # categories and hide movements between them.
        "gear_groups": [
            (group.name, _rated(group.lines)) for group in card.gear_groups
        ],
        "gear_group_choices": [
            (group.name, _item_choices(group.lines))
            for group in card.gear_groups
            if _item_choices(group.lines)
        ],
        "collections": _names(card.collections),
        # The card's own rows; a question a weapon carries is captured with
        # the weapon, where the page draws it.
        "choices": _choices(card.row_questions),
        "remarks": _remarks(card.remarks),
        "xp": card.xp,
        "xp_target": card.xp_target,
    }


def gang_state(gang):
    """One gang's pages, as comparable data. Models are keyed by their
    stored ids, so a diff names the fighter rather than an index."""
    sheet = render_gang(gang)
    return {
        "name": sheet.name,
        "gang_type": sheet.gang_type,
        "rating": sheet.rating,
        "credits": sheet.credits,
        "wealth": sheet.wealth,
        "rows": _names(sheet.rows),
        "rules": _names(sheet.rules),
        "choices": _choices(sheet.choices),
        "counters": sorted(
            (str(counter.name), str(counter.value)) for counter in sheet.counters
        ),
        # Capture campaign-provided content separately to detect broken carriers
        # and grants.
        "campaign": (
            {
                "name": sheet.campaign.name,
                "choices": _choices(sheet.campaign.choices),
                "lines": _assets(sheet.campaign.lines),
                # Grouped display and individual income facts are both kept:
                # presentation changes must not conceal a lost copy or boon.
                "assets": _asset_groups(sheet.campaign),
                "counters": sorted(
                    (str(counter.name), str(counter.value))
                    for counter in sheet.campaign.counters
                ),
                "holdings": _assets(sheet.campaign.holdings),
            }
            if sheet.campaign
            else None
        ),
        "stash": _rated(sheet.stash),
        "stash_rating": sheet.stash_rating,
        "notes": _remarks(sheet.remarks),
        "models": {card.id: _model_state(card) for card in sheet.models},
    }


def differences(before, after, at=""):
    """Every place two captures disagree, as readable paths.

    Empty means the pages say the same things. Listed rather than a bare
    boolean so a refusing conversion can say exactly what it would have
    changed.
    """
    if isinstance(before, dict) and isinstance(after, dict):
        found = []
        for key in sorted(set(before) | set(after)):
            here = f"{at}.{key}" if at else str(key)
            if key not in before:
                found.append(f"{here}: appears ({after[key]!r})")
            elif key not in after:
                found.append(f"{here}: vanishes ({before[key]!r})")
            else:
                found.extend(differences(before[key], after[key], here))
        return found
    if before != after:
        return [f"{at}: {before!r} -> {after!r}"]
    return []
