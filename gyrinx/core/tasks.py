import logging

from django.tasks import task

logger = logging.getLogger(__name__)


@task
def hello_world(name: str = "World"):
    """Demo task for testing the task framework."""
    logger.info(f"Hello, {name}!")
    return f"Greeted {name}"


@task
def refresh_list_facts(list_id: str):
    """
    Refresh the cached facts for a list by recalculating from database.

    Called asynchronously when facts_with_fallback detects a dirty cache.
    """
    from gyrinx.core.models import List

    try:
        lst: List = List.objects.with_related_data(with_fighters=True).get(pk=list_id)
        lst.facts_from_db(update=True)
        logger.info(f"Refreshed facts for list {list_id}")
    except List.DoesNotExist:
        logger.warning(f"List {list_id} not found for facts refresh")


@task
def backfill_list_action(list_id: str):
    """
    Backfill an initial ListAction for a list that was created before action tracking.

    This task:
    1. Checks if the list already has an action (idempotent)
    2. Calls facts_from_db(update=True) to ensure cached values are correct
    3. Creates a CREATE action as a snapshot of current state (zero deltas)

    The action is created directly (not via create_action) because create_action
    requires latest_action to already exist.
    """
    from django.db import transaction

    from gyrinx.core.models import List
    from gyrinx.core.models.action import ListAction, ListActionType
    from gyrinx.tracker import track

    track("backfill_list_action_started", list_id=list_id)

    try:
        with transaction.atomic():
            # select_for_update() prevents race condition where concurrent tasks
            # for the same list could both pass the exists() check before either commits.
            # We lock the row first, then fetch with related data separately because
            # FOR UPDATE cannot be applied to outer joins used in with_related_data().
            List.objects.select_for_update().filter(pk=list_id).get()
            lst: List = List.objects.with_related_data(with_fighters=True).get(
                pk=list_id
            )

            # Idempotent check: skip if list already has an action
            if ListAction.objects.filter(list=lst).exists():
                logger.info(f"List {list_id} already has actions, skipping backfill")
                track(
                    "backfill_list_action_skipped",
                    list_id=list_id,
                    reason="already_has_actions",
                )
                return

            # Ensure cached values are correct
            facts = lst.facts_from_db(update=True)

            track(
                "backfill_list_action_facts_computed",
                list_id=list_id,
                rating=facts.rating,
                stash=facts.stash,
                credits=lst.credits_current,
            )

            # Create the initial action as a snapshot (zero deltas)
            # This mirrors handle_list_creation but for existing lists
            action = ListAction.objects.create(
                user=lst.owner,
                owner=lst.owner,
                list=lst,
                action_type=ListActionType.CREATE,
                description="List upgraded to support action tracking",
                applied=True,
                # Before values match current values (snapshot, not a change)
                rating_before=facts.rating,
                stash_before=facts.stash,
                credits_before=lst.credits_current,
                # Zero deltas since this is a snapshot
                rating_delta=0,
                stash_delta=0,
                credits_delta=0,
            )

            logger.info(
                f"Backfilled initial action for list {list_id} "
                f"(rating={facts.rating}, stash={facts.stash}, credits={lst.credits_current})"
            )
            track(
                "backfill_list_action_completed",
                list_id=list_id,
                action_id=str(action.id),
                rating=facts.rating,
                stash=facts.stash,
                credits=lst.credits_current,
            )

    except List.DoesNotExist:
        logger.warning(f"List {list_id} not found for backfill")
        track(
            "backfill_list_action_failed",
            list_id=list_id,
            error="list_not_found",
        )
    except Exception as e:
        logger.error(f"Failed to backfill list {list_id}: {e}", exc_info=True)
        track(
            "backfill_list_action_failed",
            list_id=list_id,
            error=str(e),
        )
        # Re-raise to allow task framework to handle retries for transient failures
        raise
