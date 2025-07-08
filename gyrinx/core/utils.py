"""
Utility functions for the core app.
"""


from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(request, url, fallback_url="/"):
    """
    Perform a safe redirect, ensuring the URL is allowed.

    Args:
        request: The current HTTP request
        url: The URL to redirect to
        fallback_url: The URL to use if validation fails (default: "/")

    Returns:
        HttpResponseRedirect to either the validated URL or the fallback
    """
    # Validate the URL is safe
    if url and url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return HttpResponseRedirect(url)

    # Fall back to the provided fallback URL
    return HttpResponseRedirect(fallback_url)


def build_safe_url(request, path=None, query_string=None):
    """
    Build a safe URL from path and query string components.

    Args:
        request: The current HTTP request
        path: The path component (default: request.path)
        query_string: The query string (without '?')

    Returns:
        A safe URL string that can be used for redirects
    """
    # Use current path if not provided
    if path is None:
        path = request.path

    # Build the full URL
    if query_string:
        url = f"{path}?{query_string}"
    else:
        url = path

    # Validate the URL is safe
    if url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url

    # Return just the path if validation fails
    return path
