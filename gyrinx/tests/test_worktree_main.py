"""A large worktree listing must not abort dev.sh under pipefail."""

import os
import subprocess
from pathlib import Path


def test_main_worktree_consumes_a_long_listing(tmp_path):
    listing = tmp_path / "listing"
    listing.write_text(
        "worktree /main tree\nHEAD abc\n\n"
        + "".join(f"worktree /child/{i}\nHEAD def\n\n" for i in range(8000))
    )
    git = tmp_path / "git"
    git.write_text('#!/bin/sh\ncat "$GYRINX_TEST_WORKTREE_LIST"\n')
    git.chmod(0o755)
    helper = Path(__file__).resolve().parents[2] / "scripts/lib/worktree.sh"
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -euo pipefail; source "$1"; _main_worktree; echo continued',
            "test",
            str(helper),
        ],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "GYRINX_TEST_WORKTREE_LIST": str(listing),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "/main tree\ncontinued\n"
