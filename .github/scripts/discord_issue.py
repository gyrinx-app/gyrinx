"""
Create a GitHub issue from a Discord message.

This script is run by the discord-issue GitHub Action. It:
1. Fetches the target message and surrounding context from Discord
2. Calls Claude to summarise into a structured GitHub issue
3. Creates the issue via GitHub API
4. Updates the deferred Discord message with the issue link

Environment variables are set by the GitHub Action workflow.
"""

import json
import os
import subprocess
import sys

import anthropic
import requests

DISCORD_API = "https://discord.com/api/v10"


def get_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"Error: {name} not set", file=sys.stderr)
        sys.exit(1)
    return value


def discord_get(path: str, token: str) -> dict | list | None:
    """Make an authenticated GET request to the Discord API."""
    response = requests.get(
        f"{DISCORD_API}{path}",
        headers={"Authorization": f"Bot {token}"},
        timeout=30,
    )
    if response.status_code == 200:
        return response.json()
    print(f"Discord API error: {response.status_code} {response.text}", file=sys.stderr)
    return None


def fetch_context(channel_id: str, message_id: str, token: str) -> dict:
    """
    Fetch message context from Discord.

    Returns a dict with:
    - target_message: The message that was right-clicked
    - reply_chain: Messages in the reply chain (walking up via message_reference)
    - surrounding: Messages around the target in the channel
    """
    context = {
        "target_message": None,
        "reply_chain": [],
        "surrounding": [],
    }

    # Fetch the target message
    target = discord_get(f"/channels/{channel_id}/messages/{message_id}", token)
    if not target:
        return context
    context["target_message"] = target

    # Walk reply chain upward
    current = target
    for _ in range(10):  # Max 10 levels deep
        ref = current.get("message_reference")
        if not ref:
            break
        parent_id = ref.get("message_id")
        if not parent_id:
            break
        parent = discord_get(f"/channels/{channel_id}/messages/{parent_id}", token)
        if not parent:
            break
        context["reply_chain"].append(parent)
        current = parent

    # Fetch surrounding messages
    surrounding = discord_get(
        f"/channels/{channel_id}/messages?around={message_id}&limit=25", token
    )
    if surrounding:
        # Filter out the target message and reply chain messages
        seen_ids = {message_id} | {m["id"] for m in context["reply_chain"]}
        context["surrounding"] = [m for m in surrounding if m["id"] not in seen_ids]

    return context


def format_message(msg: dict) -> str:
    """Format a Discord message for the LLM prompt."""
    author = msg.get("author", {}).get("username", "unknown")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")

    # Include attachment info
    attachments = msg.get("attachments", [])
    attachment_text = ""
    if attachments:
        names = [a.get("filename", "file") for a in attachments]
        attachment_text = f" [attachments: {', '.join(names)}]"

    # Include embed info
    embeds = msg.get("embeds", [])
    embed_text = ""
    if embeds:
        embed_parts = []
        for e in embeds:
            if e.get("title"):
                embed_parts.append(f"embed: {e['title']}")
            if e.get("description"):
                embed_parts.append(e["description"][:200])
        if embed_parts:
            embed_text = f" [{'; '.join(embed_parts)}]"

    return f"**{author}** ({timestamp}):{attachment_text}{embed_text}\n{content}"


def build_prompt(context: dict, message_author: str, requesting_user: str) -> str:
    """Build the prompt for Claude to summarise the Discord context."""
    parts = []

    parts.append("You are helping create a GitHub issue from a Discord conversation.")
    parts.append(
        "Analyse the following Discord messages and create a well-structured GitHub issue.\n"
    )

    # Target message
    if context["target_message"]:
        parts.append("## Target Message (the message that was flagged)")
        parts.append(format_message(context["target_message"]))
        parts.append("")

    # Reply chain
    if context["reply_chain"]:
        parts.append(
            "## Reply Chain (conversation leading to this message, oldest first)"
        )
        for msg in reversed(context["reply_chain"]):
            parts.append(format_message(msg))
            parts.append("")

    # Surrounding context
    if context["surrounding"]:
        parts.append("## Surrounding Messages (nearby messages for additional context)")
        sorted_msgs = sorted(
            context["surrounding"], key=lambda m: m.get("timestamp", "")
        )
        for msg in sorted_msgs[:15]:  # Limit to 15 surrounding messages
            parts.append(format_message(msg))
            parts.append("")

    parts.append(f"\nRequested by Discord user: {requesting_user}")
    parts.append(f"Original message author: {message_author}")

    parts.append("""
## Instructions

Create a GitHub issue with:
1. A clear, concise title (under 80 characters)
2. A description that captures the key information from the Discord conversation
3. Include relevant context from the reply chain and surrounding messages
4. Suggest appropriate labels from: bug, documentation, operations, core, campaign, content, quality, performance

Respond in this exact JSON format:
{
    "title": "Issue title here",
    "body": "Issue body in markdown here",
    "labels": ["label1", "label2"]
}

The body should:
- Start with a summary of what was discussed
- Include key details and any specific requests
- Note who raised it and relevant context
- End with a "Source" section noting this came from Discord
- Be well-formatted with markdown headers and bullet points
- NOT include raw message timestamps or Discord-specific formatting

Respond ONLY with the JSON, no other text.
""")

    return "\n".join(parts)


def create_issue_with_claude(
    context: dict, message_author: str, requesting_user: str
) -> dict:
    """Use Claude to create a structured issue from Discord context."""
    api_key = get_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = build_prompt(context, message_author, requesting_user)

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text.strip()

    # Parse JSON response, handling potential markdown code blocks
    if response_text.startswith("```"):
        # Strip code block markers
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    return json.loads(response_text)


def create_github_issue(title: str, body: str, labels: list[str]) -> dict:
    """Create a GitHub issue using the gh CLI."""
    cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        "gyrinx-app/gyrinx",
        "--title",
        title,
        "--body",
        body,
    ]
    for label in labels:
        cmd.extend(["--label", label])

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        print(f"gh issue create failed: {result.stderr}", file=sys.stderr)
        # Try without labels in case some don't exist
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            "gyrinx-app/gyrinx",
            "--title",
            title,
            "--body",
            body,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    # gh outputs the issue URL
    issue_url = result.stdout.strip()
    return {"url": issue_url}


def update_discord_message(application_id: str, interaction_token: str, content: str):
    """Update the deferred Discord interaction response."""
    response = requests.patch(
        f"{DISCORD_API}/webhooks/{application_id}/{interaction_token}/messages/@original",
        json={"content": content},
        timeout=10,
    )
    if response.status_code not in (200, 204):
        print(
            f"Failed to update Discord message: {response.status_code} {response.text}",
            file=sys.stderr,
        )


def post_channel_reply(channel_id: str, message_id: str, content: str, token: str):
    """Post a visible reply in the channel, replying to the original message."""
    response = requests.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers={"Authorization": f"Bot {token}"},
        json={
            "content": content,
            "message_reference": {"message_id": message_id},
        },
        timeout=10,
    )
    if response.status_code not in (200, 201):
        print(
            f"Failed to post channel reply: {response.status_code} {response.text}",
            file=sys.stderr,
        )


def main():
    # Read Discord response credentials first (needed to notify user of any errors)
    application_id = os.environ.get("APPLICATION_ID", "")
    interaction_token = os.environ.get("INTERACTION_TOKEN", "")

    def fail(msg: str):
        """Update Discord and exit on failure."""
        if application_id and interaction_token:
            update_discord_message(application_id, interaction_token, msg)
        sys.exit(1)

    # Read remaining environment
    try:
        discord_token = get_env("DISCORD_BOT_TOKEN")
        channel_id = get_env("CHANNEL_ID")
        message_id = get_env("MESSAGE_ID")
    except SystemExit:
        fail("Failed to create issue: configuration error.")
        return  # unreachable, but makes type checkers happy

    if not application_id or not interaction_token:
        print("Error: APPLICATION_ID or INTERACTION_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    guild_id = os.environ.get("GUILD_ID", "")
    message_author = os.environ.get("MESSAGE_AUTHOR", "unknown")
    requesting_user = os.environ.get("REQUESTING_USER", "unknown")

    print(f"Processing Discord message {message_id} in channel {channel_id}")

    # Step 1: Fetch context from Discord
    print("Fetching message context from Discord...")
    context = fetch_context(channel_id, message_id, discord_token)

    if not context["target_message"]:
        fail("Failed to create issue: could not fetch the message from Discord.")

    msg_count = 1 + len(context["reply_chain"]) + len(context["surrounding"])
    print(
        f"Fetched {msg_count} messages (1 target, {len(context['reply_chain'])} reply chain, {len(context['surrounding'])} surrounding)"
    )

    # Step 2: Call Claude to create structured issue
    print("Calling Claude to summarise into a GitHub issue...")
    try:
        issue_data = create_issue_with_claude(context, message_author, requesting_user)
    except Exception as e:
        print(f"Error calling Claude: {e}", file=sys.stderr)
        fail("Failed to create issue: error summarising the conversation.")

    title = issue_data.get("title", "Issue from Discord")
    body = issue_data.get("body", "")
    labels = issue_data.get("labels", [])

    # Add discord-imported label
    if "discord-imported" not in labels:
        labels.append("discord-imported")

    # Add source footer to body
    discord_link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    body += f"\n\n---\n\n**Source:** [Discord message]({discord_link}) | Requested by: {requesting_user}"

    print(f"Issue title: {title}")
    print(f"Labels: {labels}")

    # Step 3: Create GitHub issue
    print("Creating GitHub issue...")
    try:
        result = create_github_issue(title, body, labels)
        issue_url = result["url"]
        print(f"Created issue: {issue_url}")
    except Exception as e:
        print(f"Error creating issue: {e}", file=sys.stderr)
        fail("Failed to create issue: error creating the GitHub issue.")

    # Step 4: Post a visible reply in the channel and update the ephemeral message
    print("Posting reply to Discord channel...")
    post_channel_reply(
        channel_id,
        message_id,
        f"Created GitHub issue: {issue_url}",
        discord_token,
    )
    update_discord_message(
        application_id,
        interaction_token,
        f"Done! Issue created: {issue_url}",
    )

    print("Done!")


if __name__ == "__main__":
    main()
