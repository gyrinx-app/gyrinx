"""Plain pytest sessions must not touch the worktree's dev database.

oriole on #lessons (7 Oct 2026): a file with no ``django_db`` tests skips
test-database creation, and the root conftest's autouse
``content_stat_definitions`` then seeds ``DB_NAME``. A fresh empty worktree
fails every test with ``relation content_contentstat does not exist``, and
a migrated one gains ContentStat rows it did not ask for.

Not marked core: that suite is capped. CI still runs this file when a
pull request changes it, and the full suite runs it on every push.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import TestCase

from gyrinx.pytest_database import session_creates_test_database

ROOT = Path(__file__).resolve().parents[2]


class _Item:
    def __init__(self, marker=None, fixturenames=(), cls=None):
        self.marker = marker
        self.fixturenames = fixturenames
        self.cls = cls

    def get_closest_marker(self, name):
        if name == "django_db":
            return self.marker
        return None


def test_a_plain_item_does_not_create_a_database():
    assert session_creates_test_database([_Item()]) is False


def test_no_items_does_not_create_a_database():
    assert session_creates_test_database([]) is False


def test_a_django_db_marker_creates_a_database():
    assert (
        session_creates_test_database([_Item(marker=pytest.mark.django_db.mark)])
        is True
    )


def test_the_db_fixture_creates_a_database():
    assert session_creates_test_database([_Item(fixturenames=["db"])]) is True


def test_one_database_test_among_plain_tests_creates_a_database():
    items = [_Item(), _Item(fixturenames=["transactional_db"])]
    assert session_creates_test_database(items) is True


def test_a_django_test_case_creates_a_database():
    class Case(TestCase):
        pass

    assert session_creates_test_database([_Item(cls=Case)]) is True


@pytest.mark.django_db
def test_a_database_session_still_seeds_content_stats():
    from n23.content.models.statline import ContentStat, ContentStatlineType

    weapon_skill = ContentStat.objects.get(field_name="weapon_skill")
    assert weapon_skill.short_name == "WS"
    assert weapon_skill.is_inverted is True
    assert ContentStatlineType.objects.filter(name="Fighter").exists()


def test_plain_tests_do_not_open_the_dev_database():
    """A missing DB_NAME must not fail a file that never requests the database."""
    env = os.environ.copy()
    env["DB_NAME"] = "gyrinx_missing_nodb_repro"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "gyrinx/tests/test_pytest_venv.py::test_this_worktree_venv_is_silent",
            "-p",
            "no:gyrinx.pytest_worktree_lock",
            "-p",
            "no:xdist",
            "--override-ini=addopts=",
            "-q",
            "--tb=line",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gyrinx_missing_nodb_repro" not in proc.stdout + proc.stderr
