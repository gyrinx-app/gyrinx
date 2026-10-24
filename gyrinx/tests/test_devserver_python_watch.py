"""The dev server restarts when an imported project module changes on disk."""

import os
from types import SimpleNamespace

from django.core.signals import request_started

from gyrinx.devserver.python_watch import (
    DISPATCH_UID,
    RESTART,
    ImportedSourceWatch,
    install,
    restart_process,
)


def _module(path):
    return SimpleNamespace(__file__=str(path))


def _watch(root, modules, restart=None):
    watch = ImportedSourceWatch(root, modules=modules, restart=restart)
    watch.arm()
    return watch


def test_an_unchanged_module_is_left_alone(tmp_path):
    source = tmp_path / "views.py"
    source.write_text("x = 1\n")
    watch = _watch(tmp_path, {"app.views": _module(source)})
    assert watch.changed() is None


def test_a_changed_module_is_reported(tmp_path):
    source = tmp_path / "views.py"
    source.write_text("x = 1\n")
    watch = _watch(tmp_path, {"app.views": _module(source)})
    source.write_text("x = 2\n")
    os.utime(source, (source.stat().st_atime, source.stat().st_mtime + 5))
    assert watch.changed() == source.resolve()


def test_a_removed_module_is_reported(tmp_path):
    source = tmp_path / "views.py"
    source.write_text("x = 1\n")
    watch = _watch(tmp_path, {"app.views": _module(source)})
    source.unlink()
    assert watch.changed() == source.resolve()


def test_a_module_imported_later_is_not_a_change(tmp_path):
    source = tmp_path / "views.py"
    source.write_text("x = 1\n")
    modules = {"app.views": _module(source)}
    watch = _watch(tmp_path, modules)
    added = tmp_path / "new.py"
    added.write_text("y = 1\n")
    modules["app.new"] = _module(added)
    assert watch.changed() is None
    assert watch.changed() is None


def test_a_module_outside_the_checkout_is_ignored(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    watch = _watch(root, {"elsewhere": _module(outside)})
    outside.write_text("x = 2\n")
    os.utime(outside, (outside.stat().st_atime, outside.stat().st_mtime + 5))
    assert watch.changed() is None


def test_a_dependency_inside_the_checkout_is_ignored(tmp_path):
    source = tmp_path / ".venv" / "lib" / "pkg.py"
    source.parent.mkdir(parents=True)
    source.write_text("x = 1\n")
    watch = _watch(tmp_path, {"pkg": _module(source)})
    source.write_text("x = 2\n")
    os.utime(source, (source.stat().st_atime, source.stat().st_mtime + 5))
    assert watch.changed() is None


def test_a_compiled_file_is_read_as_its_source(tmp_path):
    source = tmp_path / "views.py"
    source.write_text("x = 1\n")
    watch = _watch(tmp_path, {"app.views": _module(tmp_path / "views.pyc")})
    source.write_text("x = 2\n")
    os.utime(source, (source.stat().st_atime, source.stat().st_mtime + 5))
    assert watch.changed() == source.resolve()


def test_the_request_signal_restarts_when_a_module_changed(tmp_path):
    source = tmp_path / "views.py"
    source.write_text("x = 1\n")
    restarted = []
    watch = install(
        tmp_path,
        modules={"app.views": _module(source)},
        restart=restarted.append,
    )
    try:
        source.write_text("x = 2\n")
        os.utime(source, (source.stat().st_atime, source.stat().st_mtime + 5))
        request_started.send(sender=None)
        assert restarted == [source.resolve()]
    finally:
        request_started.disconnect(dispatch_uid=DISPATCH_UID)
        assert watch is not None


def test_restart_process_exits_with_the_autoreloader_code(monkeypatch, tmp_path):
    exited = []
    monkeypatch.setattr(
        "gyrinx.devserver.python_watch.os._exit", lambda code: exited.append(code)
    )
    monkeypatch.setattr("gyrinx.devserver.python_watch.logging.shutdown", lambda: None)
    restart_process(tmp_path / "views.py")
    assert exited == [RESTART]
