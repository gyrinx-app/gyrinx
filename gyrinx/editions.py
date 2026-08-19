"""Which edition a reader is in, and how the site remembers it.

The site is two editions — n23 under ``/n23/`` and n26 under ``/n26/`` — plus a
handful of pages both share: the account settings, the notification inbox, a
person's profile, the site root. An edition page announces its edition by its
own address. A shared page cannot, so the last edition a reader's address named
is kept in a cookie and answers for them: the root sends them back to it, and
the edition pill on a shared page shows it.

``gyrinx.middleware.EditionMiddleware`` is what writes the cookie and reads it.
"""

N23 = "n23"
N26 = "n26"
EDITIONS = frozenset({N23, N26})

#: The cookie holding the last edition the reader was in.
COOKIE_NAME = "edition"

#: A year. The memory is a preference rather than part of the session — a
#: reader who signs out and back in should land where they left off.
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

#: Names an edition explicitly for one navigation. The link out of n26 points
#: at the site root, which is exactly the address the memory redirects back
#: into n26, so leaving needs a way to say so. The middleware takes it and
#: redirects to the address without it: it is an instruction, and an
#: instruction left in the address bar is one the next reader inherits.
PARAM = "edition"

#: The one address the parameter is read at. See :func:`chosen_edition`.
PARAM_PATH = "/"


def edition_for_path(path):
    """The edition a path belongs to, or ``None`` for a page both share.

    The root counts as n23: it is the classic app's dashboard, and a reader who
    is looking at it is in n23 whatever they were in before.
    """
    if path == "/n26" or path.startswith("/n26/"):
        return N26
    if path == "/n23" or path.startswith("/n23/"):
        return N23
    if path == "/":
        return N23
    return None


def remembered_edition(request):
    """The edition the reader was last in, or ``None``.

    An unrecognised cookie value is treated as no memory at all, so a stale or
    hand-edited cookie cannot pin anyone to an edition that no longer exists.
    """
    value = request.COOKIES.get(COOKIE_NAME)
    return value if value in EDITIONS else None


def chosen_edition(request):
    """The edition named explicitly in the query string, or ``None``.

    Read at the site root and nowhere else. That is the only address the
    parameter is ever linked with, and the only one that needs it — the root
    belongs to neither edition, so it is the only place the memory answers
    for the reader and the only place a reader has to be able to overrule it.
    Elsewhere ``edition`` is somebody else's word: the analytics dashboard
    filters its charts by one, and a middleware that swallowed it would strip
    the filter off every link into that page.
    """
    if request.path != PARAM_PATH:
        return None
    value = request.GET.get(PARAM)
    return value if value in EDITIONS else None
