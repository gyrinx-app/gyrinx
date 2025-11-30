"""Debug-only views for development utilities.

These views are only available when DEBUG=True.
"""

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render

# Test plans directory relative to project root
TEST_PLANS_DIR = Path(settings.BASE_DIR) / ".claude" / "test-plans"


def debug_test_plan_index(request):
    """List all available test plans."""
    if not settings.DEBUG:
        raise Http404("Debug views are only available in development")

    plans = []
    if TEST_PLANS_DIR.exists():
        for f in sorted(TEST_PLANS_DIR.glob("*.md"), reverse=True):
            plans.append(
                {
                    "name": f.stem,
                    "filename": f.name,
                    "modified": f.stat().st_mtime,
                }
            )

    return render(
        request,
        "core/debug/test_plan_index.html",
        {"plans": plans},
    )


def debug_test_plan_detail(request, filename):
    """Serve raw content of a test plan file."""
    if not settings.DEBUG:
        raise Http404("Debug views are only available in development")

    # Security: resolve the path and verify it's within the allowed directory
    # This prevents path traversal attacks (e.g., ../../../etc/passwd)
    try:
        base_dir = TEST_PLANS_DIR.resolve()
        file_path = (TEST_PLANS_DIR / filename).resolve()

        # Ensure the resolved path is within the test plans directory
        if not file_path.is_relative_to(base_dir):
            raise Http404("Invalid filename")
    except (ValueError, OSError):
        raise Http404("Invalid filename")

    if not file_path.exists() or not file_path.is_file():
        raise Http404("Test plan not found")

    content = file_path.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="text/plain; charset=utf-8")
