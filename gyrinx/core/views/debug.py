"""Debug-only views for development utilities.

These views are only available when DEBUG=True or GYRINX_DEBUG=True.
"""

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render

from gyrinx.core.models import List

# Test plans directory relative to project root
TEST_PLANS_DIR = Path(settings.BASE_DIR) / ".claude" / "test-plans"


def get_available_plans():
    """Get list of available test plans.

    Returns a dict mapping filename to plan metadata including the file path.
    This provides the canonical list of servable files.
    """
    plans = {}
    if TEST_PLANS_DIR.exists():
        for f in sorted(TEST_PLANS_DIR.glob("*.md"), reverse=True):
            plans[f.name] = {
                "name": f.stem,
                "filename": f.name,
                "modified": f.stat().st_mtime,
                "path": f,
            }
    return plans


def debug_test_plan_index(request):
    """List all available test plans."""
    if not settings.DEBUG:
        raise Http404("Debug views are only available in development")

    plans = get_available_plans()

    return render(
        request,
        "core/debug/test_plan_index.html",
        {"plans": list(plans.values())},
    )


def debug_test_plan_detail(request, filename):
    """Serve raw content of a test plan file."""
    if not settings.DEBUG:
        raise Http404("Debug views are only available in development")

    # Security: only serve files from the known list of available plans
    # This prevents path traversal and arbitrary file access
    plans = get_available_plans()
    if filename not in plans:
        raise Http404("Test plan not found")

    # Read from the canonical path we enumerated, not from user input
    file_path = plans[filename]["path"]
    content = file_path.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def debug_list_actions(request, list_id):
    """Display all actions for a list, sorted newest first."""
    lst = get_object_or_404(List, id=list_id)
    actions = lst.actions.select_related("user", "list_fighter").order_by("-created")

    return render(
        request,
        "core/debug/list_actions.html",
        {"list": lst, "actions": actions},
    )
