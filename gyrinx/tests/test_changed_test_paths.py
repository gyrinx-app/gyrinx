"""The rule that picks which tests a pull request's changes pull into the
required CI job. See scripts/changed_test_paths.py."""

import pytest

from scripts.changed_test_paths import (
    find_conftests,
    is_test_file,
    select_changed_test_paths,
)

pytestmark = pytest.mark.core

CONFTESTS = {
    "conftest.py": "from gyrinx.tasks.testing import task_queue\n",
    "n26/core/conftest.py": "from n26.tests.fixtures import *  # noqa\n",
    "n26/tests/conftest.py": "from n26.tests.fixtures import *  # noqa\n",
    "n26/library/conftest.py": "from n26.tests.fixtures import *  # noqa\n",
    "n23/core/tests/conftest.py": "import pytest\n",
}


@pytest.mark.parametrize(
    "path, expected",
    [
        ("n23/core/tests/test_clone.py", True),
        ("n26/core/test_navigation.py", True),
        ("gyrinx/pages/tests.py", True),
        ("n26/library/authoring_tests.py", True),
        ("n26/tests/fixtures.py", False),
        ("n26/tests/sandbox/actions.py", False),
        ("n23/core/tests/conftest.py", False),
        ("n26/core/testing.py", False),
    ],
)
def test_is_test_file_matches_the_pyproject_globs(path, expected):
    assert is_test_file(path) is expected


def test_changed_test_files_are_listed_as_themselves():
    changed = ["n23/core/tests/test_clone.py", "n26/core/test_navigation.py"]
    assert select_changed_test_paths(changed, CONFTESTS, exists=lambda p: True) == (
        sorted(changed)
    )


def test_a_deleted_test_file_has_nothing_to_run():
    changed = ["n23/core/tests/test_clone.py", "n23/core/tests/test_gone.py"]
    assert select_changed_test_paths(
        changed, CONFTESTS, exists=lambda p: p != "n23/core/tests/test_gone.py"
    ) == ["n23/core/tests/test_clone.py"]


def test_a_deleted_conftest_still_lists_its_directory():
    changed = ["n23/core/tests/conftest.py"]
    assert select_changed_test_paths(changed, CONFTESTS, exists=lambda p: False) == [
        "n23/core/tests/"
    ]


def test_source_and_non_python_changes_add_nothing():
    changed = [
        "n26/core/views.py",
        "n23/core/models/list/fighter.py",
        "gyrinx/templates/cotton/btn.html",
        ".github/workflows/test.yaml",
    ]
    assert select_changed_test_paths(changed, CONFTESTS) == []


def test_a_changed_conftest_lists_its_directory():
    changed = ["n23/core/tests/conftest.py"]
    assert select_changed_test_paths(changed, CONFTESTS) == ["n23/core/tests/"]


def test_a_changed_fixtures_module_lists_every_tree_whose_conftest_imports_it():
    changed = ["n26/tests/fixtures.py"]
    assert select_changed_test_paths(changed, CONFTESTS) == [
        "n26/core/",
        "n26/library/",
        "n26/tests/",
    ]


def test_a_changed_root_conftest_means_the_whole_suite():
    changed = ["conftest.py", "n23/core/tests/test_clone.py"]
    assert select_changed_test_paths(changed, CONFTESTS) == ["."]


def test_a_module_no_conftest_imports_adds_nothing():
    changed = ["n26/tests/sandbox/actions.py"]
    assert select_changed_test_paths(changed, CONFTESTS) == []


def test_the_real_conftests_include_the_n26_fixture_registrations():
    conftests = find_conftests()
    assert "conftest.py" in conftests
    assert "n26/tests/conftest.py" in conftests
    assert select_changed_test_paths(["n26/tests/fixtures.py"], conftests) == [
        "n26/core/",
        "n26/library/",
        "n26/tests/",
    ]
