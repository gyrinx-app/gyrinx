"""The main worktree path survives a long porcelain listing under pipefail."""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKTREE_SH = REPO_ROOT / "scripts" / "lib" / "worktree.sh"

LISTING_COUNT = 8000


def _fake_git(bin_dir: Path) -> None:
    git = bin_dir / "git"
    git.write_text(
        """#!/bin/bash
set -eu
args=$(printf '%s\\n' "$@")
case "$args" in
  $'worktree\\nlist\\n--porcelain') ;;
  *)
    printf 'unexpected git args\\n' >&2
    exit 1
    ;;
esac
printf 'worktree /main checkout/with spaces\\n'
i=0
while [ "$i" -lt "$LISTING_COUNT" ]; do
  printf 'worktree /wt/%s\\n' "$i"
  i=$((i + 1))
done
"""
    )
    git.chmod(0o755)


def test_long_worktree_list_does_not_sigpipe(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_git(bin_dir)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["LISTING_COUNT"] = str(LISTING_COUNT)
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -euo pipefail; source "$1"; _main_worktree; echo SURVIVED',
            "test",
            str(WORKTREE_SH),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "/main checkout/with spaces",
        "SURVIVED",
    ]
    assert "Broken pipe" not in result.stderr


def test_main_worktree_reads_a_directory_argument(tmp_path):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -euo pipefail; source "$1"; _main_worktree "$2"',
            "test",
            str(WORKTREE_SH),
            str(repo),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(repo.resolve())


def test_main_worktree_matches_this_checkout():
    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    first = listing.stdout.splitlines()[0]
    assert first.startswith("worktree ")
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -euo pipefail; source "$1"; _main_worktree',
            "test",
            str(WORKTREE_SH),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == first.removeprefix("worktree ")
    from_scripts = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -euo pipefail; source "$1"; _main_worktree "$2"',
            "test",
            str(WORKTREE_SH),
            str(REPO_ROOT / "scripts"),
        ],
        text=True,
        capture_output=True,
    )
    assert from_scripts.returncode == 0, from_scripts.stderr
    assert from_scripts.stdout.strip() == first.removeprefix("worktree ")


def test_failed_git_worktree_list_returns_nonzero(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text("#!/bin/bash\nexit 1\n")
    git.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -euo pipefail; source "$1"; _main_worktree; echo SURVIVED',
            "test",
            str(WORKTREE_SH),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode != 0
    assert "SURVIVED" not in result.stdout
