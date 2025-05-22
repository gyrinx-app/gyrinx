from gyrinx.models import Archived, Base, Owned

from .history_aware_manager import HistoryAwareManager
from .history_mixin import HistoryMixin


class AppBase(HistoryMixin, Base, Owned, Archived):
    """An AppBase object is a base class for all application models.

    This base class provides:
    - UUID primary key (from Base)
    - Owner tracking (from Owned)
    - Archive functionality (from Archived)
    - History tracking with user information (from HistoryMixin)
    - History-aware manager for better user tracking
    """

    # Use the history-aware manager by default
    objects = HistoryAwareManager()

    class Meta:
        abstract = True
