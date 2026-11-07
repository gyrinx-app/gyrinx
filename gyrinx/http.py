"""Validate request-provided redirect URLs against the current host and scheme.

Use safe_redirect or get_return_url for untrusted destinations. Callers must
supply trusted fallback URLs and trusted path arguments to build_safe_url.
"""

from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(request, url, fallback_url="/"):
    """Redirect to an allowed URL, otherwise to the trusted fallback_url.

    Require HTTPS for secure requests and allow only the request host.
    """
    if not url:
        return HttpResponseRedirect(fallback_url)

    if not url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return HttpResponseRedirect(fallback_url)

    return HttpResponseRedirect(url)


def build_safe_url(request, path=None, query_string=None):
    """Combine path and query_string if the resulting URL passes host validation.

    Default path to request.path. On validation failure return path unchanged,
    so callers must supply a trusted path.
    """

    if path is None:
        path = request.path

    if query_string:
        url = f"{path}?{query_string}"
    else:
        url = path

    if not url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return path

    return url


def get_return_url(request, default_url):
    """Return a validated POST or GET return_url, otherwise the trusted default_url.

    A non-empty POST value takes precedence. Require the request host and, for
    secure requests, HTTPS.
    """

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
