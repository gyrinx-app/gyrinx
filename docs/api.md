# API

The API app provides minimal webhook endpoints for external integrations. Currently, it's primarily used for handling webhooks from Patreon to manage supporter benefits.

## Overview

The API is intentionally minimal and focused on specific integration needs rather than being a general-purpose REST API. The main application is designed as a server-rendered Django application, not an API-first application.

## Endpoints

### Webhook Handling

The primary purpose of the API app is to handle webhooks from external services:

- **Patreon Webhooks**: Handles subscription events from Patreon to manage supporter benefits and access levels

## Models

The API app includes basic models for tracking webhook requests:

- `WebhookRequest`: Logs incoming webhook requests for debugging and audit purposes

## Security

Webhook endpoints include proper signature verification to ensure requests are legitimate and coming from expected sources.

## Future Considerations

While the current API is minimal, future expansion might include:

- Read-only endpoints for public data (lists, content)
- Mobile app support APIs
- Third-party integration APIs

However, any API expansion should maintain the principle of server-rendered HTML as the primary interface.
