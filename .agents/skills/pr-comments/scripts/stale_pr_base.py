#!/usr/bin/env python3
"""Report a stale pull request base.sha.

GitHub can dismiss a fresh approval with "The merge-base changed after
approval" while the head commit is unchanged. The pull request's stored
base.sha is then an older commit, and compare already shows the base
branch tip as the merge base. Refreshing the same base ref updates that
stored sha. Passing a different branch name retargets the pull request.

Seen on #2903 (chub-5c54, 25 Oct): REST base.sha stayed on the old base
after the branch already contained the current base tip. PATCH with
``base`` set to that same ref refreshed it, and the next approval stayed.

Exit 0 when base.sha is not that stale case.
Exit 2 when it is, and print the PATCH command.
``--apply`` sends that PATCH. It does not restore a dismissed approval.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.parse

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BASE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


def is_stale_recorded_base(*, base_sha: str, base_tip: str, merge_base: str) -> bool:
    """True when the pull request already contains the base tip.

    ``base_sha`` is the sha GitHub stored on the pull request. ``base_tip``
    is the current tip of that base branch. ``merge_base`` is the merge base
    of that tip and the pull request head. A pull request that merely lags
    the base branch has an older merge base, and a dismissed review can be
    real, so that case is not stale.
    """

    if not base_sha or not base_tip or not merge_base:
        return False
    if base_sha == base_tip:
        return False
    return merge_base == base_tip


def refresh_command(repo: str, number: int, base_ref: str) -> str:
    _require_repo(repo)
    _require_number(number)
    _require_base_ref(base_ref)
    return f"gh api --method PATCH repos/{repo}/pulls/{number} -f base={base_ref}"


def describe(
    *,
    base_sha: str,
    base_tip: str,
    merge_base: str,
    repo: str,
    number: int,
    base_ref: str,
) -> tuple[int, str]:
    if is_stale_recorded_base(
        base_sha=base_sha, base_tip=base_tip, merge_base=merge_base
    ):
        command = refresh_command(repo, number, base_ref)
        return (
            2,
            "The stored base.sha is behind the base branch tip, and the "
            f"merge base is already that tip.\n{command}",
        )
    if base_sha and base_sha == base_tip:
        return 0, "base.sha is the base branch tip."
    if base_sha and merge_base and merge_base != base_tip:
        return (
            0,
            "The pull request does not contain the base branch tip. "
            "A dismissed review can be a real merge-base change.",
        )
    return 0, "base.sha is not the stale case."


def base_ref_api_path(repo: str, base_ref: str) -> str:
    _require_repo(repo)
    _require_base_ref(base_ref)
    quoted = urllib.parse.quote(base_ref, safe="")
    return f"repos/{repo}/git/ref/heads/{quoted}"


def compare_api_path(repo: str, base_tip: str, head_sha: str) -> str:
    _require_repo(repo)
    _require_sha(base_tip, "base tip")
    _require_sha(head_sha, "head")
    return f"repos/{repo}/compare/{base_tip}...{head_sha}"


def _require_repo(repo: str) -> None:
    if not _REPO.fullmatch(repo):
        raise ValueError("repo must be owner/name")


def _require_number(number: int) -> None:
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("pull request number must be a positive integer")


def _require_base_ref(base_ref: str) -> None:
    if (
        not _BASE_REF.fullmatch(base_ref)
        or ".." in base_ref
        or base_ref.endswith("/")
        or "//" in base_ref
    ):
        raise ValueError("base ref must be the pull request's current branch name")


def _require_sha(value: str, label: str) -> None:
    if not _SHA.fullmatch(value):
        raise ValueError(f"{label} must be a commit sha")


def _gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(detail or "gh failed")
    return result.stdout.strip()


def _sha_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith('"'):
        text = json.loads(text)
    if not isinstance(text, str):
        raise SystemExit("expected a commit sha")
    return text


def _load_pull(repo: str, number: int) -> dict[str, str]:
    raw = _gh(
        "api",
        f"repos/{repo}/pulls/{number}",
        "--jq",
        "{base_sha:.base.sha,base_ref:.base.ref,head_sha:.head.sha}",
    )
    payload = json.loads(raw)
    return {
        "base_sha": str(payload.get("base_sha") or ""),
        "base_ref": str(payload.get("base_ref") or ""),
        "head_sha": str(payload.get("head_sha") or ""),
    }


def _load_base_tip(repo: str, base_ref: str) -> str:
    return _sha_text(
        _gh("api", base_ref_api_path(repo, base_ref), "--jq", ".object.sha")
    )


def _load_merge_base(repo: str, base_tip: str, head_sha: str) -> str:
    return _sha_text(
        _gh(
            "api",
            compare_api_path(repo, base_tip, head_sha),
            "--jq",
            ".merge_base_commit.sha",
        )
    )


def _current_repo() -> str:
    return _gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")


def _current_pr_number() -> int:
    raw = _gh("pr", "view", "--json", "number", "-q", ".number")
    try:
        number = int(raw)
    except ValueError as exc:
        raise SystemExit(f"Could not read a pull request number from {raw!r}.") from exc
    _require_number(number)
    return number


def _apply_refresh(repo: str, number: int, base_ref: str) -> None:
    _gh(
        "api",
        "--method",
        "PATCH",
        f"repos/{repo}/pulls/{number}",
        "-f",
        f"base={base_ref}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("number", nargs="?", type=int)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="send the PATCH when base.sha is the stale case",
    )
    args = parser.parse_args(argv)
    try:
        repo = _current_repo()
        _require_repo(repo)
        number = args.number if args.number is not None else _current_pr_number()
        _require_number(number)
        pull = _load_pull(repo, number)
        base_tip = _load_base_tip(repo, pull["base_ref"])
        merge_base = _load_merge_base(repo, base_tip, pull["head_sha"])
        code, message = describe(
            base_sha=pull["base_sha"],
            base_tip=base_tip,
            merge_base=merge_base,
            repo=repo,
            number=number,
            base_ref=pull["base_ref"],
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(message)
    if code == 2 and args.apply:
        _apply_refresh(repo, number, pull["base_ref"])
        print(
            "Refreshed base.sha. A dismissed approval stays dismissed. "
            "Request the review again after this."
        )
        return 0
    return code


if __name__ == "__main__":
    raise SystemExit(main())
