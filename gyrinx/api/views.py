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
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from gyrinx.api.models import WebhookRequest

logger = logging.getLogger(__name__)


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
