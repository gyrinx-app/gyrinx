"""Confirmations — the third answer a click can get.

Two already exist and neither fits everything. A ``n26.core.notes.Note``
says something and lets the click through, which is the edition's usual
answer: we inform, never police. A ``n26.core.operations.Refusal`` stops
the click dead, and only one rule earns it — a gang may not spend past
its credits budget. Between them sits an act nobody wants to forbid but
nobody wants to do by accident: spending Trade Points a gang has not
got, and whatever joins it later. That is a confirmation, and it is
worth its own name because the alternative is faking it with a refusal
the caller catches, which reads as a rule and behaves as a prompt.

A confirmation is a **navigation, not a modal**. The click posts; the
server answers with a page that names the act, gives the numbers it was
decided against, and offers a button that posts the very same fields
back with one more saying the reader meant it. Back is a real answer,
a reload does not lose it, and none of it needs scripting.

The numbers are the point. A confirmation that only named the thing
would be asking a reader to check a decision against a word they have
already read — the same reason the gang deletion page counts the roster
rather than repeating the name.

``carry`` is what makes the second post identical to the first: every
field of the original submission, re-emitted. The view re-derives the
whole click from them exactly as it did the first time, so nothing here
is trusted — a tampered hidden field can name nothing the listing does
not offer, and the prices are bounded on the way through either way.
"""

from dataclasses import dataclass

#: The field the confirming post carries, and what it has to say. Read
#: by the view that asked, so the two cannot come to disagree about what
#: counts as "yes".
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
    """A second line under a confirmation's body, opening in bold.

    What the reader needs after the arithmetic: that the act is allowed,
    and what it leaves behind. Kept off the first line because the two
    say different things — one is the position, the other is the
    permission — and a reader skimming for the second should not have to
    read the first twice to find it.
    """

    lead: str
    rest: str = ""


@dataclass(frozen=True)
class Confirmation:
    """An act that will go ahead, once the reader says they meant it.

    ``action`` is the address the confirming post goes to — the same one
    the first post went to, so the click is read once, in one place.
    ``cancel_url`` is where saying no lands, which is the page the click
    came from.
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


def carried(post):
    """Every field of a submission, ready to be re-emitted as hidden inputs.

    Repeated names are kept repeated — a row's ticked parts arrive as
    several values under one name, and a confirmation that collapsed
    them would buy a different thing from the one it described.
    """
    return tuple(
        (name, value)
        for name in post.keys()
        if name not in _NOT_CARRIED
        for value in post.getlist(name)
    )
