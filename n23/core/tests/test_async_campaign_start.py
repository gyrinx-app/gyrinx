"""Tests for the async (two-phase) campaign start — issue #1222.

Phase 1 (`handle_campaign_start`) creates CLONING_IN_PROGRESS stub lists and enqueues one
`complete_campaign_list_clone` task per stub on commit. These tests exercise the async-only
behaviour: task idempotency, atomic rollback + retry, sibling isolation, the cloning-status
poll endpoint, the owner-only retry endpoint, the consumer guards, and the admin re-enqueue
action. (End-to-end equivalence with the old synchronous path is covered in
test_handlers_campaign_operations.py.)
"""

import base64
import json
from unittest import mock

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils.http import urlencode

from n23.core.admin.list import reenqueue_campaign_clone
from n23.core.forms.battle import BattleForm
from n23.core.handlers.campaign_operations import (
    campaign_start_group_key,
    handle_campaign_start,
)
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.campaign import Campaign
from n23.core.models.list import List
from n23.core.tasks import complete_campaign_list_clone
from gyrinx.tasks.backend import PubSubBackend
from gyrinx.tasks.groups import group_status


def _pre_campaign_with_lists(make_campaign, make_list, names, budget=1500):
    """Create a PRE_CAMPAIGN campaign with LIST_BUILDING lists added (not started)."""
    campaign = make_campaign(
        "Async Campaign", status=Campaign.PRE_CAMPAIGN, budget=budget
    )
    lists = [make_list(name) for name in names]
    campaign.lists.add(*lists)
    return campaign, lists


def _start_phase1_only(user, campaign):
    """Run Phase 1 without firing on_commit, so stubs stay CLONING_IN_PROGRESS."""
    return handle_campaign_start(user=user, campaign=campaign)


def _run_clone(stub, original, campaign, user):
    complete_campaign_list_clone.func(
        stub_id=str(stub.id),
        original_list_id=str(original.id),
        campaign_id=str(campaign.id),
        user_id=str(user.id),
    )


@pytest.mark.django_db
def test_clone_task_is_idempotent(
    user, make_campaign, make_list, make_list_fighter, content_fighter
):
    """Running the clone task twice must not double-grant budget or duplicate fighters."""
    campaign, [orig] = _pre_campaign_with_lists(make_campaign, make_list, ["Gang 1"])
    make_list_fighter(orig, "Fighter", content_fighter=content_fighter)
    orig.rating_current = 100
    orig.save()

    _start_phase1_only(user, campaign)
    stub = List.objects.get(campaign=campaign, status=List.CLONING_IN_PROGRESS)

    # First run: populates and completes.
    _run_clone(stub, orig, campaign, user)
    stub.refresh_from_db()
    assert stub.status == List.CAMPAIGN_MODE
    credits_after_first = stub.credits_current
    fighters_after_first = stub.listfighter_set.count()
    campaign_start_actions = ListAction.objects.filter(
        list=stub, action_type=ListActionType.CAMPAIGN_START
    ).count()

    # Second run: stub is no longer CLONING_IN_PROGRESS, so it's a clean no-op.
    _run_clone(stub, orig, campaign, user)
    stub.refresh_from_db()
    assert stub.status == List.CAMPAIGN_MODE
    assert stub.credits_current == credits_after_first
    assert stub.listfighter_set.count() == fighters_after_first
    assert (
        ListAction.objects.filter(
            list=stub, action_type=ListActionType.CAMPAIGN_START
        ).count()
        == campaign_start_actions
    )


@pytest.mark.django_db
def test_clone_task_failure_rolls_back_and_isolates_siblings(
    user, make_campaign, make_list
):
    """A failing clone task leaves its stub cloning (clean retry) and doesn't touch siblings."""
    campaign, [orig_a, orig_b] = _pre_campaign_with_lists(
        make_campaign, make_list, ["Gang A", "Gang B"]
    )
    _start_phase1_only(user, campaign)
    stub_a = List.objects.get(campaign=campaign, original_list=orig_a)
    stub_b = List.objects.get(campaign=campaign, original_list=orig_b)

    # Stub A's populate blows up -> the whole task transaction rolls back.
    with mock.patch.object(
        List, "_populate_clone_from", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(RuntimeError):
            _run_clone(stub_a, orig_a, campaign, user)

    stub_a.refresh_from_db()
    stub_b.refresh_from_db()
    # A rolled back to still-cloning; B untouched (its own task hasn't run).
    assert stub_a.status == List.CLONING_IN_PROGRESS
    assert stub_b.status == List.CLONING_IN_PROGRESS
    assert not ListAction.objects.filter(list=stub_a).exists()

    # Retrying A now succeeds.
    _run_clone(stub_a, orig_a, campaign, user)
    stub_a.refresh_from_db()
    assert stub_a.status == List.CAMPAIGN_MODE
    # B is still independent and still waiting.
    stub_b.refresh_from_db()
    assert stub_b.status == List.CLONING_IN_PROGRESS


@pytest.mark.django_db
def test_cloning_status_endpoint_visible_to_all(
    client, user, make_campaign, make_list, django_capture_on_commit_callbacks
):
    """The campaign's clone tasks are pollable via the generic group endpoint, readable by anyone.

    Campaign start enqueues one clone task per gang tagged with the campaign's group key. Under
    the ImmediateBackend the tasks also run inline, so once the on_commit callbacks fire the
    group reports every unit successful and complete.
    """
    campaign, _ = _pre_campaign_with_lists(
        make_campaign, make_list, ["Gang 1", "Gang 2"]
    )

    with django_capture_on_commit_callbacks(execute=True):
        handle_campaign_start(user=user, campaign=campaign)

    group_key = campaign_start_group_key(campaign.id)
    url = reverse("tasks:group-status") + "?group=" + group_key

    # Anonymous client can read it (visible to all, like the campaign page).
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["group"] == group_key
    assert data["counts"]["total"] == 2
    assert data["counts"]["successful"] == 2
    assert data["complete"] is True
    assert {entry["label"] for entry in data["units"]} == {"Gang 1", "Gang 2"}


# The prod task backend: publishes to Pub/Sub and returns immediately (task runs later, in a
# separate worker process). Locally we run ImmediateBackend, so the test below is the only
# place the genuine async path — enqueue, defer, worker picks up, completes — is exercised.
_PUBSUB_TASKS = {
    "default": {
        "BACKEND": "gyrinx.tasks.backend.PubSubBackend",
        "OPTIONS": {"project_id": "test-project"},
    }
}


def _drain_pubsub_to_handler(client, published):
    """Feed each captured Pub/Sub payload into the push handler, exactly like the prod worker.

    ``published`` holds the raw message bodies PubSubBackend handed to ``publish``. Wrapping
    each in a Pub/Sub push envelope and POSTing it to the handler runs the task the way Cloud
    Run's push subscription does.
    """
    for data in published:
        envelope = {
            "message": {
                "messageId": "test-msg",
                "data": base64.b64encode(data).decode(),
            }
        }
        resp = client.post(
            reverse("tasks:pubsub"),
            data=json.dumps(envelope),
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content


@pytest.mark.django_db
@override_settings(TASKS=_PUBSUB_TASKS)
def test_prod_async_path_roundtrips_through_pubsub(
    client,
    user,
    make_campaign,
    make_list,
    make_list_fighter,
    content_fighter,
    django_capture_on_commit_callbacks,
):
    """End-to-end over the real prod path: enqueue → Pub/Sub → worker push handler → complete.

    This is the one test that reproduces what prod actually does (ImmediateBackend hides it
    locally): after start, the clone tasks are *deferred*, so the stubs sit "joining" and the
    group status reports them pending. Only when the worker picks up each Pub/Sub message do
    they complete. It also proves the group tag survives — it's stamped on the DB row at
    enqueue, never carried in the Pub/Sub payload.
    """
    campaign, [orig1, orig2] = _pre_campaign_with_lists(
        make_campaign, make_list, ["Gang 1", "Gang 2"]
    )
    make_list_fighter(orig1, "Fighter", content_fighter=content_fighter)

    published = []

    def fake_publish(topic_path, data):
        published.append(data)
        future = mock.MagicMock()
        future.result.return_value = "message-id"
        return future

    # Bypass the OIDC check on the push handler (prod verifies a Google-signed JWT).
    with (
        mock.patch("gyrinx.tasks.views._verify_oidc_token", return_value=True),
        mock.patch.object(
            PubSubBackend, "publisher", new_callable=mock.MagicMock
        ) as publisher,
    ):
        publisher.publish.side_effect = fake_publish
        publisher.topic_path.return_value = "projects/test/topics/t"

        with django_capture_on_commit_callbacks(execute=True):
            handle_campaign_start(user=user, campaign=campaign)

        # Phase 1 committed: tasks are enqueued but NOT run yet. This is the "joining" gap a
        # prod user sees — the stubs exist, the group is pending, nothing has cloned.
        group_key = campaign_start_group_key(campaign.id)
        pending = group_status(group_key)
        assert pending["counts"]["total"] == 2
        assert pending["counts"]["ready"] == 2
        assert pending["complete"] is False
        assert len(published) == 2
        for stub in List.objects.filter(campaign=campaign):
            assert stub.status == List.CLONING_IN_PROGRESS
            assert stub.listfighter_set.count() == 0  # not populated yet

        # The worker picks up each Pub/Sub message and runs the clone.
        _drain_pubsub_to_handler(client, published)

    # Now the group is complete and both stubs have finished joining.
    done = group_status(group_key)
    assert done["complete"] is True
    assert done["counts"]["successful"] == 2
    stub1 = List.objects.get(campaign=campaign, original_list=orig1)
    stub2 = List.objects.get(campaign=campaign, original_list=orig2)
    assert stub1.status == List.CAMPAIGN_MODE
    assert stub2.status == List.CAMPAIGN_MODE
    # The fighter was cloned across (alongside the auto-created campaign stash fighter).
    assert stub1.listfighter_set.filter(name="Fighter").count() == 1


@pytest.mark.django_db
def test_retry_clone_owner_only(
    client,
    user,
    make_user,
    make_campaign,
    make_list,
    django_capture_on_commit_callbacks,
):
    """Only the campaign owner (the trigger-er) can retry a joining gang."""
    campaign, [orig] = _pre_campaign_with_lists(make_campaign, make_list, ["Gang 1"])
    _start_phase1_only(user, campaign)
    stub = List.objects.get(campaign=campaign, status=List.CLONING_IN_PROGRESS)

    url = reverse("core:campaign-list-retry-clone", args=[campaign.id, stub.id])

    # A non-owner cannot retry: the stub stays cloning (and nothing is enqueued).
    other = make_user("intruder", "password")
    client.force_login(other)
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(url)
    assert resp.status_code == 302
    stub.refresh_from_db()
    assert stub.status == List.CLONING_IN_PROGRESS

    # The owner can: the retry defers enqueue to on_commit, which the ImmediateBackend
    # then runs inline, completing the clone.
    client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(url)
    assert resp.status_code == 302
    stub.refresh_from_db()
    assert stub.status == List.CAMPAIGN_MODE


@pytest.mark.django_db
def test_stub_excluded_from_battle_participants(user, make_campaign, make_list):
    """A CLONING_IN_PROGRESS stub is not a selectable battle participant; a finished gang is."""
    campaign, [orig_a, orig_b] = _pre_campaign_with_lists(
        make_campaign, make_list, ["Gang A", "Gang B"]
    )
    _start_phase1_only(user, campaign)
    stub_a = List.objects.get(campaign=campaign, original_list=orig_a)
    stub_b = List.objects.get(campaign=campaign, original_list=orig_b)

    # Finish only A.
    _run_clone(stub_a, orig_a, campaign, user)

    form = BattleForm(campaign=campaign)
    participant_ids = set(
        form.fields["participants"].queryset.values_list("id", flat=True)
    )
    assert stub_a.id in participant_ids  # finished gang is selectable
    assert stub_b.id not in participant_ids  # still-joining stub is not


@pytest.mark.django_db
def test_campaign_page_renders_joining_state(client, user, make_campaign, make_list):
    """The campaign page shows the 'Joining…' placeholder, poller, and owner Retry button."""
    campaign, [orig] = _pre_campaign_with_lists(make_campaign, make_list, ["Gang 1"])
    _start_phase1_only(user, campaign)
    stub = List.objects.get(campaign=campaign, status=List.CLONING_IN_PROGRESS)

    client.force_login(user)
    resp = client.get(reverse("core:campaign", args=[campaign.id]))
    assert resp.status_code == 200
    content = resp.content.decode()

    # Joining placeholder instead of the rating/stash line.
    assert "Joining Campaign" in content
    # The poller is wired to the generic task-group status endpoint for this campaign. The
    # URL is urlencoded (and escapejs'd into the <script>), so assert on the context value
    # rather than a brittle escaped substring.
    assert resp.context["cloning_status_url"] == (
        reverse("tasks:group-status")
        + "?"
        + urlencode({"group": campaign_start_group_key(campaign.id)})
    )
    # The owner sees a Retry action for the stub.
    assert (
        reverse("core:campaign-list-retry-clone", args=[campaign.id, stub.id])
        in content
    )


@pytest.mark.django_db
def test_stub_list_detail_redirects_to_campaign(client, user, make_campaign, make_list):
    """Viewing a still-cloning stub's detail page redirects to its campaign."""
    campaign, [orig] = _pre_campaign_with_lists(make_campaign, make_list, ["Gang 1"])
    _start_phase1_only(user, campaign)
    stub = List.objects.get(campaign=campaign, status=List.CLONING_IN_PROGRESS)

    client.force_login(user)
    resp = client.get(reverse("core:list", args=[stub.id]))
    assert resp.status_code == 302
    assert resp.url == reverse("core:campaign", args=[campaign.id])


@pytest.mark.django_db
def test_remove_list_blocked_while_cloning(client, user, make_campaign, make_list):
    """A still-joining stub can't be removed from the campaign until it finishes."""
    campaign, [orig] = _pre_campaign_with_lists(make_campaign, make_list, ["Gang 1"])
    _start_phase1_only(user, campaign)
    stub = List.objects.get(campaign=campaign, status=List.CLONING_IN_PROGRESS)

    client.force_login(user)
    resp = client.post(
        reverse("core:campaign-remove-list", args=[campaign.id, stub.id])
    )
    assert resp.status_code == 302
    # The removal was refused: the stub is still attached and still cloning.
    stub.refresh_from_db()
    assert stub.status == List.CLONING_IN_PROGRESS
    assert stub in campaign.lists.all()


@pytest.mark.django_db
def test_resource_type_seeding_skips_cloning_stub(
    client, user, make_campaign, make_list
):
    """Adding a resource type to a running campaign seeds finished gangs, not joining stubs."""
    from n23.core.models.campaign import CampaignListResource, CampaignResourceType

    campaign, [orig_a, orig_b] = _pre_campaign_with_lists(
        make_campaign, make_list, ["Gang A", "Gang B"]
    )
    _start_phase1_only(user, campaign)
    stub_a = List.objects.get(campaign=campaign, original_list=orig_a)
    stub_b = List.objects.get(campaign=campaign, original_list=orig_b)
    _run_clone(stub_a, orig_a, campaign, user)  # A finishes joining; B is still a stub.

    client.force_login(user)
    resp = client.post(
        reverse("core:campaign-resource-type-new", args=[campaign.id]),
        {"name": "Meat", "description": "", "default_amount": 5},
    )
    assert resp.status_code == 302

    rt = CampaignResourceType.objects.get(campaign=campaign, name="Meat")
    seeded_list_ids = set(
        CampaignListResource.objects.filter(resource_type=rt).values_list(
            "list_id", flat=True
        )
    )
    assert stub_a.id in seeded_list_ids  # finished gang got the resource
    assert stub_b.id not in seeded_list_ids  # still-joining stub was skipped


@pytest.mark.django_db
def test_admin_reenqueue_campaign_clone_action(user, make_campaign, make_list):
    """The ListAdmin re-enqueue action reruns the clone for stuck stubs (smoke test)."""
    campaign, [orig] = _pre_campaign_with_lists(make_campaign, make_list, ["Gang 1"])
    _start_phase1_only(user, campaign)
    stub = List.objects.get(campaign=campaign, status=List.CLONING_IN_PROGRESS)

    request = RequestFactory().post("/admin/core/list/")
    request.user = user
    setattr(request, "session", {})
    setattr(request, "_messages", FallbackStorage(request))

    # enqueue runs the task inline under the ImmediateBackend, so the stub completes.
    reenqueue_campaign_clone(None, request, List.objects.filter(pk=stub.pk))

    stub.refresh_from_db()
    assert stub.status == List.CAMPAIGN_MODE
