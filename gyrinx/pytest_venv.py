"""Refuse pytest when the interpreter is another checkout's ``.venv``.

A sibling worktree's ``pytest`` on ``PATH`` imports that checkout's code
while the working directory is this one, which produces phantom failures.
"""

from pathlib import Path


def foreign_venv_message(rootpath, executable):
    """Return an error if pytest is running from a sibling worktree's ``.venv``.

    System Pythons and this worktree's own ``.venv`` are fine. No local
    ``.venv`` means there is nothing to mismatch against — child checkouts
    that share the parent environment are left alone.
    """
    root = Path(rootpath).resolve()
    # A venv's python is a symlink to a shared interpreter, so resolving it
    # would leave every .venv. Resolve only the directory holding it.
    executable = Path(executable)
    exe = executable.parent.resolve() / executable.name
    expected = root / ".venv"
    if not expected.exists():
        return None
    expected = expected.resolve()
    try:
        exe.relative_to(expected)
        return None
    except ValueError:
        pass
    if ".venv" not in exe.parts:
        return None
    python = expected / "bin" / "python"
    return (
        f"pytest is running from {exe}, not this worktree's {python}. "
        "A sibling checkout's interpreter imports that checkout's code "
        "and produces phantom failures. From this worktree run: "
        f"{python} -m pytest"
    )
