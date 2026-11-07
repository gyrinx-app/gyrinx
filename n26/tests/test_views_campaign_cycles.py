"""Schedule transports share ownership, revision and durable retry semantics."""

import json
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import ref_data, template_data
from n26.core.cycle_display import build, editor_url, schedule_url
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
def configured(campaign, opened, template):
    cycles.configure(
        campaign,
        actor=campaign.owner,
        template_id=template.pk,
        current_position=0,
        mode="fixed",
        request_key=uuid4(),
    )
    return cycles.load(campaign)


def props(response):
    assert response.status_code == 200
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="campaign-schedule"]')
    return json.loads(page.find(id=host["data-react-props"]).string)


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
        assert "Set up cycles" not in page.content.decode()
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
    @pytest.mark.parametrize("native", [False, True])
    def test_setup_retry_succeeds_after_the_schedule_already_exists(
        self, client, campaign, opened, template, native
    ):
        data = setup_data(template)
        first = post(client, campaign, "setup", data, native=native)
        second = post(client, campaign, "setup", data, native=native)
        assert first.status_code == second.status_code == (302 if native else 200)
        assert CampaignCycle.objects.filter(campaign=campaign).count() == 1
        assert campaign.cycle_commands.count() == 1
        assert len(props(client.get(schedule_url(campaign)))["rows"]) == 7

    @pytest.mark.parametrize("native", [False, True])
    def test_editing_a_projection_saves_the_prefix_without_advancing(
        self, client, campaign, configured, native
    ):
        selected = s.project(configured)[2]
        query = {"plan": configured.plan.id, "position": selected.source.position.index}
        prepared = props(client.get(editor_url(campaign, "cycle", **query)))["editor"]
        assert "Cycle 2 through Cycle 4" in prepared["lead"]
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
        assert current["phase"] == "Occupation Phase"

    def test_a_reused_key_with_different_input_is_not_a_revision_conflict(
        self, client, campaign, opened, template
    ):
        data = setup_data(template)
        assert post(client, campaign, "setup", data).status_code == 200
        response = post(client, campaign, "setup", {**data, "current_number": "2"})
        assert response.status_code == 409
        assert response.json()["code"] == "request_key_conflict"
        assert "current" not in response.json()

    def test_private_template_retries_create_one_reusable_copy(
        self, client, campaign, configured
    ):
        values = props(client.get(editor_url(campaign, "save-template")))["editor"][
            "values"
        ]
        data = {**values, "name": "My campaign pattern"}
        for _ in range(2):
            assert post(client, campaign, "save-template", data).status_code == 200
        assert (
            CampaignScheduleTemplate.objects.filter(
                owner=campaign.owner, name=data["name"]
            ).count()
            == 1
        )

    def test_unchanged_future_plan_does_not_replay_consumed_cycles(
        self, client, campaign, configured
    ):
        values = props(client.get(editor_url(campaign, "plan")))["editor"]["values"]
        assert [step["count"] for step in json.loads(values["steps"])] == [2, 1, 3]
        assert post(client, campaign, "plan", values).status_code == 200
        after = cycles.load(campaign)
        assert after.plan.id == configured.plan.id
        assert after.next_position == configured.next_position
        assert len(s.project(after)) == 6


class TestDisplayReads:
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
        assert len(small.rows) == 7
        assert len(large.rows) == 50
        assert large.nextHref and not large.moreHref
        second = build(campaign, reader, page=2)
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
        assert not past.startsOn and not past.endsOn

    def test_dashboard_links_the_current_cycle_and_phase(
        self, client, campaign, configured
    ):
        page = client.get(reverse("n26-campaign", args=[campaign.pk]))
        assert page.status_code == 200
        body = page.content.decode()
        assert (
            reverse(
                "n26-campaign-cycle", args=[campaign.pk, configured.current_cycle_id]
            )
            in body
        )
        assert "Occupation Phase" in body and "Schedule and rules" in body

    def test_projection_growth_does_not_add_queries(self, campaign, configured):
        reader = campaign.owner

        def read(preview):
            with CaptureQueriesContext(connection) as queries:
                display = build(campaign, reader, preview=preview)
            return display, len(queries)

        small, count = read(1)
        large, larger_count = read(12)
        assert count == larger_count
        assert len(small.rows) == 2 and len(large.rows) == 7
