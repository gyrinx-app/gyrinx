#!/usr/bin/env bash
# Google external_account executable-sourced credential for Cursor Cloud Agents.
# Mints a 5-minute OIDC JWT from the local Cursor agent socket and prints the
# JSON contract Google's auth libraries expect on stdout.
#
# Contract sources:
#   Cursor: https://cursor.com/docs/cloud-agent/identity
#   Google: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers
#
# Requires: curl, jq. Set GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES=1 in the env.

set -euo pipefail

SOCKET="${CURSOR_AGENT_SOCKET:-/run/cursor/api.sock}"
AUD="${GOOGLE_EXTERNAL_ACCOUNT_AUDIENCE:-}"
OUT="${GOOGLE_EXTERNAL_ACCOUNT_OUTPUT_FILE:-}"

# Google reads our stdout as JSON, so failures must be reported as a success:false
# document with exit 0. A non-zero exit produces a far less useful error.
fail() {
  jq -nc --arg m "$1" '{version:1, success:false, code:"401", message:$m}'
  exit 0
}

command -v jq >/dev/null 2>&1 || { echo '{"version":1,"success":false,"code":"401","message":"jq not installed"}'; exit 0; }
[[ -n "$AUD" ]] || fail "GOOGLE_EXTERNAL_ACCOUNT_AUDIENCE is not set"

body=$(jq -nc --arg aud "$AUD" '{aud: $aud}')

code=""
payload=""
delay=1
for attempt in 1 2 3 4 5; do
  # The socket can be missing briefly right after VM boot, so a connection
  # failure is retried rather than treated as fatal.
  if resp=$(curl -sS --max-time 10 -w $'\n%{http_code}' \
      --unix-socket "$SOCKET" \
      -H 'Content-Type: application/json' \
      -d "$body" \
      http://cursor-agent/v1/tokens/oidc 2>/dev/null); then
    code=$(printf '%s' "$resp" | tail -n1)
    payload=$(printf '%s' "$resp" | sed '$d')
  else
    code="000"
    payload="could not connect to $SOCKET"
  fi

  case "$code" in
    200) break ;;
    # Cursor documents 403 as fatal: this agent is not allowed to mint at all.
    403) fail "cursor refused the mint (403): $payload" ;;
    000|429|500|502|503|504)
      if [[ "$attempt" == "5" ]]; then fail "cursor mint failed after 5 attempts (last: $code $payload)"; fi
      sleep "$delay"; delay=$((delay * 2)); continue ;;
    *) fail "cursor mint failed (HTTP $code): $payload" ;;
  esac
done

[[ "$code" == "200" ]] || fail "cursor mint did not succeed (last: $code)"

token=$(printf '%s' "$payload" | jq -r '.token // empty')
exp=$(printf '%s' "$payload" | jq -r '.expires_at // empty')
[[ -n "$token" && -n "$exp" ]] || fail "unexpected mint response shape: $payload"

result=$(jq -nc --arg t "$token" --argjson e "$exp" \
  '{version:1, success:true, token_type:"urn:ietf:params:oauth:token-type:id_token", id_token:$t, expiration_time:$e}')

# Cache for the SDK. Cursor allows 30 mints/minute per VM and tokens last only
# 5 minutes, so letting the library reuse a live token matters.
if [[ -n "$OUT" ]]; then
  tmp="${OUT}.tmp.$$"
  printf '%s' "$result" > "$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$OUT"
fi

printf '%s\n' "$result"
