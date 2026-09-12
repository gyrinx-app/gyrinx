import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from django import template
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from gyrinx.pages.models import FlatPageOptions

register = template.Library()

# Note: this is largely a copy of the get_flatpages tag from Django's flatpages app


class FlatpageNode(template.Node):
    depth = 0
    # When set, only pages exactly one path segment below ``starts_with`` are
    # returned: the page's direct children, not every descendant.
    children_only = False

    def __init__(self, context_name, starts_with=None, user=None):
        self.context_name = context_name
        if starts_with:
            self.starts_with = template.Variable(starts_with)
        else:
            self.starts_with = None
        if user:
            self.user = template.Variable(user)
        else:
            self.user = None

    def render(self, context):
        if "request" in context:
            site_pk = get_current_site(context["request"]).pk
        else:
            site_pk = settings.SITE_ID

        # Build the queryset
        flatpages = FlatPage.objects.filter(sites__id=site_pk)

        # If a prefix was specified, add a filter
        starts_with = None
        if self.starts_with:
            starts_with = self.starts_with.resolve(context)
            flatpages = flatpages.filter(url__startswith=starts_with)
            if self.children_only:
                prefix = re.escape(_normalize_path(starts_with))
                flatpages = flatpages.filter(url__regex=rf"^{prefix}[^/]+/?$")

        # If the provided user is not authenticated, or no user
        # was provided, filter the list to only public flatpages.
        user = None
        if self.user:
            user = self.user.resolve(context)
            if not user.is_authenticated:
                flatpages = flatpages.filter(registration_required=False)
            else:
                # This is the addition: filter flatpages for visibility to the user
                flatpages = flatpages.filter(
                    Q(flatpagevisibility__isnull=True)
                    | Q(flatpagevisibility__groups__in=user.groups.all())
                ).distinct()
        else:
            flatpages = flatpages.filter(registration_required=False)

        if self.depth:
            # Optimized regex for depth=1 case
            if self.depth == 1:
                flatpages = flatpages.filter(url__regex=r"^/[^/]+/?$")
            else:
                flatpages = flatpages.filter(
                    url__regex=r"^/[^/]+(?:/[^/]+){0,%d}/?$" % (self.depth - 1)  # noqa: UP031 - percent-format keeps the regex readable; an f-string needs {{}} doubling
                )

        context[self.context_name] = flatpages
        return ""


@register.tag
def get_pages(parser, token):
    """
    Retrieve all flatpage objects available for the current site and
    visible to the specific user (or visible to all users if no user is
    specified). Populate the template context with them in a variable
    whose name is defined by the ``as`` clause.

    An optional ``for`` clause controls the user whose permissions are used in
    determining which flatpages are visible.

    An optional argument, ``starts_with``, limits the returned flatpages to
    those beginning with a particular base URL. This argument can be a variable
    or a string, as it resolves from the template context.

    Syntax::

        {% get_pages ['url_starts_with'] [for user] as context_name %}

    Example usage::

        {% get_pages as flatpages %}
        {% get_pages for someuser as flatpages %}
        {% get_pages '/about/' as about_pages %}
        {% get_pages prefix as about_pages %}
        {% get_pages '/about/' for someuser as about_pages %}
    """
    bits = token.split_contents()
    syntax_message = (
        "{tag_name} expects a syntax of {tag_name} "
        "['url_starts_with'] [for user] as context_name"
    ).format(tag_name=bits[0])
    # Must have at 3-6 bits in the tag
    if 3 <= len(bits) <= 6:
        # If there's an even number of bits, there's no prefix
        if len(bits) % 2 == 0:
            prefix = bits[1]
        else:
            prefix = None

        # The very last bit must be the context name
        if bits[-2] != "as":
            raise template.TemplateSyntaxError(syntax_message)
        context_name = bits[-1]

        # If there are 5 or 6 bits, there is a user defined
        if len(bits) >= 5:
            if bits[-4] != "for":
                raise template.TemplateSyntaxError(syntax_message)
            user = bits[-3]
        else:
            user = None

        return FlatpageNode(context_name, starts_with=prefix, user=user)
    else:
        raise template.TemplateSyntaxError(syntax_message)


@register.tag
def get_root_pages(parser, token):
    node = get_pages(parser, token)
    node.depth = 1
    return node


@register.tag
def get_child_pages(parser, token):
    """
    Like ``get_pages`` with a prefix, but returns only the pages directly
    below it — one path segment deeper — rather than every descendant.

    Syntax::

        {% get_child_pages parent_url [for user] as context_name %}
    """
    node = get_pages(parser, token)
    if node.starts_with is None:
        raise template.TemplateSyntaxError(
            "get_child_pages expects a syntax of get_child_pages "
            "parent_url [for user] as context_name"
        )
    node.children_only = True
    return node


@register.simple_tag
def pages_path_segment(path, segment):
    """
    Return the segment of the path at the given index.
    """
    if not path:
        return "/"
    if path.endswith("/"):
        path = path[:-1]
    if segment <= 0:
        return "/"
    return "/".join(path.split("/")[: segment + 1]) + "/"


@register.simple_tag
def pages_path_parent(path):
    """
    Return the parent of the segment of the path by removing the last segment.
    """
    if not path:
        return "/"
    if path.endswith("/"):
        path = path[:-1]
    return "/".join(path.split("/")[:-1]) + "/"


@register.simple_tag
def pages_parent(page):
    """
    Return the parent of the page.
    """
    parent_url = pages_path_parent(page.url)
    try:
        return FlatPage.objects.get(url=parent_url)
    except FlatPage.DoesNotExist:
        return None


@register.simple_tag
def page_depth(page):
    """
    Return the depth of the page in the site's hierarchy.
    """
    return max(page.url.count("/") - 2, 0)


@register.simple_tag
def get_page_by_url(url):
    """
    Return the page with the given URL.

    Results are cached for 5 minutes to avoid repeated database queries,
    especially useful for navbar links that appear on every page.
    """
    cache_key = f"flatpage_by_url_{url}"
    cached_result = cache.get(cache_key)

    if cached_result is not None:
        # Return None if we cached a miss, otherwise return the cached page
        return None if cached_result == "" else cached_result

    try:
        page = FlatPage.objects.get(url=url)
        cache.set(cache_key, page, 300)  # Cache for 5 minutes
        return page
    except FlatPage.DoesNotExist:
        cache.set(cache_key, "", 300)  # Cache the miss for 5 minutes
        return None


def slugify(text):
    """
    Convert the provided text into a slug suitable for use as an HTML id.
    """
    # Convert to lowercase
    text = text.lower()
    # Remove any characters that aren't alphanumeric, whitespace, or hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    # Replace spaces and hyphens with a single hyphen
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def _normalize_path(path):
    """Normalize a path to ensure it ends with a trailing slash."""
    if not path.endswith("/"):
        return path + "/"
    return path


def _is_flatpage_active(context, url):
    """
    Check if the current request path matches the given flatpage URL.

    Normalizes both the request path and the URL to ensure consistent comparison.
    """
    request = context.get("request")
    if not request:
        return False

    # Normalize both paths to ensure consistent comparison
    normalized_url = _normalize_path(url)
    normalized_path = _normalize_path(request.path)

    return normalized_path == normalized_url


@register.simple_tag(takes_context=True)
def active_flatpage(context, url):
    """
    Return 'active' if the current request path matches the given flatpage URL.

    Usage:
        {% active_flatpage '/help/' %}
    """
    return "active" if _is_flatpage_active(context, url) else ""


@register.simple_tag(takes_context=True)
def active_flatpage_aria(context, url):
    """
    Return 'aria-current="page"' if the current request path matches the given flatpage URL.

    Usage:
        {% active_flatpage_aria '/help/' %}
    """
    return 'aria-current="page"' if _is_flatpage_active(context, url) else ""


@dataclass
class Heading:
    """One heading found in a flat page's content."""

    level: int
    text: str
    slug: str
    children: list[Heading] = field(default_factory=list)


@dataclass
class ParsedContent:
    """A flat page's HTML with its headings made linkable, plus those headings."""

    html: str
    headings: list[Heading]


def parse_headings(html):
    """
    The one parse of a flat page's content that everything else reads from.

    Every heading (h1-h6) is given an id — a slug of its text, with ``-2``,
    ``-3``... appended when the same slug has already been used on the page —
    and wrapped in an anchor to that id, with a link icon inside. The same
    headings are returned as a flat list, in document order, so a contents
    block built from them links to the ids the HTML actually carries.

    Example:
      Input:  <h1>Foo Bar Baz!</h1>
      Output: <a href="#foo-bar-baz"><h1 id="foo-bar-baz">Foo Bar Baz!<i ...></i></h1></a>
    """
    soup = BeautifulSoup(html or "", "html.parser")
    headings = []
    # Authored content can carry its own ids (TinyMCE's anchor tool), so every
    # id already on the page is reserved before any heading slug is chosen.
    seen = {tag["id"] for tag in soup.find_all(id=True)}

    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        text = heading.get_text().strip()
        base = slugify(text) or "section"
        slug = base
        n = 1
        while slug in seen:
            n += 1
            slug = f"{base}-{n}"
        seen.add(slug)

        heading["id"] = slug
        anchor = soup.new_tag(
            "a",
            href=f"#{slug}",
            attrs={"class": "link-underline link-underline-opacity-0 text-reset"},
        )
        # Decorative: the anchor's accessible name is the heading text.
        icon = soup.new_tag(
            "i",
            attrs={
                "class": "bi-link-45deg ms-2 text-body-secondary",
                "aria-hidden": "true",
            },
        )
        heading.wrap(anchor)
        heading.append(icon)
        if text:
            headings.append(Heading(level=int(heading.name[1]), text=text, slug=slug))

    return ParsedContent(html=mark_safe(str(soup)), headings=headings)


def nest_headings(headings):
    """
    Turn a flat, document-ordered list of headings into a tree by level.

    A heading becomes a child of the nearest preceding heading with a smaller
    level. Skipped levels (an h4 straight after an h2) still nest under the
    h2; the tree follows the document, not the numbers.
    """
    roots = []
    stack = []
    for heading in headings:
        heading = Heading(heading.level, heading.text, heading.slug)
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        if stack:
            stack[-1].children.append(heading)
        else:
            roots.append(heading)
        stack.append(heading)
    return roots


@register.filter
def add_heading_links(html):
    """
    Template filter: the HTML half of ``parse_headings`` — every heading gets
    an id and is wrapped in an anchor to it.
    """
    return parse_headings(html).html


@register.simple_tag
def page_contents(page):
    """
    Render a nested list of the page's headings, linking to each one, when the
    page's options have "Show contents" ticked. Renders nothing otherwise.

    Usage:
        {% page_contents flatpage %}
    """
    if not FlatPageOptions.objects.filter(page=page, show_contents=True).exists():
        return ""
    headings = nest_headings(parse_headings(page.content).headings)
    if not headings:
        return ""
    return render_to_string("flatpages/includes/contents.html", {"headings": headings})
