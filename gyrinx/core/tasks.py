import logging
from collections import defaultdict

import requests
from django.conf import settings
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
def propagate_content_cost_change(
    content_type_id: int, object_id: str, before_snapshots: dict | None = None
):
    """Recalculate cached costs and create audit actions for a content cost change.

    Enqueued (after commit) when a content model's cost field changes. Re-fetches
    the instance via its ContentType + pk, then runs the existing
    ``_create_content_cost_change_actions`` helper, which finds every affected
    list, recalculates its facts with the new cost, and creates a
    CONTENT_COST_CHANGE action (applying credit adjustments in campaign mode).

    ``before_snapshots`` is the ``{str(list_id): [rating, stash]}`` map captured
    synchronously at enqueue time (pre-change baselines). The helper uses it as
    the delta baseline so a list viewed (and lazily recalculated) before this
    task runs doesn't cause a zero delta — which would silently drop the action
    and the campaign credit adjustment.

    Running this off the request thread is the whole point: a popular base item
    can touch thousands of lists, and the recalculation walks each list's full
    fighter suite. Doing it inline in the admin save blew the request budget.

    Idempotent: each created action records the content instance as its subject
    with the pre-change baseline, and the helper skips a list that already has a
    matching applied action — so a redelivery doesn't create spurious actions or
    double-charge credits. References to deleted instances are handled gracefully
    (the instance lookup returns and the task is a no-op).
    """
    from django.contrib.contenttypes.models import ContentType

    from gyrinx.content.models.signal_handlers import (
        _create_content_cost_change_actions,
    )

    try:
        content_type = ContentType.objects.get_for_id(content_type_id)
    except ContentType.DoesNotExist:
        logger.warning(
            "propagate_content_cost_change: unknown content_type_id %s",
            content_type_id,
        )
        return

    model_class = content_type.model_class()
    if model_class is None:
        logger.warning(
            "propagate_content_cost_change: content_type %s has no model class",
            content_type_id,
        )
        return

    # Use all_content() where available so pack-scoped content still resolves
    # (the default ContentManager excludes pack items); fall back to the default
    # manager for any sender without it.
    manager = model_class._default_manager
    base_qs = (
        manager.all_content() if hasattr(manager, "all_content") else manager.all()
    )
    try:
        instance = base_qs.get(pk=object_id)
    except model_class.DoesNotExist:
        logger.warning(
            "propagate_content_cost_change: %s %s no longer exists",
            content_type,
            object_id,
        )
        return

    _create_content_cost_change_actions(instance, before_snapshots=before_snapshots)


@task
def propagate_default_child_fighter_assignment(default_assignment_id: str):
    """Propagate a newly-created child-spawning default to existing gangs.

    When a pack author adds a ``ContentFighterDefaultAssignment`` whose
    equipment spawns a child fighter (a vehicle / exotic beast), every gang
    already subscribed to a pack containing that fighter type — and holding a
    list-fighter of that type — should get the child fighter materialised, not
    just gangs created after the change (issue #1725).

    Idempotent: re-running is safe (the materialisation helper skips disabled
    and already-materialised defaults).
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db import transaction

    from gyrinx.content.models.default_assignment import (
        ContentFighterDefaultAssignment,
    )
    from gyrinx.content.models.fighter import ContentFighter
    from gyrinx.core.models.action import ListActionType
    from gyrinx.core.models.list import (
        ListFighter,
        _materialise_child_fighter_defaults,
    )
    from gyrinx.core.models.pack import CustomContentPackItem

    try:
        default = ContentFighterDefaultAssignment.objects.get(pk=default_assignment_id)
    except ContentFighterDefaultAssignment.DoesNotExist:
        logger.warning(
            f"Default assignment {default_assignment_id} not found for propagation"
        )
        return

    # Re-verify at execution time: the profile may have been removed between
    # enqueue and run. Only child-spawning defaults need materialising.
    if not default.equipment.contentequipmentfighterprofile_set.exists():
        return

    # Packs containing this fighter type. This is a subscriber read path, so we
    # must NOT filter `archived` on the pack or pack item — archived content
    # stays visible to gangs already subscribed (see CLAUDE.md "Content packs:
    # archive semantics", issue #1742).
    fighter_ct = ContentType.objects.get_for_model(ContentFighter)
    pack_ids = list(
        CustomContentPackItem.objects.filter(
            content_type=fighter_ct, object_id=default.fighter_id
        )
        .values_list("pack_id", flat=True)
        .distinct()
    )
    if not pack_ids:
        return

    # Affected list-fighters: of this fighter type, on lists subscribed to a
    # pack that contains the fighter. Legacy-only fighters
    # (legacy_content_fighter) are a documented gap — the materialisation
    # helper acts on content_fighter defaults only, matching the hire-time
    # path.
    affected = (
        ListFighter.objects.filter(
            content_fighter=default.fighter,
            archived=False,
            list__packs__in=pack_ids,
        )
        .select_related("list")
        .distinct()
    )

    # Group by list so we create at most one action per affected gang.
    fighters_by_list: dict[str, list] = defaultdict(list)
    for fighter in affected:
        fighters_by_list[fighter.list_id].append(fighter)

    equipment_name = default.equipment.name

    propagated_count = 0
    for list_id, fighters in fighters_by_list.items():
        try:
            with transaction.atomic():
                created_total = 0
                for fighter in fighters:
                    created_total += _materialise_child_fighter_defaults(fighter)

                # Idempotent no-op: already materialised on every fighter.
                if created_total == 0:
                    continue

                # affected is select_related("list"), so reuse the loaded
                # instance rather than re-fetching the list.
                lst = fighters[0].list

                # Keep the list's cached rating/stash consistent.
                old_rating = lst.rating_current
                old_stash = lst.stash_current
                facts = lst.facts_from_db(update=True)
                rating_delta = facts.rating - old_rating
                stash_delta = facts.stash - old_stash

                # Awareness-only action. Materialising a child-spawning default
                # has a net-zero cost impact (the default is virtual/0-cost, the
                # direct assignment uses cost_override=0, and child fighters
                # don't contribute to list cost), so we never charge or refund
                # credits — even in campaign mode. We still log it so gang
                # owners see why a new fighter appeared.
                lst.create_action(
                    action_type=ListActionType.CONTENT_COST_CHANGE,
                    description=f"Pack added a default {equipment_name}",
                    rating_before=old_rating,
                    stash_before=old_stash,
                    rating_delta=rating_delta,
                    stash_delta=stash_delta,
                    credits_delta=0,
                    update_credits=False,
                    skip_apply=["rating", "stash"],
                )
                propagated_count += 1
        except Exception:
            logger.exception(
                f"Failed to propagate default {default_assignment_id} to list {list_id}"
            )

    logger.info(
        f"Propagated default {default_assignment_id}: "
        f"materialised on {propagated_count} list(s), "
        f"checked {len(fighters_by_list)}"
    )


@task
def trigger_discord_issue_action(
    channel_id: str,
    message_id: str,
    guild_id: str,
    interaction_token: str,
    application_id: str,
    message_content: str,
    message_author: str,
    requesting_user: str,
):
    """
    Trigger a GitHub Action to create an issue from a Discord message.

    Adds a 👀 reaction to the original message, then sends a repository_dispatch
    event to gyrinx-app/gyrinx. The GitHub Action fetches the full thread/reply
    chain, calls Claude to summarise, creates the issue, posts a visible reply
    with the link, and deletes the ephemeral "thinking" message (or updates it
    on failure).
    """
    # React with 👀 to signal the message is being processed
    _add_discord_reaction(channel_id, message_id)

    token = settings.GITHUB_DISPATCH_TOKEN
    if not token:
        logger.error("No GITHUB_DISPATCH_TOKEN configured")
        _update_discord_message(
            application_id,
            interaction_token,
            "Failed to create issue: GitHub integration not configured.",
        )
        return

    try:
        response = requests.post(
            "https://api.github.com/repos/gyrinx-app/gyrinx/dispatches",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "event_type": "discord-issue-request",
                "client_payload": {
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "guild_id": guild_id,
                    "interaction_token": interaction_token,
                    "application_id": application_id,
                    "message_content": message_content,
                    "message_author": message_author,
                    "requesting_user": requesting_user,
                },
            },
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to reach GitHub API: {e}")
        _update_discord_message(
            application_id,
            interaction_token,
            "Failed to create issue: could not reach GitHub.",
        )
        return

    if response.status_code == 204:
        logger.info(
            f"Triggered GitHub Action for Discord message {message_id} "
            f"in channel {channel_id}"
        )
    else:
        logger.error(
            f"Failed to trigger GitHub Action: {response.status_code} {response.text}"
        )
        _update_discord_message(
            application_id,
            interaction_token,
            "Failed to create issue: could not trigger GitHub Action.",
        )


def _add_discord_reaction(channel_id: str, message_id: str):
    """Add a 👀 reaction to a Discord message to signal processing."""
    bot_token = settings.DISCORD_BOT_TOKEN
    if not bot_token:
        logger.warning("No DISCORD_BOT_TOKEN configured, skipping reaction")
        return

    try:
        response = requests.put(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/%F0%9F%91%80/@me",
            headers={"Authorization": f"Bot {bot_token}"},
            timeout=10,
        )
        if response.status_code not in (200, 204):
            logger.warning(
                f"Failed to add reaction: {response.status_code} {response.text}"
            )
    except Exception as e:
        logger.warning(f"Failed to add Discord reaction: {e}")


def _update_discord_message(application_id: str, interaction_token: str, content: str):
    """Update a deferred Discord interaction response."""
    try:
        requests.patch(
            f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}/messages/@original",
            json={"content": content},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Failed to update Discord message: {e}")
