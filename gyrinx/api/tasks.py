"""Platform integration tasks for Discord and GitHub."""

import logging

import requests
from django.conf import settings
from django.tasks import task

from gyrinx.tasks import TaskRoute

logger = logging.getLogger(__name__)


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
    """React to a Discord message and dispatch its details to the issue-creation workflow.

    Report missing configuration, network errors or a refused dispatch through
    the deferred Discord response. The GitHub workflow owns issue creation.
    """
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
    """Add the processing reaction, logging failures without raising."""
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


task_routes = [
    TaskRoute(trigger_discord_issue_action),
]
