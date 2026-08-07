"""The preview endpoint: form state in, card state out.

Tom's framing (design/authoring.md): the scratch-card UI is earnable if
"an endpoint that takes the form state and gives back card state"
exists. This is that endpoint, deliberately thin — everything it does
lives in :mod:`n26.preview`, and nothing it does survives the request:
the preview rolls its own transaction back.
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from n26.core.preview import PreviewError, preview


@require_POST
def preview_view(request):
    try:
        state = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"errors": {"body": ["Not JSON."]}}, status=400)
    try:
        result = preview(state)
    except PreviewError as refusal:
        return JsonResponse({"errors": refusal.errors}, status=400)
    return JsonResponse(result.as_dict())
