"""Confirmation data for actions requiring explicit player agreement.

Notes inform without blocking; refusals reject invalid actions. Confirmations
allow actions such as spending beyond a Trade Point allowance after the
player reviews the quantities involved.

The HTML flow posts to a confirmation page and repeats the submitted
fields with an explicit confirmation marker. ``carry`` preserves those
fields. Views must rederive available choices and validate prices on
every submission; hidden fields are untrusted input.
"""

from dataclasses import dataclass

#: Shared confirmation field and affirmative value used by the view.
CONFIRM_FIELD = "confirmed"

#: What the confirming post never carries forward: the token belongs to
#: the form being drawn now, and Django writes a fresh one into it.
_NOT_CARRIED = {"csrfmiddlewaretoken", CONFIRM_FIELD}


@dataclass(frozen=True)
class Fact:
    """One figure a decision is made against, as a tally reads it.

    ``sub`` is where the figure came from, under the label — the ranks
    that add up to it. ``ruled`` draws a line above the row and ``strong``
    sets it in bold, which together are how a total is marked off from
    what makes it.
    """

    label: str
    value: str
    sub: str = ""
    ruled: bool = False
    strong: bool = False


@dataclass(frozen=True)
class Aside:
    """Secondary confirmation text with an opening bold phrase.

    Keep permission and consequences separate from the main numeric comparison.
    """

    lead: str
    rest: str = ""


@dataclass(frozen=True)
class Checkbox:
    """An optional checkbox on the confirmation form.

    Unchecked boxes submit no value, so the view must supply the default.
    """

    name: str
    value: str
    label: str
    description: str = ""
    checked: bool = False


@dataclass(frozen=True)
class Confirmation:
    """Action details and submission fields for an explicit confirmation.

    ``action`` is the original command URL; ``cancel_url`` returns to the
    originating page. ``checkbox`` adds an optional choice. ``variant`` selects
    warning for an unusual action or info when only a choice is required.
    """

    title: str
    lead: str
    heading: str
    body: str
    confirm_label: str
    action: str
    cancel_url: str
    facts: tuple[Fact, ...] = ()
    aside: Aside | None = None
    carry: tuple[tuple[str, str], ...] = ()
    confirm_field: str = CONFIRM_FIELD
    confirm_value: str = ""
    checkbox: Checkbox | None = None
    variant: str = "warning"


def carried(post, *, leave_out=()):
    """Every field of a submission, ready to be re-emitted as hidden inputs.

    Repeated names are kept repeated — a row's ticked parts arrive as
    several values under one name, and a confirmation that collapsed
    them would buy a different thing from the one it described.

    ``leave_out`` names the fields the confirmation draws itself, so a
    tick box is not also carried as a hidden copy that outvotes it.
    """
    return tuple(
        (name, value)
        for name in post.keys()
        if name not in _NOT_CARRIED and name not in leave_out
        for value in post.getlist(name)
    )
