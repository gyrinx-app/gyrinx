"""Template arithmetic helpers for operations absent from Django's filters.

These support computed colspans and bounded numeric inputs.
"""

from django import template

register = template.Library()


@register.filter
def sub(value, arg):
    """Subtract a numeric filter argument, returning empty for invalid input."""
    try:
        return int(value) - int(arg)
    except TypeError, ValueError:
        return ""


@register.filter
def at_least(value, minimum):
    """Floor a number. A colspan of 0 or less is invalid HTML."""
    try:
        return max(int(value), int(minimum))
    except TypeError, ValueError:
        return minimum


@register.filter
def at_most(value, maximum):
    """Cap a coerced number at the supplied upper bound.

    For negative price quotes, use zero to obtain the permitted minimum.
    """
    try:
        return min(int(value), int(maximum))
    except TypeError, ValueError:
        return maximum
