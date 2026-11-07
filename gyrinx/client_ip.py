"""Client IP extraction for the configured production proxy chain."""

import ipaddress

from django.conf import settings


def get_client_ip(request):
    """Return the load balancer's client entry, or the socket peer as fallback.

    The external load balancer appends client and forwarding-rule addresses to
    X-Forwarded-For. Earlier entries can be supplied by the caller.
    """
    if not request:
        return None

    hops = getattr(settings, "TRUSTED_X_FORWARDED_FOR_HOPS", 0)
    if hops:
        parts = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if len(parts) >= hops:
            candidate = parts[-hops].strip()
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass

    peer = request.META.get("REMOTE_ADDR")
    try:
        return str(ipaddress.ip_address(peer)) if peer else None
    except ValueError:
        return None
