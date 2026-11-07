"""Receive authenticated Patreon webhooks and Discord interactions.

Patreon signs the raw body with HMAC-MD5 in X-Patreon-Signature. Discord
uses Ed25519 over its timestamp and body. Store accepted payloads for audit;
process Patreon membership inline and enqueue Discord issue commands.
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


# Discord interaction types.
DISCORD_PING = 1
DISCORD_APPLICATION_COMMAND = 2

# Discord interaction response types.
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

        # Patreon signs the raw request body with the configured shared secret.
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

        try:
            from gyrinx.api.patreon import process_patreon_webhook

            process_patreon_webhook(payload, event)
        except Exception:
            # Keep the accepted response after storing the payload, even if processing fails.
            # The admin can replay the stored webhook without asking Patreon to redeliver it.
            logger.exception("Error processing Patreon webhook")

        return HttpResponse(status=204)

    if request.method == "GET":
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
    except BadSignatureError, ValueError:
        return False


@csrf_exempt
def discord_interactions(request):
    """Verify a Discord POST, answer PING or dispatch an application command."""
    if request.method != "POST":
        return HttpResponse(status=405)

    if not settings.DISCORD_PUBLIC_KEY:
        logger.error("No Discord public key configured")
        return HttpResponse(status=503)

    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")

    if not signature or not timestamp:
        logger.error("Missing Discord signature headers")
        return HttpResponse(status=401)

    if not _verify_discord_signature(request.body, signature, timestamp):
        logger.error("Invalid Discord signature")
        return HttpResponse(status=401)

    try:
        interaction = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in Discord interaction")
        return HttpResponse(status=400)

    interaction_type = interaction.get("type")

    if interaction_type == DISCORD_PING:
        return JsonResponse({"type": DISCORD_PONG})

    if interaction_type == DISCORD_APPLICATION_COMMAND:
        return _handle_discord_command(interaction, signature)

    logger.warning(f"Unknown Discord interaction type: {interaction_type}")
    return HttpResponse(status=400)


def _handle_discord_command(interaction: dict, signature: str) -> JsonResponse:
    """Handle a Discord application command interaction."""
    data = interaction.get("data", {})
    command_name = data.get("name", "")

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
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": "Sorry, I don't recognise that command.",
                    "flags": 64,  # Ephemeral
                },
            }
        )

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

    resolved = data.get("resolved", {})
    messages = resolved.get("messages", {})
    target_message = messages.get(target_id, {})

    member = interaction.get("member", {})
    user = member.get("user", {}) or interaction.get("user", {})
    username = user.get("username", "unknown")

    try:
        from gyrinx.api.tasks import trigger_discord_issue_action

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

    return JsonResponse(
        {
            "type": DISCORD_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"flags": 64},  # Ephemeral - only visible to the user
        }
    )
