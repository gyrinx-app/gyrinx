"""Informational messages attached to card or line objects.

Use one Note structure for restrictions and other advice. ``about`` holds
real objects so readers never match message text to find its subject.
Levels control presentation; notes do not block operations. Inform rather
than police.
"""

from dataclasses import dataclass

#: How loudly a surface should draw the note. Never a gate.
INFO = "info"
WARNING = "warning"
ERROR = "error"

_LOUDNESS = {INFO: 0, WARNING: 1, ERROR: 2}


@dataclass(frozen=True)
class Note:
    """Message text, subject object and presentation level.

    Consumers compare about by identity; text is display-only.
    """

    text: str
    about: object
    level: str = WARNING

    def at_least(self, level):
        return _LOUDNESS[self.level] >= _LOUDNESS[level]
