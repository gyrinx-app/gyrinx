"""Restart the dev server when an imported project module changes on disk.

Django prefers Watchman when it is installed. Watchman follows the inodes it
saw at startup. A checkout replaces those files, so the watch never fires.
Template directories still move when files are replaced, and the dev server
resets its template loaders on the next request. The process then serves new
templates with the Python it imported at startup.

The serving process stats the project modules it has already imported. A
changed or removed file exits with the code runserver's autoreloader reads
as restart. The baseline for a module is taken when it is loaded, not the
next time a request notices it: a module imported during startup, then
edited before that request, would otherwise keep the edited time and the
old code. ``--noreload`` has no parent to start a new process, so this
watch stays off there.
"""

import importlib.machinery
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


class _NotingLoader:
    """Runs the real loader and records the file's mtime as it is read."""

    def __init__(self, loader, watch, origin):
        self._loader = loader
        self._watch = watch
        self._origin = origin

    def create_module(self, spec):
        create = getattr(self._loader, "create_module", None)
        if create is None:
            return None
        return create(spec)

    def exec_module(self, module):
        # Stat before the loader reads the file. That mtime is what this
        # process will be running, so a later write is a real change.
        self._watch.note(self._origin)
        self._loader.exec_module(module)

    def __getattr__(self, name):
        return getattr(self._loader, name)


class _ProjectModuleFinder:
    """Claims project modules so their mtime is recorded as they load."""

    def __init__(self, watch):
        self.watch = watch

    def find_spec(self, fullname, path, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None or not spec.origin:
            return None
        if not hasattr(spec.loader, "exec_module"):
            return None
        if self.watch.project_path(spec.origin) is None:
            return None
        spec.loader = _NotingLoader(spec.loader, self.watch, spec.origin)
        return spec


class ImportedSourceWatch:
    """Reports a project module whose file no longer matches the armed snapshot."""

    def __init__(self, root, modules=None, restart=None):
        self.root = Path(root).resolve()
        self.modules = sys.modules if modules is None else modules
        self.restart = restart_process if restart is None else restart
        self.mtimes = None
        self._lock = threading.Lock()
        self._finder = None
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

    def cached_project_path(self, filename):
        if not isinstance(filename, str):
            return None
        path = self._project.get(filename)
        if path is not None:
            return path
        if filename in self._outside:
            return None
        path = self.project_path(filename)
        if path is None:
            self._outside.add(filename)
            return None
        self._project[filename] = path
        return path

    def snapshot(self):
        found = {}
        for module in list(self.modules.values()):
            path = self.cached_project_path(getattr(module, "__file__", None))
            if path is None:
                continue
            try:
                found[path] = path.stat().st_mtime_ns
            except OSError:
                found[path] = None
        return found

    def note(self, filename):
        """Record the mtime of a file this process is loading now."""
        path = self.cached_project_path(filename)
        if path is None:
            return
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = None
        with self._lock:
            if self.mtimes is None:
                self.mtimes = {}
            self.mtimes[path] = mtime

    def arm(self):
        """Baseline modules already imported. A load-time note wins."""
        found = self.snapshot()
        with self._lock:
            if self.mtimes:
                for path, mtime in self.mtimes.items():
                    found[path] = mtime
            self.mtimes = found

    def changed(self):
        current = self.snapshot()
        with self._lock:
            if self.mtimes is None:
                self.mtimes = current
                return None
            baselines = dict(self.mtimes)
        for path, mtime in baselines.items():
            # A module that failed to finish importing is not running, so its
            # absence is not a change. A loaded file that disappeared is.
            if path not in current:
                continue
            if current[path] != mtime:
                return path
        return None

    def install_finder(self):
        if self._finder is None:
            self._finder = _ProjectModuleFinder(self)
        if self._finder not in sys.meta_path:
            sys.meta_path.insert(0, self._finder)

    def close(self):
        request_started.disconnect(dispatch_uid=DISPATCH_UID)
        if self._finder is not None and self._finder in sys.meta_path:
            sys.meta_path.remove(self._finder)

    def __call__(self, **kwargs):
        path = self.changed()
        if path is not None:
            self.restart(path)


def install(root, *, modules=None, restart=None):
    """Arm the watch and check it at the start of each request."""
    watch = ImportedSourceWatch(root, modules=modules, restart=restart)
    # The finder has to be in place before arm() returns: imports that
    # finish startup, such as the URL conf, happen after ready().
    watch.install_finder()
    watch.arm()
    # weak=False keeps the watch alive after install() returns. A weak
    # reference would be collected, and the signal would never fire.
    request_started.connect(watch, dispatch_uid=DISPATCH_UID, weak=False)
    return watch
