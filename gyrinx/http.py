"""Request and redirect helpers.

Every function here validates a user-supplied URL against the requesting host
before handing it back, so a ``?next=`` or ``?return_url=`` cannot be turned into
an open redirect. Use these rather than constructing
:class:`~django.http.HttpResponseRedirect` from request data directly.

Platform code, not edition code: none of it knows anything about gangs, fighters
or campaigns.
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
    if not url:
        return HttpResponseRedirect(fallback_url)

    if not url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return HttpResponseRedirect(fallback_url)

    return HttpResponseRedirect(url)


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
    if not url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return path

    return url


def get_return_url(request, default_url):
    """
    Get a validated return URL from request parameters.

    Extracts return_url from POST data (for form submissions) or GET parameters.
    Validates the URL for security and falls back to default_url if invalid.

    Args:
        request: The HTTP request object
        default_url: Fallback URL if return_url is missing or invalid

    Returns:
        str: A validated URL safe for redirects

    Example:
        default_url = reverse("core:list", args=(list.id,))
        return_url = get_return_url(request, default_url)
    """
    # Check POST first (form submissions), then GET (query params)
    return_url = request.POST.get("return_url") or request.GET.get(
        "return_url", default_url
    )

    if not return_url:
        return default_url

    if not url_has_allowed_host_and_scheme(
        return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return default_url

    return return_url
