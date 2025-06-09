from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def theme_square(list_obj, size="0.8em", extra_classes=""):
    """
    Generate a small color square for a list's theme color.
    Shows just the color indicator without the list name.
    """
    if not list_obj:
        return ""

    theme_color = getattr(list_obj, "theme_color", None)

    if theme_color:
        return mark_safe(
            f'<span class="d-inline-block rounded {extra_classes}" '
            f'style="width: {size}; height: {size}; '
            f"background-color: {theme_color}; "
            f'border: 1px solid rgba(0,0,0,0.15);"></span>'
        )
    else:
        return ""


@register.simple_tag
def list_with_theme(list_obj, extra_classes="", square_size="0.8em"):
    """
    Display a list name with its theme color square.
    """
    if not list_obj:
        return ""

    name = getattr(list_obj, "name", str(list_obj))
    theme_color = getattr(list_obj, "theme_color", None)

    if theme_color:
        square = theme_square(list_obj, extra_classes="me-1", size=square_size)
        return mark_safe(f'<span class="{extra_classes}">{square}{name}</span>')
    else:
        return mark_safe(f'<span class="{extra_classes}">{name}</span>')


@register.simple_tag
def link_with_theme(list_obj, url, extra_classes="", square_size="0.8em"):
    """
    Display a list name with its theme color square as a link.
    """
    if not list_obj:
        return ""

    name = getattr(list_obj, "name", str(list_obj))
    theme_color = getattr(list_obj, "theme_color", None)

    if theme_color:
        square = theme_square(list_obj, extra_classes="me-1", size=square_size)
        return mark_safe(
            f'<a href="{url}" class="link-secondary link-underline-opacity-25 link-underline-opacity-100-hover {extra_classes}">'
            f'{square}{name}</a>'
        )
    else:
        return mark_safe(
            f'<a href="{url}" class="link-secondary link-underline-opacity-25 link-underline-opacity-100-hover {extra_classes}">'
            f'{name}</a>'
        )
