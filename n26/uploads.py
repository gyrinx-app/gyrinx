"""Rich-text image uploads through the shared platform media service.

The platform owns authentication, CSRF checks, quotas and storage. Edition
widgets opt into its client handler through this seam.
"""

from gyrinx.widgets import TINYMCE_UPLOAD_CONFIG

__all__ = ["TINYMCE_UPLOAD_CONFIG"]
