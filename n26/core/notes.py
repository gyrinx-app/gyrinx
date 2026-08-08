"""Notes — the one channel for telling the player something.

The app keeps needing to say things without stopping anyone: "this
fighter can't use that skill", later "you're over three weapon slots",
"this is off your list". Each is the same kind of thing — a sentence
attached to a line or a card, pointing at what it concerns — so there is
one shape for all of them, not a named boolean per rule.

A note points at real rows (``about``), never at display strings, so
nothing downstream ever matches on text. Levels say how loudly to draw
it; nothing anywhere blocks on one — we inform, never police.
"""

from dataclasses import dataclass

#: How loudly a surface should draw the note. Never a gate.
INFO = "info"
WARNING = "warning"
ERROR = "error"

_LOUDNESS = {INFO: 0, WARNING: 1, ERROR: 2}


@dataclass(frozen=True)
class Note:
    """One remark: what it says, what it points at, how loud it is.

    ``about`` is the actual content row the remark concerns — a Skill, a
    Weapon — so consumers compare identities, never strings. ``text`` is
    for humans only.
    """

    text: str
    about: object
    level: str = WARNING

    def at_least(self, level):
        return _LOUDNESS[self.level] >= _LOUDNESS[level]
