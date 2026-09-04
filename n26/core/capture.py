"""What a gang's pages say, captured as plain data for comparing two
states of the world.

A conversion that moves content from one shape to another must leave
every page saying the same things. The capture holds exactly the facts
that must not change — names, numbers, the questions asked and what
settled them — as plain primitives, sorted wherever the page's own
order carries no meaning (a statline keeps its printed order; a run of
rules does not), so two captures compare with ``==`` and any difference
is a mistake by definition. Addresses and provenance wording are
deliberately absent — a conversion may change where a control leads and
which machinery asks a question, never what the reader is told — and
the one id kept is the model key, so a difference names the fighter it
is about.

Built on ``render_gang``, the same derivation every screen uses, so the
capture cannot agree with a broken page.
"""

from n26.core.render import render_gang


def _names(lines):
    return sorted(str(line.name) for line in lines)


def _rated(lines):
    """Lines whose printed figure matters as much as their name."""
    return sorted((str(line.name), line.rating) for line in lines)


def _choices(lines):
    """Each question as (what the card calls it, what settled it)."""
    return sorted((line.kind_label, line.chosen or "") for line in lines)


def _statline(statline):
    return [(cell.short_name, str(cell.value)) for cell in statline.cells]


def _weapons(lines):
    return sorted(
        (
            weapon.name,
            weapon.base_rating,
            tuple(
                (
                    profile.name,
                    profile.rating,
                    _statline(profile.statline),
                    tuple(sorted(t.name for t in profile.traits)),
                )
                for profile in weapon.profiles
            ),
            tuple(sorted(a.name for a in weapon.accessories)),
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
        "statline": _statline(card.statline),
        "subtypes": _names(card.subtypes),
        "weapons": _weapons(card.weapons),
        "skills": _names(card.skills),
        "powers": _names(card.powers),
        "rules": _names(card.rules),
        "equipment": _rated(card.equipment),
        "collections": _names(card.collections),
        "choices": _choices([*card.choices, *card.skill_choices, *card.power_choices]),
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
        # What the campaign gave, which the sheet keeps apart from the gang's
        # own rows and counters — so a conversion that broke a campaign
        # carrier, or what it brought, would show here rather than nowhere.
        "campaign": (
            {
                "name": sheet.campaign.name,
                "lines": _names(sheet.campaign.lines),
                "counters": sorted(
                    (str(counter.name), str(counter.value))
                    for counter in sheet.campaign.counters
                ),
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
