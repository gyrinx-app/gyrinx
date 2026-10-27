"""Vite resolves React from this checkout, not a parent checkout.

A nested worktree otherwise walks into the parent node_modules. npm run js:dev
then parses that copy of react-dom-client.development.js, including a file
another npm ci has left half-written.
"""

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "n26/frontend/tooling/checkout_module.mjs"


def _package(directory: Path, name: str) -> None:
    package = directory / "node_modules" / name
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": name, "main": "index.js"}) + "\n"
    )
    (package / "index.js").write_text("module.exports = {}\n")


def _resolve(checkout: Path, specifier: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import { resolveCheckoutModule } from "
            + json.dumps(MODULE.as_uri())
            + ";\n"
            "try {\n"
            "  const resolved = resolveCheckoutModule("
            "process.env.CHECKOUT, process.env.SPECIFIER);\n"
            "  process.stdout.write(resolved === null ? 'null\\n' : resolved + '\\n');\n"
            "} catch (error) {\n"
            "  process.stderr.write(String(error.message) + '\\n');\n"
            "  process.exit(2);\n"
            "}\n",
        ],
        text=True,
        capture_output=True,
        env=os.environ | {"CHECKOUT": str(checkout), "SPECIFIER": specifier},
    )


def test_react_dom_in_a_parent_checkout_is_refused(tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir()
    (parent / "package.json").write_text("{}\n")
    _package(parent, "react-dom")
    checkout = parent / "worktree"
    checkout.mkdir()
    (checkout / "package.json").write_text("{}\n")

    result = _resolve(checkout, "react-dom")

    assert result.returncode == 2, result.stderr
    assert "outside this checkout" in result.stderr
    assert "Do not edit the other checkout's node_modules." in result.stderr
    assert str(parent / "node_modules/react-dom/index.js") in result.stderr


def test_react_dom_in_this_checkout_resolves_locally(tmp_path):
    checkout = tmp_path / "worktree"
    checkout.mkdir()
    (checkout / "package.json").write_text("{}\n")
    _package(checkout, "react-dom")

    result = _resolve(checkout, "react-dom")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == os.path.realpath(
        checkout / "node_modules/react-dom/index.js"
    )


def test_other_specifiers_are_left_to_vite(tmp_path):
    checkout = tmp_path / "worktree"
    checkout.mkdir()
    (checkout / "package.json").write_text("{}\n")

    result = _resolve(checkout, "vite")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "null"


def test_vite_config_uses_the_checkout_resolver():
    source = (REPO_ROOT / "vite.config.mts").read_text()

    assert "checkout-react" in source
    assert "resolveCheckoutModule" in source
