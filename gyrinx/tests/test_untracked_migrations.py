"""pre-commit hides untracked migration files during the missing-migration check.

pre-commit copies the index over tracked files and leaves untracked files in
place. A migration for those cleared edits stays in the graph, and
``makemigrations --check`` asks for a migration that undoes it. The hook
passes ``--pre-commit``, which hides those modules and puts them back,
including when the check fails. A manual run still sees them.
"""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "lib" / "untracked_migrations.sh"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "core.hooksPath", "/dev/null")
    (repo / "README").write_text("x\n")
    migrations = repo / "app" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "__init__.py").write_text("")
    (migrations / "0001_initial.py").write_text("# tracked\n")
    _git(repo, "add", "README", "app")
    _git(repo, "commit", "-m", "init")
    (migrations / "0002_other.py").write_text("# untracked\n")
    fresh = repo / "fresh" / "migrations"
    fresh.mkdir(parents=True)
    (fresh / "__init__.py").write_text("")
    (fresh / "0001_initial.py").write_text("# new app\n")
    (repo / "notes.txt").write_text("leave me\n")
    nested = migrations / "__pycache__"
    nested.mkdir()
    (nested / "0001_initial.cpython-314.py").write_text("# not a module\n")
    (repo / "app" / "migrations.py").write_text("# not inside the package\n")
    return repo


def _bash(repo, body, env=None):
    script = f'set -euo pipefail\nsource "$LIB"\ncd "$REPO"\n{body}'
    run_env = os.environ.copy()
    run_env["LIB"] = str(LIB)
    run_env["REPO"] = str(repo)
    run_env.pop("PRE_COMMIT", None)
    if env:
        run_env.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        env=run_env,
        check=False,
    )


def test_pre_commit_hides_an_untracked_migration_and_restores_it(tmp_path):
    repo = _repo(tmp_path)
    result = _bash(
        repo,
        """
        hide_untracked_migrations --pre-commit
        test ! -e app/migrations/0002_other.py
        test ! -e fresh/migrations/__init__.py
        test ! -e fresh/migrations/0001_initial.py
        test -e app/migrations/__init__.py
        test -e app/migrations/0001_initial.py
        test -e notes.txt
        test -e app/migrations/__pycache__/0001_initial.cpython-314.py
        test -e app/migrations.py
        restore_untracked_migrations
        test -e app/migrations/0002_other.py
        test -e fresh/migrations/__init__.py
        test -e fresh/migrations/0001_initial.py
        """,
    )
    assert result.returncode == 0, result.stderr


def test_an_untracked_migration_link_is_restored(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app" / "migrations" / "0003_linked.py").symlink_to("0001_initial.py")
    result = _bash(
        repo,
        """
        hide_untracked_migrations --pre-commit
        test ! -e app/migrations/0003_linked.py
        test ! -L app/migrations/0003_linked.py
        restore_untracked_migrations
        test -L app/migrations/0003_linked.py
        """,
    )
    assert result.returncode == 0, result.stderr
    assert (repo / "app" / "migrations" / "0003_linked.py").readlink() == Path(
        "0001_initial.py"
    )


def test_a_migration_recreated_during_the_check_is_not_overwritten(tmp_path):
    repo = _repo(tmp_path)
    result = _bash(
        repo,
        """
        hide_untracked_migrations --pre-commit
        echo "# newer" > app/migrations/0002_other.py
        parked="$_UNTRACKED_MIGRATIONS_DIR"
        if restore_untracked_migrations; then exit 3; fi
        test -e "$parked/app/migrations/0002_other.py"
        test -e fresh/migrations/0001_initial.py
        """,
    )
    assert result.returncode == 0, result.stderr
    assert "not put back" in result.stderr
    assert (repo / "app" / "migrations" / "0002_other.py").read_text() == "# newer\n"


def test_a_path_recorded_but_not_yet_moved_is_left_in_place(tmp_path):
    """An interrupt between recording a path and moving it leaves the file."""
    repo = _repo(tmp_path)
    result = _bash(
        repo,
        """
        hide_untracked_migrations --pre-commit
        mkdir -p late/migrations
        echo "# late" > late/migrations/0001_initial.py
        _UNTRACKED_MIGRATIONS+=("late/migrations/0001_initial.py")
        parked="$_UNTRACKED_MIGRATIONS_DIR"
        restore_untracked_migrations
        test ! -e "$parked"
        test -e app/migrations/0002_other.py
        """,
    )
    assert result.returncode == 0, result.stderr
    assert (repo / "late" / "migrations" / "0001_initial.py").read_text() == (
        "# late\n"
    )


def test_hidden_migrations_wait_under_the_git_directory(tmp_path):
    """A check killed before it restores leaves them with the repository."""
    repo = _repo(tmp_path)
    result = _bash(
        repo,
        """
        hide_untracked_migrations --pre-commit
        echo "$_UNTRACKED_MIGRATIONS_DIR"
        """,
    )
    assert result.returncode == 0, result.stderr
    parked = Path(result.stdout.strip())
    assert parked.parent == (repo / ".git").resolve()
    assert (parked / "app" / "migrations" / "0002_other.py").is_file()


def test_a_failed_check_still_restores_the_migration(tmp_path):
    repo = _repo(tmp_path)
    result = _bash(
        repo,
        """
        _restore() {
          local status=$?
          restore_untracked_migrations
          exit "$status"
        }
        trap _restore EXIT
        hide_untracked_migrations --pre-commit
        test ! -e app/migrations/0002_other.py
        test ! -e fresh/migrations/0001_initial.py
        exit 9
        """,
    )
    assert result.returncode == 9, result.stderr
    assert (
        repo / "app" / "migrations" / "0002_other.py"
    ).read_text() == "# untracked\n"
    assert (
        repo / "fresh" / "migrations" / "0001_initial.py"
    ).read_text() == "# new app\n"
    assert (repo / "fresh" / "migrations" / "__init__.py").is_file()


def test_a_manual_run_leaves_untracked_migrations_visible(tmp_path):
    repo = _repo(tmp_path)
    result = _bash(
        repo,
        """
        hide_untracked_migrations
        test -e app/migrations/0002_other.py
        test -e fresh/migrations/0001_initial.py
        test -e app/migrations/__init__.py
        """,
    )
    assert result.returncode == 0, result.stderr


def test_pre_commit_env_hides_without_the_flag(tmp_path):
    repo = _repo(tmp_path)
    result = _bash(
        repo,
        """
        hide_untracked_migrations
        test ! -e app/migrations/0002_other.py
        restore_untracked_migrations
        test -e app/migrations/0002_other.py
        """,
        env={"PRE_COMMIT": "1"},
    )
    assert result.returncode == 0, result.stderr


def test_a_staged_migration_stays_visible(tmp_path):
    repo = _repo(tmp_path)
    staged = repo / "app" / "migrations" / "0003_staged.py"
    staged.write_text("# staged\n")
    _git(repo, "add", "app/migrations/0003_staged.py")
    result = _bash(
        repo,
        """
        hide_untracked_migrations --pre-commit
        test -e app/migrations/0003_staged.py
        test ! -e app/migrations/0002_other.py
        restore_untracked_migrations
        test -e app/migrations/0002_other.py
        test -e app/migrations/0003_staged.py
        """,
    )
    assert result.returncode == 0, result.stderr
    assert staged.read_text() == "# staged\n"


def test_the_hook_passes_pre_commit_to_the_migration_check():
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hooks = {
        hook["id"]: hook for repo in config["repos"] for hook in repo.get("hooks", [])
    }
    hook = hooks["check-migrations"]
    assert hook["entry"] == "./scripts/check_migrations.sh"
    assert hook["args"] == ["--pre-commit"]
    assert hook["pass_filenames"] is False
    script = (ROOT / "scripts" / "check_migrations.sh").read_text()
    assert "hide_untracked_migrations --pre-commit" in script
    assert "restore_untracked_migrations" in script
