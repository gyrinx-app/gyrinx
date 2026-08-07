"""Handlers for campaign operations (starting campaigns, etc.)."""

import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.tasks.groups import enqueue_in_group
from gyrinx.tracing import traced
from gyrinx.tracker import track
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.campaign import Campaign, CampaignAction
from n23.core.models.list import List

logger = logging.getLogger(__name__)


def campaign_start_group_key(campaign_id) -> str:
    """Task group key for the background gang-clones of one campaign start (#1222).

    Shared by the enqueue (Phase 1), the owner retry endpoint, and the admin re-enqueue
    action so they all land in the same group, and by the campaign page's poller (via the
    generic /tasks/status endpoint). The campaign UUID makes the key unguessable.
    """
    return f"campaign-start:{campaign_id}"


@dataclass
class ListBudgetDistributionResult:
    """Result of distributing budget to a single list."""

    campaign_list: List
    list_action: ListAction | None
    campaign_action: CampaignAction | None
    credits_added: int
    reason: str = ""


@dataclass
class CampaignStartResult:
    """Result of starting a campaign (Phase 1 — synchronous stub creation).

    The heavy per-list work — cloning fighters/equipment/stash, distributing budget,
    allocating resources — runs afterwards in background tasks
    (``complete_campaign_list_clone``), so this reports only what Phase 1 created
    synchronously: the stub lists (each in ``CLONING_IN_PROGRESS``) and the overall action.
    """

    campaign: Campaign
    stub_lists: list[List]
    overall_campaign_action: CampaignAction


@traced("handle_campaign_start")
@transaction.atomic
def handle_campaign_start(
    *,
    user,
    campaign: Campaign,
) -> CampaignStartResult:
    """
    Handle starting a campaign — Phase 1 (fast, synchronous).

    Cloning a gang runs ``facts_from_db`` and touches many rows; doing that for every
    LIST_BUILDING list inline blocks the request for tens of seconds with 10–50 gangs
    (issue #1222). So this splits into two phases:

    Phase 1 (here, synchronous, atomic):
    - Validate the campaign can be started.
    - Create one lightweight **stub** list per LIST_BUILDING list — a campaign-mode clone
      row in ``CLONING_IN_PROGRESS`` with only cheap scalar fields copied (no fighters,
      no budget, no facts recompute) — and add it to the campaign.
    - Flip the campaign to IN_PROGRESS and record the overall "N gangs joined" action.
    - Enqueue one ``complete_campaign_list_clone`` task per stub (on commit).

    Phase 2 (``complete_campaign_list_clone``, background, one task per stub):
    - Populate the stub, book CLONE/CREATE actions, distribute budget, allocate resources,
      then flip it to CAMPAIGN_MODE.

    Enqueue is deferred to ``transaction.on_commit`` because in production the task worker
    runs in a separate process and must not dequeue a stub before it is committed; in
    dev/test the ImmediateBackend runs the task inline once the transaction commits.

    Args:
        user: The user starting the campaign
        campaign: The campaign to start

    Returns:
        CampaignStartResult with the created stub lists and overall action

    Raises:
        ValidationError: If campaign cannot be started
    """
    logger.info(f"Starting campaign {campaign.id} by user {user.id}")

    # Validate campaign can be started
    if not campaign.can_start_campaign():
        if campaign.status != Campaign.PRE_CAMPAIGN:
            raise ValidationError(
                f"Campaign cannot be started. Current status: {campaign.get_status_display()}"
            )
        elif not campaign.has_lists:
            raise ValidationError("Campaign cannot be started without lists.")
        else:
            raise ValidationError("Campaign cannot be started.")

    # Get all LIST_BUILDING lists before clearing
    original_lists: list[List] = list(campaign.lists.filter(status=List.LIST_BUILDING))
    logger.info(
        f"Campaign {campaign.id} has {len(original_lists)} lists to clone for campaign start"
    )
    campaign.lists.clear()

    stub_lists = []
    # (stub_id, original_list_id, label) entries to enqueue for Phase 2 once we commit.
    to_enqueue: list[tuple[str, str, str]] = []

    for original_list in original_lists:
        # Idempotency: if a clone or in-flight stub already exists for this original
        # (e.g. a retried Phase 1), re-add it rather than creating a duplicate.
        existing = List.objects.filter(
            original_list=original_list,
            campaign=campaign,
            status__in=[List.CAMPAIGN_MODE, List.CLONING_IN_PROGRESS],
        ).first()
        if existing:
            logger.warning(
                f"Campaign {campaign.id} already has a clone of list {original_list.id} "
                f"({existing.status}), re-adding existing"
            )
            campaign.lists.add(existing)
            stub_lists.append(existing)
            # A stub that never finished still needs its Phase 2 task.
            if existing.status == List.CLONING_IN_PROGRESS:
                to_enqueue.append(
                    (str(existing.id), str(original_list.id), existing.name)
                )
            continue

        # Create the stub: a campaign-mode clone row whose contents Phase 2 will fill in.
        # Copy only the cheap scalar fields (same set List.clone() sets at create time);
        # rating/stash are recomputed by the clone task, credits handled there too.
        stub = List.objects.create(
            name=original_list.name,
            content_house=original_list.content_house,
            owner=original_list.owner,
            public=original_list.public,
            narrative=original_list.narrative,
            notes=original_list.notes,
            theme_color=original_list.theme_color,
            credits_current=original_list.credits_current,
            credits_earned=original_list.credits_earned,
            status=List.CLONING_IN_PROGRESS,
            original_list=original_list,
            campaign=campaign,
        )
        campaign.lists.add(stub)
        stub_lists.append(stub)
        to_enqueue.append((str(stub.id), str(original_list.id), stub.name))

    # Update campaign status to IN_PROGRESS
    campaign.status = Campaign.IN_PROGRESS
    campaign.save()

    # Create overall campaign action (the count is known now — one per stub)
    overall_campaign_action = CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        description=f"Campaign Started: {campaign.name} is now in progress",
        outcome=f"{len(stub_lists)} gang(s) joined the campaign",
        owner=user,
    )

    # Enqueue Phase 2 after the transaction commits (see docstring).
    campaign_id = str(campaign.id)
    user_id = str(user.id)
    group_key = campaign_start_group_key(campaign_id)

    def _enqueue():
        from n23.core.tasks import complete_campaign_list_clone

        for stub_id, original_list_id, label in to_enqueue:
            try:
                enqueue_in_group(
                    complete_campaign_list_clone,
                    group_key=group_key,
                    label=label,
                    stub_id=stub_id,
                    original_list_id=original_list_id,
                    campaign_id=campaign_id,
                    user_id=user_id,
                )
            except Exception as e:
                # Fire-and-forget: a publish failure must not break campaign start. The
                # stub stays CLONING_IN_PROGRESS and can be retried (owner button / admin).
                logger.warning(
                    f"Failed to enqueue campaign clone for stub {stub_id}: {e}"
                )
                track(
                    "task_enqueue_failed",
                    stub_id=stub_id,
                    campaign_id=campaign_id,
                    error=str(e),
                )

    transaction.on_commit(_enqueue)

    return CampaignStartResult(
        campaign=campaign,
        stub_lists=stub_lists,
        overall_campaign_action=overall_campaign_action,
    )


@traced("_distribute_budget_to_list")
def _distribute_budget_to_list(
    *,
    user,
    campaign: Campaign,
    campaign_list: List,
    list_cost: int,
) -> ListBudgetDistributionResult:
    """
    Distribute campaign starting budget to a list.

    Creates ListAction to track the credit distribution and updates
    the list's credits atomically.

    Args:
        user: The user performing the distribution
        campaign: The campaign providing the budget
        campaign_list: The list receiving the budget

    Returns:
        ListBudgetDistributionResult with created actions and credits added
    """
    if campaign.budget <= 0:
        return ListBudgetDistributionResult(
            campaign_list=campaign_list,
            list_action=None,
            campaign_action=None,
            credits_added=0,
            reason="Campaign budget is zero",
        )

    # Calculate credits to add: max(0, budget - list cost)
    # List cost is the rating + stash (excluding any existing credits)
    credits_to_add = max(0, campaign.budget - list_cost)

    if credits_to_add <= 0:
        return ListBudgetDistributionResult(
            campaign_list=campaign_list,
            list_action=None,
            campaign_action=None,
            credits_added=0,
            reason="List cost exceeds or meets campaign budget",
        )

    description = f"Campaign starting budget: Received {credits_to_add}¢ ({campaign.budget}¢ budget - {list_cost}¢ gang rating)"

    # Record the grant, then apply the credit movement explicitly
    # (create_action is a pure record).
    list_action = campaign_list.create_action(
        user=user,
        action_type=ListActionType.CAMPAIGN_START,
        subject_app="core",
        subject_type="Campaign",
        subject_id=campaign.id,
        description=description,
        rating_delta=0,
        stash_delta=0,
        credits_delta=credits_to_add,
    )
    campaign_list.apply_credit_delta(credits_to_add)

    # Create CampaignAction for visibility
    campaign_action = CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        list=campaign_list,
        description=description,
        outcome=f"+{credits_to_add}¢ (to {campaign_list.credits_current}¢)",
        owner=user,
    )

    return ListBudgetDistributionResult(
        campaign_list=campaign_list,
        list_action=list_action,
        campaign_action=campaign_action,
        credits_added=credits_to_add,
        reason="Budget distributed successfully",
    )
