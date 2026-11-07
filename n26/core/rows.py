"""Compose display headings without merging the facts or controls beneath them.

Contributions arrive after visibility and URL decoration. Composition is pure and
keeps the original objects, including their individual addresses and provenance.
An owner is a display scope (a model, gang or carried copy), never a content kind.
"""

from collections.abc import Hashable, Iterable
from dataclasses import dataclass, field, fields
from enum import StrEnum


class PartKind(StrEnum):
    NAMES = "names"
    GEAR = "gear"
    COUNTER = "counter"
    CHOICE = "choice"
    ASSET = "asset"
    ASSET_GROUP = "asset_group"


@dataclass(frozen=True)
class Separation:
    """An exceptional second heading within the same display owner."""

    key: str
    reason: str

    def __post_init__(self):
        if not self.key.strip() or not self.reason.strip():
            raise ValueError("Separate rows require a key and a reason.")


@dataclass(frozen=True)
class RowPart:
    kind: PartKind
    value: object
    # Named-row questions use their full prompt beside existing facts.
    named_prompt: bool = False

    def __post_init__(self):
        if not isinstance(self.kind, PartKind):
            raise ValueError(f"Unsupported row part: {self.kind!r}")

    @property
    def has_actions(self):
        return self.kind == PartKind.GEAR and any(
            line.sell or line.more or line.choices for line in self.value
        )


@dataclass(frozen=True)
class Contribution:
    owner: Hashable
    label: str
    part: RowPart
    separation: Separation | None = None


@dataclass
class DetailRow:
    owner: Hashable
    label: str
    parts: list[RowPart] = field(default_factory=list)
    separation: Separation | None = None
    edit_href: str = ""

    @property
    def has_asset_groups(self):
        return any(part.kind == PartKind.ASSET_GROUP for part in self.parts)


def normalized_heading(label: str) -> str:
    return " ".join(label.split()).casefold()


def compose_rows(contributions: Iterable[Contribution]) -> list[DetailRow]:
    """Combine equal headings per owner, retaining first-seen order and spelling.

    Values are neither deduplicated nor summed: equal-looking choices may have
    different controls, and equal-looking counters may track different totals.
    """
    rows = {}
    for contribution in contributions:
        key = (
            contribution.owner,
            normalized_heading(contribution.label),
            contribution.separation.key if contribution.separation else None,
        )
        if key not in rows:
            rows[key] = DetailRow(
                owner=contribution.owner,
                label=" ".join(contribution.label.split()),
                separation=contribution.separation,
            )
        rows[key].parts.append(contribution.part)
    return list(rows.values())


def choice_rows(choices, *, owner):
    return compose_rows(
        Contribution(owner, choice.kind_label, RowPart(PartKind.CHOICE, choice))
        for choice in choices
    )


def holder_rows(holder, *, owner):
    """Project declared fact rows and dynamic questions through the same composer.

    Field metadata declares presentation, rather than opting individual labels
    into combining. Dynamic labels always take the same path.
    """
    contributions = []
    for counter in getattr(holder, "counter_lines", getattr(holder, "counters", ())):
        contributions.append(
            Contribution(owner, counter.name, RowPart(PartKind.COUNTER, counter))
        )
    for definition in fields(holder):
        label = definition.metadata.get("row_label")
        if label is None:
            continue
        values = getattr(holder, definition.name)
        if values or definition.metadata.get("row_always"):
            contributions.append(
                Contribution(
                    owner,
                    label,
                    RowPart(
                        PartKind(definition.metadata.get("row_kind", "names")), values
                    ),
                )
            )
        bucket = getattr(holder, "QUESTION_BUCKETS", {}).get(definition.name)
        if bucket:
            contributions.extend(
                Contribution(owner, label, RowPart(PartKind.CHOICE, choice, True))
                for choice in getattr(holder, bucket)
            )
    for group in getattr(holder, "gear_groups", ()):
        contributions.append(
            Contribution(owner, group.name, RowPart(PartKind.GEAR, group.lines))
        )
    contributions.extend(
        Contribution(owner, choice.kind_label, RowPart(PartKind.CHOICE, choice))
        for choice in holder.choices
    )
    rows = compose_rows(contributions)
    skills_href = getattr(holder, "skills_href", "")
    if skills_href:
        for row in rows:
            if normalized_heading(row.label) == "skills":
                row.edit_href = skills_href
    return rows


def campaign_rows(campaign):
    owner = ("campaign", campaign.campaign_id)
    return compose_rows(
        [
            *(
                Contribution(owner, choice.kind_label, RowPart(PartKind.CHOICE, choice))
                for choice in campaign.other_choices
            ),
            *(
                Contribution(owner, counter.name, RowPart(PartKind.COUNTER, counter))
                for counter in campaign.counters
            ),
            *(
                Contribution(owner, line.type_label, RowPart(PartKind.ASSET, line))
                for line in campaign.other_lines
            ),
            *(
                Contribution(owner, group.label, RowPart(PartKind.ASSET_GROUP, group))
                for group in campaign.asset_groups
            ),
        ]
    )


def campaign_owned_rows(campaign):
    # An asset's choices belong to that held or owned copy, not the campaign.
    return compose_rows(
        Contribution(
            ("asset", choice.asset_key or id(choice)),
            f"{choice.asset_name or choice.holding_name} — {choice.kind_label}",
            RowPart(PartKind.CHOICE, choice),
        )
        for choice in campaign.choices
        if choice.asset_key or choice.holding_name
    )


def part_text(part, *, prompts=False):
    """Read-only words for print and text; interactive controls stay on the part."""
    match part.kind:
        case PartKind.NAMES | PartKind.GEAR:
            return ", ".join(
                line.name + line.tier_mark + line.brought_mark + line.count_mark
                for line in part.value
            )
        case PartKind.COUNTER:
            return str(part.value.value)
        case PartKind.ASSET:
            return part.value.name
        case PartKind.ASSET_GROUP:
            return ", ".join(name.text for name in part.value.names) or "None"
        case PartKind.CHOICE:
            choice = part.value
            text = choice.chosen if choice.is_resolved else "—"
            if prompts:
                if not choice.is_resolved:
                    text += " (not chosen)"
                elif not choice.is_full:
                    text += " (add)"
            if part.named_prompt:
                text = f"{choice.kind_label}: {text}"
            return text
    raise ValueError(f"Unsupported row part: {part.kind!r}")


def readable_parts(row, *, skip_xp=True):
    return [
        part
        for part in row.parts
        if not (skip_xp and part.kind == PartKind.COUNTER and part.value.is_xp)
        if part_text(part)
    ]


def row_text(row, *, prompts=False, skip_xp=True):
    return ", ".join(
        part_text(part, prompts=prompts)
        for part in readable_parts(row, skip_xp=skip_xp)
    )
