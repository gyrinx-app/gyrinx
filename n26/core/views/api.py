"""Accept staff-only POST preview state and return card data as JSON.

n26.core.preview validates and derives the result inside a rolled-back
transaction. Invalid JSON or preview state returns structured 400 errors.
See design/authoring.md.
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
