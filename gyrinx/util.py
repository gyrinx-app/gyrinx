import difflib
import re

from rich.console import Console
from rich.text import Text

WORD_RE = re.compile(r"\s+|[\w'-]+|[^\w\s]", re.UNICODE)


def tokenize(s: str):
    """Split a string into tokens keeping whitespace & punctuation as separate tokens.

    Args:
        s: The string to tokenize.

    Returns:
        A list of tokens including words, whitespace, and punctuation marks.

    Example:
        >>> tokenize("Hello, world!")
        ['Hello', ',', ' ', 'world', '!']
    """
    return WORD_RE.findall(s)


def word_diff(old: str, new: str) -> Text:
    """Generate a word-level diff between two strings with rich formatting.

    Creates a visual diff showing deletions in red with strikethrough and
    insertions in green. This provides a more granular view than line-based
    diffs by highlighting individual word changes.

    Args:
        old: The original string to compare from.
        new: The new string to compare to.

    Returns:
        A Rich Text object with styled diff output where:
        - Unchanged text appears normally
        - Deleted text appears in red with strikethrough
        - Inserted text appears in green
        - Replaced text shows the old version struck through followed by the new version

    Example:
        >>> diff = word_diff("Hello world", "Hello beautiful world")
        # Returns Text with "beautiful" styled in green
    """
    a = tokenize(old)
    b = tokenize(new)

    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out = Text()

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append("".join(a[i1:i2]))
        elif tag == "delete":
            # deleted segment
            out.append("".join(a[i1:i2]), style="red strike")
        elif tag == "insert":
            # inserted segment
            out.append("".join(b[j1:j2]), style="green")
        elif tag == "replace":
            # show old then new
            out.append("".join(a[i1:i2]), style="red strike")
            out.append("".join(b[j1:j2]), style="green")

    return out


def print_word_diff(old: str, new: str):
    """Print a word-level diff to the console with rich formatting.

    Displays a visual diff between two strings, optionally with a legend explaining
    the color coding. Useful for showing changes in text content where word-level
    granularity is more helpful than line-level diffs.

    Args:
        old: The original string to compare from.
        new: The new string to compare to.

    Returns:
        None. Output is printed to the console.

    Example:
        >>> print_word_diff("The quick fox", "The quick brown fox")
        The quick brown fox
        # (with "brown" highlighted in green)
    """
    diff = word_diff(old, new)
    console = Console(color_system="256")
    console.print(diff)
