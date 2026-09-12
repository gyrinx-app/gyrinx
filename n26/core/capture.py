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


def _names(lines):
    return sorted(str(line.name) for line in _each(lines))


def _assets(lines):
    """What the campaign gave, each with the label it is drawn under and
    the income printed beside it."""
    return sorted(
        (str(line.type_label), str(line.name), str(line.income)) for line in lines
    )


def _rated(lines):
    """Lines whose printed figure matters as much as their name."""
    return sorted((str(line.name), line.rating) for line in _each(lines))


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
        "statline": _statline(card.statline),
        "subtypes": _names(card.subtypes),
        "weapons": _weapons(card.weapons),
        "skills": _names(card.skills),
        "powers": _names(card.powers),
        "rules": _names(card.rules),
        "equipment": _rated(card.equipment),
        # Gear drawn under its category's own heading, kept apart here as
        # it is on the card. Folding it back into equipment would let a
        # conversion move a possession between headings and still call the
        # two pages equal.
        #
        # A list in the card's own order, not a dict: heading order is the
        # taxonomy's and a reader sees it, so it is a fact worth holding.
        # Keying by name would also collide, since a category name is only
        # unique within its section — two headings alike would fold into
        # one and hide a move between them.
        "gear_groups": [
            (group.name, _rated(group.lines)) for group in card.gear_groups
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
        # What the campaign gave, which the sheet keeps apart from the gang's
        # own rows and counters — so a conversion that broke a campaign
        # carrier, or what it brought, would show here rather than nowhere.
        "campaign": (
            {
                "name": sheet.campaign.name,
                "lines": _assets(sheet.campaign.lines),
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
