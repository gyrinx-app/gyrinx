#!/usr/bin/env bash
# Fetch all PR comments, reviews, and metadata via a single GraphQL query.
#
# Usage: fetch-pr-comments.sh [PR_NUMBER_OR_URL]
#
# If no argument is provided, detects the PR from the current branch.
# Outputs structured JSON with PR metadata, reviews, review threads
# (with resolved/outdated status), conversation comments, and changed files.

set -euo pipefail

PR_ARG="${1:-}"

# --- Determine repo owner and name (needed before PR detection) ---
resolve_repo() {
    # Try gh repo view first.
    local gh_err
    if gh_err=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>&1); then
        echo "$gh_err"
        return 0
    fi

    # Fall back to parsing the git remote URL (handles proxy-based remotes
    # like Claude Code on the web, SSH, HTTPS, and ssh:// formats).
    local remote_url
    remote_url=$(git remote get-url origin 2>/dev/null) || {
        echo "ERROR: Could not determine repository (gh repo view failed and no git remote found)." >&2
        echo "gh said: $gh_err" >&2
        return 1
    }

    local repo_full=""
    if [[ "$remote_url" =~ ^git@[^:]+:([^/]+/[^/]+?)(\.git)?$ ]]; then
        repo_full="${BASH_REMATCH[1]}"
    elif [[ "$remote_url" =~ ^https?://[^/]+/([^/]+/[^/]+?)(\.git)?$ ]]; then
        repo_full="${BASH_REMATCH[1]}"
    elif [[ "$remote_url" =~ ^ssh://[^/]+/([^/]+/[^/]+?)(\.git)?$ ]]; then
        repo_full="${BASH_REMATCH[1]}"
    else
        # Last resort: strip everything up to the last two path segments.
        repo_full=$(printf '%s\n' "$remote_url" | sed -E 's#.*/([^/]+/[^/]+?)(\.git)?$#\1#')
    fi

    if [ -z "$repo_full" ] || [[ "$repo_full" != */* ]] || [[ "$repo_full" == */*/* ]]; then
        echo "ERROR: Could not parse owner/repo from remote URL '$remote_url'." >&2
        return 1
    fi

    echo "$repo_full"
}

REPO_FULL=$(resolve_repo) || exit 1
OWNER="${REPO_FULL%%/*}"
REPO="${REPO_FULL##*/}"

# --- Determine PR number ---
if [ -z "$PR_ARG" ]; then
    # Detect from current branch, using the repo we already resolved.
    GH_ERR=$(mktemp)
    PR_NUM=$(gh pr view -R "$OWNER/$REPO" --json number -q '.number' 2>"$GH_ERR") || {
        echo "ERROR: No PR found for current branch." >&2
        cat "$GH_ERR" >&2
        rm -f "$GH_ERR"
        exit 1
    }
    rm -f "$GH_ERR"
elif [[ "$PR_ARG" =~ ^[0-9]+$ ]]; then
    PR_NUM="$PR_ARG"
elif [[ "$PR_ARG" =~ /pull/([0-9]+) ]]; then
    PR_NUM="${BASH_REMATCH[1]}"
else
    echo "ERROR: Invalid argument '$PR_ARG'. Expected a PR number or GitHub URL." >&2
    exit 1
fi

# --- Fetch everything in one GraphQL call ---
# The query uses fixed limits (100 threads, 50 reviews, 100 comments, 100 files).
# totalCount is included on each connection so consumers can detect truncation.
exec gh api graphql \
    -f owner="$OWNER" \
    -f repo="$REPO" \
    -F number="$PR_NUM" \
    --jq '.data.repository.pullRequest' \
    -f query='
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            title
            state
            url
            isDraft
            additions
            deletions
            changedFiles
            baseRefName
            headRefName
            body
            createdAt
            updatedAt
            reviewDecision
            mergeable
            author { login }
            labels(first: 20) {
                nodes { name }
            }
            reviewThreads(first: 100) {
                totalCount
                nodes {
                    isResolved
                    isOutdated
                    path
                    line
                    startLine
                    comments(first: 50) {
                        nodes {
                            author { login }
                            body
                            createdAt
                            url
                        }
                    }
                }
            }
            reviews(first: 50) {
                totalCount
                nodes {
                    author { login }
                    state
                    body
                    submittedAt
                    url
                }
            }
            comments(first: 100) {
                totalCount
                nodes {
                    author { login }
                    body
                    createdAt
                    url
                }
            }
            files(first: 100) {
                totalCount
                nodes {
                    path
                    additions
                    deletions
                }
            }
        }
    }
}
'
