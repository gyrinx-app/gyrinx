import re

from bs4 import BeautifulSoup
from django import template
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
from django.utils.safestring import mark_safe

register = template.Library()

# Note: this is largely a copy of the get_flatpages tag from Django's flatpages app


class FlatpageNode(template.Node):
    depth = 0

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
                    url__regex=r"^/[^/]+(?:/[^/]+){0,%d}/?$" % (self.depth - 1)
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
        "%(tag_name)s expects a syntax of %(tag_name)s "
        "['url_starts_with'] [for user] as context_name" % {"tag_name": bits[0]}
    )
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
    """
    try:
        return FlatPage.objects.get(url=url)
    except FlatPage.DoesNotExist:
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


@register.filter
def add_heading_links(html):
    """
    Django template filter that transforms all heading tags (h1-h6) in the given HTML.
    Each heading is given an id attribute (a slugified version of its text)
    and is wrapped in an <a> tag with href set to "#<slug>".

    Example:
      Input:  <h1>Foo Bar Baz!</h1>
      Output: <a href="#foo-bar-baz"><h1 id="foo-bar-baz">Foo Bar Baz!</h1></a>
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find all heading tags h1-h6 using a regex.
    for n, heading in enumerate(soup.find_all(re.compile(r"^h[1-6]$"))):
        slug = slugify(heading.get_text())
        heading["id"] = slug
        # Create a new anchor tag with the href attribute set to "#slug"
        anchor = soup.new_tag(
            "a",
            href=f"#{slug}",
            attrs={
                "class": "link-underline link-underline-opacity-0 link-underline-opacity-75-hover text-reset",
            },
        )
        icon = soup.new_tag(
            "i", attrs={"class": "bi-link-45deg ms-2 text-body-secondary"}
        )
        # Wrap the heading with the new anchor tag and insert the icon
        heading.wrap(anchor)
        heading.insert(1, icon)

    # Mark the output as safe so Django doesn't escape the HTML
    return mark_safe(str(soup))
