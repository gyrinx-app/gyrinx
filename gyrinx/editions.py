"""Edition detection and the preference cookie for shared pages.

EditionMiddleware reads the URL prefix on edition pages and remembers it for
signed-in users. Shared pages use that cookie for navigation. The site root
redirects users who last visited N26 to its dashboard.
"""

N23 = "n23"
N26 = "n26"
EDITIONS = frozenset({N23, N26})

#: The cookie holding the last edition the reader was in.
COOKIE_NAME = "edition"

#: Keep the preference for a year so it survives signing out.
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

#: Override the remembered edition when switching through the site root.
#: Middleware removes this parameter before redirecting to a shareable URL.
PARAM = "edition"

#: The one address the parameter is read at. See :func:`chosen_edition`.
PARAM_PATH = "/"


def edition_for_path(path):
    """Return the edition for a URL path, or None for a shared page.

    The site root serves the N23 dashboard unless middleware redirects it.
    """
    if path == "/n26" or path.startswith("/n26/"):
        return N26
    if path == "/n23" or path.startswith("/n23/"):
        return N23
    if path == "/":
        return N23
    return None


def remembered_edition(request):
    """Return the edition cookie value, or None if it is absent or unknown."""
    value = request.COOKIES.get(COOKIE_NAME)
    return value if value in EDITIONS else None


def chosen_edition(request):
    """Read an explicit edition choice at the site root.

    Other pages may use the same parameter for filtering, so middleware must
    leave it unchanged there.
    """
    if request.path != PARAM_PATH:
        return None
    value = request.GET.get(PARAM)
    return value if value in EDITIONS else None
