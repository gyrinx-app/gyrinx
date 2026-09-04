"""Saying whose content a page is showing, for the platform's overlay.

A single-file seam of the same shape as ``n26/notifications.py``. Signing in
as somebody else is the site's, not an edition's: one session key, one
middleware that swaps the user for a request, one log of who went into whose
account and when. A second implementation here would give the two editions
separate records of that, which is the one thing an audit of it must not
have.

What crosses is one call. An edition knows which of its pages open for
somebody other than their owner — a roster and a campaign, and nothing else
— and says so; the platform decides whether the reader may go in, and the
account menu draws the way. This is the only file here that names the
overlay.
"""

from gyrinx.impersonation import note_page_subject

__all__ = ["note_page_subject"]
