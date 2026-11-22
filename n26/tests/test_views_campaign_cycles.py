"""Schedule transports share ownership, revision and durable retry semantics."""

import json
from dataclasses import asdict, replace
from datetime import date
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import ref_data, template_data
from n26.core.cycle_display import build, dashboard_summary, editor_url, schedule_url
from n26.core.models import CampaignCycle, CampaignSchedule, CampaignScheduleTemplate
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(client, campaign_type):
    owner = User.objects.create_user("planning-arbitrator")
    client.force_login(owner)
    return found_campaign("Ash Road", campaign_type, owner=owner)


@pytest.fixture
def opened():
    return FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )


@pytest.fixture
def template():
    return CampaignScheduleTemplate.objects.create(
        name=s.DEFAULT_TEMPLATE.name,
        system_key=cycles.DEFAULT_TEMPLATE_KEY,
        definition=template_data(s.DEFAULT_TEMPLATE),
    )


@pytest.fixture
def configured(campaign, opened, template, request):
    cycles.configure(
        campaign,
        actor=campaign.owner,
        template_id=template.pk,
        current_position=0,
        mode=getattr(request, "param", "fixed"),
        request_key=uuid4(),
        calendar=s.CycleCalendar(date(2026, 11, 1)),
    )
    return cycles.load(campaign)


def props(response):
    assert response.status_code == 200
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="campaign-schedule"]')
    return json.loads(page.find(id=host["data-react-props"]).string)


@pytest.mark.parametrize("step, expected", [("1", 1), ("2", 2), ("3", 3), ("bogus", 1)])
def test_setup_step_is_a_shareable_server_read(
    client, campaign, opened, template, step, expected
):
    page = props(client.get(editor_url(campaign, "setup", step=step)))
    assert page["editor"]["context"]["setupStage"] == expected


@pytest.mark.parametrize("json_read", [False, True])
def test_setup_normalises_sparse_template_rewards_without_changing_the_template(
    client, campaign, opened, template, json_read
):
    sparse = {"name": "Sparse opening", "rewards": {"win": {"reputation": 2}}}
    template.definition["phases"][0]["details"] = sparse
    template.clean()
    template.save(update_fields=["definition"])

    response = client.get(
        editor_url(campaign, "setup"),
        headers={"Accept": "application/json"} if json_read else {},
    )
    page = response.json()["schedule"] if json_read else props(response)
    offered = next(
        item for item in page["editor"]["templates"] if item["id"] == str(template.pk)
    )
    expected = s.PhaseDetails(
        "Sparse opening", rewards=s.RewardSettings(win=s.Reward(reputation=2))
    )
    assert offered["definition"]["phases"][0]["details"] == asdict(expected)
    assert offered["definition"]["steps"] == template.definition["steps"]
    assert offered["name"] == template.name
    template.refresh_from_db()
    assert template.definition["phases"][0]["details"] == sparse
    assert not CampaignSchedule.objects.filter(campaign=campaign).exists()


def test_dashboard_groups_cycle_information_and_management_menu(
    client, campaign, configured
):
    response = client.get(reverse("n26-campaign", args=[campaign.pk]))
    page = BeautifulSoup(response.content, "html.parser")
    info = page.select_one('[aria-label="Campaign info"]')
    assert "Current cycle" not in info.get_text()
    summary = page.select_one("#campaign-cycle-summary")
    assert "Current cycle" in summary.get_text()
    assert summary.select_one('[aria-label="Edit campaign schedule"]')[
        "href"
    ] == editor_url(campaign, "plan")
    host = page.select_one('#campaign-overview [data-react-name="campaign-setup"]')
    assert "md:col-span-2" in host["class"]
    actions = response.context["more_actions"]
    assert [(item.label, item.separator_before) for item in actions] == [
        ("Campaign settings", False),
        ("Counters and labels", False),
        ("Asset types", False),
        ("Gang grouping", False),
        ("Phases & cycles", True),
        ("Battles", False),
        ("Activity log", False),
        ("Archive campaign", True),
    ]


def command_url(campaign, action, **query):
    return editor_url(campaign, action, **query).replace("/edit/", "/commands/")


def post(client, campaign, action, data, *, native=False, **query):
    target = editor_url if native else command_url
    return client.post(target(campaign, action, **query), data)


def setup_data(template):
    return {
        "request_key": str(uuid4()),
        "template_id": str(template.pk),
        "current_number": "1",
        "mode": "fixed",
        "date_mode": "planned",
        "date_start": "2026-11-01",
        "cycle_interval": "1",
        "cycle_unit": "weeks",
    }


class TestFlagAndOwnership:
    def test_closed_flag_hides_the_workflow_and_dashboard_link(
        self, client, campaign, template
    ):
        assert client.get(schedule_url(campaign)).status_code == 404
        assert client.get(editor_url(campaign, "setup")).status_code == 404
        assert post(client, campaign, "setup", setup_data(template)).status_code == 404
        page = client.get(reverse("n26-campaign", args=[campaign.pk]))
        assert page.status_code == 200
        assert "Set up phases & cycles" not in [
            item["label"] for item in page.context["campaign_setup"]["items"]
        ]
        assert not CampaignSchedule.objects.exists()

    def test_an_empty_schedule_offers_setup_only_to_the_arbitrator(
        self, client, campaign, opened
    ):
        assert props(client.get(schedule_url(campaign)))["actions"] == {
            "setup": editor_url(campaign, "setup")
        }
        client.force_login(User.objects.create_user("planning-reader"))
        assert props(client.get(schedule_url(campaign)))["actions"] == {}
        assert client.get(editor_url(campaign, "setup")).status_code == 404

    def test_readers_get_no_management_links_or_commands(
        self, client, campaign, configured
    ):
        client.force_login(User.objects.create_user("planning-player"))
        display = props(client.get(schedule_url(campaign)))
        assert display["currentName"] == "Cycle 1"
        assert display["actions"] == {}
        assert all(not row["editHref"] for row in display["rows"])
        assert all(
            not phase["editHref"] and not phase["duplicateHref"]
            for phase in display["phases"]
        )
        assert client.get(editor_url(campaign, "plan")).status_code == 404
        assert post(client, campaign, "plan", {}).status_code == 404

    def test_a_foreign_cycle_cannot_be_read_through_another_campaign(
        self, client, campaign, configured, campaign_type
    ):
        other = found_campaign("Elsewhere", campaign_type, owner=campaign.owner)
        url = reverse(
            "n26-campaign-cycle", args=[other.pk, configured.current_cycle_id]
        )
        assert client.get(url).status_code == 404


class TestSharedCommands:
    @pytest.mark.parametrize("number", ["", "missing", "4"])
    def test_setup_current_number_is_optional_and_defaults_to_one(
        self, client, campaign, opened, template, number
    ):
        initial = props(client.get(editor_url(campaign, "setup")))["editor"]
        assert initial["values"]["current_number"] == "1"
        data = {**setup_data(template), "current_number": number}
        if number == "missing":
            data.pop("current_number")
        response = post(client, campaign, "setup", data)
        assert response.status_code == 200
        state = cycles.load(campaign)
        assert state.current.order == (4 if number == "4" else 1)
        assert not campaign.cycle_transitions.exists()

    @pytest.mark.parametrize("native", [False, True])
    @pytest.mark.parametrize("materialise", [False, True])
    def test_setup_without_current_cycle_keeps_previews_until_explicit_start(
        self, client, campaign, opened, template, native, materialise
    ):
        from n26.core.battle_workflow import form_for
        from n26.core.cycle_display import dashboard_summary
        from n26.core.cycle_selection import options
        from n26.core.models import Gang

        response = post(
            client,
            campaign,
            "setup",
            {
                **setup_data(template),
                "mode": "repeating",
                "no_current": "on",
                "current_number": "",
            },
            native=native,
        )
        assert response.status_code == (302 if native else 200), (
            response.content.decode()
            if not native
            else props(response)["editor"]["errors"]
        )
        state = cycles.load(campaign)
        assert state.current is state.current_phase is None
        assert not state.cycles
        assert CampaignSchedule.objects.get(campaign=campaign).current_cycle_id is None
        assert not campaign.cycle_transitions.exists()
        display = build(campaign, campaign.owner)
        assert display.currentName == "No current cycle" and display.currentPhase == ""
        assert all(c.state == "Projected" for c in display.rows)
        assert dashboard_summary(campaign, campaign.owner).name == "No current cycle"
        assert (
            form_for(campaign, campaign.owner, Gang.objects.none()).initial["cycle"]
            is None
        )
        choices = options(campaign)
        assert choices["currentValue"] is None
        assert choices["choices"][0]["order"] == 1
        assert not any(c["isCurrent"] for c in choices["choices"])
        if materialise:
            target = s.project(state, limit=3)[-1]
            cycles.edit_cycle(
                campaign,
                actor=campaign.owner,
                target=target.ref,
                details=s.CycleDetails(target.phase_id),
                expected_revision=state.revision,
                request_key=uuid4(),
            )
            state = cycles.load(campaign)
            assert state.current is None
            assert not campaign.cycle_transitions.exists()
        start = {
            "request_key": str(uuid4()),
            "expected_revision": state.revision,
            "expected_current": "",
        }
        for _ in range(2):
            assert post(client, campaign, "start", start).status_code == 200
        after = cycles.load(campaign)
        assert after.current.order == 1
        assert after.next_position == len(after.cycles) == (3 if materialise else 1)
        assert campaign.cycle_transitions.count() == 1

    def test_no_current_state_survives_flag_changes_and_can_start_in_a_running_campaign(
        self, client, campaign, opened, template
    ):
        from n26.core.campaigns import campaign_operation

        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.set_status("in_progress")
        response = post(
            client,
            campaign,
            "setup",
            {**setup_data(template), "no_current": "on", "current_number": "0"},
        )
        assert response.status_code == 200
        before = cycles.load(campaign)
        assert before.current is None and before.status == "in_progress"
        assert not campaign.cycle_transitions.exists()
        opened.delete()
        assert client.get(schedule_url(campaign)).status_code == 404
        assert (
            post(
                client,
                campaign,
                "start",
                {
                    "expected_revision": before.revision,
                    "expected_current": "",
                    "request_key": str(uuid4()),
                },
            ).status_code
            == 404
        )
        assert cycles.load(campaign) == before
        FeatureFlag.objects.create(
            slug=CYCLE_TRACKING,
            name="Campaign cycles",
            availability=Availability.EVERYONE,
        )
        initial = props(client.get(editor_url(campaign, "start")))["editor"]
        assert initial["heading"] == "Start first cycle"
        assert post(client, campaign, "start", initial["values"]).status_code == 200
        assert cycles.load(campaign).current.order == 1

    @pytest.mark.parametrize("json_read", [False, True])
    def test_saved_notices_preserve_the_design_system_tone_with_one_message_owner(
        self, client, campaign, configured, json_read
    ):
        editor = props(
            client.get(editor_url(campaign, "cycle", cycle=configured.current_cycle_id))
        )["editor"]
        response = post(
            client,
            campaign,
            "cycle",
            {**editor["values"], "custom_name": "Opening week"},
            cycle=configured.current_cycle_id,
        )
        assert response.status_code == 200
        response = client.get(
            schedule_url(campaign),
            headers={"Accept": "application/json"} if json_read else {},
        )
        if json_read:
            notices = response.json()["notices"]
        else:
            notices = props(response)["notices"]
            assert not BeautifulSoup(response.content, "html.parser").select(
                "[data-message]"
            )
        assert notices == [{"message": "Campaign schedule saved.", "tone": "success"}]

    @pytest.mark.parametrize("native", [False, True])
    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_date_shift_moves_later_saved_cycles_and_projections_and_replays_once(
        self, client, campaign, configured, native
    ):
        from datetime import timedelta

        future = s.project(configured, limit=2)[-1]
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=future.ref,
            details=s.CycleDetails(
                future.phase_id, starts_on=future.starts_on, ends_on=future.ends_on
            ),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        selected = before.cycles[1]
        query = {"cycle": selected.id, "fields": "dates"}
        editor = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        data = {
            **editor["values"],
            "ends_on": (selected.details.ends_on - timedelta(days=2)).isoformat(),
            "shift_later": "on",
        }
        for _ in range(2):
            response = post(client, campaign, "cycle", data, native=native, **query)
            assert response.status_code == (302 if native else 200)
        after = cycles.load(campaign)
        assert after.revision == before.revision + 1
        assert after.cycles[0] == before.cycles[0]
        assert after.cycles[2].id == before.cycles[2].id
        assert after.cycles[2].source == before.cycles[2].source
        assert after.cycles[2].details.starts_on == before.cycles[
            2
        ].details.starts_on - timedelta(days=2)
        assert s.project(after)[0].starts_on == s.project(before)[
            0
        ].starts_on - timedelta(days=2)
        assert after.current_cycle_id == before.current_cycle_id
        assert not campaign.cycle_transitions.exists()
        changed = post(client, campaign, "cycle", {**data, "shift_later": ""}, **query)
        assert changed.status_code == 409
        assert cycles.load(campaign) == after

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_replacement_pattern_credits_the_saved_phase_and_preserves_navigator_order(
        self, client, campaign, configured
    ):
        from n26.core.cycle_selection import options

        future = s.project(configured, limit=1)[0]
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=future.ref,
            details=s.CycleDetails(future.phase_id),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        editor = props(client.get(editor_url(campaign, "pattern")))["editor"]
        response = post(
            client,
            campaign,
            "pattern",
            {
                **editor["values"],
                "mode": "repeating",
                "steps": json.dumps(
                    [asdict(step) for step in configured.plan.steps[:2]]
                ),
            },
        )
        assert response.status_code == 200
        after = cycles.load(campaign)
        assert after.cycles == before.cycles
        assert after.plan.start_position == after.next_position == 2
        following = s.project(after, limit=2)
        assert [p.order for p in following] == [3, 4]
        assert [p.phase_id for p in following] == [
            configured.plan.steps[0].phase_id,
            configured.plan.steps[1].phase_id,
        ]
        choice = next(c for c in options(campaign)["choices"] if c["order"] == 3)
        assert choice["name"] == "Cycle 3"
        assert choice["phase"] == after.phases[0].details.name

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_repeating_tail_summary_tracks_the_visible_boundary_and_pattern(
        self, campaign, configured
    ):
        display = build(campaign, campaign.owner)
        assert display.plan["mode"] == "repeating"
        assert display.plan["startsAfter"] == "Cycle 13"
        bounded = build(campaign, campaign.owner, preview=2)
        assert bounded.plan["startsAfter"] == "Cycle 3"
        assert bounded.plan["steps"] == [asdict(step) for step in configured.plan.steps]

    @pytest.mark.parametrize("action", ["template", "save-template"])
    def test_retired_template_actions_only_confirm_previously_committed_commands(
        self, client, campaign, configured, template, action
    ):
        key = uuid4()
        common = {
            "actor": campaign.owner,
            "expected_revision": configured.revision,
            "request_key": key,
        }
        if action == "save-template":
            campaign.owner.is_staff = True
            campaign.owner.save(update_fields=["is_staff"])
            cycles.save_template(campaign, name="Earlier private copy", **common)
            campaign.owner.is_staff = False
            campaign.owner.save(update_fields=["is_staff"])
            values = {"name": "Earlier private copy"}
            assert cycles.save_template(
                campaign, name=values["name"], **common
            ).replayed
        else:
            cycles.apply_template(
                campaign, template_id=template.pk, mode="fixed", **common
            )
            values = {"template_id": str(template.pk), "mode": "fixed"}
        values.update(request_key=str(key), expected_revision=str(configured.revision))
        count = campaign.cycle_commands.count()
        template_count = CampaignScheduleTemplate.objects.count()
        recovered = props(client.get(editor_url(campaign, action)))["editor"]
        assert recovered["context"]["unavailable"]
        assert post(client, campaign, action, values).status_code == 200
        assert post(client, campaign, action, values, native=True).status_code == 302
        assert (
            post(
                client, campaign, action, {**values, "request_key": str(uuid4())}
            ).status_code
            == 404
        )
        changed = {
            **values,
            **(
                {"name": "Other copy"}
                if action == "save-template"
                else {"mode": "repeating"}
            ),
        }
        assert post(client, campaign, action, changed).status_code == 409
        assert campaign.cycle_commands.count() == count
        assert CampaignScheduleTemplate.objects.count() == template_count

    def test_edits_and_projected_saves_return_to_the_edited_history_page(
        self, client, campaign, configured
    ):
        cycles.replace_plan(
            campaign,
            actor=campaign.owner,
            steps=configured.plan.steps,
            mode="repeating",
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        target = s.project(state, limit=60)[-1]
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        for query in (
            {"cycle": state.cycles[-1].id},
            {
                "plan": state.plan.id,
                "position": s.project(state)[0].source.position.index,
            },
        ):
            prepared = props(client.get(editor_url(campaign, "cycle", **query)))[
                "editor"
            ]
            response = post(
                client,
                campaign,
                "cycle",
                {**prepared["values"], "custom_name": "Across history"},
                **query,
            )
            assert response.status_code == 200
            destination = response.json()["nextUrl"]
            assert "?page=2#cycle-" in destination
            listed = props(client.get(destination))
            assert any(row["name"] == "Across history" for row in listed["rows"])
        assert cycles.load(campaign).current_cycle_id == configured.current_cycle_id

    @pytest.mark.parametrize("native", [False, True])
    def test_malformed_phase_deletion_returns_validation_without_writing(
        self, client, campaign, configured, native
    ):
        before = campaign.cycle_commands.count()
        response = post(
            client,
            campaign,
            "delete-phase",
            {
                "phase_id": "bad",
                "expected_revision": configured.revision,
                "request_key": str(uuid4()),
            },
            native=native,
            phase="bad",
        )
        assert response.status_code == (200 if native else 422)
        errors = (
            props(response)["editor"]["errors"] if native else response.json()["errors"]
        )
        assert errors["phase_id"] == ["Select a valid phase."]
        assert campaign.cycle_commands.count() == before
        assert cycles.load(campaign).revision == configured.revision

    @pytest.mark.parametrize("native", [False, True])
    def test_quick_date_edits_share_the_cycle_command_and_return_to_the_list(
        self, client, campaign, configured, native
    ):
        query = {"cycle": configured.current_cycle_id, "fields": "dates"}
        editor = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        assert editor["heading"] == "Edit cycle dates"
        assert editor["context"]["datesOnly"] is True
        assert "fields=dates" in editor["commandHref"]
        assert "fields=dates" in editor["recoveryKey"]
        data = {
            **editor["values"],
            "starts_on": "2050-01-01",
            "ends_on": "2050-01-07",
            "shift_later": "on",
        }
        response = post(client, campaign, "cycle", data, native=native, **query)
        assert response.status_code == (302 if native else 200)
        target = response.url if native else response.json()["nextUrl"]
        assert (
            target
            == schedule_url(campaign) + "?page=1#cycle-" + configured.current_cycle_id
        )
        changed = cycles.load(campaign)
        assert changed.current.details.starts_on.isoformat() == "2050-01-01"
        assert changed.current.details.phase_id == configured.current.details.phase_id
        assert changed.current.source == configured.current.source

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_json_editor_reads_share_dates_permissions_and_the_html_contract(
        self, client, campaign, configured
    ):
        cycle = configured.current
        url = editor_url(campaign, "cycle", cycle=cycle.id)
        html = props(client.get(url))["editor"]
        response = client.get(url, HTTP_ACCEPT="application/json")
        assert response.status_code == 200
        editor = response.json()["schedule"]["editor"]
        assert editor["commandHref"] == html["commandHref"]
        assert editor["values"]["starts_on"] == cycle.details.starts_on.isoformat()
        assert editor["values"]["ends_on"] == cycle.details.ends_on.isoformat()
        assert CampaignCycle.objects.filter(campaign=campaign).count() == 1
        client.force_login(User.objects.create_user("json-schedule-reader"))
        assert client.get(url, HTTP_ACCEPT="application/json").status_code == 404
        read = client.get(
            schedule_url(campaign), HTTP_ACCEPT="application/json"
        ).json()["schedule"]
        assert read["actions"] == {}
        assert read["rows"][1]["startsOn"]

    @pytest.mark.parametrize("native", [False, True])
    @pytest.mark.parametrize("bound", ["starts_on", "ends_on"])
    def test_current_editors_accept_either_date_independently(
        self, client, campaign, configured, native, bound
    ):
        query = {"cycle": configured.current_cycle_id}
        editor = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        data = {**editor["values"], bound: ""}
        response = post(client, campaign, "cycle", data, native=native, **query)
        assert response.status_code == (302 if native else 200)
        changed = cycles.load(campaign)
        assert getattr(changed.current.details, bound) is None
        assert changed.current.id == configured.current.id
        assert changed.current.source == configured.current.source
        assert post(
            client, campaign, "cycle", data, native=native, **query
        ).status_code == (302 if native else 200)
        assert cycles.load(campaign) == changed

    @pytest.mark.parametrize("native", [False, True])
    def test_setup_retry_succeeds_after_the_schedule_already_exists(
        self, client, campaign, opened, template, native
    ):
        data = setup_data(template)
        first = post(client, campaign, "setup", data, native=native)
        second = post(client, campaign, "setup", data, native=native)
        assert first.status_code == second.status_code == (302 if native else 200)
        assert CampaignCycle.objects.filter(campaign=campaign).count() == 7
        assert campaign.cycle_commands.count() == 1
        assert len(props(client.get(schedule_url(campaign)))["rows"]) == 7

    @pytest.mark.parametrize("native", [False, True])
    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_editing_a_projection_saves_the_prefix_without_advancing(
        self, client, campaign, configured, native
    ):
        selected = s.project(configured)[2]
        query = {"plan": configured.plan.id, "position": selected.source.position.index}
        prepared = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        assert selected.name in prepared["lead"]
        assert json.loads(prepared["values"]["target"]) == ref_data(selected.ref)
        data = {**prepared["values"], "custom_name": "Market week"}
        response = post(client, campaign, "cycle", data, native=native, **query)
        assert response.status_code == (302 if native else 200)
        after = cycles.load(campaign)
        assert after.current_cycle_id == configured.current_cycle_id
        assert [cycle.order for cycle in after.cycles] == [1, 2, 3, 4]
        assert after.cycles[-1].name == "Market week"
        assert (
            props(client.get(schedule_url(campaign)))["rows"][3]["state"]
            == "Saved future"
        )

    @pytest.mark.parametrize("native", [False, True])
    def test_revision_conflicts_preserve_the_draft_and_show_current_facts(
        self, client, campaign, configured, native
    ):
        query = {"cycle": configured.current_cycle_id}
        draft = props(client.get(editor_url(campaign, "cycle", **query)))["editor"][
            "values"
        ]
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            request_key=uuid4(),
            expected_revision=configured.revision,
            target=s.SavedCycleRef(configured.current_cycle_id),
            details=s.CycleDetails(
                configured.current_phase.id, custom_name="Current server name"
            ),
        )
        response = post(
            client,
            campaign,
            "cycle",
            {**draft, "custom_name": "Retained draft"},
            native=native,
            **query,
        )
        if native:
            editor = props(response)["editor"]
            assert editor["initialConflict"]
            assert editor["values"]["custom_name"] == "Retained draft"
            current = editor["current"]
        else:
            assert response.status_code == 409
            assert response.json()["code"] == "revision_conflict"
            assert response.json()["reviewUrl"] == schedule_url(campaign)
            current = response.json()["current"]
        assert current["cycle"] == "Current server name"
        assert current["phase"] == "Occupation"

    def test_a_reused_key_with_different_input_is_not_a_revision_conflict(
        self, client, campaign, opened, template
    ):
        data = setup_data(template)
        assert post(client, campaign, "setup", data).status_code == 200
        response = post(client, campaign, "setup", {**data, "current_number": "2"})
        assert response.status_code == 409
        assert response.json()["code"] == "request_key_conflict"
        assert "current" not in response.json()

    def test_configured_campaigns_offer_no_template_controls_or_commands(
        self, client, campaign, configured
    ):
        display = props(client.get(schedule_url(campaign)))
        assert (
            "template" not in display["actions"]
            and "saveTemplate" not in display["actions"]
        )
        count = campaign.cycle_commands.count()
        for action in ("template", "save-template"):
            assert client.get(editor_url(campaign, action)).status_code == 404
            assert post(client, campaign, action, {}).status_code == 404
        assert campaign.cycle_commands.count() == count

    def test_setup_customises_an_independent_copy_before_the_only_write(
        self, client, campaign, template, opened
    ):
        import copy

        definition = copy.deepcopy(template.definition)
        definition["phases"][0]["details"]["name"] = "Campaign opening"
        definition["steps"][0]["count"] = 2
        page = props(client.get(editor_url(campaign, "setup")))["editor"]
        assert page["templates"][0]["definition"] == template.definition
        assert not CampaignSchedule.objects.filter(campaign=campaign).exists()
        data = {**setup_data(template), "setup_definition": json.dumps(definition)}
        assert post(client, campaign, "setup", data).status_code == 200
        state = cycles.load(campaign)
        assert state.current_phase.details.name == "Campaign opening"
        assert state.plan.steps[0].count == 2
        assert state.phases[0].id != definition["phases"][0]["id"]
        template.refresh_from_db()
        assert template.definition["steps"][0]["count"] == 3
        assert post(client, campaign, "setup", data).status_code == 200
        assert campaign.cycle_commands.count() == 1

    @pytest.mark.parametrize("native", [False, True])
    def test_custom_setup_needs_no_template_and_keeps_complete_phase_details(
        self, client, campaign, opened, native
    ):
        page = props(client.get(editor_url(campaign, "setup")))["editor"]
        assert page["values"]["template_id"] == ""
        definition = json.loads(page["values"]["setup_definition"])
        assert len(definition["phases"]) == 1
        assert definition["phases"][0]["details"]["name"] == "Phase 1"
        assert definition["steps"][0]["count"] == 1
        details = definition["phases"][0]["details"]
        details.update(
            name="Opening",
            description="The gates open.",
            effects="Use the opening missions.",
        )
        details["rewards"]["win"] = {
            "credits": {
                "fixed": 25,
                "dice": {"count": 2, "sides": 6, "multiplier": 10},
            },
            "reputation": 2,
        }
        details["rewards"]["entry_credits"] = {"fixed": 50, "dice": None}
        data = {
            **page["values"],
            "setup_definition": json.dumps(definition),
            "no_current": "on",
        }
        first = post(client, campaign, "setup", data, native=native)
        assert first.status_code == (302 if native else 200)
        state = cycles.load(campaign)
        assert state.current is None
        assert len(state.cycles) == 1
        assert state.cycles[0].details.phase_id == state.phases[0].id
        assert not campaign.cycle_transitions.exists()
        assert asdict(state.phases[0].details) == details
        assert (
            post(client, campaign, "setup", data, native=native).status_code
            == first.status_code
        )
        assert campaign.cycle_commands.count() == 1
        campaign.refresh_from_db()
        assert campaign.status == "pre_campaign"
        changed = {
            **data,
            "setup_definition": json.dumps(
                {**definition, "steps": [{**definition["steps"][0], "count": 2}]}
            ),
        }
        rejected = post(client, campaign, "setup", changed, native=native)
        assert rejected.status_code == (200 if native else 409)
        if native:
            assert "A different change was saved from this form." in str(
                props(rejected)["editor"]["errors"]
            )
        assert campaign.cycle_commands.count() == 1

    @pytest.mark.parametrize("definition", [None, {}, {"phases": [], "steps": []}])
    def test_custom_setup_requires_an_explicit_valid_definition(
        self, client, campaign, opened, definition
    ):
        data = props(client.get(editor_url(campaign, "setup")))["editor"]["values"]
        data["setup_definition"] = (
            json.dumps(definition) if definition is not None else ""
        )
        assert post(client, campaign, "setup", data).status_code == 422
        assert not CampaignSchedule.objects.filter(campaign=campaign).exists()

    def test_custom_definition_cannot_bypass_template_ownership(
        self, client, campaign, opened
    ):
        other = User.objects.create_user("private-template-author")
        data = props(client.get(editor_url(campaign, "setup")))["editor"]["values"]
        private = CampaignScheduleTemplate.objects.create(
            owner=other, name="Private", definition=json.loads(data["setup_definition"])
        )
        data["template_id"] = str(private.pk)
        response = post(client, campaign, "setup", data)
        assert response.status_code == 422
        assert not CampaignSchedule.objects.filter(campaign=campaign).exists()

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_unchanged_future_plan_does_not_replay_consumed_cycles(
        self, client, campaign, configured
    ):
        values = props(client.get(editor_url(campaign, "pattern")))["editor"]["values"]
        assert [step["count"] for step in json.loads(values["steps"])] == [3, 1, 3]
        assert post(client, campaign, "pattern", values).status_code == 200
        after = cycles.load(campaign)
        assert after.plan.id == configured.plan.id
        assert after.next_position == configured.next_position
        assert len(s.project(after)) == 12


class TestFixedPlanConversion:
    @pytest.mark.parametrize("completed", [False, True])
    def test_phase_corrections_preserve_the_installed_fixed_endpoint(
        self, client, campaign, opened, template, completed
    ):
        cycles.configure(
            campaign,
            actor=campaign.owner,
            template_id=template.pk,
            current_position=6 if completed else 4,
            mode="fixed" if completed else "repeating",
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        cycles.replace_plan(
            campaign,
            actor=campaign.owner,
            steps=state.plan.steps
            if completed
            else (s.PlanStep("new-downtime", state.phases[1].id, 2),),
            mode="repeating",
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=s.SavedCycleRef(state.current.id),
            details=replace(
                state.current.details, phase_id=state.phases[0 if completed else 1].id
            ),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        editor = props(client.get(editor_url(campaign, "plan")))["editor"]
        assert post(client, campaign, "plan", editor["values"]).status_code == 200
        assert cycles.load(campaign) == before
        editor = props(client.get(editor_url(campaign, "plan")))["editor"]
        proposed = editor["context"]["fixedSteps"]
        assert [step["count"] for step in proposed] == ([] if completed else [2])
        data = {**editor["values"], "mode": "fixed", "steps": json.dumps(proposed)}
        assert post(client, campaign, "plan", data).status_code == 200
        after = cycles.load(campaign)
        assert after.cycles[: len(before.cycles)] == before.cycles
        assert len([c for c in after.cycles if not c.archived]) == 7
        assert s.project(after) == ()
        endpoint = props(client.get(editor_url(campaign, "plan")))["editor"]["context"][
            "fixedEndpoint"
        ]
        assert endpoint == 7

    @pytest.mark.parametrize("native", [False, True])
    def test_a_replacement_pattern_keeps_one_pass_when_switched_to_fixed(
        self, client, campaign, opened, template, native
    ):
        cycles.configure(
            campaign,
            actor=campaign.owner,
            template_id=template.pk,
            current_position=4,
            mode="repeating",
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        cycles.replace_plan(
            campaign,
            actor=campaign.owner,
            steps=(s.PlanStep("new-downtime", state.phases[1].id, 2),),
            mode="repeating",
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        editor = props(client.get(editor_url(campaign, "plan")))["editor"]
        proposed = editor["context"]["fixedSteps"]
        assert [step["count"] for step in proposed] == [2]
        data = {**editor["values"], "mode": "fixed", "steps": json.dumps(proposed)}
        assert post(client, campaign, "plan", data, native=native).status_code == (
            302 if native else 200
        )
        after = cycles.load(campaign)
        assert after.cycles[: len(before.cycles)] == before.cycles
        assert len(after.cycles) == 7
        assert after.current_cycle_id == before.current_cycle_id
        assert [cycle.order for cycle in after.cycles[5:]] == [6, 7]
        assert s.project(after) == ()

    @pytest.mark.parametrize("saved,last", [(2, 7), (6, 7), (7, 7), (9, 14)])
    def test_preview_reads_do_not_write_or_change_the_fixed_endpoint(
        self, client, campaign, opened, template, saved, last
    ):
        cycles.configure(
            campaign,
            actor=campaign.owner,
            template_id=template.pk,
            current_position=1,
            mode="repeating",
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        if saved > 2:
            target = next(c for c in s.project(state) if c.order == saved)
            cycles.edit_cycle(
                campaign,
                actor=campaign.owner,
                target=target.ref,
                details=s.CycleDetails(target.phase_id),
                expected_revision=state.revision,
                request_key=uuid4(),
            )
        before = cycles.load(campaign)
        counts = (
            campaign.cycles.count(),
            campaign.cycle_plans.count(),
            campaign.cycle_commands.count(),
            campaign.cycle_transitions.count(),
        )
        proposed = None
        for preview in (12, 24, 48):
            response = client.get(schedule_url(campaign), {"preview": preview})
            assert response.status_code == 200
            editor = props(client.get(editor_url(campaign, "plan")))["editor"]
            steps = editor["context"]["fixedSteps"]
            assert proposed is None or steps == proposed
            proposed = steps
            assert saved + sum(step["count"] for step in steps) == last
        assert cycles.load(campaign) == before
        assert counts == (
            campaign.cycles.count(),
            campaign.cycle_plans.count(),
            campaign.cycle_commands.count(),
            campaign.cycle_transitions.count(),
        )
        response = post(
            client,
            campaign,
            "plan",
            {**editor["values"], "mode": "fixed", "steps": json.dumps(proposed)},
        )
        assert response.status_code == 200
        after = cycles.load(campaign)
        assert after.cycles[:saved] == before.cycles
        assert len(after.cycles) == last
        assert s.project(after) == ()
        assert after.current.order == 2
        assert after.plan.mode == "fixed"
        endpoint = props(client.get(editor_url(campaign, "plan")))["editor"]["context"][
            "fixedEndpoint"
        ]
        assert endpoint == last


class TestDisplayReads:
    @pytest.mark.parametrize("reader", [False, True])
    def test_dashboard_effects_are_collapsed_plain_text_for_arbitrators_and_readers(
        self, client, campaign, configured, reader
    ):
        phase = configured.current_phase
        phase_effects = "<script>alert('phase')</script>\nApply after each battle."
        cycle_effects = "<img src=x onerror=alert('cycle')>\nUse the cycle rule."
        cycles.edit_phase(
            campaign,
            actor=campaign.owner,
            phase_id=phase.id,
            details=replace(phase.details, effects=phase_effects),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=s.SavedCycleRef(state.current_cycle_id),
            details=replace(state.current.details, effects=cycle_effects),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        if reader:
            client.force_login(User.objects.create_user("effects-reader"))
        response = client.get(reverse("n26-campaign", args=[campaign.pk]))
        assert response.status_code == 200
        page = BeautifulSoup(response.content, "html.parser")
        card = page.select_one("#campaign-cycle-summary")
        hosts = card.select('[data-react-name="campaign-effects"]')
        assert len(hosts) == 2
        for host, label, effects in zip(
            hosts,
            ["Phase effects", "Cycle effects"],
            [phase_effects, cycle_effects],
            strict=True,
        ):
            assert json.loads(page.find(id=host["data-react-props"]).string) == {
                "label": label,
                "effects": effects,
            }
            disclosure = host.select_one("details")
            assert not disclosure.has_attr("open")
            assert disclosure.select_one("summary").get_text(strip=True) == label
            assert disclosure.select_one("p").get_text() == effects
            assert not disclosure.select("script, img")

    def test_dashboard_omits_empty_effect_disclosures(
        self, client, campaign, configured
    ):
        response = client.get(reverse("n26-campaign", args=[campaign.pk]))
        card = BeautifulSoup(response.content, "html.parser").select_one(
            "#campaign-cycle-summary"
        )
        assert not card.select('[data-react-name="campaign-effects"]')

    def test_dashboard_card_counts_the_current_phase_and_exposes_existing_owner_workflows(
        self, client, campaign, configured
    ):
        summary = dashboard_summary(campaign, campaign.owner)
        assert (
            summary.order,
            summary.cycle_limit,
            summary.phase_position,
            summary.phase_count,
        ) == (1, 7, 1, 3)
        assert (summary.next_phase, summary.cycles_until_phase) == ("Downtime", 3)
        assert (summary.starts_on, summary.ends_on) == (
            date(2026, 11, 1),
            date(2026, 11, 7),
        )
        assert summary.action_href == editor_url(campaign, "start")
        reader = User.objects.create_user("summary-reader")
        assert dashboard_summary(campaign, reader).action_href == ""
        client.force_login(reader)
        page = BeautifulSoup(
            client.get(reverse("n26-campaign", args=[campaign.pk])).content,
            "html.parser",
        )
        card = page.select_one("#campaign-cycle-summary")
        assert "Cycle 1 of 3 in this phase" in card.get_text(" ", strip=True)
        assert not card.select_one('[aria-label="Edit campaign schedule"]')

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_dashboard_uses_saved_phase_changes_instead_of_the_cycles_original_plan(
        self, campaign, configured
    ):
        target = s.project(configured, limit=4)[-1]
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = dashboard_summary(campaign, campaign.owner)
        assert (before.phase_count, before.next_phase) == (3, "Downtime")
        state = cycles.load(campaign)
        downtime = next(
            phase for phase in state.phases if phase.details.name == "Downtime"
        )
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=s.SavedCycleRef(state.current_cycle_id),
            details=replace(state.current.details, phase_id=downtime.id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        summary = dashboard_summary(campaign, campaign.owner)
        assert (
            summary.phase_position,
            summary.phase_count,
            summary.cycles_until_phase,
        ) == (1, 1, 1)
        assert summary.next_phase == "Occupation"

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_dashboard_read_cost_does_not_grow_with_saved_repeating_history(
        self, campaign, configured
    ):
        cycles.replace_plan(
            campaign,
            actor=campaign.owner,
            steps=configured.plan.steps,
            mode="repeating",
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        with CaptureQueriesContext(connection) as small:
            before = dashboard_summary(campaign, campaign.owner)
        state = cycles.load(campaign)
        target = s.project(state, limit=60)[-1]
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        with CaptureQueriesContext(connection) as large:
            after = dashboard_summary(campaign, campaign.owner)
        assert len(large) <= len(small)
        assert (after.phase_position, after.phase_count, after.next_phase) == (
            before.phase_position,
            before.phase_count,
            before.next_phase,
        )
        assert after.cycle_limit is None

    def test_a_finished_dashboard_shows_history_without_a_transition_or_countdown(
        self, client, campaign, configured
    ):
        from n26.core.campaigns import campaign_operation

        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.set_status("post_campaign")
        summary = dashboard_summary(campaign, campaign.owner)
        assert summary.complete and not summary.action_href and not summary.next_phase
        response = client.get(reverse("n26-campaign", args=[campaign.pk]))
        card = BeautifulSoup(response.content, "html.parser").select_one(
            "#campaign-cycle-summary"
        )
        assert "Last phase" in card.get_text() and "Last cycle" in card.get_text()

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_saved_history_is_paginated_with_constant_query_growth(
        self, campaign, configured
    ):
        reader = campaign.owner
        with CaptureQueriesContext(connection) as before_queries:
            small = build(campaign, reader)
        cycles.replace_plan(
            campaign,
            actor=reader,
            steps=configured.plan.steps,
            mode="repeating",
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        target = s.project(state, limit=60)[-1]
        cycles.edit_cycle(
            campaign,
            actor=reader,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        with CaptureQueriesContext(connection) as after_queries:
            large = build(campaign, reader)
        assert len(before_queries) == len(after_queries)
        assert len(small.rows) == 13
        assert len(large.rows) == 50
        assert large.nextHref and not large.moreHref
        second = build(campaign, reader, page=2)
        assert [(phase["id"], phase["number"]) for phase in second.phases] == [
            (phase["id"], phase["number"]) for phase in large.phases
        ]
        assert len([row for row in second.rows if row.state == "Saved future"]) == 11
        assert second.moreHref

    def test_actual_times_are_distinct_from_the_editable_planning_dates(
        self, campaign, configured
    ):
        reader = campaign.owner
        cycles.start(
            campaign,
            actor=reader,
            expected_current=configured.current_cycle_id,
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        cycles.advance(
            campaign,
            actor=reader,
            expected_current=before.current_cycle_id,
            expected_revision=before.revision,
            request_key=uuid4(),
        )
        display = build(campaign, reader)
        past, current = display.rows[:2]
        assert past.startedAt and past.endedAt and current.startedAt
        assert past.endedAt == current.startedAt
        assert not current.endedAt
        assert past.startsOn == configured.current.details.starts_on.isoformat()
        assert past.endsOn == configured.current.details.ends_on.isoformat()

    def test_dashboard_links_the_current_cycle_and_phase(
        self, client, campaign, configured
    ):
        page = client.get(reverse("n26-campaign", args=[campaign.pk]))
        assert page.status_code == 200
        body = page.content.decode()
        assert schedule_url(campaign) in body
        assert "Occupation" in body
        assert any(
            item.label == "Phases & cycles" for item in page.context["more_actions"]
        )

    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_projection_growth_does_not_add_queries(self, campaign, configured):
        reader = campaign.owner

        def read(preview):
            with CaptureQueriesContext(connection) as queries:
                display = build(campaign, reader, preview=preview)
            return display, len(queries)

        small, count = read(1)
        large, larger_count = read(12)
        assert count == larger_count
        assert len(small.rows) == 2 and len(large.rows) == 13


class TestRecoveryAfterTheCommandChangesItsOwnPage:
    def test_setup_reload_keeps_the_form_shape_and_recovery_key(
        self, client, campaign, opened, template
    ):
        initial = props(client.get(editor_url(campaign, "setup")))["editor"]
        data = {
            **initial["values"],
            "template_id": str(template.pk),
            "mode": "fixed",
            "current_number": "1",
            "date_start": "2026-11-01",
        }
        assert post(client, campaign, "setup", data).status_code == 200
        recovered = props(client.get(editor_url(campaign, "setup")))["editor"]
        assert recovered["context"]["unavailable"]
        assert recovered["recoveryKey"] == initial["recoveryKey"]
        assert recovered["values"].keys() == initial["values"].keys()
        assert post(client, campaign, "setup", data).status_code == 200
        assert campaign.cycle_commands.count() == 1

    @pytest.mark.parametrize("status", ["pre_campaign", "post_campaign"])
    def test_native_stale_advance_after_status_change_retains_the_conflict_instead_of_failing(
        self, client, campaign, configured, status
    ):
        from n26.core.campaigns import campaign_operation

        state = cycles.load(campaign)
        cycles.start(
            campaign,
            actor=campaign.owner,
            expected_current=state.current_cycle_id,
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        before = props(client.get(editor_url(campaign, "advance")))["editor"]
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.set_status(status)
        failed = post(client, campaign, "advance", before["values"], native=True)
        editor = props(failed)["editor"]
        assert editor["initialConflict"]
        assert editor["values"]["request_key"] == before["values"]["request_key"]
        assert editor["context"]["unavailable"]

    def test_deletion_reload_can_retry_the_original_phase_command(
        self, client, campaign, configured
    ):
        cycles.duplicate_phase(
            campaign,
            actor=campaign.owner,
            phase_id=configured.phases[0].id,
            name="Unused copy",
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        occurrence = cycles.load(campaign).occurrences[-1]
        query = {"phase": occurrence.id}
        before = props(client.get(editor_url(campaign, "delete-phase", **query)))[
            "editor"
        ]
        assert (
            post(
                client, campaign, "delete-phase", before["values"], **query
            ).status_code
            == 200
        )
        after = props(client.get(editor_url(campaign, "delete-phase", **query)))[
            "editor"
        ]
        assert after["context"]["unavailable"]
        assert after["values"].keys() == before["values"].keys()
        assert after["recoveryKey"] == before["recoveryKey"]
        assert (
            post(
                client, campaign, "delete-phase", before["values"], **query
            ).status_code
            == 200
        )

    def test_advancing_into_the_final_cycle_keeps_reload_recovery_available(
        self, client, campaign, configured
    ):
        state = cycles.load(campaign)
        cycles.start(
            campaign,
            actor=campaign.owner,
            expected_current=state.current_cycle_id,
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        for _ in range(5):
            state = cycles.load(campaign)
            cycles.advance(
                campaign,
                actor=campaign.owner,
                expected_current=state.current_cycle_id,
                expected_revision=state.revision,
                request_key=uuid4(),
            )
        before = props(client.get(editor_url(campaign, "advance")))["editor"]
        assert post(client, campaign, "advance", before["values"]).status_code == 200
        assert cycles.load(campaign).current.order == 7
        after = props(client.get(editor_url(campaign, "advance")))["editor"]
        assert after["context"]["unavailable"]
        assert after["values"].keys() == before["values"].keys()
        assert after["recoveryKey"] == before["recoveryKey"]
        assert post(client, campaign, "advance", before["values"]).status_code == 200
        assert cycles.load(campaign).current.order == 7


class TestManualCycleDates:
    def test_setup_defaults_to_manual_and_existing_calendar_stays_planned(
        self, client, campaign, opened, template
    ):
        editor = props(client.get(editor_url(campaign, "setup")))["editor"]
        assert editor["values"]["date_mode"] == "manual"
        response = post(
            client, campaign, "setup", {**setup_data(template), "date_mode": "planned"}
        )
        assert response.status_code == 200
        editor = props(client.get(editor_url(campaign, "plan")))["editor"]
        assert editor["values"]["date_mode"] == "planned"

    def test_manual_selection_ignores_inactive_calendar_fields(
        self, client, campaign, opened, template
    ):
        response = post(
            client,
            campaign,
            "setup",
            {
                **setup_data(template),
                "date_mode": "manual",
                "date_start": "bad-date",
                "cycle_interval": "bad-length",
                "cycle_unit": "bad-unit",
            },
        )
        assert response.status_code == 200
        assert cycles.load(campaign).calendar is None

    def test_new_planned_dates_fill_generated_future_cycles_after_current(
        self, client, campaign, opened, template
    ):
        assert (
            post(
                client,
                campaign,
                "setup",
                {**setup_data(template), "date_mode": "manual"},
            ).status_code
            == 200
        )
        before = cycles.load(campaign)
        editor = props(client.get(editor_url(campaign, "plan")))["editor"]
        assert (
            post(
                client,
                campaign,
                "plan",
                {
                    **editor["values"],
                    "date_mode": "planned",
                    "date_start": "2026-12-01",
                },
            ).status_code
            == 200
        )
        state = cycles.load(campaign)
        assert state.current == before.current
        assert [(c.id, c.source) for c in state.cycles] == [
            (c.id, c.source) for c in before.cycles
        ]
        assert state.cycles[1].details.starts_on == date(2026, 12, 1)
        assert all(c.details.starts_on and c.details.ends_on for c in state.cycles[1:])
        assert s.project(state) == ()

    @pytest.mark.parametrize("native", [False, True])
    def test_manual_setup_fills_dates_when_cycles_start_and_end(
        self, client, campaign, opened, template, native
    ):
        response = post(
            client,
            campaign,
            "setup",
            {
                **setup_data(template),
                "mode": "repeating",
                "date_mode": "manual",
                "no_current": "on",
            },
            native=native,
        )
        assert response.status_code == (302 if native else 200)
        assert cycles.load(campaign).calendar is None
        for action in ("start", "advance"):
            editor = props(client.get(editor_url(campaign, action)))["editor"]
            assert post(
                client, campaign, action, editor["values"], native=native
            ).status_code == (302 if native else 200)
        state = cycles.load(campaign)
        assert state.current.order == 2
        started, advanced = campaign.cycle_transitions.order_by("occurred_at")
        assert state.cycles[0].details.starts_on == timezone.localdate(
            started.occurred_at
        )
        assert state.cycles[0].details.ends_on == timezone.localdate(
            advanced.occurred_at
        )
        assert state.current.details.starts_on == timezone.localdate(
            advanced.occurred_at
        )
        assert state.current.details.ends_on is None
        target = s.project(state)[2]
        query = {"plan": state.plan.id, "position": target.source.position.index}
        editor = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        assert post(
            client, campaign, "cycle", editor["values"], native=native, **query
        ).status_code == (302 if native else 200)
        assert len(cycles.load(campaign).cycles) == target.order
        assert all(
            c.details.starts_on is c.details.ends_on is None
            for c in cycles.load(campaign).cycles[2:]
        )

    @pytest.mark.parametrize("native", [False, True])
    @pytest.mark.parametrize("configured", ["repeating"], indirect=True)
    def test_switching_date_modes_preserves_saved_ranges_and_replays(
        self, client, campaign, configured, native
    ):
        editor = props(client.get(editor_url(campaign, "plan")))["editor"]
        clear = {**editor["values"], "date_mode": "manual"}
        for _ in range(2):
            assert post(client, campaign, "plan", clear, native=native).status_code == (
                302 if native else 200
            )
        state = cycles.load(campaign)
        assert state.calendar is None
        assert state.cycles == configured.cycles
        editor = props(client.get(editor_url(campaign, "plan")))["editor"]
        planned = {
            **editor["values"],
            "date_mode": "planned",
            "date_start": "2026-12-01",
        }
        for _ in range(2):
            assert post(
                client, campaign, "plan", planned, native=native
            ).status_code == (302 if native else 200)
        state = cycles.load(campaign)
        assert state.cycles == configured.cycles
        assert s.project(state)[0].starts_on == date(2026, 12, 1)

    @pytest.mark.parametrize("native", [False, True])
    def test_cycle_dates_can_be_cleared_after_a_partial_edit(
        self, client, campaign, configured, native
    ):
        query = {"cycle": configured.current.id, "fields": "dates"}
        editor = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        partial = {**editor["values"], "ends_on": ""}
        assert post(
            client, campaign, "cycle", partial, native=native, **query
        ).status_code == (302 if native else 200)
        editor = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        clear = {**editor["values"], "starts_on": "", "ends_on": ""}
        assert post(
            client, campaign, "cycle", clear, native=native, **query
        ).status_code == (302 if native else 200)
        state = cycles.load(campaign)
        assert state.current.details.starts_on is state.current.details.ends_on is None


class TestDeletionWorkflow:
    @pytest.mark.parametrize("native", [False, True])
    @pytest.mark.parametrize("action", ["delete-cycle", "delete-phase"])
    def test_unused_deletion_confirmations_preserve_current_and_retry(
        self, client, campaign, configured, native, action
    ):
        selected = configured.cycles[4]
        query = (
            {"cycle": selected.id}
            if action == "delete-cycle"
            else {"phase": selected.occurrence_id}
        )
        editor = props(client.get(editor_url(campaign, action, **query)))["editor"]
        assert not editor["context"]["replacesCurrent"]
        data = editor["values"]
        for _ in range(2):
            assert post(
                client, campaign, action, data, native=native, **query
            ).status_code == (302 if native else 200)
        state = cycles.load(campaign)
        assert state.current == configured.current
        assert next(c for c in state.cycles if c.id == selected.id).archived
        assert props(client.get(editor_url(campaign, action, **query)))["editor"][
            "context"
        ]["unavailable"]

    def test_deleted_cycles_are_hidden_with_consecutive_order_and_bounded_queries(
        self, campaign, configured
    ):
        cycles.replace_plan(
            campaign,
            actor=campaign.owner,
            mode="repeating",
            steps=configured.plan.steps,
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        target = s.project(state, limit=60)[-1]
        cycles.edit_cycle(
            campaign,
            actor=campaign.owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        cycles.delete_phase(
            campaign,
            actor=campaign.owner,
            phase_id=state.phases[1].id,
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        reader = campaign.owner
        with CaptureQueriesContext(connection) as first_queries:
            first = build(campaign, reader)
        with CaptureQueriesContext(connection) as last_queries:
            last = build(campaign, reader, page=2)
        assert len(first_queries) == len(last_queries)
        assert [
            row.order for row in (*first.rows, *last.rows) if row.state != "Projected"
        ] == list(
            range(
                1,
                CampaignCycle.objects.filter(campaign=campaign, archived=False).count()
                + 1,
            )
        )
        assert all(
            row.phaseId != state.phases[1].id for row in (*first.rows, *last.rows)
        )
        assert (
            sum(phase["count"] for phase in first.phases)
            == CampaignCycle.objects.filter(campaign=campaign, archived=False).count()
        )
        assert len([row for row in first.rows if row.state != "Projected"]) == 50
        assert first.nextHref

    def test_last_phase_can_be_removed_and_rebuilt(
        self, client, campaign, opened, template
    ):
        cycles.configure(
            campaign,
            actor=campaign.owner,
            template_id=template.pk,
            current_position=None,
            mode="fixed",
            request_key=uuid4(),
        )
        original = cycles.load(campaign)
        for occurrence in original.occurrences:
            state = cycles.load(campaign)
            cycles.author_timeline(
                campaign,
                actor=campaign.owner,
                action="remove_occurrence",
                occurrence_id=occurrence.id,
                expected_revision=state.revision,
                request_key=uuid4(),
            )
        display = props(client.get(schedule_url(campaign)))
        assert not display["phases"] and not display["rows"]
        assert "transition" not in display["actions"]
        assert display["actions"]["addPhase"]
        editor = props(client.get(display["actions"]["addPhase"]))["editor"]
        response = post(
            client, campaign, "add-phase", {**editor["values"], "name": "Fresh phase"}
        )
        assert response.status_code == 200
        state = cycles.load(campaign)
        occurrence = next(o for o in state.occurrences if not o.archived)
        cycles.author_timeline(
            campaign,
            actor=campaign.owner,
            action="insert_cycle",
            occurrence_id=occurrence.id,
            details=s.CycleDetails(occurrence.phase_id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        assert build(campaign, campaign.owner).actions["transition"]


@pytest.mark.parametrize("native", [False, True])
def test_start_after_clearing_an_unused_current_choice_requires_selection_and_replays(
    client, campaign, configured, native
):
    state = configured
    cycles.delete_cycle(
        campaign,
        actor=campaign.owner,
        target=s.SavedCycleRef(state.current_cycle_id),
        no_current=True,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    editor = props(client.get(editor_url(campaign, "start")))["editor"]
    assert editor["context"]["selectStart"]
    assert all(
        json.loads(choice["value"]) != {"cycle_id": state.current_cycle_id}
        for choice in editor["context"]["startChoices"]
    )
    refused = post(client, campaign, "start", editor["values"], native=native)
    assert refused.status_code == (200 if native else 422)
    assert cycles.load(campaign).current is None
    target = editor["context"]["startChoices"][1]["value"]
    data = {**editor["values"], "start_target": target}
    assert post(client, campaign, "start", data, native=native).status_code == (
        302 if native else 200
    )
    assert post(client, campaign, "start", data, native=native).status_code == (
        302 if native else 200
    )
    assert cycles.load(campaign).current.order == 2


@pytest.mark.parametrize("delete_phase", [False, True])
def test_dashboard_history_keeps_earlier_cycle_and_phase_positions(
    campaign, opened, template, delete_phase
):
    cycles.configure(
        campaign,
        actor=campaign.owner,
        template_id=template.pk,
        current_position=6,
        mode="fixed",
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    common = {
        "actor": campaign.owner,
        "expected_revision": state.revision,
        "request_key": uuid4(),
    }
    from n26.core.operations import Refusal

    with pytest.raises(Refusal):
        cycles.author_timeline(
            campaign,
            action="remove_occurrence" if delete_phase else "remove_cycle",
            **(
                {"occurrence_id": state.occurrences[1].id}
                if delete_phase
                else {"cycle_id": state.cycles[1].id}
            ),
            **common,
        )
    summary = dashboard_summary(campaign, campaign.owner)
    assert summary.name == "Cycle 7"
    assert summary.order == summary.cycle_limit == 7


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize(
    "action", ["phase", "add-phase", "duplicate-phase", "delete-phase"]
)
def test_phase_management_returns_to_the_timeline(
    client, campaign, configured, native, action
):
    query = {} if action == "add-phase" else {"phase": configured.occurrences[1].id}
    editor = props(client.get(editor_url(campaign, action, **query)))["editor"]
    overview = schedule_url(campaign)
    assert editor["back"] == overview
    values = editor["values"]
    if action == "phase":
        values["name"] = "Updated phase"
    saved = post(client, campaign, action, values, native=native, **query)
    assert saved.status_code == (302 if native else 200)
    assert (saved.url if native else saved.json()["nextUrl"]) == overview
    returned = props(client.get(overview))
    assert returned["editor"] is None
    assert cycles.load(campaign).revision == configured.revision + 1
    assert cycles.load(campaign).current_cycle_id == configured.current_cycle_id
    if action != "delete-phase":
        fresh = props(client.get(editor_url(campaign, action, **query)))["editor"]
        assert fresh["values"]["request_key"] != values["request_key"]


def test_timeline_exposes_active_occurrences_with_future_actions(
    client, campaign, configured
):
    page = props(client.get(schedule_url(campaign)))
    assert {phase["id"] for phase in page["phases"]} == {
        occurrence.id for occurrence in configured.occurrences
    }
    assert [phase["number"] for phase in page["phases"]] == [1, 2, 3]
    assert page["actions"]["addPhase"] == editor_url(campaign, "add-phase")
    assert all(
        phase["editHref"] and phase["duplicateHref"] and phase["deleteHref"]
        for phase in page["phases"][1:]
    )


def test_timeline_queries_stay_flat_as_occurrence_list_grows(
    client, campaign, configured
):
    url = schedule_url(campaign)
    client.get(url, HTTP_ACCEPT="application/json")
    with CaptureQueriesContext(connection) as small:
        initial = client.get(url, HTTP_ACCEPT="application/json").json()["schedule"]
    state = configured
    for index in range(4):
        cycles.author_timeline(
            campaign,
            actor=campaign.owner,
            action="insert_occurrence",
            details=s.PhaseDetails(f"Extra phase {index}"),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
    with CaptureQueriesContext(connection) as large:
        expanded = client.get(url, HTTP_ACCEPT="application/json").json()["schedule"]
    assert len(expanded["phases"]) == len(initial["phases"]) + 4
    assert len(large) <= len(small)


def test_phase_deletion_confirms_revision_without_materialising_a_replacement(
    client, campaign, configured
):
    old = props(client.get(editor_url(campaign, "plan")))["editor"]
    phase = configured.occurrences[-1].id
    editor = props(client.get(editor_url(campaign, "delete-phase", phase=phase)))[
        "editor"
    ]
    values = editor["values"]
    response = post(client, campaign, "delete-phase", values, phase=phase)
    assert response.status_code == 200
    assert (
        post(client, campaign, "delete-phase", values, phase=phase).json()
        == response.json()
    )
    assert response.json()["nextUrl"] == schedule_url(campaign)
    fresh = props(client.get(editor_url(campaign, "plan")))["editor"]
    assert str(response.json()["revision"]) == fresh["values"]["expected_revision"]
    assert fresh["values"]["date_start"] == old["values"]["date_start"]
    state = cycles.load(campaign)
    assert len(state.cycles) == len(configured.cycles)
    assert state.current_cycle_id == configured.current_cycle_id


def test_phase_deletion_reports_saved_source_counts_across_repetitions(
    client, campaign, opened
):
    definition = s.ScheduleTemplate(
        "Repeating",
        (s.Phase("a", s.PhaseDetails("A")), s.Phase("b", s.PhaseDetails("B"))),
        (s.PlanStep("a-step", "a", 1), s.PlanStep("b-step", "b", 2)),
    )
    cycles.configure(
        campaign,
        actor=campaign.owner,
        template_id=None,
        current_position=0,
        mode="repeating",
        request_key=uuid4(),
        definition=template_data(definition),
    )
    state = cycles.load(campaign)
    before = props(client.get(editor_url(campaign, "plan")))["editor"]
    a, b = state.plan.steps
    assert before["context"]["savedStepCounts"] == {a.id: 1}
    target = next(cycle for cycle in s.project(state) if cycle.order == 5)
    cycles.edit_cycle(
        campaign,
        actor=campaign.owner,
        target=target.ref,
        details=s.CycleDetails(target.phase_id),
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    removed = state.cycles[3]
    phase = removed.occurrence_id
    editor = props(client.get(editor_url(campaign, "delete-phase", phase=phase)))[
        "editor"
    ]
    response = post(client, campaign, "delete-phase", editor["values"], phase=phase)
    assert response.status_code == 200
    after = props(client.get(editor_url(campaign, "plan")))["editor"]
    assert after["context"]["savedStepCounts"] == {a.id: 2, b.id: 3}
    assert after["context"]["fixedSteps"] == [
        {"id": b.id, "phase_id": b.phase_id, "count": 1}
    ]
    changed = cycles.load(campaign)
    assert next(c for c in changed.cycles if c.id == removed.id).archived
    assert not changed.current.archived
    assert changed.plan == state.plan
    assert {c.id: c.source for c in changed.cycles} == {
        c.id: c.source for c in state.cycles
    }


def test_overview_adopts_missing_occurrences_without_writing_on_get(
    campaign, configured
):
    from n26.core.models import CampaignPhase

    first = CampaignCycle.objects.get(pk=configured.cycles[0].id)
    CampaignCycle.objects.filter(pk=first.pk).update(phase_occurrence=None)
    empty = CampaignPhase.objects.create(campaign=campaign, name="Unlinked empty phase")
    before = list(CampaignCycle.objects.filter(campaign=campaign).values())
    with CaptureQueriesContext(connection) as queries:
        display = build(campaign, campaign.owner)
    assert not any(
        q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries
    )
    assert any(p["name"] == empty.name and p["count"] == 0 for p in display.phases)
    assert all(row.occurrenceId for row in display.rows)
    assert list(CampaignCycle.objects.filter(campaign=campaign).values()) == before


def test_dashboard_counts_separate_occurrences_with_the_same_rules(
    campaign, configured
):
    state = cycles.load(campaign)
    first = state.occurrences[0]
    cycles.author_timeline(
        campaign,
        actor=campaign.owner,
        action="duplicate_occurrence",
        occurrence_id=first.id,
        after_occurrence_id=first.id,
        clear_dates=True,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    summary = dashboard_summary(campaign, campaign.owner)
    assert (summary.phase_count, summary.next_phase, summary.cycles_until_phase) == (
        3,
        "Occupation",
        3,
    )
    assert summary.cycle_limit == 10


def test_dashboard_fixed_endpoint_uses_arranged_count_after_future_removal(
    campaign, configured
):
    state = cycles.load(campaign)
    last = state.cycles[-1]
    cycles.author_timeline(
        campaign,
        actor=campaign.owner,
        action="remove_cycle",
        cycle_id=last.id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    summary = dashboard_summary(campaign, campaign.owner)
    assert (summary.cycle_limit, summary.phase_count) == (6, 3)


@pytest.mark.parametrize("configured", ["repeating"], indirect=True)
def test_dashboard_continues_the_edited_phase_block_until_the_next_recipe_step(
    campaign, configured
):
    cycles.plan_cycles(
        campaign,
        actor=campaign.owner,
        count=1,
        expected_revision=configured.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    original = state.occurrences[0]
    phase = next(p for p in state.phases if p.id == original.phase_id)
    cycles.author_timeline(
        campaign,
        actor=campaign.owner,
        action="edit_occurrence",
        occurrence_id=original.id,
        details=replace(phase.details, name="Revised occupation"),
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    cycles.start(
        campaign,
        actor=campaign.owner,
        expected_current=state.current_cycle_id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    cycles.advance(
        campaign,
        actor=campaign.owner,
        expected_current=state.current_cycle_id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    summary = dashboard_summary(campaign, campaign.owner)
    assert summary.phase == "Revised occupation"
    assert (summary.phase_position, summary.phase_count) == (2, 3)
    assert (summary.next_phase, summary.cycles_until_phase) == ("Downtime", 2)


@pytest.mark.parametrize("json_read", [False, True])
def test_long_repeating_pattern_summary_names_definitions_beyond_the_preview(
    client, campaign, opened, template, json_read
):
    definition = replace(
        s.DEFAULT_TEMPLATE,
        steps=tuple(
            replace(step, count=count)
            for step, count in zip(s.DEFAULT_TEMPLATE.steps, (40, 1, 3), strict=True)
        ),
    )
    template.definition = template_data(definition)
    template.save(update_fields=["definition"])
    cycles.configure(
        campaign,
        actor=campaign.owner,
        template_id=template.pk,
        current_position=0,
        mode="repeating",
        request_key=uuid4(),
    )
    response = client.get(
        schedule_url(campaign),
        headers={"Accept": "application/json"} if json_read else {},
    )
    page = response.json()["schedule"] if json_read else props(response)
    assert {phase["name"] for phase in page["phases"]} == {"Occupation"}
    assert {row["phaseName"] for row in page["rows"]} == {"Occupation"}
    pattern = page["plan"]
    assert [
        (pattern["phaseNames"][step["phase_id"]], step["count"])
        for step in pattern["steps"]
    ] == [("Occupation", 40), ("Downtime", 1), ("Takeover", 3)]


@pytest.mark.parametrize("configured", ["repeating"], indirect=True)
@pytest.mark.parametrize("adjacent_same_phase", [False, True])
@pytest.mark.parametrize("legacy_pointer", [False, True])
def test_dashboard_counts_occurrence_boundaries_when_pattern_rules_repeat(
    campaign, configured, adjacent_same_phase, legacy_pointer
):
    opening = configured.plan.steps[0]
    steps = (replace(opening, count=3),)
    if adjacent_same_phase:
        steps += (s.PlanStep("second-block", opening.phase_id, 2),)
    cycles.replace_plan(
        campaign,
        actor=campaign.owner,
        steps=steps,
        mode="repeating",
        expected_revision=configured.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    cycles.plan_cycles(
        campaign,
        actor=campaign.owner,
        count=2,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    cycles.start(
        campaign,
        actor=campaign.owner,
        expected_current=state.current_cycle_id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    for _ in range(2):
        state = cycles.load(campaign)
        cycles.advance(
            campaign,
            actor=campaign.owner,
            expected_current=state.current_cycle_id,
            expected_revision=state.revision,
            request_key=uuid4(),
        )
    if legacy_pointer:
        CampaignSchedule.objects.filter(campaign=campaign).update(
            continuation_occurrence=None
        )
    summary = dashboard_summary(campaign, campaign.owner)
    assert (summary.order, summary.phase_position, summary.phase_count) == (3, 3, 3)
    assert (summary.next_phase, summary.cycles_until_phase) == ("Occupation", 1)
    rows = build(campaign, campaign.owner).rows
    assert rows[3].occurrenceId != rows[2].occurrenceId
    assert rows[3].phaseId == rows[2].phaseId


@pytest.mark.parametrize("configured", ["repeating"], indirect=True)
def test_dashboard_legacy_continuation_pointer_still_counts_the_current_remainder(
    campaign, configured
):
    CampaignSchedule.objects.filter(campaign=campaign).update(
        continuation_occurrence=None
    )
    summary = dashboard_summary(campaign, campaign.owner)
    assert (
        summary.phase_position,
        summary.phase_count,
        summary.cycles_until_phase,
    ) == (1, 3, 3)
    assert summary.next_phase == "Downtime"


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("phase_index", [0, 1, 2])
def test_arbitrators_correct_past_current_and_future_phase_rules_without_progression(
    client, campaign, configured, native, phase_index
):
    from n26.core.models import CampaignCycleDelivery, CampaignCycleTransition

    cycles.start(
        campaign,
        actor=campaign.owner,
        expected_current=configured.current_cycle_id,
        expected_revision=configured.revision,
        request_key=uuid4(),
    )
    for _ in range(3):
        state = cycles.load(campaign)
        cycles.advance(
            campaign,
            actor=campaign.owner,
            expected_current=state.current_cycle_id,
            expected_revision=state.revision,
            request_key=uuid4(),
        )
    before = cycles.load(campaign)
    occurrence = before.occurrences[phase_index]
    transitions = list(
        CampaignCycleTransition.objects.filter(campaign=campaign).values()
    )
    deliveries = list(
        CampaignCycleDelivery.objects.filter(transition__campaign=campaign).values()
    )
    display = props(client.get(schedule_url(campaign)))
    shown = next(p for p in display["phases"] if p["id"] == occurrence.id)
    assert shown["editHref"]
    if phase_index < 2:
        assert not shown["moveHref"] and not shown["deleteHref"]
    query = {"phase": occurrence.id}
    editor = props(client.get(editor_url(campaign, "phase", **query)))["editor"]
    values = editor["values"] | {
        "name": "Corrected phase",
        "effects": "Revised effects",
    }
    saved = post(client, campaign, "phase", values, native=native, **query)
    assert saved.status_code == (302 if native else 200)
    after = cycles.load(campaign)
    changed = next(o for o in after.occurrences if o.id == occurrence.id)
    assert s._phase(after, changed.phase_id).details.effects == "Revised effects"
    assert after.current_cycle_id == before.current_cycle_id
    assert after.plan == before.plan
    for original, updated in zip(before.cycles, after.cycles, strict=True):
        assert updated == (
            replace(
                original, details=replace(original.details, phase_id=changed.phase_id)
            )
            if original.occurrence_id == occurrence.id
            else original
        )
    assert (
        list(CampaignCycleTransition.objects.filter(campaign=campaign).values())
        == transitions
    )
    assert (
        list(
            CampaignCycleDelivery.objects.filter(transition__campaign=campaign).values()
        )
        == deliveries
    )
    replayed = post(client, campaign, "phase", values, native=native, **query)
    assert replayed.status_code == (302 if native else 200)
    assert cycles.load(campaign) == after


@pytest.mark.parametrize("native", [False, True])
def test_readers_cannot_open_or_submit_a_current_phase_correction(
    client, campaign, configured, native
):
    query = {"phase": configured.occurrences[0].id}
    values = props(client.get(editor_url(campaign, "phase", **query)))["editor"][
        "values"
    ]
    client.force_login(User.objects.create_user("phase-reader"))
    assert client.get(editor_url(campaign, "phase", **query)).status_code == 404
    assert (
        post(
            client,
            campaign,
            "phase",
            values | {"effects": "Unauthorised"},
            native=native,
            **query,
        ).status_code
        == 404
    )
    assert cycles.load(campaign) == configured
