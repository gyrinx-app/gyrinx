"""Tests for the async (two-phase) campaign start — issue #1222.

Phase 1 (`handle_campaign_start`) creates CLONING_IN_PROGRESS stub lists and enqueues one
`complete_campaign_list_clone` task per stub on commit. These tests exercise the async-only
behaviour: task idempotency, atomic rollback + retry, sibling isolation, the cloning-status
poll endpoint, the owner-only retry endpoint, the consumer guards, and the admin re-enqueue
action. (End-to-end equivalence with the old synchronous path is covered in
test_handlers_campaign_operations.py.)
"""

from unittest import mock

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.core.admin.list import reenqueue_campaign_clone
from gyrinx.core.forms.battle import BattleForm
from gyrinx.core.handlers.campaign_operations import handle_campaign_start
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List
from gyrinx.core.tasks import complete_campaign_list_clone


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
    """The poll endpoint reports per-gang status and is readable without logging in."""
    campaign, _ = _pre_campaign_with_lists(
        make_campaign, make_list, ["Gang 1", "Gang 2"]
    )
    _start_phase1_only(user, campaign)

    url = reverse("core:campaign-cloning-status", args=[campaign.id])

    # Anonymous client can read it (visible to all, like the campaign page).
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["cloning"] is True
    assert len(data["lists"]) == 2
    assert all(entry["ready"] is False for entry in data["lists"])

    # After the clone tasks run, everything reports ready.
    for stub in List.objects.filter(campaign=campaign):
        orig = stub.original_list
        _run_clone(stub, orig, campaign, user)

    resp = client.get(url)
    data = resp.json()
    assert data["cloning"] is False
    assert all(entry["ready"] is True for entry in data["lists"])


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
    # The poller is wired to the status endpoint.
    assert reverse("core:campaign-cloning-status", args=[campaign.id]) in content
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
