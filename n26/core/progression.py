"""Read fighter ranks from effective cards and the actions earned at each rank.

Ranks are authored library content. The current title follows the counter value
written on the fighter's card; an earned action remains in the history even if
the fighter later loses access to its original rank table. Neither read grants
an allowance or changes old counter history.
"""

from dataclasses import dataclass
from types import SimpleNamespace

from django.db.models import Prefetch

from n26.core.access import rank_tables_for
from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import ActionAllowance, ActionRecord
from n26.library.models import Counter, RankTable, RankThreshold
from n26.library.standard_content import XP_COUNTER


@dataclass(frozen=True)
class RankSummary:
    """One effective table's standing and the next threshold to reach."""

    table_id: object
    table_name: str
    counter_name: str
    is_xp: bool
    value: int | None
    current_title: str
    next_threshold: int | None
    next_title: str
    remaining: int | None


@dataclass(frozen=True)
class RankHistory:
    """An earned rank action, including its original table and outcome."""

    table_id: object
    table_name: str
    counter_name: str
    threshold: int
    title: str
    action_name: str
    state: str
    result: str
    record_id: object | None


@dataclass(frozen=True)
class FighterProgression:
    summaries: tuple[RankSummary, ...]
    history: tuple[RankHistory, ...]


_NO_EFFECTS = SimpleNamespace(acquired=(), echoed=())


def _written_counters(card):
    """Read only model-owned, stored figures, as rank allowance grants do."""
    values = {}
    for node in card.all_nodes():
        if (
            node.broadcast
            or node.suppressed
            or node.computed
            or not isinstance(node.assignable, Counter)
        ):
            continue
        if node.assignment is None:
            value = node.opens_at
        else:
            held = getattr(node.assignment, "counter_value", None)
            value = held.value if held is not None else None
        values.setdefault(node.assignable.pk, value)
    return values


def _thresholds_for(table_ids):
    rows = RankThreshold.objects.filter(rank_table_id__in=table_ids).order_by(
        "rank_table_id", "threshold"
    )
    by_table = {table_id: [] for table_id in table_ids}
    for row in rows:
        by_table[row.rank_table_id].append(row)
    return by_table


def _summaries_for(card, accesses, tables, thresholds):
    values = _written_counters(card) if card is not None else {}
    by_counter = {}
    for access in accesses:
        counter_id = tables[access.rank_table.pk].counter_id
        by_counter.setdefault(counter_id, []).append(access)
    # A counter with competing tables has no one next rank. Action grants
    # refuse that content; read-only cards leave its standing unlabelled.
    ambiguous = {
        counter_id for counter_id, found in by_counter.items() if len(found) > 1
    }
    summaries = []
    for access in accesses:
        table = tables[access.rank_table.pk]
        if table.counter_id in ambiguous:
            continue
        value = values.get(table.counter_id)
        current_title = table.initial_title if value is not None else ""
        following = None
        for rank in thresholds[table.pk]:
            if value is not None and rank.threshold <= value:
                current_title = rank.title
            elif following is None:
                following = rank
                break
        summaries.append(
            RankSummary(
                table_id=table.pk,
                table_name=str(table),
                counter_name=str(table.counter),
                is_xp=table.counter.name.casefold() == XP_COUNTER.casefold(),
                value=value,
                current_title=current_title,
                next_threshold=following.threshold if following else None,
                next_title=following.title if following else "",
                remaining=(
                    following.threshold - value
                    if following is not None and value is not None
                    else None
                ),
            )
        )
    return tuple(sorted(summaries, key=lambda row: row.table_name))


def progression_summaries_for_cards(entries):
    """Read standings for keyed fighter cards with two library queries.

    Keys may name different selections of the same fighter's card. The
    caller supplies each card and its computed effects; this reader neither
    rebuilds a card nor computes modifiers inside the loop.
    """
    entries = tuple(entries)
    accesses = {}
    table_ids = set()
    for key, fighter, card, computed in entries:
        if card is None:
            accesses[key] = ()
            continue
        found = rank_tables_for(fighter, card=card, computed=computed or _NO_EFFECTS)
        accesses[key] = found
        table_ids.update(row.rank_table.pk for row in found)
    if not table_ids:
        return {key: () for key, _fighter, _card, _computed in entries}

    tables = {
        row.pk: row
        for row in RankTable.objects.filter(pk__in=table_ids).select_related("counter")
    }
    thresholds = _thresholds_for(table_ids)
    return {
        key: _summaries_for(card, accesses[key], tables, thresholds)
        for key, _fighter, card, _computed in entries
    }


def progression_summaries(cards, fighters, computed):
    """Build roster standings from preloaded card maps, without model queries.

    When effects have not been computed, pass an empty map: stored tables
    still appear, but no per-fighter compute or query is hidden here.
    """
    return progression_summaries_for_cards(
        (fighter.pk, fighter, cards.get(fighter.pk), computed.get(fighter.pk))
        for fighter in fighters
    )


def _result_for(record):
    if record is None or record.state != ActionRecord.State.COMPLETED:
        return ""
    skill = getattr(record, "skill_selection", None)
    # A random skill may have been rolled, then left behind when the player
    # went back and completed a different result. Only its written assignment
    # confirms that the skill was the advancement actually taken.
    if skill is not None and skill.skill_assignment_id and skill.selected_skill_id:
        return str(skill.selected_skill)
    advancement = getattr(record, "advancement_selection", None)
    if advancement is not None and advancement.intended_pick_id:
        return str(advancement.intended_pick)
    if record.outcome_id:
        return str(record.outcome)
    return ""


def progression_for(fighter, *, card=None, computed=None):
    """Read one fighter's current standings and durable rank-action history.

    Edit pages can pass their already-built card and computed effects. The
    history uses the table recorded on each allowance, not today's effective
    table, so changing access never relabels which schedule earned a use.
    """
    if card is None:
        card = build_card(fighter)
    if computed is None:
        computed = compute(card, build_modifier_index(carriers(card)))
    active_records = ActionRecord.objects.filter(
        state__in=(ActionRecord.State.STARTED, ActionRecord.State.COMPLETED)
    ).select_related(
        "outcome",
        "advancement_selection__intended_pick",
        "skill_selection__selected_skill",
    )
    allowances = list(
        ActionAllowance.objects.filter(
            fighter=fighter, source_kind=ActionAllowance.Source.RANK
        )
        .select_related("rank_table__counter", "action")
        .prefetch_related(Prefetch("records", queryset=active_records))
        .order_by("created", "pk")
    )
    accesses = rank_tables_for(fighter, card=card, computed=computed)
    current_ids = {row.rank_table.pk for row in accesses}
    table_ids = current_ids | {row.rank_table_id for row in allowances}
    thresholds = _thresholds_for(table_ids) if table_ids else {}
    tables = {
        row.pk: row
        for row in RankTable.objects.filter(pk__in=current_ids).select_related(
            "counter"
        )
    }
    titles = {
        (table_id, row.threshold): row.title
        for table_id, rows in thresholds.items()
        for row in rows
    }
    history = []
    for allowance in allowances:
        record = next(iter(allowance.records.all()), None)
        history.append(
            RankHistory(
                table_id=allowance.rank_table_id,
                table_name=str(allowance.rank_table),
                counter_name=str(allowance.rank_table.counter),
                threshold=allowance.threshold,
                title=titles.get((allowance.rank_table_id, allowance.threshold), ""),
                action_name=str(allowance.action),
                state=record.state if record is not None else "available",
                result=_result_for(record),
                record_id=record.pk if record is not None else None,
            )
        )
    summaries = _summaries_for(card, accesses, tables, thresholds)
    return FighterProgression(summaries=summaries, history=tuple(history))
