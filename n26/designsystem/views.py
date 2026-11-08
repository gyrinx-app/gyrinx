"""Staff-only component gallery pages using synthetic data."""

import json
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from n26.core import icons
from n26.core.brand_icons import BRAND_ICONS

from . import catalog, introspect, printlab, sampledata, tokens
from .forms import (
    UNSAFE_HTML,
    RichTextForm,
    bound_signup_form,
    create_gang_context,
)

ICON_PAGE_SIZE = 120


def _base_context():
    return {
        "groups": catalog.GROUPS,
        "component_count": len(catalog.COMPONENTS),
        "kit_version": introspect.kit_version(),
    }


@staff_member_required
def index(request):
    return render(
        request,
        "designsystem/index.html",
        _base_context()
        | {
            **sampledata.context(),
            "showcase_body": (
                "<p>Working the eastern sumps out of a stripped rail yard. Two "
                "fighters are in recovery after the <em>Dust Falls</em> raid; the "
                "rest are fit.</p>"
            ),
            "stats": [
                (len(catalog.COMPONENTS), "Components"),
                (sum(len(c.parts) for c in catalog.COMPONENTS), "Subcomponents"),
                (sum(len(c.demos) for c in catalog.COMPONENTS), "Live examples"),
                (len(catalog.GROUPS), "Groups"),
            ],
        },
    )


@staff_member_required
def component(request, slug):
    found = catalog.get(slug)
    if found is None:
        raise Http404(f"No component {slug!r}")

    ordered = catalog.COMPONENTS
    position = ordered.index(found)

    # Load TinyMCE only when a demo uses rich text, determined from the demo source.
    rich_text_form = RichTextForm()
    needs_rich_text = any("c-n26.rich-text" in demo.source for demo in found.demos)
    icon_context = {}
    if found.slug == "icon":
        icon_query = request.GET.get("q", "").strip()
        icon_names = icons.names()
        matching_icons = [
            name for name in icon_names if icon_query.casefold() in name.casefold()
        ]
        icon_paginator = Paginator(matching_icons, ICON_PAGE_SIZE)
        icon_page = icon_paginator.get_page(request.GET.get("page"))
        icon_context = {
            "icon_page": icon_page,
            "icon_page_numbers": icon_paginator.get_elided_page_range(
                icon_page.number, on_each_side=2, on_ends=1
            ),
            "icon_ellipsis": icon_paginator.ELLIPSIS,
            "icon_query": icon_query,
            "icon_result_count": len(matching_icons),
            "icon_total": len(icon_names),
            "brand_icon_names": BRAND_ICONS,
        }
    return render(
        request,
        "designsystem/component.html",
        _base_context()
        | {
            "component": found,
            "previous": ordered[position - 1] if position else None,
            "next": ordered[position + 1] if position + 1 < len(ordered) else None,
            # Use real Django Page and bound form objects to exercise component
            # integration.
            "page_obj": Paginator(range(96), 10).page(4),
            "signup_form": bound_signup_form(),
            **create_gang_context(),
            # Pass the form as well as its media so templates can render widgets and
            # load TinyMCE.
            "rich_text_form": rich_text_form,
            "unsafe_html": UNSAFE_HTML,
            "model_card": sampledata.model_card(),
            "model_card_editable": sampledata.model_card_editable(),
            "model_card_digital": sampledata.model_card_digital(),
            "model_card_unwritten": sampledata.model_card_unwritten(),
            "model_card_founding": sampledata.model_card_founding(),
            "model_card_actions_waiting": sampledata.model_card_actions_waiting(),
            "model_card_written": sampledata.model_card_written(),
            "model_card_in_recovery": sampledata.model_card_in_recovery(),
            "model_card_dead": sampledata.model_card_dead(),
            "model_card_pet": sampledata.model_card_pet(),
            "model_card_in_the_stash": sampledata.model_card_in_the_stash(),
            "model_card_header_short": sampledata.model_card_header_short(),
            "model_card_header_long_name": sampledata.model_card_header_long_name(),
            "model_card_header_long_owner": sampledata.model_card_header_long_owner(),
            "model_card_header_long_both": sampledata.model_card_header_long_both(),
            "model_card_header_badged": sampledata.model_card_header_badged(),
            "needs_rich_text": needs_rich_text,
            **icon_context,
            **sampledata.context(),
        },
    )


@staff_member_required
def theming(request):
    return render(
        request,
        "designsystem/theming.html",
        _base_context()
        | {
            "buckets": tokens.BUCKETS,
            "presets": tokens.PRESETS,
            "presets_json": json.dumps(tokens.PRESETS),
        },
    )


@staff_member_required
def react_demo(request):
    """A database-free comparison using the real list and Cotton primitives."""
    rows = [
        {
            "pk": "sample-lasgun",
            "label": "Lasgun",
            "qualifier": "House",
            "notes": ["15cr"],
            "help": "Basic weapon",
            "staged": False,
        },
        {
            "pk": "sample-autopistol",
            "label": "Autopistol",
            "qualifier": "",
            "notes": ["10cr"],
            "help": "Pistol",
            "staged": False,
        },
        {
            "pk": "sample-lasgun-staged",
            "label": "Lasgun",
            "qualifier": "Trading post",
            "notes": ["15cr"],
            "help": "Needs review",
            "staged": True,
        },
    ]
    for row in rows:
        row["url"] = reverse("authoring-leaf", args=["weapon"])
        row["search"] = " ".join(
            [
                row["label"],
                row["qualifier"],
                row["help"],
                *row["notes"],
                "staged" if row["staged"] else "",
            ]
        ).lower()
    directory = Path(__file__).resolve().parent
    return render(
        request,
        "designsystem/react.html",
        _base_context()
        | {
            "demo": {
                "rows": rows,
                "pluralLabel": "sample weapons",
                "bulkActionUrl": None,
            },
            "entry_source": (
                directory.parent / "frontend/islands/authoring-list/entry.tsx"
            ).read_text(),
            "template_source": (
                directory / "templates/designsystem/react_example.html"
            ).read_text(),
        },
    )


@staff_member_required
def react_model_preview(request):
    """Compare the two preview renderers using the same database-free cards."""
    from dataclasses import replace

    from n26.core.model_card_display import model_card_props
    from n26.core.model_preview import model_preview_props

    cards = sampledata.model_preview_cards()
    stored_examples = []
    for stored in sampledata.model_card_equip_examples():
        stored.counters = [
            replace(line, adjust_href="", assignment_id=f"gallery-counter-{index}")
            for index, line in enumerate(stored.counters)
        ]
        stored.equipment = [
            replace(line, id=f"gallery-gear-{index}")
            for index, line in enumerate(stored.equipment)
        ]
        stored_examples.append(
            {
                "card": stored,
                "props": {
                    "card": model_card_props(
                        stored, rename_href="#rename", status_href="#status"
                    )
                },
            }
        )
    return render(
        request,
        "designsystem/react_model_preview.html",
        _base_context()
        | {
            "examples": [
                {"card": card, "props": model_preview_props(card)} for card in cards
            ],
            "stored_examples": stored_examples,
        },
    )


@staff_member_required
def print_lab(request):
    """Show print controls, computed geometry and a sheet preview."""
    options = printlab.Options.from_request(request)
    return render(
        request,
        "designsystem/print_lab.html",
        _base_context()
        | {
            "options": options,
            "pages": printlab.PAGES,
            "orientations": printlab.ORIENTATIONS,
            "specimens": printlab.SPECIMENS,
            # Use the same URL for the iframe preview and standalone print target.
            "sheet_url": f"{reverse('designsystem:print_sheet')}?{options.query}",
        },
    )


@staff_member_required
@xframe_options_sameorigin
def print_sheet(request):
    """Render the standalone print target. Allow same-origin framing for the lab preview
    without including gallery navigation.
    """
    return render(
        request,
        "designsystem/print_sheet.html",
        printlab.sheet_context(printlab.Options.from_request(request)),
    )


@staff_member_required
def sample_fragment(request):
    """Serve the bare sample card fragment fetched by the deferred component demo."""
    return render(
        request,
        "n26/hire_card.html",
        {"card": sampledata.model_card()},
    )


@staff_member_required
def view_preview(request, slug):
    """Render a component demo at full viewport width without gallery navigation or source
    panels.
    """
    found = catalog.get(slug)
    if found is None or not found.demos:
        raise Http404(f"No view {slug!r}")
    return render(
        request,
        "designsystem/view_preview.html",
        {
            "component": found,
            "demo_template": found.demos[0].template_name,
            "model_card": sampledata.model_card(),
            "model_card_editable": sampledata.model_card_editable(),
            "model_card_digital": sampledata.model_card_digital(),
            "model_card_unwritten": sampledata.model_card_unwritten(),
            "model_card_founding": sampledata.model_card_founding(),
            "model_card_actions_waiting": sampledata.model_card_actions_waiting(),
            "model_card_written": sampledata.model_card_written(),
            "model_card_in_recovery": sampledata.model_card_in_recovery(),
            "model_card_dead": sampledata.model_card_dead(),
            "model_card_pet": sampledata.model_card_pet(),
            "model_card_in_the_stash": sampledata.model_card_in_the_stash(),
            "model_card_header_short": sampledata.model_card_header_short(),
            "model_card_header_long_name": sampledata.model_card_header_long_name(),
            "model_card_header_long_owner": sampledata.model_card_header_long_owner(),
            "model_card_header_long_both": sampledata.model_card_header_long_both(),
            "model_card_header_badged": sampledata.model_card_header_badged(),
            # Load TinyMCE when this demo's source includes a rich-text component.
            "rich_text_form": RichTextForm(),
            "needs_rich_text": "c-n26.rich-text" in found.demos[0].source,
            **create_gang_context(),
            **sampledata.context(),
        },
    )


#: Synthetic banner for shell previews. Its ID must be a UUID because the click-tracking
#: URL validates that format; no corresponding database record is created.
_SHELL_BANNER = {
    "id": "3f47d1a0-0000-4000-8000-000000000001",
    "colour": "info",
    "text": "The site banner sits above the nav, where it cannot be missed.",
    "cta_text": "Read the notes",
    "cta_url": "#",
}


@staff_member_required
def shell_home(request):
    """Preview the dashboard together with the banner, navigation, messages and footer."""
    messages.info(request, "Messages land above the content, one alert each.")
    return render(
        request,
        "designsystem/shell/home.html",
        {"banner": _SHELL_BANNER, **sampledata.dashboard_context()},
    )


@staff_member_required
def shell_new_gang(request):
    """Preview the unbound create form inside the application shell without writing data."""
    return render(
        request,
        "designsystem/shell/new_gang.html",
        {
            "banner": _SHELL_BANNER,
            "gang_owner": sampledata.OWNER,
            **create_gang_context(),
        },
    )


@staff_member_required
def shell_hire(request):
    """Preview the hire workflow, including URL-selected dialogs and form-local messages,
    inside the application shell.
    """
    here = reverse("designsystem:shell_hire")
    if request.method == "POST":
        return redirect(f"{here}?hire={request.POST.get('hire', '')}")
    messages.success(request, "Hired Vex — Ganger, 80¢.")
    return render(
        request,
        "designsystem/shell/hire.html",
        {
            "banner": _SHELL_BANNER,
            **sampledata.nav_context(),
            "gang_owner": sampledata.OWNER,
            "hire_entry": sampledata.hire_entry(request.GET.get("hire")),
            **create_gang_context(),
            **sampledata.hire_context(),
        },
    )


@staff_member_required
def shell_next(request):
    """Preview compulsory, completed and optional follow-up choices at the same viewport
    width.
    """
    here = reverse("designsystem:shell_next")
    if request.method == "POST":
        return redirect(here)
    messages.success(request, "Founded The Forgotten.")
    return render(
        request,
        "designsystem/shell/next.html",
        {
            "banner": _SHELL_BANNER,
            **sampledata.nav_context(),
            "screen": sampledata.arrival_screen(),
            "here": here,
            "gang_name": "The Forgotten",
        },
    )


@staff_member_required
def shell_gang(request):
    """Preview the gang sheet inside the application shell without adding a sample message."""
    return render(
        request,
        "designsystem/shell/gang.html",
        {
            "banner": _SHELL_BANNER,
            **sampledata.nav_context(),
            **sampledata.gang_sheet_context(),
            **sampledata.dashboard_context(),
        },
    )


@staff_member_required
def shell_campaign(request):
    """Preview the campaign sheet inside the same shell as the gang sheet."""
    return render(
        request,
        "designsystem/shell/campaign.html",
        {
            "banner": _SHELL_BANNER,
            **sampledata.nav_context(),
            **sampledata.campaign_sheet_context(),
            **sampledata.dashboard_context(),
        },
    )


@staff_member_required
def shell_print(request):
    """Preview the real print composition inside the application shell using the lab's URL
    options.
    """
    return render(
        request,
        "designsystem/shell/print.html",
        {
            "banner": _SHELL_BANNER,
            **sampledata.nav_context(),
            **printlab.sheet_context(printlab.Options.from_request(request)),
            **sampledata.gang_sheet_context(),
        },
    )


@staff_member_required
def shell_shop(request):
    """Preview the equipment catalogue with its sticky filter bar beneath the sticky
    application navigation.
    """
    return render(
        request,
        "designsystem/shell/shop.html",
        {
            "banner": _SHELL_BANNER,
            **sampledata.nav_context(),
            **sampledata.trading_post_context(),
        },
    )


@staff_member_required
def token_reference(request):
    return render(
        request,
        "designsystem/tokens.html",
        _base_context()
        | {
            "buckets": tokens.BUCKETS,
            "weights": tokens.WEIGHTS,
            "sizes": tokens.SIZES,
        },
    )
