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
