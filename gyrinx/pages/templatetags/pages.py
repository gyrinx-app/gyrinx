from django import template
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q

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
        flatpages = FlatPage.objects.filter(sites__id=site_pk)
        # If a prefix was specified, add a filter
        if self.starts_with:
            flatpages = flatpages.filter(
                url__startswith=self.starts_with.resolve(context)
            )

        # If the provided user is not authenticated, or no user
        # was provided, filter the list to only public flatpages.
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
            # Another addition: filter flatpages by depth
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
def page_depth(page):
    """
    Return the depth of the page in the site's hierarchy.
    """
    return max(page.url.count("/") - 2, 0)
