"""Full-document layout components: Foundation, Base, and SimplePage.

Faithful component ports of ``core/layouts/foundation.html``,
``core/layouts/base.html`` and ``core/layouts/page.html``. Page components
return a :class:`Page` describing their content; :func:`render_page` wraps it in
the requested layout using the render context (request, user, messages, banner,
notifications, impersonation, debug).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from django.templatetags.static import static
from django.urls import reverse

from . import bridge
from .design import Messages
from .elements import Node, fragment, raw
from .tags import (
    a,
    body,
    button,
    div,
    footer,
    form,
    h2,
    h3,
    head,
    html,
    i,
    img,
    input_,
    li,
    link,
    meta,
    nav,
    noscript,
    p,
    script,
    span,
    strong,
    title,
    ul,
)

__all__ = ["Page", "Foundation", "Base", "SimplePage", "render_page"]

DOCTYPE = raw("<!DOCTYPE html>\n")

# Favicon link set from foundation.html, in original order.
_APPLE_SIZES = ["57", "114", "72", "144", "60", "120", "76", "152"]
_PNG_SIZES = ["196", "96", "32", "16", "128"]

_GTM_HEAD = raw(
    "(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':"
    "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],"
    "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src="
    "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);"
    "})(window,document,'script','dataLayer','GTM-PFFPCMPF');"
)


@dataclass
class Page:
    """The result a page component returns.

    * ``content`` — the node placed in the layout's content area.
    * ``title`` — the ``<title>`` text (before `` | Gyrinx``).
    * ``layout`` — ``"base"`` (default) / ``"page"`` / ``"foundation"``.
    * ``description`` — sub-title text, for the ``"page"`` layout.
    * ``prebody`` / ``extra_script`` / ``stylesheet`` — optional layout slots.
    """

    content: Node
    title: str = ""
    layout: str = "base"
    description: Node = None
    prebody: Node = None
    extra_script: Node = None
    stylesheet: Node = None


def _favicons() -> Node:
    links: list[Node] = [
        link(rel="shortcut icon", href="/favicon.ico", type="image/x-icon"),
        link(rel="icon", href="/favicon.ico", type="image/x-icon"),
    ]
    for size in _APPLE_SIZES:
        links.append(
            link(
                rel="apple-touch-icon-precomposed",
                sizes=f"{size}x{size}",
                href=static(
                    f"core/img/brand/favicon/apple-touch-icon-{size}x{size}.png"
                ),
            )
        )
    for size in _PNG_SIZES:
        links.append(
            link(
                rel="icon",
                type="image/png",
                href=static(f"core/img/brand/favicon/favicon-{size}x{size}.png"),
                sizes=f"{size}x{size}",
            )
        )
    return fragment[tuple(links)]


def Foundation(
    *,
    head_title: str,
    content: Node,
    request: Any = None,
    debug: bool = False,
    stylesheet: Node | None = None,
    extra_script: Node | None = None,
) -> Node:
    """Full HTML document shell (port of ``foundation.html``)."""
    theme = "auto"
    if request is not None:
        theme = request.COOKIES.get("theme_active") or "auto"

    default_stylesheet = link(rel="stylesheet", href=static("core/css/screen.css"))

    document = html(lang="en", data_bs_theme=theme)[
        head[
            meta(charset="utf-8"),
            meta(name="viewport", content="width=device-width, initial-scale=1"),
            meta(
                name="description",
                content="Gyrinx is a free set of tools for the Necromunda community",
            ),
            meta(name="author", content="Gyrinx"),
            meta(name="keywords", content="Necromunda, Gyrinx"),
            meta(name="application-name", content="Gyrinx"),
            _favicons(),
            title[raw((head_title or "").strip()), " | Gyrinx"],
            link(rel="dns-prefetch", href="https://use.typekit.net"),
            link(rel="preconnect", href="https://use.typekit.net", crossorigin=True),
            link(rel="stylesheet", href="https://use.typekit.net/rso6ezl.css"),
            link(
                rel="stylesheet",
                href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
                integrity="sha384-XGjxtQfXaH2tnPFa9x+ruJTuLE3Aa6LhHSWRr1XeTyhezb4abCG4ccI5AkVDxqC+",
                crossorigin="anonymous",
            ),
            stylesheet if stylesheet is not None else default_stylesheet,
            script[_GTM_HEAD],
        ],
        body[
            noscript[
                raw(
                    '<iframe src="https://www.googletagmanager.com/ns.html?id=GTM-PFFPCMPF" '
                    'height="0" width="0" style="display:none;visibility:hidden"></iframe>'
                )
            ],
            content,
            script(
                src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js",
                integrity="sha384-FKyoEForCGlyvwx9Hj09JcYn3nv7wiPVlz7YYwJrWVcXK/BmnVDxM+D2scQbITxI",
                crossorigin="anonymous",
            ),
            script(type="module", src=static("core/js/index.js")),
            extra_script,
            script(
                src="https://mcp.figma.com/mcp/html-to-design/capture.js", async_=True
            )
            if debug
            else None,
        ],
    ]
    return fragment[DOCTYPE, document]


# --------------------------------------------------------------------------
# Shell fragments (banners, nav, footer)
# --------------------------------------------------------------------------


def SiteBanner(banner: Any) -> Node:
    if not banner:
        return None
    colour = banner.colour
    cta = None
    if getattr(banner, "cta_url", None) and getattr(banner, "cta_text", None):
        cta = a(
            href=reverse("core:track-banner-click", args=[banner.id]),
            target="_new",
            class_=f"btn btn-sm btn-{colour}",
        )[banner.cta_text, " ", i(class_="bi-arrow-right ms-1")]
    return div(
        class_=f"bg-{colour}-subtle border-bottom border-1 border-{colour}",
        id=f"site-banner-{banner.id}",
    )[
        div(class_="container")[
            div(
                class_=f"alert alert-{colour} hstack gap-2 border-0 mb-0 py-2 px-0 "
                "alert-dismissible fade show align-middle align-items-center",
                role="alert",
            )[
                i(class_=banner.icon) if getattr(banner, "icon", None) else None,
                div(class_="flex-grow-1 hstack gap-2 flex-wrap")[banner.text, cta],
                button(
                    type="button",
                    class_=f"btn btn-sm btn-outline-{colour} icon-link",
                    data_bs_dismiss="alert",
                    aria_label="Close",
                    data_gy_banner_dismiss=str(banner.id),
                )[i(class_="bi-x-lg")],
            ]
        ]
    ]


def ImpersonationBanner(
    *, is_impersonating: bool, request: Any, impersonator: Any
) -> Node:
    if not is_impersonating:
        return None
    return div(class_="bg-danger text-white", id="impersonation-banner")[
        div(class_="container")[
            div(class_="hstack gap-2 flex-wrap py-2 align-items-center")[
                i(class_="bi-person-bounding-box"),
                div(class_="flex-grow-1")[
                    "Impersonating ",
                    strong[request.user.username],
                    " — signed in as ",
                    impersonator.username if impersonator else "",
                    ". Everything you do is recorded as this user.",
                ],
                form(
                    method="post", action=reverse("core:impersonate-stop"), class_="m-0"
                )[
                    bridge_csrf(request),
                    input_(type="hidden", name="next", value=request.get_full_path()),
                    button(type="submit", class_="btn btn-sm btn-light")[
                        i(class_="bi-box-arrow-left"), " Stop impersonating"
                    ],
                ],
            ]
        ]
    ]


def bridge_csrf(request: Any) -> Node:
    from .design.forms import CsrfInput

    return CsrfInput(request)


def NotificationNavButton(
    *, request: Any, unread_count: int, extra_classes: str = ""
) -> Node:
    has_unread = bool(unread_count)
    badge_text = "99+" if (unread_count or 0) > 99 else str(unread_count)
    return a(
        class_=[
            "btn btn-dark position-relative",
            extra_classes,
            bridge.active_view(request, "core:notifications"),
        ],
        href=reverse("core:notifications"),
        data_bs_toggle="tooltip",
        data_bs_title="You have unread notifications"
        if has_unread
        else "No unread notifications",
        aria_label=f"Inbox ({unread_count} unread)" if has_unread else "Inbox",
    )(bridge.active_aria(request, "core:notifications"))[
        i(class_="bi-inbox"),
        span(
            class_="position-absolute top-0 start-100 translate-middle badge rounded-pill text-bg-danger"
        )[badge_text, span(class_="visually-hidden")[" unread notifications"]]
        if has_unread
        else None,
    ]


def _theme_dropdown() -> Node:
    def item(value: str, icon: str, label: str, active: bool) -> Node:
        return li[
            button(
                type="button",
                class_=["dropdown-item d-flex align-items-center", {"active": active}],
                data_bs_theme_value=value,
                aria_pressed="true" if active else "false",
            )[
                i(class_=f"bi-{icon} theme-icon opacity-50 me-2"),
                label,
                i(class_="bi-check2 ms-auto d-none"),
            ]
        ]

    return li(class_="nav-item dropdown")[
        button(
            class_="btn btn-link nav-link py-2 px-0 px-lg-2 dropdown-toggle d-flex align-items-center",
            id="bd-theme",
            type="button",
            aria_expanded="false",
            data_bs_toggle="dropdown",
            aria_label="Toggle theme (auto)",
        )[
            i(class_="bi-circle-half theme-icon-active"),
            span(class_="d-lg-none ms-2", id="bd-theme-text")["Toggle theme"],
        ],
        ul(class_="dropdown-menu dropdown-menu-end", aria_labelledby="bd-theme-text")[
            item("light", "sun-fill", "Light", True),
            item("dark", "moon-stars-fill", "Dark", False),
            item("auto", "circle-half", "Auto", False),
        ],
    ]


def _navbar(context: Mapping[str, Any]) -> Node:
    request = context.get("request")
    user = context.get("user")
    authenticated = bool(user and user.is_authenticated)
    unread = context.get("unread_notification_count", 0)
    help_page = bridge.get_page_by_url("/help/")

    nav_links = ul(class_="navbar-nav me-auto mb-2 mb-lg-0")[
        _nav_item(
            "Home",
            reverse("core:index"),
            bridge.active_view(request, "core:index"),
            request,
            "core:index",
        ),
        _nav_item(
            "Lists & Gangs",
            reverse("core:lists"),
            bridge.active_path(request, "/lists/", "/list/"),
        ),
        _nav_item(
            "Campaigns",
            reverse("core:campaigns"),
            bridge.active_path(request, "/campaigns/", "/campaign/", "/battle/"),
        ),
        _nav_item(
            "Customisation",
            reverse("core:packs"),
            bridge.active_path(request, "/packs/", "/pack/"),
        ),
        li(class_="nav-item")[
            a(
                class_=["nav-link", bridge.active_flatpage(request, help_page.url)],
                href=help_page.url,
            )(bridge.active_flatpage_aria(request, help_page.url))["Help"]
        ]
        if help_page
        else None,
        li(class_="nav-item")[
            a(class_="nav-link", href=reverse("admin:maintenance_index"))["Maintenance"]
        ]
        if authenticated and user.is_superuser
        else None,
        _theme_dropdown(),
    ]

    if authenticated:
        auth_area = div(class_="d-flex flex-column flex-sm-row gap-2")[
            NotificationNavButton(
                request=request,
                unread_count=unread,
                extra_classes="d-none d-lg-inline-flex align-items-center",
            ),
            a(href=reverse("core:account_home"), class_="btn btn-outline-light")[
                i(class_="bi-gear"), " ", user.username, bridge.user_badge(user)
            ],
        ]
    else:
        auth_area = _auth_buttons(request)

    return nav(class_="navbar navbar-expand-lg bg-dark", data_bs_theme="dark")[
        div(class_="container")[
            a(
                class_="navbar-brand hstack gap-1 align-items-center",
                href=reverse("core:index"),
            )[
                img(
                    src=static("core/img/brand/logo-gold-transparent-bg.svg"),
                    alt="Logo",
                    width="24",
                    height="24",
                    class_="d-inline-block align-text-top",
                ),
                span(class_="fs-5 ms-1 fw-normal")["Gyrinx"],
            ],
            div(class_="hstack gap-2 gap-sm-1 me-sm-1")[
                fragment[
                    a(
                        class_=[
                            "btn btn-dark",
                            bridge.active_view(request, "core:dice"),
                        ],
                        href=reverse("core:dice") + "?m=d6&d=1",
                    )(bridge.active_aria(request, "core:dice"))[i(class_="bi-dice-6")],
                    NotificationNavButton(
                        request=request, unread_count=unread, extra_classes="d-lg-none"
                    ),
                ]
                if authenticated
                else None,
                button(
                    class_="navbar-toggler",
                    type="button",
                    data_bs_toggle="collapse",
                    data_bs_target="#navbarSupportedContent",
                    aria_controls="navbarSupportedContent",
                    aria_expanded="false",
                    aria_label="Toggle navigation",
                )[span(class_="navbar-toggler-icon")],
            ],
            div(class_="collapse navbar-collapse", id="navbarSupportedContent")[
                nav_links, auth_area
            ],
        ]
    ]


def _nav_item(
    label: str,
    href: str,
    active: str,
    request: Any = None,
    view_name: str | None = None,
) -> Node:
    link_el = a(class_=["nav-link", active], href=href)
    if request is not None and view_name is not None:
        link_el = link_el(bridge.active_aria(request, view_name))
    return li(class_="nav-item")[link_el[label]]


def _auth_buttons(request: Any) -> Node:
    login_url = reverse("account_login")
    try:
        signup_url = reverse("account_signup")
    except Exception:
        signup_url = None
    on_auth_page = request is not None and request.path in {login_url, signup_url}
    if request is not None and not on_auth_page:
        from urllib.parse import quote

        next_param = "?next=" + quote(request.get_full_path(), safe="")
    else:
        next_param = ""
    return div(class_="d-flex flex-column flex-sm-row gap-2")[
        a(href=login_url + next_param, class_="btn btn-outline-light")["Sign In"],
        a(href=signup_url + next_param, class_="btn btn-success")["Sign Up"]
        if signup_url
        else None,
    ]


def _footer(context: Mapping[str, Any]) -> Node:
    user = context.get("user")
    request = context.get("request")
    pages = bridge.root_pages(user, request) if user is not None else []
    patreon = (
        "https://patreon.com/Gyrinx?utm_medium=unknown&utm_source=join_link"
        "&utm_campaign=creatorshare_creator&utm_content=copyLink"
    )
    brand_col = div(class_="col-md-4 mb-3")[
        a(
            class_="d-inline-flex align-items-center mb-3 text-body-emphasis text-decoration-none",
            href=reverse("core:index"),
            aria_label="Gyrinx",
        )[
            img(
                src=static("core/img/brand/logo-gold-transparent-bg.svg"),
                alt="Logo",
                width="24",
                height="24",
                class_="d-inline-block align-text-top me-1",
            ),
            h2(class_="fs-5 mb-0")["Gyrinx"],
        ],
        ul(class_="list-unstyled fs-7")[
            li(class_="mb-2")["Designed and built in the UK."],
            li(class_="mb-2")[
                a(
                    class_="linked-secondary",
                    href=reverse("admin:index"),
                    target="_new",
                )["Admin"],
                " ",
                i(class_="bi-box-arrow-up-right"),
            ]
            if user is not None and getattr(user, "is_staff", False)
            else None,
            li(class_="mb-2")[
                a(href=patreon, target="_new", class_="linked-secondary icon-link")[
                    "Support Gyrinx"
                ]
            ],
            li(class_="mt-3 mb-2")[
                div(class_="hstack gap-2")[
                    a(
                        href="https://github.com/gyrinx-app",
                        bs_tooltip=True,
                        data_bs_toggle="tooltip",
                        title="Contribute to Gyrinx on GitHub",
                        target="_new",
                        class_="linked-secondary",
                    )[i(class_="bi-github"), span(class_="visually-hidden")["GitHub"]],
                    a(
                        href="https://discord.gg/NjMVRSEMAz",
                        bs_tooltip=True,
                        data_bs_toggle="tooltip",
                        title="Join the Gyrinx Discord server",
                        target="_new",
                        class_="linked-secondary ms-2",
                    )[
                        i(class_="bi-discord"),
                        span(class_="visually-hidden")["Discord"],
                    ],
                ]
            ],
        ],
    ]
    help_col = div(class_="col-md-4 mb-3 pt-1")[
        h3(class_="fs-6 mb-3")["Help & Documentation"],
        ul(class_="list-unstyled fs-7")[
            tuple(
                li(class_="mb-2")[
                    a(href=page.url, class_="linked-secondary")[page.title]
                ]
                for page in pages
            )
        ],
    ]
    patreon_col = div(class_="col-md-4 mb-3 pt-1")[
        h3(class_="fs-6 mb-3")[
            a(href=patreon, target="_new", class_="linked-secondary icon-link")[
                "Support Gyrinx on Patreon"
            ]
        ],
        p[
            a(href=patreon, target="_new", class_="img-link-transform")[
                img(
                    src=static("core/img/content/patreon.png"),
                    class_="img-fluid rounded-2 border",
                    alt="Support Gyrinx on Patreon",
                )
            ]
        ],
    ]
    return footer(class_="bd-footer py-4 py-md-5 mt-5 bg-body-tertiary")[
        div(class_="container py-4 py-md-5 text-body-secondary")[
            div(class_="row")[brand_col, help_col, patreon_col]
        ]
    ]


def Base(page: "Page", context: Mapping[str, Any]) -> Node:
    """Port of ``base.html``: nav, banners, messages, content, footer."""
    request = context.get("request")
    content_area = div(id="content", class_="container my-3 my-md-5")[
        Messages(context.get("messages")),
        page.content,
    ]
    base_body = fragment[
        a(class_="visually-hidden-focusable", href="#content")["Skip to main content"],
        SiteBanner(context.get("banner")),
        _navbar(context),
        ImpersonationBanner(
            is_impersonating=context.get("is_impersonating", False),
            request=request,
            impersonator=context.get("impersonator"),
        ),
        page.prebody,
        content_area,
        _footer(context),
    ]
    return Foundation(
        head_title=page.title,
        content=base_body,
        request=request,
        debug=context.get("debug", False),
        stylesheet=page.stylesheet,
        extra_script=page.extra_script,
    )


def SimplePage(page: "Page", context: Mapping[str, Any]) -> Node:
    """Port of ``page.html``: a base layout with a title/description header."""
    inner = div(class_="col-lg-12 px-0 vstack gap-4")[
        div[
            h1_h3(page.title),
            p(class_="fs-5 col-12 col-md-6 mb-0")[page.description],
        ],
        div(class_="col-lg-12 px-0 vstack gap-4")[page.content],
    ]
    wrapped = Page(
        content=inner,
        title=page.title,
        prebody=page.prebody,
        extra_script=page.extra_script,
        stylesheet=page.stylesheet,
    )
    return Base(wrapped, context)


def h1_h3(text: Node) -> Node:
    from .tags import h1

    return h1(class_="h3 mb-0")[text]


def render_page(page: "Page", context: Mapping[str, Any]):
    """Render a :class:`Page` to a full HTML ``SafeString`` using its layout."""
    from .elements import render

    if page.layout == "foundation":
        node = Foundation(
            head_title=page.title,
            content=page.content,
            request=context.get("request"),
            debug=context.get("debug", False),
            stylesheet=page.stylesheet,
            extra_script=page.extra_script,
        )
    elif page.layout == "page":
        node = SimplePage(page, context)
    else:
        node = Base(page, context)
    return render(node)
