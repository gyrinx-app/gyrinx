---
name: Edit GitHub Discussion
description: |
  This skill should be used when the user asks to "edit a GitHub discussion", "update discussion content",
  "iterate on a discussion", "modify discussion body", or wants to make changes to an existing GitHub
  Discussion. Provides workflow for fetching, editing, and updating GitHub Discussions via GraphQL API.
---

# Edit GitHub Discussion

Guide for editing GitHub Discussion content using the GitHub CLI's GraphQL API.

## When to Use

This skill applies when:
- User wants to edit the body/content of a GitHub Discussion
- User mentions "update discussion" or "iterate on discussion"
- User provides a discussion URL like `github.com/owner/repo/discussions/123`
- User wants to incorporate feedback into a design document hosted as a Discussion

## Workflow Overview

1. **Fetch** discussion content via GraphQL query
2. **Save** to temporary file for editing
3. **Edit** the markdown content
4. **Get** discussion node ID
5. **Update** via GraphQL mutation

## Step 1: Fetch Discussion Content

Extract owner, repo, and discussion number from the URL, then fetch:

```bash
gh api graphql -f query='
  query {
    repository(owner: "OWNER", name: "REPO") {
      discussion(number: NUMBER) {
        id
        title
        body
      }
    }
  }
' --jq '.data.repository.discussion.body' > /tmp/discussion-NUMBER.md
```

The `--jq` flag extracts just the body content. Save the discussion ID for the update step.

## Step 2: Edit the Content

Read the saved file with the Read tool, then use Edit tool to make changes:

```bash
# File is at /tmp/discussion-NUMBER.md
```

Make targeted edits using the Edit tool. For substantial rewrites, use Write tool to replace the entire content.

## Step 3: Get Discussion Node ID

The node ID is needed for the update mutation. Fetch it if not already captured:

```bash
gh api graphql -f query='
  query {
    repository(owner: "OWNER", name: "REPO") {
      discussion(number: NUMBER) {
        id
      }
    }
  }
' --jq '.data.repository.discussion.id'
```

Returns an ID like `D_kwDOM_QUS84Ajl4m`.

## Step 4: Update the Discussion

Use the GraphQL mutation with proper variable passing:

```bash
BODY=$(cat /tmp/discussion-NUMBER.md)
gh api graphql \
  -f discussionId="D_kwDO..." \
  -f body="$BODY" \
  -f query='
mutation($discussionId: ID!, $body: String!) {
  updateDiscussion(input: {
    discussionId: $discussionId,
    body: $body
  }) {
    discussion {
      url
    }
  }
}'
```

**Key technique:** Use `-f` flags to pass variables, not inline substitution. The body variable must be passed as a shell variable to handle special characters correctly.

## Combined One-Liner (Fetch + Save)

```bash
gh api graphql -f query='
  query {
    repository(owner: "OWNER", name: "REPO") {
      discussion(number: NUMBER) {
        title
        body
      }
    }
  }
' --jq '.data.repository.discussion.body' > /tmp/discussion-NUMBER.md
```

## Common Issues

### Variable Parsing Errors

If the GraphQL mutation fails with "Expected VAR_SIGN" errors, ensure:
- Variables are passed via `-f varName="value"` flags
- The query uses `$varName` syntax in the mutation
- Special characters in body content are properly escaped (using shell variable)

### Permission Errors

The user must have write access to the discussion. Check with:

```bash
gh api repos/OWNER/REPO --jq '.permissions.push'
```

### Large Content

For very large discussions, the shell variable approach works but consider:
- Breaking content into sections if editing is complex
- Using a local file as the source of truth

## Example Session

```bash
# 1. Fetch and save
gh api graphql -f query='query { repository(owner: "gyrinx-app", name: "gyrinx") { discussion(number: 1299) { id body } } }' --jq '.data.repository.discussion.body' > /tmp/discussion-1299.md

# 2. Edit with Claude's Edit tool
# [Make changes to /tmp/discussion-1299.md]

# 3. Update
BODY=$(cat /tmp/discussion-1299.md)
gh api graphql -f discussionId="D_kwDOM_QUS84Ajl4m" -f body="$BODY" -f query='mutation($discussionId: ID!, $body: String!) { updateDiscussion(input: { discussionId: $discussionId, body: $body }) { discussion { url } } }'
```

## Related GitHub CLI Commands

| Command | Purpose |
|---------|---------|
| `gh api graphql` | Execute GraphQL queries/mutations |
| `gh discussion list` | List discussions (REST, limited) |
| `gh discussion view` | View discussion (REST, limited) |

Note: REST API support for discussions is limited. GraphQL is preferred for full read/write access.

## Tips

- Always fetch fresh content before editing to avoid overwriting others' changes
- Keep a backup of the original content before major edits
- Use the discussion URL in responses so user can verify changes
- For design documents, consider asking user to confirm changes before updating
