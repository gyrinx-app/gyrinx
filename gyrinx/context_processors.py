"""Platform context processors.

``site_banner`` and ``notifications`` deliberately stay in
``n23.core.context_processors``: they query the ``Banner`` and ``Notification``
models, which are still edition models. They move here once those models do.
"""

from django.conf import settings


def gyrinx_debug(request):
    """Add gyrinx_debug flag to the context for debug UI elements."""
    return {"gyrinx_debug": settings.GYRINX_DEBUG}


def impersonation(request):
    """Expose impersonation state to templates.

    Set by :class:`n23.core.middleware.ImpersonationMiddleware`. When
    ``is_impersonating`` is true, ``request.user`` is the impersonated user and
    ``impersonator`` is the real admin.
    """
    return {
        "is_impersonating": getattr(request, "is_impersonating", False),
        "impersonator": getattr(request, "impersonator", None),
    }
