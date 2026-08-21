#!/usr/bin/env bash
# Google external_account executable-sourced credential for Cursor Cloud Agents.
# Mints a five-minute OIDC JWT from the local Cursor agent socket and prints the
# JSON contract Google's auth libraries expect on stdout.
#
# Contract sources:
#   Cursor: https://cursor.com/docs/cloud-agent/identity
#   Google: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers
#
# Requires: curl, jq. Set GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES=1 in the env.
#
# errexit is deliberately NOT enabled. The contract is to exit 0 having printed
# a JSON document in every circumstance, so a stray non-zero status from any
# command must not terminate the script; each step is checked explicitly instead.
set -uo pipefail

SOCKET="${CURSOR_AGENT_SOCKET:-/run/cursor/api.sock}"
AUD="${GOOGLE_EXTERNAL_ACCOUNT_AUDIENCE:-}"
OUT="${GOOGLE_EXTERNAL_ACCOUNT_OUTPUT_FILE:-}"

# The auth library reads stdout as JSON, so a failure is reported as a document
# rather than an exit status; a non-zero exit yields a far less useful error.
# The code is carried through so that it matches the condition being described.
emit_failure() {
  local message="$1" code="${2:-401}"
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg m "$message" --arg c "$code" \
      '{version:1, success:false, code:$c, message:$m}'
  else
    printf '{"version":1,"success":false,"code":"401","message":"jq is not installed"}\n'
  fi
  exit 0
}

command -v jq >/dev/null 2>&1 || emit_failure "jq is not installed"
command -v curl >/dev/null 2>&1 || emit_failure "curl is not installed"
[ -n "$AUD" ] || emit_failure "GOOGLE_EXTERNAL_ACCOUNT_AUDIENCE is not set"

body=$(jq -nc --arg aud "$AUD" '{aud: $aud}') \
  || emit_failure "could not build the mint request body"

code=""
payload=""
delay=1
for attempt in 1 2 3 4 5; do
  # The socket can be absent briefly after boot, so a connection failure is
  # retried rather than treated as fatal.
  if resp=$(curl -sS --max-time 10 -w $'\n%{http_code}' \
      --unix-socket "$SOCKET" \
      -H 'Content-Type: application/json' \
      -d "$body" \
      http://cursor-agent/v1/tokens/oidc 2>/dev/null); then
    code=$(printf '%s' "$resp" | tail -n1)
    payload=$(printf '%s' "$resp" | sed '$d')
  else
    code="000"
    payload="could not connect to ${SOCKET}"
  fi

  case "$code" in
    200) break ;;
    # Cursor documents 403 as fatal: this run is not allowed to mint at all.
    403) emit_failure "cursor refused the mint: ${payload}" "403" ;;
    000 | 429 | 500 | 502 | 503 | 504)
      if [ "$attempt" = "5" ]; then
        emit_failure "cursor mint failed after 5 attempts (last: ${code} ${payload})" "$code"
      fi
      sleep "$delay"
      delay=$((delay * 2))
      ;;
    *) emit_failure "cursor mint failed: ${payload}" "$code" ;;
  esac
done

[ "$code" = "200" ] || emit_failure "cursor mint did not succeed (last: ${code})" "$code"

token=$(printf '%s' "$payload" | jq -r '.token // empty' 2>/dev/null) \
  || emit_failure "mint response was not valid JSON"
expiry=$(printf '%s' "$payload" | jq -r '.expires_at // empty' 2>/dev/null) \
  || emit_failure "mint response was not valid JSON"

[ -n "$token" ] || emit_failure "mint response carried no token"
# Guards --argjson below, which rejects anything that is not a JSON number, and
# accepts an expiry delivered as a string because jq -r has already unquoted it.
case "$expiry" in
  '' | *[!0-9]*) emit_failure "mint response carried no usable expiry" ;;
esac

result=$(jq -nc --arg t "$token" --argjson e "$expiry" \
  '{version:1, success:true, token_type:"urn:ietf:params:oauth:token-type:id_token", id_token:$t, expiration_time:$e}') \
  || emit_failure "could not build the credential document"

# Cache for the library. Cursor allows 30 mints a minute per machine and tokens
# last five minutes, so letting it reuse a live token matters.
#
# Best effort throughout: a token in hand must still reach stdout even if it
# cannot be cached. The file is created by mktemp alongside its destination and
# renamed into place, because the nominated path can sit in a shared directory
# where another process may have pre-placed a symlink. rename(2) replaces such a
# link rather than writing through it, and mktemp opens at mode 600 to begin with.
if [ -n "$OUT" ]; then
  if cache_tmp=$(mktemp "$(dirname "$OUT")/.cursor-gcp-token.XXXXXX" 2>/dev/null); then
    if ! { printf '%s' "$result" > "$cache_tmp" 2>/dev/null \
      && chmod 600 "$cache_tmp" 2>/dev/null \
      && mv -f "$cache_tmp" "$OUT" 2>/dev/null; }; then
      rm -f "$cache_tmp" 2>/dev/null
      echo "warning: could not cache the token at ${OUT}" >&2
    fi
  else
    echo "warning: could not create a cache file beside ${OUT}" >&2
  fi
fi

printf '%s\n' "$result"
exit 0
