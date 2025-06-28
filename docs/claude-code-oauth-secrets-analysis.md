# Claude Code OAuth Secrets Management Analysis

## Overview

The `update_claude_secrets.py` Django management command is designed to extract Claude Code OAuth credentials from the macOS keychain and update GitHub repository secrets. This analysis explains how the secrets are retrieved and how they can be integrated with Anthropic API calls for other agents.

## How Secrets are Retrieved from Keychain

### 1. Keychain Access
The script retrieves credentials from the macOS keychain using the `security` command:

```python
KEYCHAIN_NAME = "Claude Code-credentials"

# Command executed:
security find-generic-password -s "Claude Code-credentials" -w
```

This command:
- Searches for a generic password entry with the service name "Claude Code-credentials"
- Returns only the password content (`-w` flag)
- Outputs the raw JSON credential data

### 2. Credential Structure
The keychain stores a JSON object with the following structure:

```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-...",
    "refreshToken": "refresh_token_value",
    "expiresAt": 1234567890000  // Unix timestamp in milliseconds
  }
}
```

### 3. Secret Mapping
The script maps these JSON fields to GitHub secret names:

```python
SECRET_MAPPING = {
    "accessToken": "CLAUDE_ACCESS_TOKEN",
    "refreshToken": "CLAUDE_REFRESH_TOKEN",
    "expiresAt": "CLAUDE_EXPIRES_AT",
}
```

## Integration with Anthropic API

### Using the OAuth Tokens

To use these OAuth credentials with the Anthropic API, other agents would need to:

1. **Retrieve the secrets** (from GitHub Actions environment or other secret storage)
2. **Check token expiration** before making API calls
3. **Refresh tokens** when expired
4. **Include the access token** in API requests

### Example Implementation

```python
import os
import time
import requests
from anthropic import Anthropic

class ClaudeOAuthClient:
    def __init__(self):
        self.access_token = os.environ.get('CLAUDE_ACCESS_TOKEN')
        self.refresh_token = os.environ.get('CLAUDE_REFRESH_TOKEN')
        self.expires_at = int(os.environ.get('CLAUDE_EXPIRES_AT', '0'))

    def is_token_expired(self):
        """Check if the access token has expired"""
        current_time_ms = int(time.time() * 1000)
        return current_time_ms >= self.expires_at

    def refresh_access_token(self):
        """Refresh the access token using the refresh token"""
        # This would make a request to Claude's OAuth refresh endpoint
        # Implementation depends on Claude's OAuth API specification
        response = requests.post(
            'https://api.anthropic.com/oauth/token',
            json={
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token
            }
        )

        if response.status_code == 200:
            data = response.json()
            self.access_token = data['access_token']
            self.refresh_token = data.get('refresh_token', self.refresh_token)
            self.expires_at = data['expires_at']

            # Update stored secrets
            self._update_stored_secrets()
        else:
            raise Exception("Failed to refresh token")

    def get_anthropic_client(self):
        """Get an authenticated Anthropic client"""
        if self.is_token_expired():
            self.refresh_access_token()

        # Use the OAuth access token instead of API key
        return Anthropic(
            auth_token=self.access_token,
            # Or however OAuth tokens are passed in the Anthropic SDK
        )
```

### GitHub Actions Integration

In a GitHub Actions workflow, the secrets would be available as environment variables:

```yaml
name: Use Claude OAuth
on: [push]

jobs:
  claude-api-call:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Call Claude API
        env:
          CLAUDE_ACCESS_TOKEN: ${{ secrets.CLAUDE_ACCESS_TOKEN }}
          CLAUDE_REFRESH_TOKEN: ${{ secrets.CLAUDE_REFRESH_TOKEN }}
          CLAUDE_EXPIRES_AT: ${{ secrets.CLAUDE_EXPIRES_AT }}
        run: |
          python scripts/claude_api_call.py
```

## Security Considerations

1. **Token Storage**: The script never logs actual token values, using sanitization for display
2. **Secure Transmission**: Secrets are passed via stdin to `gh` CLI, not command line arguments
3. **Error Handling**: Error messages are sanitized to prevent accidental token exposure
4. **Expiration Tracking**: The `expiresAt` timestamp allows for proactive token refresh

## Key Features for Other Agents

1. **Automated Token Retrieval**: Direct access to macOS keychain where Claude Code stores credentials
2. **GitHub Secrets Integration**: Automatic upload to GitHub secrets for CI/CD use
3. **Token Lifecycle Management**: Includes expiration timestamp for refresh handling
4. **Security-First Design**: Built-in sanitization and secure handling of sensitive data

## Usage Pattern for Other Agents

1. **Local Development**: Read directly from macOS keychain using similar `security` command
2. **CI/CD**: Use GitHub secrets populated by this script
3. **Production**: Store in secure secret management system (AWS Secrets Manager, etc.)
4. **Token Refresh**: Implement refresh logic based on `expiresAt` timestamp

This approach allows other agents and automation tools to leverage the same OAuth credentials that Claude Code uses, enabling seamless integration with the Anthropic API while maintaining security best practices.
