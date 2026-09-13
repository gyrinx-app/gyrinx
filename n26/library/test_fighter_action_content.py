import pytest

from n26.library.models import Action, Modifier, OffersChoice, Picklist, RankTable
from n26.library.standard_content import (
    FIGHTER_ADVANCEMENTS,
    FIGHTER_RANK_THRESHOLDS,
    STANDARD_CONTENT,
)

pytestmark = pytest.mark.django_db


def test_fighter_action_content_is_complete_and_idempotent():
    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    content.create()
    assert content.check() == (42, 42)
    table = Picklist.objects.get(name="Fighter advancement table")
    assert table.dice == "2d6"
    assert table.roll_selects == "threshold"
    assert list(
        table.members.values_list(
            "pickable__name", "roll_low", "pickable__rating_contribution"
        )
    ) == list(FIGHTER_ADVANCEMENTS)
    ranks = RankTable.objects.get(name="Standard fighter ranks")
    assert (
        tuple(ranks.thresholds.values_list("threshold", flat=True))
        == FIGHTER_RANK_THRESHOLDS
    )
    actions = {
        action.name: action
        for action in Action.objects.prefetch_related("use_price", "outcomes")
    }
    assert set(actions) >= {
        "Suit Evolution",
        "Suit Maintenance",
        "Recruitment augmentation",
        "Advancement",
    }
    assert [
        (p.resource, p.payer, p.amount, str(p.counter) if p.counter else None)
        for p in actions["Suit Evolution"].use_price.all()
    ] == [("counter", "fighter", 4, "Kill Count")]
    assert [
        (p.resource, p.payer, p.amount)
        for p in actions["Suit Maintenance"].use_price.all()
    ] == [("credits", "gang", 100)]
    assert actions["Recruitment augmentation"].recruitment_allowance_rule_id
    assert actions["Advancement"].rank_allowance_rule.counter == ranks.counter
    offers = {
        modifier.name.removeprefix("Advancement: "): modifier.effect
        for modifier in Modifier.objects.filter(name__startswith="Advancement: ")
        if isinstance(modifier.effect, OffersChoice)
    }
    assert {
        (name, offer.mode, offer.from_section.name if offer.from_section else "any")
        for name, offer in offers.items()
    } == {
        ("Random Primary skill", "random", "Primary"),
        ("Select Primary skill", "select", "Primary"),
        ("Random Secondary skill", "random", "Secondary"),
        ("Select Secondary skill", "select", "Secondary"),
        ("Select any skill", "select", "any"),
    }
    assert not Action.objects.filter(name__icontains="Power Boost").exists()
