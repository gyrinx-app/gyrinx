"""Prepare default flat pages for the n26 presentation layer."""

import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from django.contrib.flatpages.models import FlatPage
from django.utils.safestring import SafeString, mark_safe

from gyrinx.pages.access import accessible_flatpages
from gyrinx.site.templatetags.platform_tags import safe_rich_text


@dataclass(frozen=True)
class Heading:
    """One linkable heading found in a flat page's content."""

    level: int
    text: str
    slug: str
    children: tuple[Heading, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ParsedContent:
    """Sanitised article HTML and the headings found in it."""

    html: SafeString
    headings: tuple[Heading, ...]


@dataclass(frozen=True)
class PageNavigationNode:
    """One accessible page in the documentation hierarchy."""

    page: FlatPage
    children: tuple[PageNavigationNode, ...]
    is_current: bool
    is_ancestor: bool


@dataclass(frozen=True)
class FlatPagePresentation:
    """The complete, precomputed context consumed by the default template."""

    content_html: SafeString
    introduction_html: SafeString
    headings: tuple[Heading, ...]
    toc: tuple[Heading, ...]
    show_toc: bool
    is_help: bool
    navigation_tree: tuple[PageNavigationNode, ...]
    ancestors: tuple[FlatPage, ...]
    parent: FlatPage | None
    children: tuple[FlatPage, ...]


def slugify_heading(text: str) -> str:
    """Convert heading text to the stable fragment format used by flat pages."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def sanitise_flatpage_html(html: str) -> SafeString:
    """Sanitise editor HTML while retaining inert, local iframe embeds."""
    source = BeautifulSoup(html or "", "html.parser")
    for element in source.find_all(["script", "style"]):
        element.decompose()
    local_embeds: dict[str, dict[str, str]] = {}

    for iframe in source.find_all("iframe"):
        src = str(iframe.get("src", "")).strip()
        try:
            parsed = urlsplit(src)
        except ValueError:
            iframe.decompose()
            continue
        is_local = (
            src.startswith("/")
            and not src.startswith("//")
            and "\\" not in src
            and not parsed.scheme
            and not parsed.netloc
        )
        if is_local:
            token = f"flatpage-embed-{uuid.uuid4().hex}"
            while source.find(id=token):
                token = f"flatpage-embed-{uuid.uuid4().hex}"
            placeholder = source.new_tag("span", id=token)
            iframe.replace_with(placeholder)

            attributes = {
                "src": src,
                "sandbox": "",
                "loading": "lazy",
                "title": str(iframe.get("title") or "Embedded content"),
                "class": "flatpage-embed",
            }
            for dimension in ("width", "height"):
                value = str(iframe.get(dimension, ""))
                if re.fullmatch(r"[1-9]\d{0,3}", value):
                    attributes[dimension] = value
            local_embeds[token] = attributes
            continue

        if parsed.scheme in {"http", "https"} and parsed.netloc:
            link = source.new_tag("a", href=src)
            link.string = str(iframe.get("title") or "Open embedded content")
            iframe.replace_with(link)
        else:
            iframe.decompose()

    cleaned = BeautifulSoup(str(safe_rich_text(str(source))), "html.parser")
    for token, attributes in local_embeds.items():
        marker = cleaned.find(id=token)
        if marker is None:
            continue
        embed = cleaned.new_tag("iframe", attrs=attributes)
        marker.replace_with(embed)

    # safe_rich_text cleaned the document and iframe attributes above are
    # constructed from a root-relative URL allowlist.
    return mark_safe(str(cleaned))  # nosec B703 B308


def parse_content(html: str) -> ParsedContent:
    """Sanitise article HTML, then add stable ids and heading permalinks."""
    soup = BeautifulSoup(str(sanitise_flatpage_html(html)), "html.parser")
    headings: list[Heading] = []
    seen = {tag["id"] for tag in soup.find_all(id=True)}

    for element in soup.find_all(re.compile(r"^h[1-6]$")):
        text = element.get_text().strip()
        base = slugify_heading(text) or "section"
        slug = base
        suffix = 1
        while slug in seen:
            suffix += 1
            slug = f"{base}-{suffix}"
        seen.add(slug)

        element["id"] = slug
        permalink = soup.new_tag(
            "a",
            href=f"#{slug}",
            attrs={
                "class": "flatpage-heading-link",
                "aria-label": f"Link to {text or 'this section'}",
            },
        )
        permalink.string = "#"
        element.append(permalink)
        if text:
            headings.append(Heading(level=int(element.name[1]), text=text, slug=slug))

    return ParsedContent(
        html=mark_safe(str(soup)),  # nosec B703 B308 - sanitised above
        headings=tuple(headings),
    )


def nest_headings(headings: tuple[Heading, ...] | list[Heading]) -> tuple[Heading, ...]:
    """Nest headings under the nearest earlier heading at a shallower level."""
    mutable_roots: list[dict] = []
    stack: list[dict] = []
    for heading in headings:
        node = {
            "level": heading.level,
            "text": heading.text,
            "slug": heading.slug,
            "children": [],
        }
        while stack and stack[-1]["level"] >= heading.level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            mutable_roots.append(node)
        stack.append(node)

    def freeze(node: dict) -> Heading:
        return Heading(
            level=node["level"],
            text=node["text"],
            slug=node["slug"],
            children=tuple(freeze(child) for child in node["children"]),
        )

    return tuple(freeze(node) for node in mutable_roots)


def _parent_url(url: str) -> str | None:
    segments = [segment for segment in url.strip("/").split("/") if segment]
    if len(segments) <= 1:
        return None
    return f"/{'/'.join(segments[:-1])}/"


def _navigation_pages(*, site_id: int, user) -> list[FlatPage]:
    candidates = list(
        accessible_flatpages(
            site_id=site_id,
            user=user,
            include_registration_required=bool(user and user.is_authenticated),
        )
        .exclude(url="/")
        .only("pk", "url", "title", "registration_required")
        .order_by("url")
    )
    candidates_by_url = {page.url: page for page in candidates}
    included: list[FlatPage] = []
    included_urls: set[str] = set()
    for page in candidates:
        parent_url = _parent_url(page.url)
        if parent_url is None or (
            parent_url in candidates_by_url and parent_url in included_urls
        ):
            included.append(page)
            included_urls.add(page.url)
    return included


def _navigation_context(*, page: FlatPage, site_id: int, user):
    pages = _navigation_pages(site_id=site_id, user=user)
    pages_by_url = {candidate.url: candidate for candidate in pages}
    children_by_url: dict[str | None, list[FlatPage]] = {}
    for candidate in pages:
        children_by_url.setdefault(_parent_url(candidate.url), []).append(candidate)

    ancestor_urls: list[str] = []
    parent_url = _parent_url(page.url)
    while parent_url is not None:
        if parent_url in pages_by_url:
            ancestor_urls.append(parent_url)
        parent_url = _parent_url(parent_url)
    ancestor_urls.reverse()
    ancestor_set = set(ancestor_urls)

    def make_node(candidate: FlatPage) -> PageNavigationNode:
        return PageNavigationNode(
            page=candidate,
            children=tuple(
                make_node(child) for child in children_by_url.get(candidate.url, [])
            ),
            is_current=candidate.pk == page.pk,
            is_ancestor=candidate.url in ancestor_set,
        )

    roots = tuple(make_node(root) for root in children_by_url.get(None, []))
    ancestors = tuple(pages_by_url[url] for url in ancestor_urls)
    parent = pages_by_url.get(_parent_url(page.url))
    children = tuple(children_by_url.get(page.url, []))
    return roots, ancestors, parent, children


def build_flatpage_presentation(
    *, page: FlatPage, site_id: int, user
) -> FlatPagePresentation:
    """Build all data required to render one default flat page."""
    parsed = parse_content(page.content)
    toc_headings = tuple(
        heading for heading in parsed.headings if heading.level in (2, 3)
    )
    is_help = page.url == "/help/" or page.url.startswith("/help/")

    navigation_tree, ancestors, parent, children = _navigation_context(
        page=page, site_id=site_id, user=user
    )

    try:
        introduction = page.options.introduction
    except FlatPage.options.RelatedObjectDoesNotExist:
        introduction = ""

    return FlatPagePresentation(
        content_html=parsed.html,
        introduction_html=sanitise_flatpage_html(introduction),
        headings=parsed.headings,
        toc=nest_headings(toc_headings),
        show_toc=len(toc_headings) >= 2,
        is_help=is_help,
        navigation_tree=navigation_tree,
        ancestors=ancestors,
        parent=parent,
        children=children,
    )
