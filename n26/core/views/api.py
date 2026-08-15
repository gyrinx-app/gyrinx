"""The preview endpoint: form state in, card state out.

The scratch-card UI becomes possible once an endpoint takes form state
and gives back card state (design/authoring.md). This is that endpoint,
deliberately thin — everything it does lives in :mod:`n26.core.preview`,
and nothing it does survives the request: the preview rolls its own
transaction back.

It answers for the authoring pages, so it wants the same account they
do: the state it is handed names library content, and the card it gives
back is the whole of what they mean.
"""

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from n26.core.preview import PreviewError, preview


@staff_member_required
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
