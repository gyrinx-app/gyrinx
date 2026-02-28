import logging

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
