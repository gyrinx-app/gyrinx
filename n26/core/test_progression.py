"""Rank display comes from authored tables and stored counter values."""

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core.models import ActionRecord
from n26.core.progression import _result_for, progression_summaries
from n26.library import authoring

pytestmark = [pytest.mark.django_db, pytest.mark.core]


class _Card:
    def __init__(self, nodes):
        self.nodes = nodes

    def all_nodes(self):
        return iter(self.nodes)


def _node(key, assignable, assignment, **extra):
    return SimpleNamespace(
        key=key,
        assignable=assignable,
        assignment=assignment,
        caused_by_key=None,
        suppressed=False,
        broadcast=False,
        computed=False,
        opens_at=0,
        **extra,
    )


def _card(table, counter, value):
    nodes = [_node("rank", table, SimpleNamespace(rank_table_id=table.pk))]
    if value is not None:
        nodes.append(
            _node(
                "counter",
                counter,
                SimpleNamespace(counter_value=SimpleNamespace(value=value)),
            )
        )
    return _Card(nodes)


def _ladder():
    xp = authoring.create_counter("XP")
    table = authoring.create_rank_table("Fighter ranks", xp, initial_title="Rookie")
    for threshold, title in (
        (4, "Rookie"),
        (13, "Gang Member"),
        (37, "Gang Exemplar"),
        (49, "Gang Exemplar"),
        (229, "Legend of the Underhive"),
    ):
        authoring.add_rank_threshold(table, threshold, title=title)
    return xp, table


class TestRosterRankSummaries:
    """One batch read describes every effective schedule without model queries."""

    def test_titles_and_next_threshold_follow_the_written_counter(self, default_pack):
        xp, table = _ladder()
        fighters = [SimpleNamespace(pk=number) for number in range(4)]
        cards = {
            fighter.pk: _card(table, xp, value)
            for fighter, value in zip(fighters, (0, 37, 229, None), strict=True)
        }

        summaries = progression_summaries(cards, fighters, {})

        first, exemplar, legend, untracked = (
            summaries[fighter.pk][0] for fighter in fighters
        )
        assert (
            first.value,
            first.current_title,
            first.next_threshold,
            first.next_title,
            first.remaining,
        ) == (0, "Rookie", 4, "Rookie", 4)
        assert (
            exemplar.current_title,
            exemplar.next_threshold,
            exemplar.remaining,
        ) == ("Gang Exemplar", 49, 12)
        assert (legend.current_title, legend.next_threshold, legend.remaining) == (
            "Legend of the Underhive",
            None,
            None,
        )
        assert (untracked.value, untracked.current_title, untracked.remaining) == (
            None,
            "",
            None,
        )

    def test_more_fighters_do_not_add_queries(self, default_pack):
        xp, table = _ladder()
        fighters = [SimpleNamespace(pk=number) for number in range(12)]
        cards = {fighter.pk: _card(table, xp, 37) for fighter in fighters}

        with CaptureQueriesContext(connection) as one:
            progression_summaries(cards, fighters[:1], {})
        with CaptureQueriesContext(connection) as many:
            progression_summaries(cards, fighters, {})

        assert len(one) == len(many) == 2

    def test_competing_tables_leave_only_unambiguous_rank_summaries(self, default_pack):
        xp, first = _ladder()
        second = authoring.create_rank_table("Other XP ranks", xp)
        authoring.add_rank_threshold(second, 5, title="Other rank")
        renown = authoring.create_counter("Renown")
        renown_table = authoring.create_rank_table(
            "Renown ranks", renown, initial_title="Known"
        )
        authoring.add_rank_threshold(renown_table, 3, title="Famous")
        card = _Card(
            [
                _node("first", first, SimpleNamespace(rank_table_id=first.pk)),
                _node("second", second, SimpleNamespace(rank_table_id=second.pk)),
                _node(
                    "renown-table",
                    renown_table,
                    SimpleNamespace(rank_table_id=renown_table.pk),
                ),
                _node(
                    "xp", xp, SimpleNamespace(counter_value=SimpleNamespace(value=4))
                ),
                _node(
                    "renown",
                    renown,
                    SimpleNamespace(counter_value=SimpleNamespace(value=0)),
                ),
            ]
        )
        fighter = SimpleNamespace(pk=1)

        (summary,) = progression_summaries({fighter.pk: card}, [fighter], {})[
            fighter.pk
        ]

        assert summary.table_id == renown_table.pk
        assert summary.current_title == "Known"
        assert summary.next_threshold == 3


class TestCompletedRankResults:
    """A discarded random roll is not the result of a later chosen advance."""

    def test_an_abandoned_skill_roll_does_not_replace_the_completed_pick(self):
        record = SimpleNamespace(
            state=ActionRecord.State.COMPLETED,
            skill_selection=SimpleNamespace(
                selected_skill_id="rolled",
                selected_skill="Dodge",
                skill_assignment_id=None,
            ),
            advancement_selection=SimpleNamespace(
                intended_pick_id="chosen",
                intended_pick="Strength",
            ),
            outcome_id="advancement",
            outcome="Advancement",
        )

        assert _result_for(record) == "Strength"
        record.skill_selection.skill_assignment_id = "applied"
        assert _result_for(record) == "Dodge"
