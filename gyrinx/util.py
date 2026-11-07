import difflib
import re

from rich.console import Console
from rich.text import Text

WORD_RE = re.compile(r"\s+|[\w'-]+|[^\w\s]", re.UNICODE)


def tokenize(s: str):
    """Split text into word, whitespace and punctuation tokens."""
    return WORD_RE.findall(s)


def word_diff(old: str, new: str) -> Text:
    """Return Rich Text with deletions red and struck through, and insertions green.

    Show replaced text as its deletion followed by its insertion.
    """
    a = tokenize(old)
    b = tokenize(new)

    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out = Text()

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append("".join(a[i1:i2]))
        elif tag == "delete":
            out.append("".join(a[i1:i2]), style="red strike")
        elif tag == "insert":
            out.append("".join(b[j1:j2]), style="green")
        elif tag == "replace":
            out.append("".join(a[i1:i2]), style="red strike")
            out.append("".join(b[j1:j2]), style="green")

    return out


def print_word_diff(old: str, new: str):
    """Print the styled word diff to the console."""
    diff = word_diff(old, new)
    console = Console(color_system="256")
    console.print(diff)
