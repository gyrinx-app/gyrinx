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


def debug_design_system(request):
    """Design system reference page for rebuilding in Figma."""
    if not settings.DEBUG:
        raise Http404("Debug views are only available in development")

    theme_colours = [
        ("blue", "#0771ea"),
        ("indigo", "#5111dc"),
        ("purple", "#5d3cb0"),
        ("pink", "#c02d83"),
        ("red", "#cb2b48"),
        ("orange", "#ea5d0c"),
        ("yellow", "#e8a10a"),
        ("green", "#1a7b49"),
        ("teal", "#1fb27e"),
        ("cyan", "#10bdd3"),
    ]
    semantic_colours = [
        "primary",
        "secondary",
        "success",
        "danger",
        "warning",
        "info",
        "light",
        "dark",
    ]
    common_icons = [
        ("bi-plus", "plus"),
        ("bi-plus-lg", "plus-lg"),
        ("bi-dash", "dash"),
        ("bi-pencil", "pencil"),
        ("bi-trash", "trash"),
        ("bi-archive", "archive"),
        ("bi-person", "person"),
        ("bi-house-door", "house-door"),
        ("bi-crosshair", "crosshair"),
        ("bi-wrench", "wrench"),
        ("bi-journal-text", "journal-text"),
        ("bi-lightning", "lightning"),
        ("bi-exclamation-triangle", "warning"),
        ("bi-link-45deg", "link"),
        ("bi-search", "search"),
        ("bi-gear", "gear"),
        ("bi-arrow-left", "arrow-left"),
        ("bi-chevron-right", "chevron-right"),
    ]
    spacing_scale = [
        ("0", "0"),
        ("1", "0.25"),
        ("2", "0.5"),
        ("3", "1"),
        ("4", "1.5"),
        ("5", "3"),
    ]

    return render(
        request,
        "core/debug/design_system.html",
        {
            "theme_colours": theme_colours,
            "semantic_colours": semantic_colours,
            "common_icons": common_icons,
            "spacing_scale": spacing_scale,
        },
    )


def debug_list_actions(request, list_id):
    """Display all actions for a list, sorted newest first."""
    lst = get_object_or_404(List, id=list_id)
    actions = lst.actions.select_related("user", "list_fighter").order_by("-created")

    return render(
        request,
        "core/debug/list_actions.html",
        {"list": lst, "actions": actions},
    )
