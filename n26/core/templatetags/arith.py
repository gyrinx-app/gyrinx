"""Arithmetic Django's template language leaves out.

Only what a template genuinely cannot express. Django ships ``add`` but has no
subtract, and its argument cannot itself be a filtered value — so working out a
colspan from two lengths is impossible without help. That is the whole reason
this exists.
"""

from django import template

register = template.Library()


@register.filter
def sub(value, arg):
    """``{{ wide|sub:narrow }}`` — subtraction, for colspans.

    Non-numeric input yields "" rather than raising, matching how the rest of the
    template filters behave: a broken colspan should not take a page down.
    """
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
    """Cap a number — ``{{ quoted|at_most:0 }}`` is the least a price box
    may hold, which is the quote where the quote is below zero.

    Coerces first, because a value reaches a template as a string as
    often as a number, and a comparison between the two is not an answer.
    """
    try:
        return min(int(value), int(maximum))
    except TypeError, ValueError:
        return maximum
