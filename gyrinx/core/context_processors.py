from gyrinx.core.models import Banner


def site_banner(request):
    """Add the current live banner to the context, if any exists and hasn't been dismissed."""
    context = {"banner": None}

    # Check if there's a live banner
    try:
        live_banner = Banner.objects.filter(is_live=True).first()
        if live_banner:
            # Check if the user has dismissed this banner
            dismissed_banners = request.session.get("dismissed_banners", [])
            if str(live_banner.id) not in dismissed_banners:
                context["banner"] = live_banner
    except Exception:  # nosec B110
        # Fail silently if there are any issues - context processors should not break page rendering
        pass

    return context
