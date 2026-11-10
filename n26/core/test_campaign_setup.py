from types import SimpleNamespace as Facts

from n26.core.campaign_setup import setup_checklist
from n26.library.territory_table import TERRITORY


def test_setup_uses_existing_facts_and_hides_cycle_actions_when_flag_is_closed():
    actor = Facts(pk="owner")
    campaign = Facts(pk="01M719WDA7XGQVY5ZTMRE9PZ0V", owner_id=actor.pk, archived=False)
    sheet = Facts(
        summary="<p>Welcome</p>",
        budget=0,
        gangs=[Facts()],
        assets=[Facts(label=TERRITORY, tables=[Facts()], entries=[])],
    )
    players = [Facts(state="invited")]
    closed = setup_checklist(campaign, sheet, players, None, actor=actor)
    assert [item["complete"] for item in closed["items"]] == [True, True, True, False]
    assert "Set up cycles" not in [item["label"] for item in closed["items"]]
    cycles = Facts(setup_href="/setup/", schedule_href="/cycles/")
    opened = setup_checklist(campaign, sheet, players, cycles, actor=actor)
    assert opened["items"][3] == {
        "label": "Set up cycles",
        "href": "/setup/",
        "complete": False,
    }
    assert (
        setup_checklist(campaign, sheet, players, cycles, actor=Facts(pk="player"))
        is None
    )
    campaign.archived = True
    assert setup_checklist(campaign, sheet, players, cycles, actor=actor) is None


def test_territory_completion_ignores_other_rollable_holding_types():
    actor = Facts(pk="owner")
    campaign = Facts(pk="01M719WDA7XGQVY5ZTMRE9PZ0V", owner_id=actor.pk, archived=False)
    racket = Facts(label="Racket", tables=[Facts()], entries=[])
    territory = Facts(label=TERRITORY, tables=[Facts()], entries=[Facts()])
    sheet = Facts(summary="", budget=None, gangs=[], assets=[racket])

    def territory_item():
        return next(
            (
                item
                for item in setup_checklist(campaign, sheet, [], None, actor=actor)[
                    "items"
                ]
                if item["label"] == "Roll territories"
            ),
            None,
        )

    assert territory_item() is None
    sheet.assets.append(territory)
    assert territory_item()["complete"] is True
    territory.entries.clear()
    assert territory_item()["complete"] is False
