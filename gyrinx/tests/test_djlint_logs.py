"""djlint skips HTML saved under logs/.

``scripts/fmt.sh`` runs ``djlint --reformat .``. ``logs/`` is gitignored, but
djlint does not read ``.gitignore``. Without the exclusion, a curl capture
saved as ``logs/404-response.html`` is rewritten and then fails the lint
check.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]
UGLY = b"<div><p>captured page</p></div>\n"


def test_djlint_does_not_reformat_html_under_logs():
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    target = logs / "djlint-capture-fixture.html"
    target.write_bytes(UGLY)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "djlint",
                "--profile=django",
                "--reformat",
                str(target.relative_to(ROOT)),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert target.read_bytes() == UGLY
        assert result.returncode == 0
        assert "No files to check" in result.stderr
    finally:
        target.unlink(missing_ok=True)


def test_the_same_capture_is_reformatted_outside_logs(tmp_path):
    """The fixture above is a file djlint rewrites when it is in scope."""
    target = tmp_path / "capture.html"
    target.write_bytes(UGLY)
    result = subprocess.run(
        [sys.executable, "-m", "djlint", "--profile=django", "--reformat", str(target)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert target.read_bytes() != UGLY
    assert b"<p>captured page</p>" in target.read_bytes()
    assert result.returncode == 1


@pytest.mark.parametrize("hook_id", ["djlint-reformat-django", "djlint-django"])
def test_each_pre_commit_djlint_hook_skips_logs(hook_id):
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hooks = {
        hook["id"]: hook for repo in config["repos"] for hook in repo.get("hooks", [])
    }
    exclude = hooks[hook_id].get("exclude", "")
    assert re.search(exclude, "logs/404-response.html"), exclude
    assert not re.search(exclude, "n26/core/templates/n26/page.html"), exclude
