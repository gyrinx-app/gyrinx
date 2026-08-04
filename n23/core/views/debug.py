"""Debug-only views for development utilities.

These views are only available when DEBUG=True or GYRINX_DEBUG=True.
"""

from pathlib import Path

from django import forms
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe

from n23.core.cost.balance_sheet import build_balance_sheet
from n23.core.models import List

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


class _DesignSystemDemoForm(forms.Form):
    """A throwaway form so the page can demo <c-form.field> against real
    BoundFields. The component refuses to render anything else -- passing a
    stringified widget is exactly the mistake that used to drop a field's
    errors silently (#2001), so it raises instead."""

    # The Bootstrap class goes on the WIDGET, exactly as every real form in
    # n23/core/forms/ does it. <c-form.field> renders the widget as the form
    # declares it and deliberately does not inject form-control -- a form that
    # omits the class renders an unstyled input, with or without the component.
    name = forms.CharField(
        label="Fighter name",
        initial="Stig the Miner",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    fighter_type = forms.ChoiceField(
        label="Fighter type",
        choices=[(c, c) for c in ("Juve", "Ganger", "Champion", "Leader")],
        initial="Champion",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    cost = forms.IntegerField(
        label="Cost",
        initial=55,
        help_text="Credits. Leave as-is to use the fighter type's base cost.",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    in_roster = forms.BooleanField(
        label="Include in roster",
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        initial="Some notes about this fighter.",
    )


def _design_system_demo_form(*, bound):
    """Unbound for the happy path; deliberately invalid when bound, so the page
    shows what a field with errors actually looks like."""
    if not bound:
        return _DesignSystemDemoForm()
    form = _DesignSystemDemoForm(
        data={"name": "", "fighter_type": "Wanderer", "cost": "x"}
    )
    form.is_valid()  # populate errors
    return form


def debug_design_system(request):
    """Design system living reference page."""
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
    # <c-btn variant="…"> takes the Bootstrap suffix verbatim, so these double as
    # the component's variant vocabulary. "link" is button-only (there is no
    # bg-link), which is why it is not in semantic_colours.
    button_variants = semantic_colours + ["link"]
    button_outline_variants = ["primary", "secondary", "success", "danger"]
    # <c-badge state="…"> maps a domain state to a colour so call sites never
    # pick one. Kept in step with the table in cotton/badge.html by
    # test_cotton_badge.py::test_state_table_covers_model_choices.
    badge_states = [
        ("active", "Fighter alive and available"),
        ("recovery", "Fighter recovering from injury"),
        ("convalescence", "Fighter in convalescence"),
        ("in_repair", "Vehicle under repair"),
        ("captured", "Held by another gang"),
        ("sold_to_guilders", "Sold to the Guilders"),
        ("dead", "Fighter is dead"),
        ("draft", "Crew not yet locked"),
        ("locked", "Crew locked for battle"),
        ("in_progress", "Battle or campaign running"),
    ]
    # Slot-free demo data for the <c-list> items-mode example.
    ds_skills = ["Nerves of Steel", "Spring Up"]
    # Canonical icons from the design system spec
    common_icons = [
        ("bi-plus-lg", "Add"),
        ("bi-pencil", "Edit"),
        ("bi-trash", "Delete"),
        ("bi-check-lg", "Save/confirm"),
        ("bi-chevron-left", "Back"),
        ("bi-search", "Search"),
        ("bi-exclamation-triangle", "Warning/error"),
        ("bi-info-circle", "Info"),
        ("bi-three-dots-vertical", "More options"),
        ("bi-box-seam", "Content pack"),
        ("bi-archive", "Archive"),
        ("bi-copy", "Clone"),
    ]
    # Additional icons used in the app
    extra_icons = [
        ("bi-dash", "dash"),
        ("bi-person", "person"),
        ("bi-house-door", "house-door"),
        ("bi-crosshair", "crosshair"),
        ("bi-wrench", "wrench"),
        ("bi-journal-text", "journal-text"),
        ("bi-lightning", "lightning"),
        ("bi-link-45deg", "link"),
        ("bi-gear", "gear"),
        ("bi-chevron-right", "chevron-right"),
        ("bi-eye", "public/visible"),
        ("bi-eye-slash", "unlisted"),
    ]
    spacing_scale = [
        ("0", "0"),
        ("1", "0.25"),
        ("2", "0.5"),
        ("3", "1"),
        ("4", "1.5"),
        ("5", "3"),
    ]

    page_shells = [
        ("Form page", "col-12 col-md-8 col-lg-6", "gap-3", "Edit forms, settings"),
        (
            "List/detail page",
            "col-lg-12 px-0",
            "gap-4",
            "Index, listing, and detail pages",
        ),
        ("Sidebar page", "row g-4", "\u2014", "Lore, notes (with TOC nav)"),
    ]
    custom_classes = [
        (".alert-icon", "Flex layout for alerts with pinned icon"),
        (".caps-label", "Uppercase, tracked, semibold section labels"),
        (".linked", "Composed link style (secondary, underline-opacity)"),
        (".fs-7", "Compact font size (0.79rem)"),
        (".mb-last-0", "Remove margin from last child in rich text"),
        (".flash-warn", "2s warning-colour fade animation for new items"),
        (".tooltipped", "Info-underline style with help cursor"),
        (".table-fixed", "table-layout: fixed for stat grids"),
        (
            ".house-icon",
            "Inline house SVG badge; transform-scaled ~25% (line-height safe), "
            "currentColor; emitted by {% house_icon house %}",
        ),
    ]

    # Mock campaign for breadcrumb demo (needs .id and .name)
    from types import SimpleNamespace

    ds_campaign = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000000", name="Underhive Wars"
    )

    # Mock owner for breadcrumb demo so the page renders logged-out too. The
    # breadcrumb reverses {% url 'core:user' owner.username %} and displays
    # str(owner); a fake object keeps the sample self-contained and avoids
    # depending on request.user (AnonymousUser has no username when logged out).
    class _DSUser:
        username = "underhive-boss"

        def __str__(self):
            return "Underhive Boss"

    ds_user = _DSUser()

    # Sample house icon for the design system preview. Mirrors the markup that
    # {% house_icon %} emits (class + fill + role/aria on the <svg> itself) so the
    # .house-icon CSS can be previewed without the alpha-gated tag or a real
    # house. Defined here as one source of truth for the section and table cell.
    # nosec B703 B308 - hardcoded literal SVG, no user input
    ds_house_icon_svg = mark_safe(  # nosec B703 B308
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
        'class="house-icon" fill="currentColor" role="img" aria-hidden="true">'
        '<path d="M8 1 1 5.5V15h4.5v-4h5v4H15V5.5L8 1Z" /></svg>'
    )

    return render(
        request,
        "core/debug/design_system.html",
        {
            "theme_colours": theme_colours,
            "semantic_colours": semantic_colours,
            "button_variants": button_variants,
            "button_outline_variants": button_outline_variants,
            "badge_states": badge_states,
            "ds_skills": ds_skills,
            "ds_form": _design_system_demo_form(bound=False),
            "ds_form_errors": _design_system_demo_form(bound=True),
            "common_icons": common_icons,
            "extra_icons": extra_icons,
            "spacing_scale": spacing_scale,
            "page_shells": page_shells,
            "custom_classes": custom_classes,
            "ds_campaign": ds_campaign,
            "ds_user": ds_user,
            "ds_house_icon_svg": ds_house_icon_svg,
        },
    )


def _get_debug_list_or_404(request, list_id):
    """Fetch a list for the internal debug views.

    Staff may view any list in any environment — these views double as
    production support tooling. Everyone else gets them only in development,
    and only for lists they own; anonymous users and non-owners get a 404
    rather than another list's data. (AnonymousUser has is_staff=False, so
    the staff branch never matches logged-out requests.)
    """
    if request.user.is_staff:
        return get_object_or_404(List, id=list_id)
    if settings.DEBUG and request.user.is_authenticated:
        return get_object_or_404(List, id=list_id, owner=request.user)
    raise Http404("List not found")


def debug_list_balance_sheet(request, list_id):
    """Itemised cost balance sheet for a list, with reconciliation problems.

    The read-only companion to debug_list_actions: decomposes every fighter
    and assignment into priced component lines, compares computed values with
    the caches, and checks the credits ledger and action-chain continuity.
    Part of the cost-pinning programme (#1826).
    """
    lst = _get_debug_list_or_404(request, list_id)

    sheet = build_balance_sheet(lst)
    problems = sheet.reconcile()

    return render(
        request,
        "core/debug/list_balance_sheet.html",
        {
            "list": lst,
            "sheet": sheet,
            "problems": problems,
            "all_fighters": sheet.all_fighters,
        },
    )


def debug_list_actions(request, list_id):
    """Display all actions for a list, sorted newest first."""
    lst = _get_debug_list_or_404(request, list_id)
    actions = lst.actions.select_related("user", "list_fighter").order_by("-created")

    return render(
        request,
        "core/debug/list_actions.html",
        {"list": lst, "actions": actions},
    )
