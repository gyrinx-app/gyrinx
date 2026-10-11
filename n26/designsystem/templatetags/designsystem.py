from django import template
from django.utils.safestring import mark_safe
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

register = template.Library()

# The Django lexer over HTML, so both the Cotton tags and any {% %} in a demo
# come out sensibly. Token colours are mapped onto theme tokens in app.css, which
# is why no Pygments stylesheet is pulled in here.
_LEXER = get_lexer_by_name("html+django", stripnl=False)
_FORMATTER = HtmlFormatter(nowrap=True)


@register.filter
def highlight(source):
    # nosec B703 B308 - pygments escapes its input; nothing user-supplied.
    return mark_safe(pygments_highlight(source, _LEXER, _FORMATTER))  # nosec B703 B308


@register.filter
def split(value, separator=","):
    return value.split(separator)


@register.filter
def get(mapping, key):
    """Dict lookup by a variable key, which the template language otherwise can't do."""
    return mapping.get(key)


@register.filter
def prop_row_class(prop):
    """Dim the internal lookup tables so the props people actually set stand out."""
    return "opacity-55" if prop.dynamic and prop.default.startswith("{") else ""


# The gallery's own pages, in sidebar order, by URL name.
_PAGES = (
    ("index", "Overview"),
    ("theming", "Theming"),
    ("tokens", "Tokens"),
    ("react", "React islands"),
    ("print_lab", "Print lab"),
)


@register.simple_tag(takes_context=True)
def gallery_nav(context):
    """The sidebar's links and filter terms, as the gallery-nav island's props.

    The Cotton fallback draws from the same structure, so the links match
    before and after the island mounts.
    """
    from django.urls import reverse

    from n26.designsystem import catalog

    match = getattr(context.get("request"), "resolver_match", None)
    here = match.url_name if match else None
    component = context.get("component")
    index = reverse("designsystem:index")
    return {
        "pages": [
            {
                "label": label,
                "href": reverse(f"designsystem:{name}"),
                "current": here == name,
            }
            for name, label in _PAGES
        ],
        # The only link that leaves the gallery, so it is never the current page.
        "shell": {"label": "App shell", "href": reverse("designsystem:shell_home")},
        "groups": [
            {
                "name": group.name,
                "href": f"{index}#{group.anchor}",
                "current": component is not None and component.group == group.name,
                "components": [
                    {
                        "slug": c.slug,
                        "href": reverse("designsystem:component", args=[c.slug]),
                        "current": component is not None and component.slug == c.slug,
                        "usesReact": c.uses_react,
                        "parts": len(c.parts),
                        "term": c.search_term,
                    }
                    for c in group.components
                ],
            }
            for group in catalog.GROUPS
        ],
    }
