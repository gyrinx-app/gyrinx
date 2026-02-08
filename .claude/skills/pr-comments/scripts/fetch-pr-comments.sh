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

# --- Determine PR number ---
if [ -z "$PR_ARG" ]; then
    # Try to detect from current branch. Use -R if we can determine the repo,
    # otherwise fall back to plain gh pr view.
    PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null) || \
    PR_NUM=$(gh pr view -R gyrinx-app/gyrinx --json number -q '.number' 2>/dev/null) || {
        echo "ERROR: No PR found for current branch. Provide a PR number or URL." >&2
        exit 1
    }
elif [[ "$PR_ARG" =~ ^[0-9]+$ ]]; then
    PR_NUM="$PR_ARG"
elif [[ "$PR_ARG" =~ /pull/([0-9]+) ]]; then
    PR_NUM="${BASH_REMATCH[1]}"
else
    echo "ERROR: Invalid argument '$PR_ARG'. Expected a PR number or GitHub URL." >&2
    exit 1
fi

# --- Determine repo owner and name ---
# Try gh repo view first; fall back to parsing the git remote URL (handles
# proxy-based remotes like Claude Code on the web).
REPO_FULL=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null) || \
    REPO_FULL=$(git remote get-url origin 2>/dev/null | sed -E 's#.*/([^/]+/[^/]+?)(\.git)?$#\1#') || {
        echo "ERROR: Could not determine repository owner/name." >&2
        exit 1
    }
OWNER="${REPO_FULL%%/*}"
REPO="${REPO_FULL##*/}"

# --- Fetch everything in one GraphQL call ---
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
