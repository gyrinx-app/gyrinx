"""Run the local toolkit report clock while its demo launcher is open."""

import logging
import os
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings_dev")
import django

django.setup()
from django.conf import settings  # noqa: E402
from django.db import close_old_connections  # noqa: E402

from n26.notifications import deliver_toolkit_reports, retry_toolkit_notifications  # noqa: E402

if not settings.DEBUG:
    raise RuntimeError("The local alert clock requires development settings.")
stop = threading.Event()
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, lambda *_: stop.set())
parent = os.getppid()
while not stop.is_set() and os.getppid() == parent:
    try:
        deliver_toolkit_reports.func()
        retry_toolkit_notifications.func()
    except Exception:
        logging.exception("Toolkit reports will retry on the next local tick.")
    finally:
        close_old_connections()
    stop.wait(30)
