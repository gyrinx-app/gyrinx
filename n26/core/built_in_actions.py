"""Default discovery of actions with dedicated execution screens."""

from n26.library.models import BuiltInAction


def trading_post_visit_relevant(gang):
    """Missing configuration preserves the default of showing visit setup."""
    return not BuiltInAction.objects.filter(
        key=BuiltInAction.Key.TRADING_POST_VISIT,
        excluded_gang_types=gang.gang_type_id,
    ).exists()
