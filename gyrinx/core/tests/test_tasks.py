"""
Tests for background tasks in gyrinx.core.tasks.
"""

import uuid

import pytest

from gyrinx.core.tasks import refresh_list_facts


@pytest.mark.django_db
def test_refresh_list_facts_updates_dirty_list(user, make_list, content_fighter):
    """Test that refresh_list_facts clears the dirty flag and updates cached values."""
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Test List")
    lst.dirty = True
    lst.rating_current = 0
    lst.save()

    # Create a fighter to have some rating
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    expected_rating = fighter.cost_int()

    # Call the task directly (not via enqueue, to test the function itself)
    refresh_list_facts.func(list_id=str(lst.pk))

    # Verify list was updated
    lst.refresh_from_db()
    assert lst.dirty is False
    assert lst.rating_current == expected_rating


@pytest.mark.django_db
def test_refresh_list_facts_handles_missing_list():
    """Test that refresh_list_facts handles non-existent list gracefully."""
    fake_id = str(uuid.uuid4())

    # Should not raise - just logs a warning
    refresh_list_facts.func(list_id=fake_id)


@pytest.mark.django_db
def test_refresh_list_facts_via_enqueue(user, make_list, content_fighter):
    """Test that refresh_list_facts works when called via enqueue (ImmediateBackend)."""
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Test List")
    lst.dirty = True
    lst.rating_current = 0
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    expected_rating = fighter.cost_int()

    # Use enqueue (runs synchronously with ImmediateBackend)
    refresh_list_facts.enqueue(list_id=str(lst.pk))

    # Verify list was updated
    lst.refresh_from_db()
    assert lst.dirty is False
    assert lst.rating_current == expected_rating


# =============================================================================
# backfill_list_action tests
# =============================================================================


@pytest.mark.django_db
def test_backfill_list_action_creates_initial_action(user, make_list, content_fighter):
    """Test that backfill_list_action creates an initial CREATE action for a list."""
    from gyrinx.core.models.action import ListAction, ListActionType
    from gyrinx.core.models.list import ListFighter
    from gyrinx.core.tasks import backfill_list_action

    # Create list WITHOUT initial action (using create_initial_action=False)
    lst = make_list("Test List", create_initial_action=False)

    # Add a fighter so we have some rating
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    expected_rating = fighter.cost_int()

    # Verify no actions exist yet
    assert not ListAction.objects.filter(list=lst).exists()

    # Run the backfill task
    backfill_list_action.func(list_id=str(lst.pk))

    # Verify action was created
    assert ListAction.objects.filter(list=lst).count() == 1
    action = ListAction.objects.get(list=lst)

    # Verify action properties
    assert action.action_type == ListActionType.CREATE
    assert action.description == "List upgraded to support action tracking"
    assert action.applied is True
    assert action.rating_before == expected_rating
    assert action.rating_delta == 0
    assert action.stash_delta == 0
    assert action.credits_delta == 0

    # Verify list cached values are correct
    lst.refresh_from_db()
    assert lst.rating_current == expected_rating
    assert lst.dirty is False


@pytest.mark.django_db
def test_backfill_list_action_skips_list_with_existing_action(user, make_list):
    """Test that backfill_list_action is idempotent - skips if action already exists."""
    from gyrinx.core.models.action import ListAction
    from gyrinx.core.tasks import backfill_list_action

    # Create list WITH initial action
    lst = make_list("Test List", create_initial_action=True)

    # Verify one action exists
    initial_count = ListAction.objects.filter(list=lst).count()
    assert initial_count == 1

    # Run the backfill task
    backfill_list_action.func(list_id=str(lst.pk))

    # Verify no new action was created (idempotent)
    assert ListAction.objects.filter(list=lst).count() == initial_count


@pytest.mark.django_db
def test_backfill_list_action_handles_missing_list():
    """Test that backfill_list_action handles non-existent list gracefully."""
    from gyrinx.core.tasks import backfill_list_action

    fake_id = str(uuid.uuid4())

    # Should not raise - just logs a warning
    backfill_list_action.func(list_id=fake_id)


@pytest.mark.django_db
def test_backfill_list_action_via_enqueue(user, make_list, content_fighter):
    """Test that backfill_list_action works when called via enqueue."""
    from gyrinx.core.models.action import ListAction
    from gyrinx.core.models.list import ListFighter
    from gyrinx.core.tasks import backfill_list_action

    lst = make_list("Test List", create_initial_action=False)

    ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Use enqueue (runs synchronously with ImmediateBackend)
    backfill_list_action.enqueue(list_id=str(lst.pk))

    # Verify action was created
    assert ListAction.objects.filter(list=lst).count() == 1


# =============================================================================
# enqueue_backfill_tasks tests
# =============================================================================


@pytest.mark.django_db
def test_enqueue_backfill_tasks_finds_lists_without_actions(user, make_list):
    """Test that enqueue_backfill_tasks finds lists without actions and enqueues tasks."""
    from unittest.mock import MagicMock, patch

    from gyrinx.core.tasks import enqueue_backfill_tasks

    # Create lists without initial actions
    lst1 = make_list("List 1", create_initial_action=False)
    lst2 = make_list("List 2", create_initial_action=False)
    # Create list WITH initial action (should be skipped)
    make_list("List 3", create_initial_action=True)

    # Mock backfill_list_action at module level
    mock_task = MagicMock()
    with patch("gyrinx.core.tasks.backfill_list_action", mock_task):
        # Run the scheduler task
        enqueue_backfill_tasks.func()

        # Verify enqueue was called for each list without actions
        assert mock_task.enqueue.call_count == 2
        enqueued_ids = {
            call.kwargs["list_id"] for call in mock_task.enqueue.call_args_list
        }
        assert str(lst1.pk) in enqueued_ids
        assert str(lst2.pk) in enqueued_ids


@pytest.mark.django_db
def test_enqueue_backfill_tasks_respects_kill_switch(user, make_list, monkeypatch):
    """Test that enqueue_backfill_tasks respects ENABLE_BACKFILL_SCHEDULER env var."""
    from unittest.mock import MagicMock, patch

    from gyrinx.core.tasks import enqueue_backfill_tasks

    # Create list without action
    make_list("List 1", create_initial_action=False)

    # Disable via env var
    monkeypatch.setenv("ENABLE_BACKFILL_SCHEDULER", "false")

    # Mock backfill_list_action at module level
    mock_task = MagicMock()
    with patch("gyrinx.core.tasks.backfill_list_action", mock_task):
        # Run the scheduler task
        enqueue_backfill_tasks.func()

        # Verify enqueue was NOT called (kill switch active)
        assert mock_task.enqueue.call_count == 0


@pytest.mark.django_db
def test_enqueue_backfill_tasks_handles_no_lists_to_backfill(user, make_list):
    """Test that enqueue_backfill_tasks handles case where all lists have actions."""
    from unittest.mock import MagicMock, patch

    from gyrinx.core.tasks import enqueue_backfill_tasks

    # Create only lists WITH initial actions
    make_list("List 1", create_initial_action=True)
    make_list("List 2", create_initial_action=True)

    # Mock backfill_list_action at module level
    mock_task = MagicMock()
    with patch("gyrinx.core.tasks.backfill_list_action", mock_task):
        # Run the scheduler task
        enqueue_backfill_tasks.func()

        # Verify enqueue was NOT called (no lists to backfill)
        assert mock_task.enqueue.call_count == 0


@pytest.mark.django_db
def test_enqueue_backfill_tasks_limits_to_100_lists(user, make_list):
    """Test that enqueue_backfill_tasks only processes up to 100 lists per run."""
    from unittest.mock import MagicMock, patch

    from gyrinx.core.tasks import enqueue_backfill_tasks

    # Create 105 lists without initial actions
    for i in range(105):
        make_list(f"List {i}", create_initial_action=False)

    # Mock backfill_list_action at module level
    mock_task = MagicMock()
    with patch("gyrinx.core.tasks.backfill_list_action", mock_task):
        # Run the scheduler task
        enqueue_backfill_tasks.func()

        # Verify only 100 were enqueued (batch limit)
        assert mock_task.enqueue.call_count == 100
