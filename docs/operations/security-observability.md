# Security and availability observability

The production Cloud Run service is `gyrinx` in project
`windy-ellipse-440618-p9`. Cloud Run request logs show the network client,
status and URL. Application logs add a bounded route pattern, actor where
known, request correlation and explicit rejection outcome. Use the trace ID
to join an application event to its Cloud Run request log; a request ID
links application records when a trace header is unavailable.

## What is recorded

| Event | Meaning | Useful fields |
| --- | --- | --- |
| `security_request` | Rejected login, signup, MFA, CSRF, permission (403 or login redirect), or invalid-host request | `action`, `outcome`, `reason`, `route`, `actor_id`, `target_fingerprint`, `client_ip`, `request_id`, `trace_id` |
| `http_route_response` | All 4xx/5xx and a 10% sample of successful responses | `route`, `status`, `duration_ms`, `request_id`, `trace_id`, `sampled` |
| `db_pool_stats` | Once per minute per worker with an active psycopg pool | `pool_size`, `pool_available`, `requests_waiting`, `requests_queued`, `requests_errors` |
| `db_pool_timeout` | A request failed to acquire a database connection | `route`, `request_id`, `trace_id` |
| `event_*` | Persisted user action, also sent to Cloud Logging | `user_id`, `session_fingerprint`, `noun`, `verb` |

The application does not record passwords, MFA codes, request bodies, query
strings, CSRF failure detail, raw session keys, or raw User-Agent strings in
these new records. The session fingerprint is a keyed one-way hash. The
`Event` migration adds a database trigger that clears new `session_id` values.
The legacy column remains temporarily for older Cloud Run revisions during a
rolling deploy; Django no longer reads or writes it. The maintenance operation
below clears historical values in batches. Historical rows then lose session
correlation. The `Event` record and N26 operation
ledger remain the sources for successful writes; allauth signals also record successful
account actions. Failed attempts are log-only because many have no account.

The configured external load balancer appends the client and forwarding-rule
addresses to `X-Forwarded-For`. Application and allauth audit IP extraction
use the second address from the right. Earlier entries can be caller supplied.
The deployment config restricts public ingress to the load balancer; internal
Pub/Sub push requests can still use the Cloud Run service URL.
If the proxy chain changes, review `TRUSTED_X_FORWARDED_FOR_HOPS` and
`ALLAUTH_TRUSTED_PROXY_COUNT` together before treating the stored address as
the client. For a disputed source address, inspect the Cloud Run request
log's `httpRequest.remoteIp` through the trace.

## First queries during an incident

In Cloud Logging, set the project and a narrow time range. These filters can
be pasted into Logs Explorer:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="gyrinx"
jsonPayload.event="security_request"
```

```text
resource.type="cloud_run_revision"
resource.labels.service_name="gyrinx"
(jsonPayload.event="db_pool_timeout" OR jsonPayload.event="db_pool_stats")
```

```text
resource.type="cloud_run_revision"
resource.labels.service_name="gyrinx"
jsonPayload.event="http_route_response"
jsonPayload.labels.status>=500
```

For an alert, group the Cloud Run request logs by source IP and URL path,
then inspect `http_route_response` for the affected route and `db_pool_stats`
for growing `requests_waiting`, depleted `pool_available`, and rising
`requests_errors`. The app's response sample is useful for route timing; use
Cloud Run request metrics for total request and error rates. A 302 from the
custom CSRF handler is identified by `security_request.action="csrf"`, not
by status alone. Rejected login attempts carry a keyed `target_fingerprint`.
Group equal fingerprints to find attempts against the same identifier without
putting usernames or email addresses in logs. An authorised investigator can
compare a known account identifier against those fingerprints locally.

## Alerts

Versioned policy definitions live in [monitoring](monitoring/). The existing
uptime alert detects external unavailability; these policies add a pool
timeout alert, sustained 5xx/429 alert, and authentication-rejection spike
alert. They use the existing operations notification channel. Apply them
**after the application revision is deployed**, with a Monitoring editor
account and the channel resource name for the intended project:

```bash
bash scripts/provision_security_monitoring.sh \
  --project windy-ellipse-440618-p9 \
  --notification-channel projects/windy-ellipse-440618-p9/notificationChannels/7536541924529136581 \
  --dry-run
bash scripts/provision_security_monitoring.sh \
  --project windy-ellipse-440618-p9 \
  --notification-channel projects/windy-ellipse-440618-p9/notificationChannels/7536541924529136581
```

The script upserts the `gyrinx_auth_rejections` log-based counter and three
policies by display name. It leaves unrelated policies alone. Verify all
three are enabled in Cloud Monitoring and that the configured channel
receives a test notification. The auth metric starts counting when created;
it does not backfill earlier logs. Review thresholds after a week of normal
traffic. A request spike shorter than a Cloud Monitoring alignment interval
can still be visible in logs without firing a rate alert.
The pool-timeout log alert limits notifications to one every five minutes.

## Clear historical database values after deployment

The production table has many non-null legacy `session_id` values. Updating
them inside a startup migration could exceed the
Cloud Run startup limit and hold locks during a deployment. Once the new
revision is serving traffic, open **Admin → Maintenance → Clear legacy Event
session keys**, check the preview count, and start the job. It clears at most
5,000 rows per task delivery, records a cursor and counts on one Backfill
record, and confirms continuation publication before acknowledging a batch.
It can be cancelled or safely retried. Check that the Backfill reaches
Done and the preview count becomes zero. If it fails, inspect the record and
rerun after resolving the cause. Do not copy session values into the incident
record. The database trigger blocks values from older revisions during the
rollout and continues to block any legacy writer until the column is later
removed.

## Historical session-key exposure

Older `event_*` log entries could carry raw session keys. Coordinate the
historical log review through the private reporting path in `SECURITY.md`.
Keep key values out of tickets, chat, and shell history. The security owner
should restrict log access, determine whether affected sessions remain active,
invalidate them as needed, and decide whether a retention or purge action is
needed. The batched database
cleanup does not remove copies already exported to Cloud Logging. Record the
decision in the incident record. Database backups taken before the cleanup
may also retain the old values until their retention period ends.

## Limits

These records show attempts that reached Django and were handled by its
instrumented routes. CDN or load-balancer rejections may appear only in edge
logs. A redirect to login may also be an ordinary navigation by a signed-out
user, so investigate its timing and source before calling it an attack. The
security log does not capture submitted account identifiers in plaintext.
Cloud Run request logs remain necessary for complete request counts and network
attribution.
