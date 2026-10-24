"""Generated trees stay out of the editable install.

Hazel hit this on #lessons (11 Oct): after a rebase removed the gitignored
Vite directory, ``uv sync`` still named ``n26/core/static/n26/react/assets``
and failed before the frontend rebuild. The same discovery records
``node_modules`` — more than a thousand packages — on the import path.
"""

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]

EXCLUDED = (
    "logs*",
    "node_modules*",
    "staticfiles*",
    "n26.core.static.n26.react*",
    "n26.frontend.generated*",
)

ABSENT = (
    "logs",
    "node_modules",
    "staticfiles",
    "n26.core.static.n26.react",
    "n26.core.static.n26.react.assets",
    "n26.frontend.generated",
)


def _discovered_packages():
    from setuptools.config.expand import find_packages

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    find = pyproject["tool"]["setuptools"]["packages"]["find"]
    exclude = find["exclude"]
    assert tuple(exclude) == EXCLUDED
    return find_packages(root_dir=ROOT, namespaces=True, exclude=exclude)


def test_generated_trees_are_not_python_packages():
    assets = ROOT / "n26/core/static/n26/react/assets"
    created = not assets.is_dir()
    if created:
        assets.mkdir(parents=True)
    try:
        packages = set(_discovered_packages())
    finally:
        if created:
            assets.rmdir()

    assert "gyrinx" in packages
    assert "n26.core" in packages
    for name in ABSENT:
        assert name not in packages
        assert not any(package.startswith(name + ".") for package in packages)
