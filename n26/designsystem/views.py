import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from n26.core import icons

from . import catalog, introspect, printlab, sampledata, tokens
from .forms import (
    UNSAFE_HTML,
    RichTextForm,
    bound_signup_form,
    create_gang_context,
)


def _base_context():
    return {
        "groups": catalog.GROUPS,
        "component_count": len(catalog.COMPONENTS),
        "kit_version": introspect.kit_version(),
        # Every component's searchable text, so the sidebar filter can tell
        # "no results" from "this group has no results".
        "all_search_terms": json.dumps([c.search_term for c in catalog.COMPONENTS]),
    }


def index(request):
    return render(
        request,
        "designsystem/index.html",
        _base_context()
        | {
            # The showcase needs the sample data the component demos use, plus a
            # little rendered rich text.
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


def component(request, slug):
    found = catalog.get(slug)
    if found is None:
        raise Http404(f"No component {slug!r}")

    ordered = catalog.COMPONENTS
    position = ordered.index(found)

    # TinyMCE is heavy, so its media only goes on pages that actually use it.
    # Asking the demos rather than keeping a list means a rich-text example
    # dropped into some other component's page brings the editor with it.
    rich_text_form = RichTextForm()
    needs_rich_text = any("c-n26.rich-text" in demo.source for demo in found.demos)
    return render(
        request,
        "designsystem/component.html",
        _base_context()
        | {
            "component": found,
            "previous": ordered[position - 1] if position else None,
            "next": ordered[position + 1] if position + 1 < len(ordered) else None,
            # Demos that document Django integration need the real objects: the
            # pagination component's auto mode takes a Page, and the error and field
            # components read errors off a bound form.
            "page_obj": Paginator(range(96), 10).page(4),
            "signup_form": bound_signup_form(),
            **create_gang_context(),
            # The editor demos need a form, and — separately — its media, which is
            # what actually loads TinyMCE. See needs_rich_text below.
            "rich_text_form": rich_text_form,
            "unsafe_html": UNSAFE_HTML,
            "model_card": sampledata.model_card(),
            "needs_rich_text": needs_rich_text,
            # The icon gallery renders the registry rather than a written-out
            # list, so adding an icon puts it on the page and no demo goes stale.
            "icon_names": icons.names(),
            **sampledata.context(),
        },
    )


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


def print_lab(request):
    """Controls, a readout of the geometry, and a live preview of the sheet."""
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
            # The preview iframe and the "open" links are the same URL, so what
            # you are looking at is exactly what you would print.
            "sheet_url": f"{reverse('designsystem:print_sheet')}?{options.query}",
        },
    )


@xframe_options_sameorigin
def print_sheet(request):
    """The sheet on its own — the actual print target.

    Framing is allowed from the same origin so the lab can preview it live; the
    project default is DENY. It is a plain page with no gallery chrome, because
    this URL is also what a phone opens and what headless Chrome renders to PDF,
    and anything the harness added would be in the artefact under test.
    """
    return render(
        request,
        "designsystem/print_sheet.html",
        printlab.sheet_context(printlab.Options.from_request(request)),
    )


def view_preview(request, slug):
    """One view, at real width, with none of the gallery around it.

    The component page cannot answer "does this fit a phone": it has a sidebar,
    a heading set in a long monospace tag name and a code block, and at 390px
    those decide the width before the view gets a say. Same stylesheet, same
    demo, no chrome — so what renders here is what a phone would get.
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
            # The same test the component page makes: a view whose demo
            # draws an editor brings TinyMCE with it, and only then.
            "rich_text_form": RichTextForm(),
            "needs_rich_text": "c-n26.rich-text" in found.demos[0].source,
            **create_gang_context(),
            **sampledata.context(),
        },
    )


#: The banner every shell page carries, so the region above the nav is drawn
#: rather than assumed. Nothing here is stored: a real site banner is a model.
_SHELL_BANNER = {
    "id": "preview",
    "colour": "info",
    "text": "The site banner sits above the nav, where it cannot be missed.",
    "cta_text": "Read the notes",
    "cta_url": "#",
}


def shell_home(request):
    """The dashboard, in the shell it will actually live in.

    Two jobs at once. A base template nothing inherits from is markup nobody has
    compiled, so the shell needs something extending it; and a view only ever seen
    on its own is a view nobody has seen next to a nav and a footer. Rendering a
    real page here puts the banner, the nav, a message, the page and the footer in
    one screen, which is the only place their spacing can be judged.
    """
    messages.info(request, "Messages land above the content, one alert each.")
    return render(
        request,
        "designsystem/shell/home.html",
        {"banner": _SHELL_BANNER, **sampledata.dashboard_context()},
    )


def shell_new_gang(request):
    """The create form, in the shell, and the only page here that posts.

    Unbound every time: this writes nothing, so there is no submit to handle and
    nothing to redisplay. The error state lives in the component's second demo,
    where a bound form can be shown without pretending the gallery has a
    database behind it.
    """
    return render(
        request,
        "designsystem/shell/new_gang.html",
        {
            "banner": _SHELL_BANNER,
            "gang_owner": sampledata.OWNER,
            **create_gang_context(),
        },
    )


def shell_hire(request):
    """The hire screen, in the shell, and the long form to the create form's short one.

    Unbound every time, like the other form page: the gallery writes nothing, so
    there is no submit to handle. What it is here to show is the pattern under a
    scroll — a sticky bar whose heading outlives the h1, and a form whose submit
    is three hundred rows down rather than at the bottom.

    A press is answered the way the real screen answers one — with this page's
    URL naming the profile, and the dialog drawn over it — because the whole
    point of the loop is that it happens without leaving the list, and a shell
    that skipped it would be showing half of the pattern.

    The message is pushed for the same reason the home page pushes one, and
    proves the opposite thing: this screen takes its messages out of the
    layout's slot and draws them inside the form, above the list.
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


def shell_gang(request):
    """One gang's sheet, in the shell.

    No message pushed in. The home page proves that region draws; repeating it on
    every page would say a gang sheet always opens with an alert, which is not
    something the shell should be teaching by accident.
    """
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


def shell_print(request):
    """Printing a gang, from inside the application.

    The lab drives the bare sheet and the proof script renders it; neither can
    answer what happens when a real page in the real shell meets a printer. The
    sheet is laid out in millimetres and the shell in a window, and the question
    is whether the second leaves a mark on the first.

    Same specimen and the same partial as the lab, so there is no fourth
    composition to keep in step — and the same Options, so the query parameters
    that drive the lab drive this too.
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


def shell_shop(request):
    """Buying equipment, in the shell.

    The trading post is the longest list in the library and the one most likely to
    fight its surroundings — a sticky filter bar under a sticky nav is two things
    competing for the top of the window, and that only shows up here.
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
