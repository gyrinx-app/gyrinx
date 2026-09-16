"""Counter journal readiness, read under the n26 write barrier by writers."""

from n26.core.models.counter_tracking import CounterTracking


def is_active():
    """True only after every existing counter has passed the activation audit."""
    return CounterTracking.objects.filter(pk=1, activated_at__isnull=False).exists()
