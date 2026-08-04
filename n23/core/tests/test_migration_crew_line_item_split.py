"""0194 splits a line item's single ``cost`` into what it's worth and what it cost.

Two things have to hold, and neither is exercised by the suite otherwise —
``--nomigrations`` means the data migration never runs.

The live and historical tables must both be converted. Left alone, every
pre-existing history row would claim the item was worth nothing, and reverting
one through django-simple-history would write that zero onto the live item.

And the reverse must be the forward's inverse. The old single field meant
credits value, so it is the *rating* that survives a fold-back, for every row
and not just the free ones.

Both fields still exist on the current models, so the migration functions run
against the real registry.
"""

import pytest
from django.apps import apps as real_apps

from n23.core.models.battle import Battle
from n23.core.models.crew import Crew, CrewLineItem
from n23.core.models.list import List

migration = __import__(
    "n23.core.migrations.0194_crew_line_item_split_amounts",
    fromlist=["split_amounts", "unsplit_amounts"],
)


@pytest.fixture
def crew(user, campaign, make_list):
    gang = make_list("Riot Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(gang)
    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    battle.set_participants([gang])
    return Crew.objects.create(battle=battle, list=gang, owner=user, status=Crew.LOCKED)


def _make(crew, label, cost, payment):
    """A row as 0194 finds it: one amount, in ``cost``, meaning credits value."""
    item = CrewLineItem.objects.create(
        crew=crew, label=label, cost=cost, payment=payment, owner=crew.owner
    )
    CrewLineItem.objects.filter(pk=item.pk).update(rating_value=0)
    return item


@pytest.mark.django_db
def test_split_moves_worth_to_rating_and_zeroes_free_costs(crew):
    paid = _make(crew, "Hired gun", 55, Crew.PAY_CREDITS)
    free = _make(crew, "Mysterious stranger", 80, Crew.PAY_FREE)

    migration.split_amounts(real_apps, None)

    paid.refresh_from_db()
    free.refresh_from_db()
    assert (paid.rating_value, paid.cost) == (55, 55)
    # The free entry was recorded at its worth. That worth is the whole point —
    # it still fights — but it costs nothing.
    assert (free.rating_value, free.cost) == (80, 0)


@pytest.mark.django_db
def test_split_converts_the_history_table_too(crew):
    item = _make(crew, "Hired gun", 55, Crew.PAY_CREDITS)
    assert item.history.count() == 1

    migration.split_amounts(real_apps, None)

    record = item.history.first()
    assert record.rating_value == 55


@pytest.mark.django_db
def test_reverse_keeps_the_rating_for_every_row(crew):
    # A tactics card is the case the old single field had no room for: worth
    # nothing, costs 20. Folding back keeps the worth, because that is what the
    # field it folds into means.
    card = CrewLineItem.objects.create(
        crew=crew,
        label="Tactics card",
        rating_value=0,
        cost=20,
        payment=Crew.PAY_CREDITS,
        owner=crew.owner,
    )
    free = CrewLineItem.objects.create(
        crew=crew,
        label="Mysterious stranger",
        rating_value=80,
        cost=0,
        payment=Crew.PAY_FREE,
        owner=crew.owner,
    )

    migration.unsplit_amounts(real_apps, None)

    card.refresh_from_db()
    free.refresh_from_db()
    assert card.cost == 0
    assert free.cost == 80


@pytest.mark.django_db
def test_split_round_trips(crew):
    _make(crew, "Hired gun", 55, Crew.PAY_CREDITS)
    _make(crew, "Mysterious stranger", 80, Crew.PAY_FREE)

    migration.split_amounts(real_apps, None)
    migration.unsplit_amounts(real_apps, None)

    assert sorted(CrewLineItem.objects.values_list("label", "cost")) == [
        ("Hired gun", 55),
        ("Mysterious stranger", 80),
    ]
