"""
Core views package.

This module provides the main views for the core app and re-exports
from submodules for convenience.
"""

from urllib.parse import urlencode

from .banner import dismiss_banner, track_banner_click
from .csrf import csrf_failure
from .dice import dice
from .home import account_home, index
from .upload import tinymce_upload
from .user import change_username, user


def make_query_params_str(**kwargs) -> str:
    """Build a URL query string from keyword arguments, excluding None values."""
    return urlencode(dict([(k, v) for k, v in kwargs.items() if v is not None]))


__all__ = [
    # Utilities
    "make_query_params_str",
    # Home views
    "index",
    "account_home",
    # User views
    "user",
    "change_username",
    # Dice views
    "dice",
    # Banner views
    "dismiss_banner",
    "track_banner_click",
    # Other
    "csrf_failure",
    "tinymce_upload",
]
