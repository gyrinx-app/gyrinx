#!/usr/bin/env bash
# Upsert the security and availability alerts in docs/operations/monitoring.
set -euo pipefail

PROJECT_ID=""
NOTIFICATION_CHANNEL=""
DRY_RUN=0
while (($#)); do
    case "$1" in
        --project) PROJECT_ID="$2"; shift 2 ;;
        --notification-channel) NOTIFICATION_CHANNEL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$PROJECT_ID" || "$NOTIFICATION_CHANNEL" != "projects/$PROJECT_ID/notificationChannels/"* ]]; then
    echo "Pass --project and a notification channel belonging to that project." >&2
    exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY_DIR="$ROOT/docs/operations/monitoring"
POLICIES=(
    "$POLICY_DIR/gyrinx-pool-timeout.json"
    "$POLICY_DIR/gyrinx-http-errors.json"
    "$POLICY_DIR/gyrinx-auth-rejections.json"
)
METRIC="gyrinx_auth_rejections"
AUTH_FILTER='resource.type="cloud_run_revision" AND resource.labels.service_name="gyrinx" AND jsonPayload.event="security_request" AND jsonPayload.labels.outcome="rejected" AND (jsonPayload.labels.action="login" OR jsonPayload.labels.action="signup" OR jsonPayload.labels.action="mfa")'

if ((DRY_RUN)); then
    echo "Would upsert $METRIC and ${#POLICIES[@]} alert policies:"
    for policy in "${POLICIES[@]}"; do
        jq -r '"- " + .displayName' "$policy"
    done
    exit 0
fi

metrics_json="$(gcloud logging metrics list --project="$PROJECT_ID" --format='json(name)')"
if jq -e --arg name "$METRIC" 'any(.[]; .name == $name)' <<< "$metrics_json" > /dev/null; then
    metric_action=update
else
    metric_action=create
fi
gcloud logging metrics "$metric_action" "$METRIC" \
    --project="$PROJECT_ID" \
    --log-filter="$AUTH_FILTER" \
    --description="Rejected Gyrinx login, signup, and MFA submissions"

policies_json="$(gcloud alpha monitoring policies list --project="$PROJECT_ID" --format=json)"
TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT
for policy in "${POLICIES[@]}"; do
    display_name="$(jq -r .displayName "$policy")"
    matches="$(jq --arg name "$display_name" '[.[] | select(.displayName == $name)] | length' <<< "$policies_json")"
    if ((matches > 1)); then
        echo "Duplicate alert policy: $display_name" >&2
        exit 1
    fi
    existing="$(jq -r --arg name "$display_name" '[.[] | select(.displayName == $name)] | .[0].name // empty' <<< "$policies_json")"
    jq --arg channel "$NOTIFICATION_CHANNEL" --arg name "$existing" \
        '.notificationChannels = [$channel] | if $name == "" then del(.name) else .name = $name end' \
        "$policy" > "$TMP_FILE"
    if [[ -n "$existing" ]]; then
        gcloud alpha monitoring policies update "$existing" \
            --project="$PROJECT_ID" --policy-from-file="$TMP_FILE"
        echo "Updated: $display_name"
    else
        gcloud alpha monitoring policies create \
            --project="$PROJECT_ID" --policy-from-file="$TMP_FILE"
        echo "Created: $display_name"
    fi
done
