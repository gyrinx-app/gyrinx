"""The rule that decides whether a pull request needs the fresh-database
migrate. See scripts/fresh_database_needed.py."""

import pytest

from scripts.fresh_database_needed import (
    migration_imports,
    module_path,
    paths_needing_fresh_migrate,
)

pytestmark = pytest.mark.core

IMPORTS = {
    "n26/core/fields",
    "n23/content/house_icons",
    "n23/core/models/list",
    "n23/content/models",
}


@pytest.mark.parametrize(
    "path, expected",
    [
        ("n23/core/migrations/0207_x.py", True),
        ("n26/library/migrations/__init__.py", True),
        ("gyrinx/settings.py", True),
        ("gyrinx/settings_dev.py", True),
        ("gyrinx/settings/n26.py", True),
        ("n26/library/apps.py", True),
        ("uv.lock", True),
        ("n26/core/fields.py", True),
        ("n23/content/house_icons.py", True),
        ("n23/core/models/list/fighter.py", True),
        ("n23/core/models/__init__.py", True),
        ("n23/content/models/skill.py", True),
        ("n26/core/views.py", False),
        ("pyproject.toml", False),
        ("n26/core/fields_extra.py", False),
        ("gyrinx/templates/cotton/btn.html", False),
        ("docs/migrations/notes.md", False),
        (".github/workflows/test.yaml", False),
    ],
)
def test_which_changes_need_a_fresh_migrate(path, expected):
    assert (paths_needing_fresh_migrate([path], IMPORTS) == [path]) is expected


def test_matches_are_reported_in_order_and_others_dropped():
    changed = [
        "n26/core/views.py",
        "n23/core/migrations/0207_x.py",
        "README.md",
        "n26/core/fields.py",
    ]
    assert paths_needing_fresh_migrate(changed, IMPORTS) == [
        "n23/core/migrations/0207_x.py",
        "n26/core/fields.py",
    ]


def test_module_path_treats_a_package_init_as_the_package():
    assert module_path("n23/core/models/__init__.py") == "n23/core/models"
    assert module_path("n23/core/models/crew.py") == "n23/core/models/crew"


def test_the_real_migrations_import_project_modules():
    imports = migration_imports()
    assert "n26/core/fields" in imports
    assert "n23/content/house_icons" in imports
    assert paths_needing_fresh_migrate(["n26/core/fields.py"], imports) == [
        "n26/core/fields.py"
    ]
