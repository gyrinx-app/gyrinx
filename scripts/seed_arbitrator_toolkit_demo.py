"""Create an isolated synthetic campaign once; subsequent runs preserve its data.

Run with .codex/run.sh manage shell < scripts/seed_arbitrator_toolkit_demo.py.
"""

import json
from datetime import date
from uuid import uuid4

from django.conf import settings
from django.db import transaction

from gyrinx.debug_login import ensure_debug_agent_user
from n26.core import toolkit
from n26.core.campaigns import campaign_operation
from n26.core.models import Campaign, Gang
from n26.core.operations import operation
from n26.library.authoring import (
    create_campaign_type,
    create_counter,
    create_gang_type,
    create_profile,
    create_profile_type,
    create_statline_type,
    create_wargear,
    create_weapon,
)
from n26.library.models import CampaignType, GangType, ProfileType
from n26.write_pause import write_guard

if not settings.DEBUG:
    raise RuntimeError("This sample campaign is only for local development.")
arb = ensure_debug_agent_user("agent-toolkit")
campaign = Campaign.objects.filter(
    owner=arb, name="Ash Road — Arbitrator Toolkit"
).first()
if campaign is None:
    with transaction.atomic(), write_guard():
        campaign_type = CampaignType.objects.selectable().filter(
            name="Territory campaign"
        ).first() or create_campaign_type("Toolkit demo campaign")
        campaign = Campaign(
            name="Ash Road — Arbitrator Toolkit",
            owner=arb,
            budget=1000,
            status=Campaign.Status.IN_PROGRESS,
            summary="<p>Three gangs contest the Ash Road. Supplies are scarce, and the arbitrator has issued a new contract.</p><p>This local sample campaign uses synthetic rosters to demonstrate the Arbitrator Toolkit.</p>",
        )
        with campaign_operation(campaign, actor=arb) as act:
            act.found(campaign_type)
        gang_type = (
            GangType.objects.selectable().filter(name="Escher").first()
            or GangType.objects.selectable().first()
            or create_gang_type("Ash Road crew", pack=campaign.pack)
        )
        fighter_type = ProfileType.objects.filter(name="Fighter").first()
        if fighter_type is None:
            stat_type = create_statline_type("Toolkit model", pack=campaign.pack)
            fighter_type = create_profile_type("Fighter", stat_type, pack=campaign.pack)
        vehicle_type = ProfileType.objects.filter(
            name="Vehicle"
        ).first() or create_profile_type(
            "Vehicle", fighter_type.statline_type, pack=campaign.pack
        )
        runner = create_profile(
            "Ash Road runner", fighter_type, gang_type, price=50, pack=campaign.pack
        )
        vehicle = create_profile(
            "Ash Road cargo crawler",
            vehicle_type,
            gang_type,
            price=120,
            pack=campaign.pack,
        )
        shotgun = create_weapon("Ash Road shotgun", price=30, pack=campaign.pack)
        kit = create_wargear("Field repair kit", price=20, pack=campaign.pack)
        supply = create_counter("Supply crates", pack=campaign.pack)
        gangs = []
        players = []
        for suffix, name, colour in [
            ("ada", "The Glass Vipers", "#7c3aed"),
            ("bram", "Iron Lanterns", "#b45309"),
            ("cora", "Sump Runners", "#0f766e"),
        ]:
            player = ensure_debug_agent_user("agent-toolkit-" + suffix)
            players.append(player)
            with campaign_operation(campaign, actor=arb) as act:
                act.invite(player)
            with campaign_operation(campaign, actor=player) as act:
                act.answer_invitation(player, True)
            gang = Gang(
                name=name,
                owner=player,
                gang_type=gang_type,
                starting_credits=1000,
                credits=1000,
                colour=colour,
            )
            gang.save()
            with operation(gang, actor=player) as op:
                op.found(gang_type)
                op.hire(runner, "Road captain", paid=50)
                op.hire(runner, "Lookout", paid=50)
                op.join_campaign(campaign)
            gangs.append(gang)

        def send(action, payload):
            form, url = toolkit.change(
                campaign,
                arb,
                action,
                {"request_key": str(uuid4()), "payload": json.dumps(payload)},
            )
            if not url:
                raise RuntimeError(dict(form.errors))
            return url

        base = {
            "mode": "bundle",
            "choices": 1,
            "recipients_mode": "all",
            "gangs": [],
            "inform_all": False,
        }
        send(
            "intervention",
            {
                **base,
                "title": "Supplies from the guild",
                "narrative": "A sealed convoy has reached the Ash Road. Each gang receives supplies for the next battle.",
                "rewards": [
                    {"kind": "credits", "amount": 50},
                    {"kind": "resource", "id": str(supply.pk), "amount": 2},
                    {"kind": "equipment", "id": str(kit.pk), "amount": 1},
                ],
            },
        )
        send(
            "intervention",
            {
                **base,
                "recipients_mode": "selected",
                "gangs": [str(gangs[0].pk)],
                "title": "Bounty issued",
                "narrative": "The guild has posted a bounty on the Glass Vipers.",
                "inform_all": True,
                "rewards": [
                    {
                        "kind": "tag",
                        "name": "Most Wanted",
                        "icon": "crosshair",
                        "info": "50 credits for defeating this gang in a recorded battle.",
                        "amount": 1,
                    }
                ],
            },
        )
        send(
            "intervention",
            {
                **base,
                "target": "players",
                "recipients_mode": "selected",
                "players": [str(players[1].pk)],
                "title": "Campaign quartermaster",
                "narrative": "Bram is coordinating printed campaign records.",
                "rewards": [
                    {
                        "kind": "tag",
                        "name": "Quartermaster",
                        "icon": "printer",
                        "info": "Contact this player for printed campaign sheets.",
                        "amount": 1,
                    }
                ],
            },
        )
        send(
            "intervention",
            {
                **base,
                "title": "The guild's offer",
                "narrative": "Choose support for the next journey: a new recruit, a shotgun, credits or a cargo crawler.",
                "mode": "choice",
                "choices": 1,
                "inform_all": True,
                "rewards": [
                    {"kind": "profile", "id": str(runner.pk), "amount": 1},
                    {"kind": "weapon", "id": str(shotgun.pk), "amount": 1},
                    {"kind": "credits", "amount": 30},
                    {"kind": "profile", "id": str(vehicle.pk), "amount": 1},
                ],
            },
        )
        send(
            "communication",
            {
                **base,
                "title": "Next campaign night",
                "body": "The next battle period begins on Friday. Log your battle outcomes so the campaign records stay current.",
            },
        )
        send("alerts", {"events": ["gang_added", "battle_outcome"]})
        with campaign_operation(campaign, actor=arb) as act:
            act.record_battle(date.today(), gangs[:2], scenario="Ash Road crossing")
print("Campaign:", toolkit.campaign_href(campaign))
print("Toolkit:", toolkit.toolkit_href(campaign))
print(
    "Choice:", campaign.interventions.filter(mode="choice").first().get_absolute_url()
)
print(
    "Arbitrator: agent-toolkit; players: agent-toolkit-ada, agent-toolkit-bram, agent-toolkit-cora"
)
