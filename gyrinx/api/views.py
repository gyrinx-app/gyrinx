"""
Webhooks allow you to receive real-time updates from Patreon servers.

We provie a URL for Patreon to send an HTTP POST to when one of a few events occur. This POST request will
contain the relevant data from the user action in JSON format. It will also have headers:

    X-Patreon-Event: [trigger]
    X-Patreon-Signature: [message signature]

where the message signature is the HEX digest of the message body HMAC signed (with MD5) using your webhook's secret viewable on the webhooks page.
You can use this to verify us as the sender of the message.


Sample Webhook payload

{
  "data": {
    "attributes": {
      "amount_cents": 250,
      "created_at": "2015-05-18T23:50:42+00:00",
      "declined_since": null,
      "patron_pays_fees": false,
      "pledge_cap_cents": null
    },
    "id": "1",
    "relationships": {
      "address": {
        "data": null
      },
      "card": {
        "data": null
      },
      "creator": {
        "data": {
          "id": "3024102",
          "type": "user"
        },
        "links": {
          "related": "https://www.patreon.com/api/user/3024102"
        }
      },
      "patron": {
        "data": {
          "id": "32187",
          "type": "user"
        },
        "links": {
          "related": "https://www.patreon.com/api/user/32187"
        }
      },
      "reward": {
        "data": {
          "id": "599336",
          "type": "reward"
        },
        "links": {
          "related": "https://www.patreon.com/api/rewards/599336"
        }
      }
    },
    "type": "pledge"
  },
  "included": [{ ** * Creator Object ** *
    },
    { ** * Patron Object ** *
    },
    { ** * Reward Object ** *
    },
  ]
}

Triggers
A trigger is an event type. The syntax of a trigger is [resource]:[action] (e.g. pledges:create).
We can add or remove triggers for a webhook to listen to on the webhooks page:
https://www.patreon.com/portal/registration/register-webhooks

Trigger	Description
pledge:create	Fires when a user pledges to a creator. This trigger fires even if the charge is declined or fraudulent.
    The pledge object is still created, even if the user is not a valid patron due to charge status.
pledge:update	Fires when a user edits their pledge. Notably, the pledge ID will change, because the underlying pledge object is different.
    The user id should be the primary key to reference.
pledge:delete	Fires when a user stops pledging or the pledge is cancelled altogether. Does not fire for pledge pausing, as the pledge still exists.
members:create    Fires when a user becomes a patron of a creator.
members:update    Fires when a user updates their membership tier.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from gyrinx.api.models import WebhookRequest

logger = logging.getLogger(__name__)


# Discord interaction types
DISCORD_PING = 1
DISCORD_APPLICATION_COMMAND = 2

# Discord interaction response types
DISCORD_PONG = 1
DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5


@csrf_exempt
def hook_patreon(request):
    if not settings.PATREON_HOOK_SECRET:
        logger.error("No Patreon hook secret set")
        return HttpResponse(status=503)

    if request.method == "POST":
        signature = request.headers.get("X-Patreon-Signature", "")
        if not signature:
            logger.error("No signature provided")
            return HttpResponse(status=400)

        # "the message signature is the HEX digest of the message body HMAC signed (with MD5)"
        computed_signature = hmac.new(
            settings.PATREON_HOOK_SECRET.encode(), request.body, hashlib.md5
        ).hexdigest()

        if settings.DEBUG:
            print(f"Computed signature: {computed_signature}")
            print(f"Received signature: {signature}")

        if not hmac.compare_digest(computed_signature, signature):
            logger.error("Invalid signature")
            return HttpResponse(status=400)

        try:
            event = request.headers.get("X-Patreon-Event", "")
            payload = json.loads(request.body)
            wr = WebhookRequest.objects.create(
                source="patreon",
                event=event,
                payload=payload,
                signature=signature,
            )
            wr.save()
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return HttpResponse(status=400)
        except Exception as e:
            logger.error(f"Error saving webhook request: {e}")
            return HttpResponse(status=500)

        return HttpResponse(status=204)

    if request.method == "GET":
        # Handle GET requests if needed, e.g., for health checks
        return HttpResponse(
            json.dumps(
                {
                    "status": "ok",
                    "message": "Patreon webhook is active and ready to receive events.",
                }
            ),
            status=200,
            content_type="application/json",
        )

    return HttpResponse(status=400)


def _verify_discord_signature(body: bytes, signature: str, timestamp: str) -> bool:
    """Verify Discord interaction signature using Ed25519."""
    try:
        verify_key = VerifyKey(bytes.fromhex(settings.DISCORD_PUBLIC_KEY))
        verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


@csrf_exempt
def discord_interactions(request):
    """
    Discord Interactions Endpoint.

    Receives HTTP POST from Discord when users invoke the "Create Issue"
    message context menu command. Verifies the Ed25519 signature, handles
    PING for endpoint verification, and enqueues a background task for
    application commands.

    See: https://discord.com/developers/docs/interactions/overview
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    if not settings.DISCORD_PUBLIC_KEY:
        logger.error("No Discord public key configured")
        return HttpResponse(status=503)

    # Verify Ed25519 signature
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")

    if not signature or not timestamp:
        logger.error("Missing Discord signature headers")
        return HttpResponse(status=401)

    if not _verify_discord_signature(request.body, signature, timestamp):
        logger.error("Invalid Discord signature")
        return HttpResponse(status=401)

    # Parse interaction
    try:
        interaction = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in Discord interaction")
        return HttpResponse(status=400)

    interaction_type = interaction.get("type")

    # Handle PING (Discord endpoint verification)
    if interaction_type == DISCORD_PING:
        return JsonResponse({"type": DISCORD_PONG})

    # Handle application commands (context menu)
    if interaction_type == DISCORD_APPLICATION_COMMAND:
        return _handle_discord_command(interaction, signature)

    logger.warning(f"Unknown Discord interaction type: {interaction_type}")
    return HttpResponse(status=400)


def _handle_discord_command(interaction: dict, signature: str) -> JsonResponse:
    """Handle a Discord application command interaction."""
    data = interaction.get("data", {})
    command_name = data.get("name", "")

    # Store for audit trail
    try:
        WebhookRequest.objects.create(
            source="discord",
            event=f"command:{command_name}",
            payload=interaction,
            signature=signature,
        )
    except Exception as e:
        logger.error(f"Error saving Discord webhook request: {e}")

    if command_name != "Create Issue":
        logger.warning(f"Unknown Discord command: {command_name}")
        return JsonResponse(
            {
                "type": DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
                "data": {"flags": 64},  # Ephemeral
            }
        )

    # Extract required fields
    target_id = data.get("target_id")
    channel_id = interaction.get("channel_id")
    guild_id = interaction.get("guild_id")
    interaction_token = interaction.get("token")

    if not all([target_id, channel_id, interaction_token]):
        logger.error("Missing required fields in Discord interaction")
        return JsonResponse(
            {
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": "Sorry, the request was missing required information.",
                    "flags": 64,  # Ephemeral
                },
            }
        )

    # Extract the target message from resolved data
    resolved = data.get("resolved", {})
    messages = resolved.get("messages", {})
    target_message = messages.get(target_id, {})

    # Get the user who triggered the command
    member = interaction.get("member", {})
    user = member.get("user", {}) or interaction.get("user", {})
    username = user.get("username", "unknown")

    # Enqueue the background task to trigger GitHub Action
    try:
        from gyrinx.core.tasks import trigger_discord_issue_action

        trigger_discord_issue_action.enqueue(
            channel_id=channel_id,
            message_id=target_id,
            guild_id=guild_id or "",
            interaction_token=interaction_token,
            application_id=settings.DISCORD_APPLICATION_ID,
            message_content=target_message.get("content", ""),
            message_author=target_message.get("author", {}).get("username", "unknown"),
            requesting_user=username,
        )
    except Exception as e:
        logger.error(f"Error enqueuing Discord issue task: {e}", exc_info=True)
        return JsonResponse(
            {
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": "Sorry, something went wrong. Please try again later.",
                    "flags": 64,  # Ephemeral
                },
            }
        )

    # Return deferred response ("Bot is thinking...")
    return JsonResponse(
        {
            "type": DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"flags": 64},  # Ephemeral - only visible to the user
        }
    )
