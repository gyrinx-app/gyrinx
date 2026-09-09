"""Exercise the real shell entry points without touching local databases."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class CodexLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex lifecycle ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source tree"
        self.target = self.root / "new tree"
        self.bin = self.root / "tools" / "bin"
        self.bin.mkdir(parents=True)
        self.log = self.root / "commands.log"
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("CODEX_", "GIT_", "PG", "GYRINX_"))
        }
        self.env.update(
            PATH=f"{self.bin}:{os.environ['PATH']}",
            COMMAND_LOG=str(self.log),
            FAKE_TOOLS=str(self.bin.parent),
        )
        self.source.mkdir()
        self.git("init", "-q", cwd=self.source)
        (self.source / ".codex").mkdir()
        (self.source / "scripts" / "lib").mkdir(parents=True)
        for name in ("setup.sh", "cleanup.sh", "worktree.sh", "dev-url.sh"):
            shutil.copy2(REPO / ".codex" / name, self.source / ".codex" / name)
        shutil.copy2(
            REPO / "scripts" / "lib" / "worktree.sh",
            self.source / "scripts" / "lib" / "worktree.sh",
        )
        self.write_script(
            self.source / "scripts" / "dev.sh",
            'printf "dev|%s|%s\\n" "$PWD" "$*" >> "$COMMAND_LOG"\n'
            'exit "${DEV_STATUS:-0}"\n',
        )
        self.git("add", ".", cwd=self.source)
        self.git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "Fixture",
            cwd=self.source,
        )
        self.git("worktree", "add", "-q", "--detach", str(self.target), cwd=self.source)
        self.env.update(
            CODEX_SOURCE_TREE_PATH=str(self.source),
            CODEX_WORKTREE_PATH=str(self.target),
        )
        self.db = (
            "gyrinx_wt_"
            + hashlib.md5(str(self.target).encode(), usedforsecurity=False).hexdigest()[
                :8
            ]
        )
        self.write_script(self.bin / "brew", 'echo "$FAKE_TOOLS"\n')
        self.write_script(
            self.bin / "psql",
            'printf "psql|%s\\n" "$*" >> "$COMMAND_LOG"\n'
            'printf "%s\\n" "${DATABASES:-}"\nexit "${QUERY_STATUS:-0}"\n',
        )
        self.write_script(
            self.bin / "dropdb",
            'printf "dropdb|%s\\n" "$*" >> "$COMMAND_LOG"\nexit "${DROP_STATUS:-0}"\n',
        )
        self.write_script(self.bin / "uname", "echo Darwin\n")
        self.write_script(
            self.bin / "open", 'printf "open|%s\\n" "$*" >> "$COMMAND_LOG"\n'
        )

    def write_script(self, path, body):
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def git(self, *args, cwd):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def run_script(self, script, *args, cwd=None, **env):
        return subprocess.run(
            ["/bin/bash", str(self.source / ".codex" / script), *args],
            cwd=cwd or self.source,
            env=self.env | env,
            text=True,
            capture_output=True,
        )

    def commands(self):
        return self.log.read_text() if self.log.exists() else ""

    def test_setup_uses_target_from_unrelated_cwd_and_copies_source_env(self):
        (self.source / ".env").write_text("LOCAL_SETTING=source\n")
        result = self.run_script("setup.sh", cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / ".env").read_text(), "LOCAL_SETTING=source\n")
        self.assertEqual((self.target / ".env").stat().st_mode & 0o777, 0o600)
        self.assertIn(f"dev|{self.target}|--no-watch --setup-only", self.commands())
        self.assertNotIn("LOCAL_SETTING", result.stdout)

    def test_setup_preserves_existing_env_and_propagates_failure(self):
        (self.source / ".env").write_text("source\n")
        (self.target / ".env").write_text("target\n")
        result = self.run_script("setup.sh", DEV_STATUS="7")
        self.assertEqual(result.returncode, 7)
        self.assertEqual((self.target / ".env").read_text(), "target\n")

    def test_setup_uses_explicit_child_source(self):
        child = self.root / "another source"
        self.git("worktree", "add", "-q", "--detach", str(child), cwd=self.source)
        (self.source / ".env").write_text("main\n")
        (child / ".env").write_text("child\n")
        result = self.run_script("setup.sh", CODEX_SOURCE_TREE_PATH=str(child))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / ".env").read_text(), "child\n")

    def test_setup_rejects_shared_symlinks(self):
        for name in (".env", ".venv", "node_modules"):
            with self.subTest(name=name):
                link = self.target / name
                link.symlink_to(self.root / "missing")
                result = self.run_script("setup.sh")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("dev|", self.commands())
                link.unlink()

    def test_setup_falls_back_to_current_checkout(self):
        (self.source / ".env").write_text("main\n")
        result = self.run_script(
            "setup.sh",
            cwd=self.target,
            CODEX_SOURCE_TREE_PATH="",
            CODEX_WORKTREE_PATH="",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / ".env").read_text(), "main\n")

    def test_invalid_paths_fail_before_any_command(self):
        other = self.root / "unrelated repo"
        other.mkdir()
        self.git("init", "-q", cwd=other)
        for path in (self.root / "missing", self.target / "scripts", other):
            for script in ("setup.sh", "cleanup.sh"):
                with self.subTest(path=path, script=script):
                    result = self.run_script(script, CODEX_WORKTREE_PATH=str(path))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.commands(), "")
        result = self.run_script("setup.sh", CODEX_SOURCE_TREE_PATH=str(other))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.commands(), "")

    def test_cleanup_refuses_main_even_via_symlink(self):
        alias = self.root / "main alias"
        alias.symlink_to(self.source, target_is_directory=True)
        for path in (self.source, alias):
            result = self.run_script("cleanup.sh", CODEX_WORKTREE_PATH=str(path))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("main worktree", result.stderr)
            self.assertEqual(self.commands(), "")

    def test_cleanup_selects_exact_database_family_and_pins_socket(self):
        family = [
            self.db,
            f"test_{self.db}",
            f"test_{self.db}_gw0",
            f"test_{self.db}_gw12",
        ]
        result = self.run_script(
            "cleanup.sh",
            DATABASES="\n".join(family),
            GYRINX_DB_HOST="/private/tmp",
            PGHOST="remote.invalid",
            PGPORT="9999",
            CODEX_WORKTREE_PATH=f"{self.target}/",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands().splitlines()
        self.assertIn(f"^({self.db}|test_{self.db}(_gw[0-9]+)?)$", commands[0])
        self.assertEqual(len(commands), 5)
        for line, database in zip(commands[1:], family, strict=True):
            self.assertTrue(line.endswith(f" {database}"), line)
            self.assertIn("--host=/private/tmp --port=5432", line)
            self.assertNotIn("--force", line)
            self.assertNotIn("remote.invalid", line)

    def test_cleanup_dry_run_and_empty_database_list(self):
        result = self.run_script("cleanup.sh", "--dry-run", DATABASES=self.db)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Would drop database: {self.db}", result.stdout)
        self.assertNotIn("dropdb|", self.commands())
        result = self.run_script("cleanup.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No databases to remove", result.stdout)
        self.assertNotIn("dropdb|", self.commands())

    def test_cleanup_propagates_query_and_drop_failures(self):
        result = self.run_script("cleanup.sh", QUERY_STATUS="9")
        self.assertEqual(result.returncode, 9)
        self.assertNotIn("dropdb|", self.commands())
        result = self.run_script("cleanup.sh", DATABASES=self.db, DROP_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Stop this worktree's dev server", result.stderr)

    def test_cleanup_refuses_unexpected_names_and_remote_host(self):
        for database in ("gyrinx_main", "gyrinx_wt_deadbeef", f"test_{self.db}_other"):
            result = self.run_script("cleanup.sh", DATABASES=database)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("dropdb|", self.commands())
        result = self.run_script("cleanup.sh", GYRINX_DB_HOST="remote.invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("dropdb|", self.commands())

    def test_url_uses_current_worktree_ignoring_inherited_port_and_hook_path(self):
        result = self.run_script(
            "dev-url.sh", "--open", cwd=self.target, DJANGO_PORT="1"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        url = result.stdout.strip()
        self.assertRegex(url, r"^http://localhost:[89][0-9]{3}/$")
        self.assertIn(f"open|{url}", self.commands())
        result = self.run_script("dev-url.sh", cwd=self.source)
        self.assertEqual(result.stdout.strip(), "http://localhost:8000/")


if __name__ == "__main__":
    unittest.main()
