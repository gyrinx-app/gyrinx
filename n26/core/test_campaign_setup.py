from types import SimpleNamespace as Facts

from n26.core.campaign_setup import setup_checklist


def test_setup_uses_existing_facts_and_hides_cycle_actions_when_flag_is_closed():
    actor = Facts(pk="owner")
    campaign = Facts(pk="01M719WDA7XGQVY5ZTMRE9PZ0V", owner_id=actor.pk, archived=False)
    sheet = Facts(
        summary="<p>Welcome</p>",
        budget=0,
        gangs=[Facts()],
        assets=[Facts(tables=[Facts()], entries=[])],
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
