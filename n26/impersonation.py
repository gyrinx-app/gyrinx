"""Expose a page's content owner to the platform impersonation service. The platform checks
permission, changes the request user and records the shared audit trail.
"""

from gyrinx.impersonation import note_page_subject

__all__ = ["note_page_subject"]
