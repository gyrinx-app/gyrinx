"""Restart the dev server when an imported project module changes on disk.

Django prefers Watchman when it is installed. Watchman follows the inodes it
saw at startup. A checkout replaces those files, so the watch never fires.
Template directories still move when files are replaced, and the dev server
resets its template loaders on the next request. The process then serves new
templates with the Python it imported at startup.

The serving process stats the project modules it has already imported. A
changed or removed file exits with the code runserver's autoreloader reads
as restart. ``--noreload`` has no parent to start a new process, so this
watch stays off there.
"""

import logging
import os
import sys
import threading
from pathlib import Path

from django.core.signals import request_started

logger = logging.getLogger(__name__)

#: runserver's autoreloader starts a new server process when the old one exits
#: with this code. The dev server guard uses the same value.
RESTART = 3

DISPATCH_UID = "gyrinx.devserver.python_watch"

# Generated trees and dependencies live inside the checkout. Their Python is
# not the source a checkout is trying to reload.
_SKIPPED_PARTS = frozenset(
    {".venv", "node_modules", "logs", "staticfiles", "media", "__pycache__"}
)


def _python_source(filename):
    if not isinstance(filename, str):
        return None
    if filename.endswith(".pyc"):
        filename = filename[:-1]
    path = Path(filename)
    if path.suffix != ".py":
        return None
    return path


def restart_process(path):
    message = f"Restarting the dev server: {path} changed on disk."
    logger.warning(message)
    logging.shutdown()
    # The request runs off the main thread. sys.exit would end that thread
    # and leave the process up with nothing serving.
    os._exit(RESTART)


class ImportedSourceWatch:
    """Reports a project module whose file no longer matches the armed snapshot."""

    def __init__(self, root, modules=None, restart=None):
        self.root = Path(root).resolve()
        self.modules = sys.modules if modules is None else modules
        self.restart = restart_process if restart is None else restart
        self.mtimes = None
        self._lock = threading.Lock()
        # __file__ strings already classified. A request then stats project
        # modules and skips everything else in sys.modules.
        self._project = {}
        self._outside = set()

    def project_path(self, filename):
        path = _python_source(filename)
        if path is None:
            return None
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(self.root)
        except OSError, ValueError:
            return None
        if _SKIPPED_PARTS.intersection(relative.parts) or any(
            part.endswith((".egg-info", ".dist-info")) for part in relative.parts
        ):
            return None
        return resolved

    def snapshot(self):
        found = {}
        for module in list(self.modules.values()):
            filename = getattr(module, "__file__", None)
            path = self._project.get(filename)
            if path is None:
                if filename in self._outside:
                    continue
                path = self.project_path(filename)
                if path is None:
                    if isinstance(filename, str):
                        self._outside.add(filename)
                    continue
                self._project[filename] = path
            try:
                found[path] = path.stat().st_mtime_ns
            except OSError:
                found[path] = None
        return found

    def arm(self):
        self.mtimes = self.snapshot()

    def changed(self):
        current = self.snapshot()
        if self.mtimes is None:
            self.mtimes = current
            return None
        for path, mtime in self.mtimes.items():
            if current.get(path) != mtime:
                return path
        for path, mtime in current.items():
            self.mtimes.setdefault(path, mtime)
        return None

    def __call__(self, **kwargs):
        with self._lock:
            path = self.changed()
        if path is not None:
            self.restart(path)


def install(root, *, modules=None, restart=None):
    """Arm the watch and check it at the start of each request."""
    watch = ImportedSourceWatch(root, modules=modules, restart=restart)
    watch.arm()
    # weak=False keeps the watch alive after install() returns. A weak
    # reference would be collected, and the signal would never fire.
    request_started.connect(watch, dispatch_uid=DISPATCH_UID, weak=False)
    return watch
