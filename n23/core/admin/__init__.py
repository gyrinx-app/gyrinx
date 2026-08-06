"""The edition's admin surface.

Importing a module here is what registers it — both the ``@admin.register``
classes and the side-effect-only modules (``analytics``, ``broadcast``,
``maintenance``) that push edition features into platform registries. Those
three export nothing, so they look removable and are not: drop one and the
feature quietly vanishes from the admin.
``gyrinx/tests/test_admin_registration.py`` guards against exactly that.
"""

from .action import *  # noqa: F403
from .analytics import *  # noqa: F403
from .broadcast import *  # noqa: F403
from .campaign import *  # noqa: F403
from .events import *  # noqa: F403
from .impersonation import *  # noqa: F403
from .list import *  # noqa: F403
from .maintenance import *  # noqa: F403
from .pack import *  # noqa: F403
from .site import *  # noqa: F403
from .upload import *  # noqa: F403
