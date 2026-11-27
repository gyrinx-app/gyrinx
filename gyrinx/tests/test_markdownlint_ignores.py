"""markdownlint skips Markdown inside any node_modules directory.

``scripts/fmt.sh`` runs ``markdownlint-cli2 --fix "**/*.md"``. The config
ignore ``node_modules`` matches only a top-level directory of that name, and
markdownlint does not apply a nested ``.gitignore`` unless ``gitignore`` is
enabled. A canvas-viewer install at ``tools/canvas-viewer/node_modules`` was
therefore linted, and ``--fix`` would rewrite dependency READMEs.
"""

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]
UGLY = "# Title\n* star\n"
MARKDOWNLINT = ROOT / "node_modules" / ".bin" / "markdownlint-cli2"
NESTED = (
    "tools/canvas-viewer/node_modules/_fmt_probe/README.md",
    "node_modules/_fmt_probe/README.md",
)


def _remove_probe(target: Path) -> None:
    target.unlink(missing_ok=True)
    probe = target.parent
    if probe.name != "_fmt_probe":
        return
    probe.rmdir()
    node_modules = probe.parent
    if node_modules.name == "node_modules" and not any(node_modules.iterdir()):
        node_modules.rmdir()


def _lint(relative: str, *, fix: bool) -> subprocess.CompletedProcess[str]:
    command = [str(MARKDOWNLINT)]
    if fix:
        command.append("--fix")
    command.append(relative)
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_markdownlint_does_not_rewrite_node_modules_markdown():
    assert MARKDOWNLINT.is_file(), MARKDOWNLINT
    targets = []
    try:
        for relative in NESTED:
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(UGLY)
            targets.append(target)
            result = _lint(relative, fix=True)
            assert target.read_text() == UGLY
            assert result.returncode == 0, result.stdout + result.stderr
            assert "Linting: 0 files" in result.stdout
    finally:
        for target in targets:
            _remove_probe(target)


def test_the_same_markdown_is_reported_outside_node_modules():
    """The fixture above is a file markdownlint reports when it is in scope."""
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    target = logs / "markdownlint-probe.md"
    target.write_text(UGLY)
    try:
        result = _lint(str(target.relative_to(ROOT)), fix=False)
        assert target.read_text() == UGLY
        assert result.returncode == 1
        assert "MD004/ul-style" in result.stdout + result.stderr
    finally:
        target.unlink(missing_ok=True)
